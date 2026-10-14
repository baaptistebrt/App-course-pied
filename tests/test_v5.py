"""
Tests de la v5 : nom de la course, plusieurs programmes par élève (même code), correction de
l'e-mail, historique des courses terminées.
"""

import io
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import auth, emails, historique, moteur, profils, referentiel, suivi  # noqa: E402
from core.exports import profile_rows  # noqa: E402
from core.stockage import Store, read_workbook, write_workbook  # noqa: E402

TODAY = date.today()


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "data")
    referentiel.ensure_referentiel(s)
    return s


def test_nom_de_course_et_programmes(store):
    a = profils.create_student(store, "lea@x.fr", "Léa", "10k", "0:48:00", TODAY + timedelta(days=60), 3,
                               course="10 km de Lyon")
    b = profils.create_student(store, "LEA@x.fr", "", "semi", "1:50:00", TODAY + timedelta(days=150), 4,
                               course="Semi de Paris")
    c = profils.create_student(store, "tom@x.fr", "Tom", "10k", "0:45:00")
    assert b.code == a.code and b.prenom == "Léa" and c.code != a.code       # même élève, même code
    assert profils.get_student(store, a.id).course == "10 km de Lyon" and a.race_name == "10 km de Lyon"
    assert c.race_name == "10 km"
    assert [p.id for p in profils.programs_of(store, b)] == [a.id, b.id]
    with pytest.raises(ValueError):                                          # vrai doublon
        profils.create_student(store, "lea@x.fr", "", "10k", "0:48:00", TODAY + timedelta(days=60),
                               course="10 KM DE LYON")
    # connexion : la prochaine course ; une fois courue, la suivante
    assert auth.authenticate(a.code, store, auth.EditorCode("X", "env")) == ("eleve", a.id)
    suivi.set_race_time(store, a.id, "47:30")
    assert profils.find_by_code(store, a.code).id == b.id
    # nouveau code : pour tous ses programmes
    new = profils.regenerate_code(store, profils.get_student(store, b.id))
    assert profils.get_student(store, a.id).code == new.code != a.code
    assert profils.find_by_code(store, a.code) is None


def test_fichier_sans_nom_de_course(store):
    s = profils.create_student(store, "m@x.fr", "M", "marathon", "3:30:00")
    sheets = read_workbook(store.read(s.file))
    sheets["profil"] = sheets["profil"][sheets["profil"]["cle"] != "course"]
    store.write(s.file, write_workbook(sheets))
    assert profils.get_student(store, s.id).course == "" and profils.get_student(store, s.id).race_name == "Marathon"


def test_modifier_email(store):
    a = profils.create_student(store, "faux@x.fr", "Zoé", "10k", "0:50:00", course="A")
    b = profils.create_student(store, "faux@x.fr", "", "semi", "1:55:00", course="B")
    profils.save_student(store, a.with_(email_envoye_le="2026-10-01 10:00"))
    other = profils.create_student(store, "autre@x.fr", "Max", "10k", "0:40:00")
    with pytest.raises(ValueError):
        profils.update_identity(store, a, "pas-un-email", "Zoé")
    with pytest.raises(ValueError):                                          # adresse d'un autre élève
        profils.update_identity(store, a, "AUTRE@x.fr", "Zoé")
    updated = profils.update_identity(store, profils.get_student(store, a.id), " zoe@x.fr ", "Zoé B.")
    assert updated.email == "zoe@x.fr" and updated.prenom == "Zoé B." and updated.email_envoye_le == ""
    assert profils.get_student(store, b.id).email == "zoe@x.fr"              # tous ses programmes
    assert profils.get_student(store, other.id).email == "autre@x.fr"
    assert updated.code == a.code                                             # le code ne change pas
    same = profils.update_identity(store, updated, "zoe@x.fr", "Zoé")        # prénom seul
    assert same.prenom == "Zoé"


def test_historique(store):
    a = profils.create_student(store, "h@x.fr", "Hugo", "10k", "0:45:00", TODAY - timedelta(days=3), 3,
                               vma="16", methode="temps", course="Corrida")
    b = profils.create_student(store, "h@x.fr", "", "semi", "1:40:00", TODAY + timedelta(days=90), 4)
    profils.create_student(store, "i@x.fr", "Iris", "marathon", "3:40:00", TODAY - timedelta(days=10))
    state = historique.program_state(store, a)
    race = state.table[state.table["seance"] == "JOUR J"]["session_id"].iloc[0]
    for sid in state.table["session_id"].iloc[:5]:
        suivi.set_done(store, a.id, sid, True)
    suivi.set_race_time(store, a.id, "44:10")
    suivi.set_note(store, a.id, race, 5, "Record !")
    records = historique.race_history(store, profils.list_students(store))
    assert [r.name for r in records] == ["Hugo", "Iris"]                      # b n'est pas terminé
    r = records[0]
    assert r.course == "Corrida" and r.race_time == "44'10" and r.gap == "−0'50" and r.gap_seconds == -50
    assert r.feeling == "😄 Excellent" and r.comment == "Record !" and r.done == 6 and r.completion > 0
    assert records[1].race_time == "" and records[1].gap_seconds is None    # date passée, temps non saisi
    mine = historique.race_history(store, profils.programs_of(store, b))
    assert [x.student_id for x in mine] == [a.id]
    xl = pd.read_excel(io.BytesIO(historique.history_excel(records)))
    assert {"Course", "Temps réalisé", "Temps (s)", "Écart (s)", "Ressenti", "Récit de la course"} <= set(xl.columns)
    assert xl["Temps (s)"].iloc[0] == 2650


def test_nom_de_course_dans_exports_et_email(store):
    s = profils.create_student(store, "n@x.fr", "Nina", "semi", "1:45:00", course="Semi de Nice")
    sp = moteur.student_paces(s)
    assert ("Course", "Semi de Nice") in profile_rows(s, sp, 4)
    cfg = emails.EmailConfig("localhost", 25, "coach@x.fr", "x", "Coach", "https://app", "none")
    msg = emails.build_access_email(s, cfg, "https://app")
    assert msg["Subject"] == "Ton plan d'entraînement pour Semi de Nice est prêt"
