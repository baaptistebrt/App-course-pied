"""
Tests de la logique métier. Lancer avec :  python -m pytest -q
"""

import html
import io
import math
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import auth, profils, referentiel  # noqa: E402
from core.calculs import compute_paces, format_pace, parse_objective  # noqa: E402
from core.exports import export_csv, export_excel, print_document  # noqa: E402
from core.plan import full_plan_table, weeks_until  # noqa: E402
from core.stockage import Store  # noqa: E402

OBJ = 3 * 3600 + 29 * 60   # 3:29:00, cellule D4 de l'Excel

# Valeurs calculées par Excel (classeur lu en data_only) : (km/h, min/km décimales)
EXCEL = {
    "Endurance": (10.297607655502391, 5.826596041260107), "A1": (12.114832535885167, 4.95260663507109),
    "A2": (12.720574162679426, 4.716768223877229), "A3": (13.356602870813399, 4.492160213216407),
    "A4": (14.02443301435407, 4.278247822110864), "Sprint": (16.829319617224883, 3.5652065184257204),
}


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "data")
    referentiel.ensure_referentiel(s)
    return s


# ---------------------------------------------------------------- calculs
@pytest.mark.parametrize("code", EXCEL)
def test_marathon_identique_excel(code):
    p = compute_paces(OBJ, "marathon")[code]
    assert math.isclose(p.kmh, EXCEL[code][0], rel_tol=1e-12)
    assert math.isclose(p.min_per_km, EXCEL[code][1], rel_tol=1e-12)


def test_equivalences_excel():
    p = compute_paces(OBJ, "marathon")
    assert math.isclose(p["A1"].ref_time_minutes, 209.0, rel_tol=1e-12)            # Q6
    assert math.isclose(p["A2"].ref_time_minutes, 99.52380952380953, rel_tol=1e-12)  # Q7
    assert math.isclose(p["A3"].ref_time_minutes, 44.921602132164075, rel_tol=1e-12)  # Q8
    assert math.isclose(p["A4"].ref_time_minutes, 21.39123911055432, rel_tol=1e-12)   # Q9


def test_ancre_semi_et_10k():
    semi = compute_paces(parse_objective("1:45:00", "semi"), "semi")
    assert math.isclose(semi["A2"].min_per_km, 105 / 21.1)            # l'objectif fixe A2
    assert math.isclose(semi["A1"].kmh * 1.05, semi["A2"].kmh)        # A2 = A1 × 105 %
    dix = compute_paces(parse_objective("45:00", "10k"), "10k")
    assert math.isclose(dix["A3"].min_per_km, 4.5)                    # 45 min / 10 km
    assert math.isclose(dix["A4"].kmh, dix["A3"].kmh * 1.05)
    # Cohérence : un objectif marathon donne le même A3 que le 10 km équivalent
    m = compute_paces(OBJ, "marathon")
    d = compute_paces(round(m["A3"].min_per_km * 10 * 60), "10k")
    assert abs(d["A1"].min_per_km - m["A1"].min_per_km) < 0.001


def test_ratios_personnalises():
    base = compute_paces(OBJ, "marathon")
    custom = compute_paces(OBJ, "marathon", {"Endurance": 80, "Sprint": 125})
    assert math.isclose(custom["Endurance"].kmh, base["A1"].kmh * 0.80)
    assert math.isclose(custom["Sprint"].kmh, base["A4"].kmh * 1.25)
    assert math.isclose(custom["A1"].kmh, base["A1"].kmh)            # l'ancre ne bouge pas


def test_format_colonne_O():
    p = compute_paces(OBJ, "marathon")
    assert [format_pace(p[c].min_per_km) for c in ("Endurance", "A1", "A2", "A4", "Sprint")] == \
           ["5'50\"", "4'57\"", "4'43\"", "4'17\"", "3'34\""]


@pytest.mark.parametrize("txt,dist,sec", [
    ("03:29:00", "marathon", OBJ), ("3:29", "marathon", OBJ), ("3h29", "marathon", OBJ),
    ("1:45", "semi", 6300), ("45:30", "10k", 2730), ("0:45:30", "10k", 2730), ("45'30", "10k", 2730),
])
def test_parse_objectif(txt, dist, sec):
    assert parse_objective(txt, dist) == sec


@pytest.mark.parametrize("txt,dist", [("", "marathon"), ("abc", "semi"), ("0:30:00", "marathon"), ("3:00:00", "10k")])
def test_parse_objectif_invalide(txt, dist):
    with pytest.raises(ValueError):
        parse_objective(txt, dist)


# ---------------------------------------------------------------- modèles et plan
def test_modeles_par_defaut():
    for d, n in (("marathon", 7), ("semi", 7), ("10k", 12)):
        t = referentiel.default_template(d)
        assert t.n_weeks == n                                  # 6 sem. + course ; 10 km : 12 sem. (Excel)
        last = t.sessions_of(t.weeks["week_id"].iloc[-1])
        assert "JOUR J" in list(last["seance"])
    m = referentiel.default_template("marathon")
    s1 = m.sessions_of(m.weeks["week_id"].iloc[0])
    assert list(s1["allure"]) == ["Sprint", "A2", "A1", "A1"]  # S01 de l'Excel


def test_frequence_et_jour_j():
    m = referentiel.default_template("marathon")
    paces = compute_paces(OBJ, "marathon")
    t4 = full_plan_table(m, paces, OBJ, date(2026, 10, 18), frequency=4)
    t3 = full_plan_table(m, paces, OBJ, date(2026, 10, 18), frequency=3)
    assert len(t4) - len(t3) == 6
    race = t4[t4["seance"] == "JOUR J"].iloc[0]
    assert race["duree_env"] == "3:29:00" and math.isclose(race["temps_spe_min"], 209.0)
    assert t4["debut"].iloc[-1] == date(2026, 10, 12)          # B10 : lundi de la semaine de course
    assert t4["debut"].iloc[0] == date(2026, 8, 31)            # A39 : S01


def test_semaines_restantes():
    assert weeks_until(date(2026, 10, 18), date(2026, 10, 13)) == 1
    assert weeks_until(date(2026, 11, 29), date(2026, 10, 13)) == 7


# ---------------------------------------------------------------- profils
def test_creation_eleve_et_persistance(store):
    s = profils.create_student(store, "julie@example.com", "Julie", "semi", "1:50", date(2026, 12, 6), 3)
    assert len(profils.normalize_code(s.code)) == 8 and "-" in s.code
    loaded = profils.get_student(store, s.id)
    assert loaded.prenom == "Julie" and loaded.objectif == "01:50:00" and loaded.frequence == 3
    assert loaded.date_course == date(2026, 12, 6) and loaded.plan.n_weeks == 7
    assert profils.find_by_code(store, s.code.lower().replace("-", " ")).id == s.id
    with pytest.raises(ValueError):
        profils.create_student(store, "julie@example.com", "", "semi", "1:45:00")       # doublon
    with pytest.raises(ValueError):
        profils.create_student(store, "pas-un-email", "", "semi", "1:45:00")


def test_codes_uniques(store):
    codes = {profils.create_student(store, f"e{i}@x.fr", "", "10k", "0:50:00").code for i in range(25)}
    assert len(codes) == 25


def test_formules_globales_non_retroactives(store):
    ancien = profils.create_student(store, "a@x.fr", "A", "marathon", "3:30:00")
    referentiel.save_global_ratios(store, "marathon", {"Endurance": 80})
    nouveau = profils.create_student(store, "b@x.fr", "B", "marathon", "3:30:00")
    assert profils.get_student(store, ancien.id).ratios["Endurance"] == 85
    assert nouveau.ratios["Endurance"] == 80
    assert referentiel.load_global_ratios(store)["semi"]["Endurance"] == 85   # autres distances intactes


def test_modele_modifie_pour_nouveaux_eleves(store):
    t = referentiel.load_template(store, "10k").resize(9)
    referentiel.save_template(store, "10k", t)
    s = profils.create_student(store, "c@x.fr", "", "10k", "0:50:00")
    assert s.plan.n_weeks == 9
    s2 = s.with_(plan=s.plan.resize(5))
    profils.save_student(store, s2)
    assert referentiel.load_template(store, "10k").n_weeks == 9                # le modèle n'est pas touché


def test_regeneration_et_suppression(store):
    s = profils.create_student(store, "d@x.fr", "", "semi", "1:45:00")
    s2 = profils.regenerate_code(store, s)
    assert s2.code != s.code and profils.find_by_code(store, s.code) is None
    profils.delete_student(store, s.id)
    assert profils.get_student(store, s.id) is None


def test_authentification(store):
    s = profils.create_student(store, "e@x.fr", "", "marathon", "3:30:00")
    editor = auth.EditorCode("Coach-Secret", "env")
    assert auth.authenticate("Coach-Secret", store, editor) == ("editeur", None)
    assert auth.authenticate(s.code, store, editor) == ("eleve", s.id)
    assert auth.authenticate("faux", store, editor) is None


# ---------------------------------------------------------------- exports
def test_exports(store):
    from core.moteur import student_paces

    s = profils.create_student(store, "f@x.fr", "Fanny", "marathon", "3:29:00", date(2026, 10, 18), 3)
    sp = student_paces(s)
    table = full_plan_table(s.plan, sp.paces, sp.race_seconds, s.date_course, 3, hide_empty=True)
    sheets = pd.read_excel(io.BytesIO(export_excel(s, table, sp, 3, done=set())), sheet_name=None)
    assert set(sheets) == {"Plan", "Allures", "Profil"} and len(sheets["Plan"]) == len(table)
    assert "Réalisée" in sheets["Plan"].columns
    assert export_csv(table).decode("utf-8-sig").splitlines()[0].startswith("Semaine;Du;Au")
    doc = html.unescape(print_document(s, table, sp, 3))
    assert "Fanny" in doc and "3h29'00" in doc and doc.count("class='week'") == 7
