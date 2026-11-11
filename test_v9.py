"""
Tests de la v9 : séance « pas faite », km réellement courus, signalements (douleur, absence,
maladie), réponses du coach, tableau « À surveiller », agenda (.ics), records personnels,
checklist du jour J, récap du dimanche par e-mail, recherche par adresse.
"""

import sys
import time
from datetime import date, timedelta
from email import message_from_bytes, policy
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fake_osm  # noqa: E402
from core import (agenda, alertes, analyse, decouverte, emails, historique, profils, recap, records,  # noqa: E402
                  referentiel, reglages, reponses, suivi)
from core.plan import activity_kind, is_race_day  # noqa: E402
from core.stockage import Store  # noqa: E402

TODAY = date.today()


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "data")
    referentiel.ensure_referentiel(s)
    return s


def _student(store, days_to_race=21, email="eva@x.fr", freq=3):
    """Élève 10 km (12 semaines) dont la course est dans `days_to_race` jours : plusieurs semaines passées."""
    s = profils.create_student(store, email, "Éva", "10k", "50:00", TODAY + timedelta(days=days_to_race), freq)
    return s, historique.program_state(store, s)


def _past_rows(state):
    """Séances d'avant aujourd'hui (date réelle ou jour conseillé, hors jour de course), dans l'ordre du plan."""
    days = agenda.session_days(state.student, state.table)
    return [r for _, r in suivi.ordered(state.table).iterrows()
            if days.get(r["session_id"], TODAY) < TODAY and not is_race_day(r["seance"])]


def _write(store, s, **fields):
    suivi.save_suivi(store, s.id, suivi.Suivi(**fields))
    return historique.program_state(store, s)


# ----------------------------------------------------------------------------- suivi de l'élève
def test_pas_faite_et_km_reels(store):
    s, st0 = _student(store)
    rows = _past_rows(st0)
    a, b = rows[0]["session_id"], rows[1]["session_id"]
    suivi.set_done(store, s.id, a, True)
    suivi.set_note(store, s.id, a, 4, "bien", km="8,5")
    suivi.set_skipped(store, s.id, b, "Fatigue")
    sv = suivi.load_suivi(store, s.id)
    assert a in sv.done and sv.km[a] == 8.5 and sv.note(a).ressenti == 4
    assert b in sv.skipped and sv.skipped[b].raison == "Fatigue" and b not in sv.done
    # cocher une séance « pas faite » enlève la marque ; la marquer « pas faite » la décoche
    suivi.set_done(store, s.id, b, True)
    assert b not in suivi.load_suivi(store, s.id).skipped
    suivi.set_skipped(store, s.id, b, "Météo")
    sv = suivi.load_suivi(store, s.id)
    assert b not in sv.done and sv.skipped[b].raison == "Météo"
    suivi.set_skipped(store, s.id, b, None)                                   # « elle reste à faire »
    assert b not in suivi.load_suivi(store, s.id).skipped
    # km : vide = km prévus ; invalide = refusé sans rien modifier
    with pytest.raises(ValueError):
        suivi.set_note(store, s.id, a, 4, "bien", km="beaucoup")
    assert suivi.load_suivi(store, s.id).km[a] == 8.5
    suivi.set_km(store, s.id, a, "")
    assert a not in suivi.load_suivi(store, s.id).km
    assert suivi.parse_km("9 km") == 9 and suivi.parse_km(" ") is None


def test_prochaine_seance_saute_les_pas_faites(store):
    s, st0 = _student(store, days_to_race=60)
    first = suivi.next_session(st0.table, st0.suivi, TODAY)
    suivi.set_skipped(store, s.id, first["session_id"], "Malade")
    st1 = historique.program_state(store, s)
    assert suivi.next_session(st1.table, st1.suivi, TODAY)["session_id"] != first["session_id"]
    entry = next(x for x in suivi.journal(st1.table, st1.suivi) if x["row"]["session_id"] == first["session_id"])
    assert entry["skip"].raison == "Malade" and not entry["done"]


def test_signalements(store):
    s, _ = _student(store)
    with pytest.raises(ValueError):
        suivi.add_report(store, s.id, "absence", TODAY)                        # absence sans date de retour
    with pytest.raises(ValueError):
        suivi.add_report(store, s.id, "absence", TODAY, TODAY - timedelta(days=1))
    pain = suivi.add_report(store, s.id, "douleur", TODAY - timedelta(days=2), zone="Genou", level=2,
                            comment="Mal en descente")
    away = suivi.add_report(store, s.id, "absence", TODAY + timedelta(days=3), TODAY + timedelta(days=9))
    sv = suivi.load_suivi(store, s.id)
    assert [r.kind for r in sv.reports] == ["douleur", "absence"]
    assert pain.label == "Douleur (genou), gênante" and pain.active() and not away.active() and away.upcoming()
    assert sv.absence_on(TODAY + timedelta(days=5)) is not None and sv.absence_on(TODAY) is None
    suivi.close_report(store, s.id, pain.id)                                   # « Je vais mieux »
    closed = suivi.load_suivi(store, s.id).reports[0]
    assert closed.closed and closed.end == TODAY and not closed.active()
    suivi.delete_report(store, s.id, away.id)
    assert len(suivi.load_suivi(store, s.id).reports) == 1


def test_checklist_et_recap(store):
    s, _ = _student(store)
    item = reglages.default_checklist()[0]
    suivi.set_checklist_item(store, s.id, item.key, True)
    assert item.key in suivi.load_suivi(store, s.id).checklist
    suivi.set_checklist_item(store, s.id, item.key, False)
    assert not suivi.load_suivi(store, s.id).checklist
    assert suivi.load_suivi(store, s.id).recap is True
    suivi.set_recap(store, s.id, False)
    assert suivi.load_suivi(store, s.id).recap is False


# ----------------------------------------------------------------------------- réponses du coach
def test_reponses_du_coach(store):
    s, st0 = _student(store)
    sid = _past_rows(st0)[0]["session_id"]
    assert reponses.load_coach(store, s.id).reply(sid) is None
    reponses.set_reply(store, s.id, sid, "  Bravo, garde ce rythme  ")
    data = reponses.load_coach(store, s.id)
    assert data.reply(sid).texte == "Bravo, garde ce rythme"
    assert [k for k, _ in reponses.unread(data, suivi.load_suivi(store, s.id).reponses_vues_le)] == [sid]
    suivi.mark_replies_seen(store, s.id)
    assert reponses.unread(data, suivi.load_suivi(store, s.id).reponses_vues_le) == []
    # le fichier de suivi de l'élève n'est pas touché par le coach, et inversement
    assert not store.exists(f"suivi/{s.id}.xlsx") or "reponses" not in str(store.read(f"suivi/{s.id}.xlsx"))
    reponses.set_reply(store, s.id, sid, "")
    assert reponses.load_coach(store, s.id).reply(sid) is None
    profils.delete_student(store, s.id)
    assert not store.exists(f"coach/{s.id}.xlsx")


# ----------------------------------------------------------------------------- À surveiller
@pytest.mark.parametrize("text,pain", [
    ("J'ai mal au genou depuis mardi", True), ("Petite douleur au mollet", True), ("Ma tendinite revient", True),
    ("Gêne au tendon d'Achille", True), ("C'était pas mal du tout !", False), ("Aucune douleur, top", False),
    ("Sans douleur cette fois", False), ("Super séance, jambes légères", False),
])
def test_mots_de_douleur(text, pain):
    assert alertes.mentions_pain(text) is pain


def _keys(state, coach=None):
    return [a.key.split(":")[0] for a in alertes.program_alerts(state, coach, TODAY)]


def test_alertes(store):
    s, st0 = _student(store)
    rows = _past_rows(st0)
    now = f"{TODAY:%Y-%m-%d} 09:00"
    ids = [r["session_id"] for r in rows]
    # rien coché depuis le début : inactif
    assert _keys(st0) == ["inactif"]
    # deux « Très dur » d'affilée + un commentaire qui parle de douleur
    done = {sid: TODAY.isoformat() for sid in ids[-3:]}
    notes = {ids[-2]: suivi.Note(1, "", f"{TODAY:%Y-%m-%d} 08:00"),
             ids[-1]: suivi.Note(1, "J'ai mal au genou", now)}
    stt = _write(store, s, done=done, notes=notes)
    keys = _keys(stt)
    assert "tresdur" in keys and "mot" in keys and "inactif" not in keys
    alert = next(a for a in alertes.program_alerts(stt, None, TODAY) if a.key.startswith("mot"))
    assert alert.level == "rouge" and alert.reply_key == ids[-1]
    # le coach l'a vue : elle disparaît
    reponses.dismiss_alert(store, s.id, alert.key)
    assert "mot" not in _keys(stt, reponses.load_coach(store, s.id))
    # footing ressenti « Dur » : signe de fatigue
    footing = next((r for r in rows if activity_kind(r) == "footing"), None)
    if footing is not None:
        stt = _write(store, s, done={footing["session_id"]: TODAY.isoformat()},
                     notes={footing["session_id"]: suivi.Note(2, "", now)})
        assert "facile" in _keys(stt)
    # ressentis en baisse sur 3 séances
    stt = _write(store, s, done=dict.fromkeys(ids[-3:], TODAY.isoformat()),
                 notes={ids[-3]: suivi.Note(5, "", f"{TODAY:%Y-%m-%d} 07:00"),
                        ids[-2]: suivi.Note(4, "", f"{TODAY:%Y-%m-%d} 08:00"),
                        ids[-1]: suivi.Note(3, "", now)})
    assert "baisse" in _keys(stt)
    # deux séances « pas faites » d'affilée
    stt = _write(store, s, done={ids[-3]: TODAY.isoformat()},
                 skipped={ids[-2]: suivi.Skip(TODAY.isoformat(), "Fatigue"), ids[-1]: suivi.Skip(TODAY.isoformat())})
    assert "skip" in _keys(stt)
    # douleur signalée : alerte rouge, avec la clé de réponse du signalement
    rep = suivi.Report("r1", "douleur", TODAY, zone="Cheville", level=3, created=now)
    stt = _write(store, s, done={ids[-1]: TODAY.isoformat()}, reports=(rep,))
    first = alertes.program_alerts(stt, None, TODAY)[0]
    assert first.level == "rouge" and first.reply_key == reponses.signal_key("r1")
    # absente cette semaine : pas d'alerte d'inactivité
    away = suivi.Report("r2", "absence", TODAY - timedelta(days=10), TODAY + timedelta(days=2), created=now)
    assert "inactif" not in _keys(_write(store, s, reports=(away,)))
    assert "signal" in _keys(_write(store, s, reports=(away,)))


def test_alerte_charge(store):
    s, st0 = _student(store)
    weeks = [w for _, w in st0.table.groupby("position") if isinstance(w["fin"].iloc[0], date)
             and w["fin"].iloc[0] < TODAY]
    assert len(weeks) >= 4
    done, km = {}, {}
    for w in weeks[-4:-1]:                          # 3 semaines tranquilles : ~5 km par séance
        for sid in w["session_id"]:
            done[sid], km[sid] = TODAY.isoformat(), 5.0
    for sid in weeks[-1]["session_id"]:             # puis une semaine à 14 km par séance
        done[sid], km[sid] = TODAY.isoformat(), 14.0
    stt = _write(store, s, done=done, km=km)
    alert = next(a for a in alertes.program_alerts(stt, None, TODAY) if a.key.startswith("charge"))
    assert alert.title == "Kilomètres en forte hausse" and "km courus" in alert.detail
    weekly = analyse.weekly_frame(stt, TODAY)
    assert weekly.loc[weekly["position"] == weeks[-1]["position"].iloc[0], "km_courus"].iloc[0] == \
        14.0 * len(weeks[-1])
    # sans hausse : pas d'alerte
    stt = _write(store, s, done=done, km=dict.fromkeys(km, 5.0))
    assert "charge" not in _keys(stt)


def test_assiduite_absence_et_pas_faite(store):
    s, st0 = _student(store)
    past = [w for _, w in st0.table.groupby("position") if w["fin"].iloc[0] < TODAY]
    w0, w1 = past[0], past[1]
    start = w1["debut"].iloc[0]
    away = suivi.Report("a1", "absence", start, start + timedelta(days=6), created="2026-01-01 10:00")
    stt = _write(store, s, done=dict.fromkeys(w0["session_id"], TODAY.isoformat()), reports=(away,))
    weekly = analyse.weekly_frame(stt, TODAY)
    row1 = weekly[weekly["position"] == w1["position"].iloc[0]].iloc[0]
    assert row1["excusees"] == len(w1) and row1["manquees"] == 0          # absence : excusées, pas manquées
    adh_with = analyse.adherence(weekly)
    weekly_no = analyse.weekly_frame(_write(store, s, done=dict.fromkeys(w0["session_id"], TODAY.isoformat())),
                                     TODAY)
    assert adh_with > analyse.adherence(weekly_no)                       # l'absence ne pénalise pas
    # une séance « pas faite » de la semaine à venir compte tout de suite comme manquée
    future = st0.table[st0.table["debut"] > TODAY]
    sid = future["session_id"].iloc[0]
    weekly = analyse.weekly_frame(_write(store, s, skipped={sid: suivi.Skip(TODAY.isoformat(), "Autre")}), TODAY)
    assert weekly[weekly["position"] == future["position"].iloc[0]]["manquees"].iloc[0] == 1


# ----------------------------------------------------------------------------- agenda
def test_agenda_ics(store):
    s, st0 = _student(store, days_to_race=40)
    content, count = agenda.ics_calendar(s, st0.table, st0.sp.paces, "https://mon-app.streamlit.app")
    text = content.decode()
    assert text.startswith("BEGIN:VCALENDAR\r\n") and text.rstrip().endswith("END:VCALENDAR")
    assert count > 0 and text.count("BEGIN:VEVENT") == count and text.count("TRIGGER:PT8H") == count
    assert "Jour J" in text and "https://mon-app.streamlit.app" in text
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    days = agenda.session_days(s, st0.table)
    assert count == sum(1 for d in days.values() if d >= TODAY)
    uids = [line for line in text.split("\r\n") if line.startswith("UID:")]
    assert len(set(uids)) == len(uids)                                     # un identifiant stable par séance
    s2 = profils.create_student(store, "sans@x.fr", "Sans", "10k", "50:00")    # pas de date de course
    st2 = historique.program_state(store, s2)
    assert agenda.ics_calendar(s2, st2.table, st2.sp.paces)[1] == 0


# ----------------------------------------------------------------------------- records
def test_records():
    def rec(dist, secs, d, name):
        return SimpleNamespace(distance=dist, race_seconds=secs, race_date=d, course=name, student_id=name)
    history = [rec("10k", 2900, date(2025, 3, 1), "A"), rec("10k", 2750, date(2025, 10, 1), "B"),
               rec("semi", 6300, date(2025, 6, 1), "C"), rec("10k", None, date(2026, 1, 1), "D")]
    prs = records.personal_records(history)
    assert [p.distance for p in prs] == ["10k", "semi"]
    assert prs[0].seconds == 2750 and prs[0].improvement == "−2'30 sur ton ancien record" and prs[0].count == 2
    assert prs[1].improvement == "" and prs[0].pace_str == "4'35\" /km"
    assert records.is_record(history, "B").seconds == 2750 and records.is_record(history, "A") is None
    assert records.is_record(history, "C") is None                         # seule course : pas un « record battu »


# ----------------------------------------------------------------------------- réglages et checklist
def test_reglages_et_checklist(store):
    assert reglages.load_settings(store) == reglages.Settings()
    reglages.save_settings(store, reglages.Settings("coach@x.fr", recap_eleves=False))
    loaded = reglages.load_settings(store)
    assert loaded.coach_email == "coach@x.fr" and not loaded.recap_eleves and loaded.recap_coach
    assert reglages.load_checklist(store) == reglages.default_checklist()
    mine = [reglages.ChecklistItem("toutes", "La veille", "Dossard"), reglages.ChecklistItem("marathon", "Pendant",
                                                                                              "Gels")]
    reglages.save_checklist(store, mine)
    assert reglages.load_checklist(store) == mine
    assert [m for m, _ in reglages.checklist_for(mine, "10k")] == ["La veille"]
    assert [m for m, _ in reglages.checklist_for(mine, "marathon")] == ["La veille", "Pendant"]


# ----------------------------------------------------------------------------- récap du dimanche
@pytest.fixture
def smtp_server():
    from aiosmtpd.controller import Controller

    received = []

    class Handler:
        async def handle_DATA(self, server, session, envelope):
            received.append(message_from_bytes(envelope.content, policy=policy.default))
            return "250 OK"

    ctl = Controller(Handler(), hostname="127.0.0.1", port=8026)
    ctl.start()
    yield received
    ctl.stop()


CFG = emails.EmailConfig(host="127.0.0.1", port=8026, user="coach@x.fr", password="", security="none",
                         sender_name="Baptiste")


def _sunday_before_sessions(state):
    days = sorted(d for d in agenda.session_days(state.student, state.table).values() if d > TODAY)
    monday = days[0] - timedelta(days=days[0].weekday())
    return monday - timedelta(days=1)


def test_recap_du_dimanche(store, smtp_server):
    s, st0 = _student(store, days_to_race=40, email="eva@x.fr")
    s2, _ = _student(store, days_to_race=40, email="leo@x.fr")
    suivi.set_recap(store, s2.id, False)                                   # Léo a décoché le récap
    sunday = _sunday_before_sessions(st0)
    sent = recap.run_weekly(store, CFG, "https://app.test", today=sunday)
    assert [x.to for x in sent] == ["eva@x.fr", "coach@x.fr"] and all(x.ok for x in sent)
    for _ in range(40):
        if len(smtp_server) >= 2:
            break
        time.sleep(0.05)
    student_mail = next(m for m in smtp_server if m["To"] == "eva@x.fr")
    body = student_mail.get_body(preferencelist=("plain",)).get_content()
    assert student_mail["Subject"].startswith("Ta semaine du") and "https://app.test" in body
    coach_mail = next(m for m in smtp_server if m["To"] == "coach@x.fr")
    assert coach_mail["Subject"].startswith("Bilan de la semaine")
    # réglages : pas de récap élèves, bilan coach vers une autre adresse
    reglages.save_settings(store, reglages.Settings("moi@coach.fr", recap_eleves=False))
    sent = recap.run_weekly(store, CFG, "", today=sunday, dry_run=True)
    assert [x.to for x in sent] == ["moi@coach.fr"]
    # aperçu : tout part à une seule adresse
    sent = recap.run_weekly(store, CFG, "", today=sunday, dry_run=True, preview_to="test@x.fr")
    assert {x.to for x in sent} == {"test@x.fr"} and any("[Aperçu élève" in x.subject for x in sent)


def test_emails_signalement_et_reponse(store):
    s, _ = _student(store)
    rep = suivi.add_report(store, s.id, "douleur", TODAY, zone="Genou", level=3, comment="Ça tire")
    msg = recap.report_email(s, rep, CFG, "coach@x.fr", "https://app.test")
    assert msg["To"] == "coach@x.fr" and "Douleur (genou), forte" in msg["Subject"]
    msg = recap.reply_email(s, "ta sortie longue", "Bravo !", CFG, "https://app.test")
    assert msg["To"] == s.email and "Bravo !" in msg.get_body(preferencelist=("plain",)).get_content()
    assert recap.send_now(msg, None) == (False, "e-mails non configurés")


def test_script_recap_sans_config(tmp_path, monkeypatch, capsys):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    import recap_hebdo
    for var in ("PLAN_EMAIL_USER", "PLAN_EMAIL_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    assert recap_hebdo.main(["--data", str(tmp_path / "rien")]) == 1
    (tmp_path / "d" / "eleves").mkdir(parents=True)
    assert recap_hebdo.main(["--data", str(tmp_path / "d")]) == 1
    assert "non configurés" in capsys.readouterr().out


# ----------------------------------------------------------------------------- adresse
@pytest.fixture
def osm(monkeypatch):
    server = fake_osm.start()
    base = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setattr(decouverte, "OVERPASS_URLS", [f"{base}/api/interpreter"])
    monkeypatch.setattr(decouverte, "POSTPASS_URLS", [f"{base}/postpass/interpreter"])
    monkeypatch.setattr(decouverte, "NOMINATIM_URL", f"{base}/search")
    monkeypatch.setattr(decouverte, "IGN_URL", f"{base}/geocodage/search")
    monkeypatch.setattr(decouverte, "IGN_COMPLETION_URL", f"{base}/geocodage/completion")
    monkeypatch.setattr(decouverte, "_DOWN", {})
    for flag in ("fail_overpass", "fail_details", "fail_postpass", "fail_ign", "fail_nominatim"):
        setattr(fake_osm.FakeOSM, flag, False)
    yield base
    server.shutdown()


def test_adresse(osm):
    sugg = decouverte.complete("12 rue des lil")
    assert sugg[0]["label"].startswith("12 Rue des Lilas") and sugg[0]["kind"] == "adresse"
    assert decouverte.complete("12") == []                                 # moins de 3 lettres
    place = decouverte.geocode("12 rue des Lilas, Ville Test", address=True)
    assert place.kind == "adresse" and place.name == "Ville Test" and "Lilas" in place.label
    found = decouverte.discover(place, 5)
    assert found and all(r.center_km <= 5.5 for r in found)
    # les distances sont comptées depuis l'adresse, pas depuis le centre de la ville
    from_city = {r.name: r.center_km for r in decouverte.discover(decouverte.geocode("ville test"), 5)}
    assert any(abs(r.center_km - from_city.get(r.name, r.center_km)) > 0.05 for r in found)
