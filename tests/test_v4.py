"""
Tests de la v4 : ressentis et commentaires (séances et course), prochaine séance, carnet,
compatibilité des anciens fichiers de suivi et des % de VMA à valeur unique.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import moteur, profils, referentiel, suivi  # noqa: E402
from core.plan import full_plan_table  # noqa: E402
from core.stockage import Store, read_workbook, write_workbook  # noqa: E402


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "data")
    referentiel.ensure_referentiel(s)
    return s


def _student(store, race_date=None):
    s = profils.create_student(store, "m@x.fr", "Maud", "10k", "0:44:00", race_date, 3, vma="16")
    sp = moteur.student_paces(s)
    return s, full_plan_table(s.plan, sp.paces, sp.race_seconds, s.date_course, 3, hide_empty=True)


def test_ressenti_et_commentaire(store):
    s, table = _student(store, date(2026, 11, 29))
    sid = table["session_id"].iloc[0]
    race_id = table[table["seance"] == "JOUR J"]["session_id"].iloc[0]
    suivi.set_done(store, s.id, sid, True)
    suivi.set_note(store, s.id, sid, 4, "  Jambes lourdes au début, puis ça a déroulé.  ")
    suivi.set_note(store, s.id, race_id, 5, "Record battu !")
    sv = suivi.load_suivi(store, s.id)
    assert sv.note(sid).ressenti == 4 and sv.note(sid).commentaire.startswith("Jambes") and sv.note(sid).emoji == "🙂"
    assert sv.note(race_id).label == "😄 Excellent" and race_id not in sv.done
    # décocher garde le commentaire ; tout effacer supprime la note
    suivi.set_done(store, s.id, sid, False)
    sv = suivi.load_suivi(store, s.id)
    assert sid not in sv.done and sv.note(sid).ressenti == 4
    suivi.set_note(store, s.id, sid, None, "   ")
    assert suivi.load_suivi(store, s.id).note(sid).empty
    suivi.set_note(store, s.id, sid, 9, "x" * 5000)                       # ressenti invalide, texte tronqué
    n = suivi.load_suivi(store, s.id).note(sid)
    assert n.ressenti is None and len(n.commentaire) == 1000


def test_ancien_fichier_de_suivi(store):
    s, table = _student(store)
    ids = list(table["session_id"].iloc[:2])
    store.write(f"suivi/{s.id}.xlsx", write_workbook({
        "seances": pd.DataFrame({"session_id": ids, "fait_le": ["2026-09-01", "2026-09-03"]}),
        "infos": pd.DataFrame({"cle": ["temps_realise", "frequence", "maj_le"], "valeur": ["", 4, ""]})}))
    sv = suivi.load_suivi(store, s.id)
    assert set(sv.done) == set(ids) and sv.frequence == 4 and not sv.notes
    suivi.set_note(store, s.id, ids[0], 3, "ok")                           # réécrit au nouveau format
    cols = list(read_workbook(store.read(f"suivi/{s.id}.xlsx"))["seances"].columns)
    assert cols == ["session_id", "fait", "fait_le", "ressenti", "commentaire", "note_le"]
    assert set(suivi.load_suivi(store, s.id).done) == set(ids)


def test_prochaine_seance_et_carnet(store):
    s, table = _student(store, date(2026, 11, 29))
    rows = suivi.ordered(table)
    sv = suivi.load_suivi(store, s.id)
    first = rows.iloc[0]
    # avant le début du plan : la toute première séance
    assert suivi.next_session(table, sv, first["debut"] - timedelta(days=3))["session_id"] == first["session_id"]
    # en semaine 3 : les séances oubliées des semaines 1-2 ne bloquent pas
    w3 = rows[rows["position"] == 2]
    today = w3["debut"].iloc[0] + timedelta(days=1)
    assert suivi.next_session(table, sv, today)["session_id"] == w3["session_id"].iloc[0]
    suivi.set_done(store, s.id, w3["session_id"].iloc[0], True)
    sv = suivi.load_suivi(store, s.id)
    assert suivi.next_session(table, sv, today)["session_id"] == w3["session_id"].iloc[1]
    # ressenti attendu pour la séance cochée aujourd'hui, plus après l'avoir donné
    assert suivi.pending_feedback(table, sv)["session_id"] == w3["session_id"].iloc[0]
    sv = suivi.set_note(store, s.id, w3["session_id"].iloc[0], 2, "")
    assert suivi.pending_feedback(table, sv) is None
    entries = suivi.journal(table, sv)
    assert len(entries) == 1 and entries[0]["note"].ressenti == 2
    pr = suivi.progress(table, sv, None)
    assert pr.done == 1 and pr.km_done > 0
    # tout fait : plus de prochaine séance
    for sid in table["session_id"]:
        suivi.set_done(store, s.id, sid, True)
    assert suivi.next_session(table, suivi.load_suivi(store, s.id), today) is None


def test_pct_vma_valeur_unique(store):
    """Fichier écrit avec une seule colonne « pct » : relu comme une valeur unique."""
    store.write(referentiel.RATIOS_FILE, write_workbook({
        "formules": pd.DataFrame([{"distance": "10k", "allure": "Sprint", "pourcentage": 120}]),
        "vma": pd.DataFrame([{"distance": "10k", "allure": "A3", "pct": 86}])}))
    assert referentiel.load_global_vma_pct(store)["10k"]["A3"] == (86.0, 86.0)
    assert referentiel.load_global_vma_pct(store)["10k"]["A2"] == (80.0, 85.0)


def test_exports_avec_ressentis(store):
    import html
    import io

    from core.exports import export_csv, export_excel, print_document

    s, table = _student(store, date(2026, 11, 29))
    sid = table["session_id"].iloc[0]
    suivi.set_done(store, s.id, sid, True)
    sv = suivi.set_note(store, s.id, sid, 1, "Côte de 2 km : terrible")
    sp = moteur.student_paces(s)
    xl = pd.read_excel(io.BytesIO(export_excel(s, table, sp, 3, done=set(sv.done), notes=sv.notes)), sheet_name="Plan")
    assert xl["Ressenti"].iloc[0] == "😣 Très dur" and xl["Commentaire"].iloc[0].startswith("Côte")
    assert "Commentaire" in export_csv(table, set(sv.done), sv.notes).decode("utf-8-sig").splitlines()[0]
    assert "Commentaire" not in export_csv(table).decode("utf-8-sig").splitlines()[0]   # export du coach sans suivi
    assert "terrible" in html.unescape(print_document(s, table, sp, 3, set(sv.done), "", sv.notes))
