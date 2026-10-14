"""
Tests de la v3 : calcul par VMA (fidèle au plan 10 km de référence), comparaison des méthodes,
suivi élève, e-mails (serveur SMTP local), compatibilité avec les données de la version précédente.
"""

import math
import shutil
import sys
import time
from datetime import date
from email import message_from_bytes
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import emails, moteur, profils, referentiel, suivi  # noqa: E402
from core.calculs import compute_paces_vma, parse_vma, race_seconds_from_paces  # noqa: E402
from core.plan import full_plan_table, pace_codes  # noqa: E402
from core.stockage import Store  # noqa: E402

V2_SAMPLE = Path("/home/claude/v2_sample")      # jeu de données au format de la version précédente


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "data")
    referentiel.ensure_referentiel(s)
    return s


# ---------------------------------------------------------------- VMA (Excel 10 km, VMA 16 en L10)
def test_vma_identique_excel():
    p = compute_paces_vma(16, "10k")
    assert math.isclose(p["Endurance"].kmh, 10.88) and math.isclose(p["Endurance"].min_per_km, 5.514705882352941)  # M5/N5
    assert math.isclose(p["A1"].kmh, 12.0) and math.isclose(p["A1"].min_per_km, 5.0)                              # M6/N6
    assert math.isclose(p["A2"].kmh, 12.8) and math.isclose(p["A2"].min_per_km, 4.6875)                           # M7/N7
    assert math.isclose(p["A3"].kmh, 13.6) and math.isclose(p["A3"].min_per_km, 4.411764705882353)                # M8/N8
    assert p["A2"].pace_str == "4'25\"–4'41\"" and p["A3"].pace_str == "4'10\"–4'25\""   # plages 80-85 / 85-90 %
    assert round(p["A3"].ref_time_minutes) == 44                                         # Q8 « 44mn »
    assert race_seconds_from_paces(p, "10k") == 2647


@pytest.mark.parametrize("txt,val", [("16", 16.0), ("16,5", 16.5), ("17.2 km/h", 17.2)])
def test_parse_vma(txt, val):
    assert parse_vma(txt) == val


def test_parse_vma_invalide():
    for txt in ("", "abc", "45"):
        with pytest.raises(ValueError):
            parse_vma(txt)


def test_modele_10k_excel():
    t = referentiel.default_template("10k")
    table = full_plan_table(t, compute_paces_vma(16, "10k"), 2640, date(2026, 10, 4), 3)
    assert table["debut"].iloc[0] == date(2026, 7, 13)                   # S1 (A54)
    assert table[table["semaine"] == "S12"]["debut"].iloc[0] == date(2026, 9, 28)   # S12 (B9)
    race = table[table["seance"] == "JOUR J"].iloc[0]
    assert race["date"] == date(2026, 10, 4) and race["duree_env"] == "0:44:00"
    s3 = table[table["semaine"] == "S3"].reset_index(drop=True)
    assert pace_codes(s3.loc[1, "allure"]) == ["A2", "A3"] and s3.loc[1, "temps_aff"] == "18'"   # G47 / H47
    assert pace_codes(s3.loc[2, "allure"]) == ["A1", "A2"]                                        # « A1 à A2 »


# ---------------------------------------------------------------- moteur double
def test_creation_methodes(store):
    a = profils.create_student(store, "a@x.fr", "A", "10k", None, vma="16")
    assert a.methode == "vma" and not a.objectif
    sp = moteur.student_paces(a)
    assert sp.race_is_estimate and sp.race_seconds == 2647
    b = profils.create_student(store, "b@x.fr", "B", "10k", "0:44:00", vma="16")
    assert b.methode == "vma"                                              # défaut de la distance 10 km
    rows = moteur.comparison(b)
    assert len(rows) == 6 and any(r["is_anchor"] for r in rows)
    c = profils.create_student(store, "c@x.fr", "C", "marathon", "3:29:00", vma="16.5")
    assert c.methode == "temps" and moteur.student_paces(c).paces["A1"].pace_str == "4'57\""
    with pytest.raises(ValueError):
        profils.create_student(store, "d@x.fr", "", "semi")               # ni objectif ni VMA
    with pytest.raises(ValueError):
        profils.create_student(store, "e@x.fr", "", "semi", None, vma="16", methode="temps")


def test_vma_globale_non_retroactive(store):
    a = profils.create_student(store, "a@x.fr", "", "10k", None, vma="16")
    referentiel.save_global_vma_pct(store, "10k", {"A1": (76, 78)})
    b = profils.create_student(store, "b@x.fr", "", "10k", None, vma="16")
    assert profils.get_student(store, a.id).vma_pct["A1"] == (75.0, 75.0)
    assert b.vma_pct["A1"] == (76.0, 78.0)
    assert referentiel.load_global_ratios(store)["10k"]["Sprint"] == 120      # ratios intacts


# ---------------------------------------------------------------- suivi élève
def test_suivi(store):
    s = profils.create_student(store, "m@x.fr", "Maud", "10k", "0:44:00", date(2026, 11, 29), 3, vma="16")
    sp = moteur.student_paces(s)
    table = full_plan_table(s.plan, sp.paces, sp.race_seconds, s.date_course, 3, hide_empty=True)
    sid = table["session_id"].iloc[0]
    suivi.set_done(store, s.id, sid, True)
    suivi.set_frequency(store, s.id, 4)
    suivi.set_race_time(store, s.id, "45:12")
    sv = suivi.load_suivi(store, s.id)
    assert sid in sv.done and sv.frequence == 4 and sv.temps_realise == "0:45:12"
    pr = suivi.progress(table, sv, sp.race_seconds)
    assert pr.done == 2 and pr.race_gap == "+1'12"
    # Le coach modifie le plan : le suivi de l'élève n'est pas touché
    profils.save_student(store, s.with_(plan=s.plan.resize(10)))
    assert sid in suivi.load_suivi(store, s.id).done
    suivi.set_done(store, s.id, sid, False)
    assert sid not in suivi.load_suivi(store, s.id).done
    with pytest.raises(ValueError):
        suivi.set_race_time(store, s.id, "45:75")
    profils.delete_student(store, s.id)
    assert not store.exists(f"suivi/{s.id}.xlsx")


@pytest.mark.parametrize("txt,sec", [("3:31:12", 12672), ("44:30", 2670), ("1h38'20", 5900), ("1:38", 5880)])
def test_temps_realise(txt, sec):
    assert suivi.parse_race_time(txt) == sec


# ---------------------------------------------------------------- e-mails (serveur SMTP local)
@pytest.fixture
def smtp_server():
    from aiosmtpd.controller import Controller

    received = []

    class Handler:
        async def handle_DATA(self, server, session, envelope):
            received.append(message_from_bytes(envelope.content))
            return "250 OK"

    ctl = Controller(Handler(), hostname="127.0.0.1", port=8025)
    ctl.start()
    yield received
    ctl.stop()


def test_email_code(store, smtp_server):
    s = profils.create_student(store, "julie@x.fr", "Julie", "semi", "1:50:00")
    cfg = emails.EmailConfig(host="127.0.0.1", port=8025, user="coach@x.fr", password="", security="none",
                             sender_name="Coach")
    ok, msg = emails.send_access_email(s, cfg, "https://mon-app.streamlit.app")
    assert ok, msg
    for _ in range(20):
        if smtp_server:
            break
        time.sleep(0.05)
    m = smtp_server[0]
    text = m.get_payload()[0].get_payload(decode=True).decode()
    assert m["To"] == "julie@x.fr" and s.code in text and "https://mon-app.streamlit.app" in text
    ok, msg = emails.send_access_email(s, None, "https://x")
    assert not ok and "non configuré" in msg


# ---------------------------------------------------------------- compatibilité des données existantes
@pytest.mark.skipif(not V2_SAMPLE.exists(), reason="jeu de données v2 absent")
def test_donnees_version_precedente(tmp_path):
    shutil.copytree(V2_SAMPLE, tmp_path / "data")
    s = Store(tmp_path / "data")
    referentiel.ensure_referentiel(s)
    old = profils.list_students(s)[0]
    assert old.methode == "temps" and old.objectif == "03:29:00" and old.vma is None
    assert suivi.effective_frequency(old, suivi.load_suivi(s, old.id)) == 3        # choix v2 conservé
    ids = list(old.plan.sessions["session_id"])
    assert ids == list(profils.list_students(s)[0].plan.sessions["session_id"])     # identifiants stables
    assert referentiel.load_template(s, "10k").n_weeks == 12                        # modèle 10 km mis à jour
    assert s.exists("modeles/10k_v2.xlsx")                                          # ancien conservé
    assert referentiel.load_template(s, "marathon").n_weeks == 7                    # marathon inchangé
