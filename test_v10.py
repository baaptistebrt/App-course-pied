"""
Tests de la v10 : onglets Trail (50 km) et Triathlon (L), séances optionnelles, choix des séances
de la semaine (triathlon), courses intermédiaires avec temps, note d'introduction du plan, note
technique, nutrition du jour de course, exports et agenda adaptés. Les plans de route ne changent pas.
"""

import html
import io
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import (agenda, analyse, exports, historique, profils, recap, records, referentiel,  # noqa: E402
                  reglages, suivi)
from core.config import DISTANCES, ROUTE_KEYS, SPORT_KEYS  # noqa: E402
from core.moteur import student_paces  # noqa: E402
from core.plan import (activity_kind, is_intermediate_race, is_optional, is_race_day, session_heading,  # noqa: E402
                       session_label, vma_hints)
from core.stockage import Store  # noqa: E402

TODAY = date.today()
RACE_TRAIL = date(2026, 9, 13)          # date du document de référence (dimanche)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "data")
    referentiel.ensure_referentiel(s)
    return s


def _sessions(plan, position):
    week_id = plan.weeks.sort_values("position").iloc[position]["week_id"]
    return plan.sessions_of(week_id)


def _trail(store, race=RACE_TRAIL, **kw):
    s = profils.create_student(store, "quentin@x.fr", "Quentin", "trail50", None, race, **kw)
    return s, historique.program_state(store, s)


def _tri(store, race=None, **kw):
    race = race or TODAY + timedelta(days=(6 - TODAY.weekday()) + 7 * 9)     # dimanche, dans 10 semaines
    s = profils.create_student(store, "lea@x.fr", "Léa", "triL", None, race, **kw)
    return s, historique.program_state(store, s)


# ----------------------------------------------------------------------------- distances et onglets
def test_distances_et_onglets():
    assert ROUTE_KEYS == ["marathon", "semi", "10k", "10k_bis"]
    assert SPORT_KEYS == {"trail": ["trail50"], "triathlon": ["triL"]}
    assert DISTANCES["trail50"].short == "50 km" and DISTANCES["triL"].short == "L"
    assert not DISTANCES["trail50"].uses_paces and DISTANCES["marathon"].uses_paces and DISTANCES["10k_bis"].uses_paces


# ----------------------------------------------------------------------------- modèle trail 50 km
def test_modele_trail_fidele_au_document():
    plan = referentiel.default_template("trail50")
    assert plan.n_weeks == 11
    phases = list(plan.weeks.sort_values("position")["phase"])
    assert phases[:4] == ["A - Phase de développement général"] * 4
    assert phases[4:9] == ["B - Phase de travail spécifique"] * 5
    assert phases[9:] == ["C - Phase de relâchement"] * 2
    assert "11 semaines" in plan.intro and "semaines « allégées » 4 et 7" in plan.intro
    # S1 : mardi VMA, mercredi footing optionnel, jeudi côtes, dimanche SL
    s1 = _sessions(plan, 0)
    assert list(s1["jour"]) == ["mar", "mer", "jeu", "dim"]
    assert list(s1["tag"]) == ["VMA", "Footing", "Côtes", "SL"]
    assert list(s1["statut"]) == ["obligatoire", "optionnel", "obligatoire", "obligatoire"]
    assert "105 % VMA" in s1.iloc[0]["contenu"]
    # 3 séances obligatoires + 1 optionnelle par semaine (S1 à S10)
    for pos in range(10):
        sub = _sessions(plan, pos)
        assert sum(is_optional(r) for _, r in sub.iterrows()) == 1, pos
    # note technique « triangle » rattachée aux séances M/D (S9 et S10)
    md = plan.sessions[plan.sessions["tag"] == "M/D"]
    assert len(md) == 2 and all("triangle" in n for n in md["note"])
    # dernière semaine : footings puis JOUR J (compétition, 50 km)
    last = _sessions(plan, 10)
    race = last[[is_race_day(x) for x in last["seance"]]].iloc[0]
    assert race["jour"] == "dim" and race["km_env"] == "50" and "Compétition" in race["contenu"]


def test_trail_dates_a_rebours(store):
    s, state = _trail(store)
    first = state.table.iloc[0]
    assert first["debut"] == date(2026, 6, 29)               # « Mardi 30 06 » dans le document
    assert first["date"] == date(2026, 6, 30)
    race = state.table[[is_race_day(x) for x in state.table["seance"]]].iloc[0]
    assert race["date"] == RACE_TRAIL
    s8 = state.table[state.table["position"] == 7].iloc[0]
    assert s8["date"] == date(2026, 8, 17)                   # « Lundi 17 » (août)


# ----------------------------------------------------------------------------- modèle triathlon L
def test_modele_triathlon_fidele_au_document():
    plan = referentiel.default_template("triL")
    assert plan.n_weeks == 10                                  # départ direct à la semaine 1
    tags = set(plan.sessions["tag"]) - {""}
    assert tags <= {"natation", "velo", "cap", "enchainement", "course_inter"}
    inter = plan.sessions[[is_intermediate_race(r) for _, r in plan.sessions.iterrows()]]
    assert len(inter) == 2
    assert session_label(inter.iloc[0]) == "Triathlon sprint"
    assert session_label(inter.iloc[1]) == "Triathlon distance olympique"
    s10 = _sessions(plan, 9)
    race = s10[[is_race_day(x) for x in s10["seance"]]].iloc[0]
    assert race["km_env"] == "113" and "Half Iron Man" in race["contenu"]
    assert all(str(d).strip() for d, se in zip(plan.sessions["duree_env"], plan.sessions["seance"])
               if not is_race_day(se))                         # chaque jour a sa durée
    # aucun tableau de chiffres résiduel : chaque séance a une discipline et une description
    assert all(t and c for t, c, se in zip(plan.sessions["tag"], plan.sessions["contenu"], plan.sessions["seance"])
               if not is_race_day(se))
    assert plan.intro


# ----------------------------------------------------------------------------- titres, types, allures
def test_titres_types_et_allures():
    row = lambda **kw: pd.Series({"seance": "s1", "tag": "", "contenu": "", "allure": None, "km_env": "",  # noqa: E731
                                  "statut": "", "note": "", **kw})
    vma = row(tag="VMA", contenu="Footing de 25' + 2 x 8 x 30\"-30\" à 105 % VMA avec R = 3' + 10' de récup")
    assert session_heading(vma) == ("VMA", vma["contenu"])          # contenu long : sous l'étiquette
    assert session_label(vma).startswith("VMA · Footing")
    foot = row(tag="Footing", contenu="Footing de 1h")
    assert session_heading(foot) == ("Footing de 1h", "")
    nat = row(tag="natation", contenu="• 400 m souple\n• 10 x 100 m")
    assert session_heading(nat) == ("Sortie natation", "• 400 m souple\n• 10 x 100 m")
    assert activity_kind(vma) == "fractionne" and activity_kind(row(tag="Côtes")) == "cotes"
    assert activity_kind(row(tag="M/D")) == "md" and activity_kind(row(tag="SL")) == "longue"
    assert activity_kind(nat) == "natation" and activity_kind(row(tag="enchainement")) == "enchainement"
    assert activity_kind(row(contenu="footing", km_env="8", allure="Endurance")) == "footing"   # route : inchangé
    assert session_heading(row(contenu="10 km footing")) == ("10 km footing", "")
    assert vma_hints(vma["contenu"], 16) == ["105 % VMA = 3'34\" /km"]
    assert vma_hints(vma["contenu"], None) == []


# ----------------------------------------------------------------------------- élève trail / triathlon
def test_creation_sans_objectif_ni_vma(store):
    s, state = _trail(store)
    assert s.objectif == "" and s.vma is None
    sp = student_paces(s)
    assert sp.race_seconds == 0 and not sp.known
    s2 = profils.create_student(store, "max@x.fr", "Max", "trail50", "7:30:00", RACE_TRAIL, vma="16")
    sp2 = student_paces(s2)
    assert sp2.known and sp2.race_seconds == 7 * 3600 + 30 * 60
    again = profils.get_student(store, s2.id)
    assert again.vma == 16 and again.objectif and again.plan.intro           # relu depuis le fichier
    with pytest.raises(ValueError):
        profils.create_student(store, "z@x.fr", "Z", "marathon", None, None)  # route : toujours obligatoire


def test_optionnelles_comptent_seulement_si_faites(store):
    s, state = _trail(store, race=TODAY + timedelta(days=(6 - TODAY.weekday()) + 70))
    week = state.table[state.table["position"] == 0]
    opt = next(r for _, r in week.iterrows() if is_optional(r))
    required = [r for _, r in week.iterrows() if not is_optional(r)]
    total0 = state.progress.total
    assert total0 == sum(1 for _, r in state.table.iterrows() if not is_optional(r))
    nxt = suivi.next_session(state.table, state.suivi, TODAY)
    assert nxt is not None and not is_optional(nxt)
    suivi.set_done(store, s.id, opt["session_id"], True)
    state = historique.program_state(store, s)
    assert state.progress.total == total0 + 1 and state.progress.done == 1
    for r in required:
        suivi.set_done(store, s.id, r["session_id"], True)
    state = historique.program_state(store, s)
    assert state.progress.done == len(required) + 1


def test_choisir_mes_seances(store):
    s, state = _tri(store)
    week = s.plan.sessions_of(s.plan.weeks.iloc[0]["week_id"])
    ids = list(week["session_id"])
    kept = ids[:3]
    suivi.set_week_selection(store, s.id, ids, kept)
    state = historique.program_state(store, s)
    shown = set(state.table[state.table["position"] == 0]["session_id"])
    assert shown == set(kept)
    assert state.progress.total == len(state.table)                       # écartées : ni faites ni manquées
    # les autres semaines ne bougent pas, et tout revient à l'identique
    assert len(state.table[state.table["position"] == 1]) == len(s.plan.sessions_of(s.plan.weeks.iloc[1]["week_id"]))
    suivi.set_week_selection(store, s.id, ids, ids)
    state = historique.program_state(store, s)
    assert set(state.table[state.table["position"] == 0]["session_id"]) == set(ids)
    # le jour J n'est jamais écarté
    last = s.plan.sessions_of(s.plan.weeks.sort_values("position").iloc[-1]["week_id"])
    race_id = next(r["session_id"] for _, r in last.iterrows() if is_race_day(r["seance"]))
    suivi.set_week_selection(store, s.id, list(last["session_id"]), [])
    state = historique.program_state(store, s)
    assert race_id in set(state.table["session_id"])
    sv = suivi.load_suivi(store, s.id)
    assert race_id in sv.excluded                                           # mémorisé, mais sans effet


def test_course_intermediaire_temps(store):
    s, state = _tri(store)
    inter = next(r for _, r in state.table.iterrows() if is_intermediate_race(r))
    sid = inter["session_id"]
    with pytest.raises(ValueError):
        suivi.set_session_time(store, s.id, sid, "vite")
    suivi.set_session_time(store, s.id, sid, "1:12:30")
    sv = suivi.load_suivi(store, s.id)
    assert sv.times[sid] == "1:12:30" and sid in sv.done
    assert sv.temps_realise == ""                                  # distinct du JOUR J
    state = historique.program_state(store, s)
    assert suivi.is_done(inter, state.suivi) and not state.finished()
    entry = next(x for x in suivi.journal(state.table, state.suivi) if x["row"]["session_id"] == sid)
    assert entry["time"] == "1h12'30"
    suivi.set_session_time(store, s.id, sid, "")
    assert sid not in suivi.load_suivi(store, s.id).times
    # le fichier de suivi relit bien les temps
    suivi.set_session_time(store, s.id, sid, "1:10:00")
    assert suivi.load_suivi(store, s.id).times == {sid: "1:10:00"}


def test_volume_en_heures_et_records(store):
    s, state = _tri(store)
    weekly = analyse.weekly_frame(state)
    assert weekly["km_prevus"].sum() == 113 and weekly["h_prevues"].sum() > 50     # seul le jour J a des km
    from ui.progression import in_hours
    assert in_hours(state) and not in_hours(_trail(store)[1])
    # une course de trail terminée : record sans allure au km
    t, _ = _trail(store, race=TODAY - timedelta(days=2))
    suivi.set_race_time(store, t.id, "7:45:10")
    hist = historique.race_history(store, [t])
    assert hist[0].race_time == "7h45'10" and hist[0].objective == "" and not hist[0].objective_is_estimate
    prs = records.personal_records(hist)
    assert prs[0].time_str == "7h45'10" and prs[0].pace_str == ""
    assert analyse.races_frame(hist)["allure_s"].isna().all()


# ----------------------------------------------------------------------------- note d'introduction
def test_note_d_introduction_aller_retour(store):
    s, _ = _trail(store)
    plan = s.plan.with_intro("Bonjour Quentin,\nvoici ton plan.")
    sheets = referentiel.plan_to_sheets(plan)
    assert "plan" in sheets
    assert referentiel.plan_from_sheets(sheets).intro == "Bonjour Quentin,\nvoici ton plan."
    route = referentiel.default_template("marathon")
    assert route.intro == "" and "plan" not in referentiel.plan_to_sheets(route)   # route : fichier inchangé
    # la note suit les opérations sur le plan
    assert plan.insert_week(0).intro == plan.intro and plan.delete_week(plan.weeks.iloc[0]["week_id"]).intro


# ----------------------------------------------------------------------------- nutrition
def test_nutrition_par_distance_et_par_eleve(store):
    texts = reglages.load_nutrition(store)
    assert set(texts) >= {"marathon", "semi", "10k", "trail50", "triL"} and all(texts.values())
    reglages.save_nutrition(store, "trail50", "Mange toutes les 30 min.")
    assert reglages.load_nutrition(store)["trail50"] == "Mange toutes les 30 min."
    assert reglages.load_nutrition(store)["marathon"] == texts["marathon"]
    s, _ = _trail(store)
    assert reglages.nutrition_for(store, s) == "Mange toutes les 30 min."
    s.nutrition = "Pour toi : pas de lactose."
    profils.save_student(store, s)
    assert reglages.nutrition_for(store, profils.get_student(store, s.id)) == "Pour toi : pas de lactose."
    assert {"trail50", "triL"} <= set(reglages.FOR_OPTIONS)
    assert reglages.checklist_for(reglages.default_checklist(), "triL")


# ----------------------------------------------------------------------------- exports, agenda, récap
def test_exports_trail(store):
    s, state = _trail(store)
    s = s.__class__(**{**s.__dict__, "plan": s.plan.with_intro("Intro du coach")})
    state = historique.program_state(store, s)
    table = exports.export_table(state.table, set(), {}, "trail")
    assert {"Type", "Statut", "Note technique", "Contenu"} <= set(table.columns)
    assert "Allure" not in table.columns and "Fréquence" not in table.columns
    assert "Optionnel" in set(table["Statut"]) and "VMA" in set(table["Type"])
    xl = pd.read_excel(io.BytesIO(exports.export_excel(s, state.table, state.sp, 3, done=set())), sheet_name=None)
    assert "Allures" not in xl and "Plan" in xl                          # pas de VMA : pas d'onglet allures
    doc = html.unescape(exports.print_document(s, state.table, state.sp, 3, nutrition="Boire souvent"))
    assert "Intro du coach" in doc and "Optionnel" in doc and "triangle" in doc and "Boire souvent" in doc
    assert "séances par semaine" not in doc and "50 km" in doc
    rows = dict(exports.profile_rows(s, state.sp, 3))
    assert "Séances par semaine" not in rows and "Méthode de calcul" not in rows
    csv = exports.export_csv(state.table, sport="trail").decode("utf-8-sig").splitlines()[0]
    assert "Statut" in csv


def test_agenda_et_recap_triathlon(store):
    s, state = _tri(store)
    content, count = agenda.ics_calendar(s, state.table, state.sp.paces, today=TODAY - timedelta(days=7))
    text = content.decode()
    assert count > 0 and "🏊 Sortie natation" in text and "🚴 Sortie vélo" in text
    row = next(r for _, r in state.table.iterrows() if str(r["tag"]) == "natation")
    t, h = recap._session_line(row, state.sp.paces)
    assert t.startswith("🏊 Sortie natation") and "0h45" in t


def test_route_inchange(store):
    """Un élève de route garde exactement le même plan et les mêmes exports qu'avant."""
    s = profils.create_student(store, "eva@x.fr", "Éva", "10k", "50:00", TODAY + timedelta(days=60), 3)
    state = historique.program_state(store, s)
    assert set(state.table["tag"]) == {""} and set(state.table["statut"]) == {""}
    cols = list(exports.export_table(state.table).columns)
    assert "Statut" not in cols and cols[0] == "Semaine"
    row = state.table.iloc[0]
    assert session_heading(row) == (session_label(row), "")


def test_modele_10k_bis_fidele_au_pdf(store):
    """Nouvel onglet « 10 km bis » (11 semaines, 3 cycles PPG / VMA / Spécifique) avec toutes les fonctions route."""
    plan = referentiel.default_template("10k_bis")
    assert plan.n_weeks == 11
    phases = list(plan.weeks.sort_values("position")["phase"])
    assert phases[:3] == ["Cycle de travail - PPG"] * 3
    assert phases[3:7] == ["Cycle de travail en VMA"] * 4
    assert phases[7:] == ["Cycle de travail spécifique"] * 4
    # Sem 1-3, 7, 11 ont 3 séances ; Sem 4-6, 8-10 ont 4 séances
    counts = [len(_sessions(plan, i)) for i in range(11)]
    assert counts == [3, 3, 3, 4, 4, 4, 3, 4, 4, 4, 3]
    # Un élève créé sur 10k_bis a toutes les fonctionnalités d'un plan 10 km (VMA, objectif, 3/4 séances, hints VMA)
    s = profils.create_student(store, "paul@x.fr", "Paul", "10k_bis", "45:00", TODAY + timedelta(days=70), 4, vma="16")
    state4 = historique.program_state(store, s)
    assert len(state4.table) == sum(counts)
    # À 3 séances/semaine, la séance 2 d'endurance des semaines de 4 séances est retirée (33 séances au total)
    suivi.set_frequency(store, s.id, 3)
    state3 = historique.program_state(store, s)
    assert len(state3.table) == 11 * 3
    # Les pourcentages de VMA (« VMA 60% », « VMA 95% », « 100% de la VMA ») donnent l'allure correspondante
    assert vma_hints("Footing 40' VMA 60%", 16) == ["60 % VMA = 6'15\" /km"]
    assert vma_hints("Ech 20' + 6 x 600 m VMA 95% r1'30 R 15'", 16) == ["95 % VMA = 3'57\" /km"]
    # Le modèle 10 km d'origine (12 semaines) n'est pas touché
    assert referentiel.default_template("10k").n_weeks == 12
