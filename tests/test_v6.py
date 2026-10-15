"""
Tests de la v6 : séances par semaine (2, 3 ou 4, masquage sans perte), intensité libre, type
d'activité, analyse de progression, découverte de parcours.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import analyse, historique, parcours, profils, referentiel, suivi  # noqa: E402
from core.plan import Plan, activity_kind, select_sessions  # noqa: E402
from core.stockage import Store, read_workbook, write_workbook  # noqa: E402

TODAY = date.today()


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "data")
    referentiel.ensure_referentiel(s)
    return s


def _week(n=4, only4=(2,)):
    rows = [{"seance": f"s{i + 1}", "km_env": "10", "contenu": f"séance {i + 1}", "allure": "A1",
             "frequence": "4" if i in only4 else "3-4"} for i in range(n)]
    return Plan.from_week_list([{"phase": "", "sessions": rows}]).sessions.reset_index(drop=True)


def test_selection_garde_premiere_et_derniere():
    sub = _week(4)                                            # s3 marquée « si 4 séances »
    assert list(select_sessions(sub, 3)["seance"]) == ["s1", "s2", "s4"]   # la séance « 4 » est masquée d'abord
    assert list(select_sessions(sub, 2)["seance"]) == ["s1", "s4"]
    assert list(select_sessions(sub, 4)["seance"]) == ["s1", "s2", "s3", "s4"]
    assert list(select_sessions(_week(5, only4=()), 3)["seance"]) == ["s1", "s2", "s5"]


def test_semaine_modifiee_sans_perte(store):
    s = profils.create_student(store, "w@x.fr", "W", "marathon", "3:30:00", TODAY + timedelta(days=60), 4)
    state = historique.program_state(store, s)
    w1 = state.table[state.table["position"] == 0]
    w2 = state.table[state.table["position"] == 1]
    assert len(w1) == 4
    for sid in w1["session_id"]:
        suivi.set_done(store, s.id, sid, True)
    suivi.set_note(store, s.id, w1["session_id"].iloc[1], 4, "bien")
    wid = w1["week_id"].iloc[0]
    suivi.set_week_count(store, s.id, wid, 2)
    state2 = historique.program_state(store, s)
    v1 = state2.table[state2.table["week_id"] == wid]
    assert list(v1["session_id"]) == [w1["session_id"].iloc[0], w1["session_id"].iloc[-1]]
    assert len(state2.table[state2.table["position"] == 1]) == len(w2)       # autre semaine intacte
    suivi.set_week_count(store, s.id, wid, 4)                                 # on remet 4 séances
    state3 = historique.program_state(store, s)
    v3 = state3.table[state3.table["week_id"] == wid]
    assert list(v3["session_id"]) == list(w1["session_id"]) and list(v3["contenu"]) == list(w1["contenu"])
    sv = suivi.load_suivi(store, s.id)
    assert set(w1["session_id"]) <= set(sv.done) and sv.note(w1["session_id"].iloc[1]).commentaire == "bien"
    suivi.set_week_count(store, s.id, wid, None)
    assert wid not in suivi.load_suivi(store, s.id).semaines
    assert "semaines" in read_workbook(store.read(f"suivi/{s.id}.xlsx"))


def test_intensite_et_type(store):
    s = profils.create_student(store, "i@x.fr", "I", "10k", "0:45:00")
    sessions = s.plan.sessions.copy()
    sessions.loc[0, "intensite"] = "Facile, en aisance respiratoire"
    plan = Plan(s.plan.weeks, sessions)
    profils.save_student(store, s.with_(plan=plan))
    assert profils.get_student(store, s.id).plan.sessions["intensite"].iloc[0] == "Facile, en aisance respiratoire"
    sheets = read_workbook(store.read(s.file))                       # ancien fichier sans la colonne
    sheets["seances"] = sheets["seances"].drop(columns=["intensite"])
    store.write(s.file, write_workbook(sheets))
    assert (profils.get_student(store, s.id).plan.sessions["intensite"] == "").all()
    row = lambda **kw: pd.Series({"seance": "s1", "allure": None, "contenu": "", "km_env": "", **kw})  # noqa: E731
    assert activity_kind(row(seance="JOUR J")) == "course"
    assert activity_kind(row(contenu='10x30"/30"', allure="Sprint")) == "fractionne"
    assert activity_kind(row(contenu="30' progressif", allure="A2,A3")) == "progressif"
    assert activity_kind(row(contenu="footing", km_env="18")) == "longue"
    assert activity_kind(row(contenu="footing", km_env="8", allure="Endurance")) == "footing"


def test_analyse(store):
    start = TODAY - timedelta(days=TODAY.weekday()) - timedelta(weeks=2)       # semaine 1 il y a 2 semaines
    race = start + timedelta(weeks=6, days=6)
    s = profils.create_student(store, "a@x.fr", "A", "marathon", "3:30:00", race, 4)
    state = historique.program_state(store, s)
    w = state.table
    for sid in w[w["position"] == 0]["session_id"]:
        suivi.set_done(store, s.id, sid, True)
    suivi.set_note(store, s.id, w["session_id"].iloc[0], 2, "")
    state = historique.program_state(store, s)
    weekly = analyse.weekly_frame(state)
    assert list(weekly["statut"][:3]) == ["passee", "passee", "en_cours"]
    assert weekly["faites"].iloc[0] == weekly["prevues"].iloc[0] and weekly["manquees"].iloc[1] == weekly["prevues"].iloc[1]
    assert weekly["km_courus"].iloc[0] == weekly["km_prevus"].iloc[0] > 0
    adh = analyse.adherence(weekly)
    expected = weekly["prevues"].iloc[0] / weekly["prevues"].iloc[:3].sum()
    assert adh == pytest.approx(expected)
    assert len(analyse.feelings_frame(state)) == 1
    suivi.set_race_time(store, s.id, "3:25:00")
    races = analyse.races_frame([historique.race_record(historique.program_state(store, s))])
    assert races["ecart_s"].iloc[0] == -300 and races["ecart_pct"].iloc[0] == pytest.approx(-2.4)
    assert races["allure_s"].iloc[0] == pytest.approx(12300 / 42.2)


def test_parcours(store):
    assert parcours.load_routes(store) == []
    parcours.add_route(store, "Saint-Étienne", "Boucle du Pilat", "12,5", "www.openrunner.com/r/123")
    parcours.add_route(store, "Lyon", "Parc de la Tête d'Or", 7.2, "")
    parcours.add_route(store, "Lyon", "Berges du Rhône", "10")
    with pytest.raises(ValueError):
        parcours.add_route(store, "lyon", "berges du rhone", 9)                # doublon
    with pytest.raises(ValueError):
        parcours.add_route(store, "Lyon", "X", "abc")                          # distance
    with pytest.raises(ValueError):
        parcours.add_route(store, "Lyon", "Y", 5, "pas un lien")
    routes = parcours.load_routes(store)
    assert parcours.cities(routes) == ["Lyon", "Saint-Étienne"]
    found = parcours.search(routes, "saint etienne")
    assert len(found) == 1 and found[0].lien == "https://www.openrunner.com/r/123" and found[0].distance_str == "12,5 km"
    assert [r.nom for r in parcours.search(routes, " LYON ")] == ["Parc de la Tête d'Or", "Berges du Rhône"]
    assert len(parcours.search(routes, "ly")) == 2 and parcours.search(routes, "Paris") == []
