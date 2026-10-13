"""
Gestion des profils élèves : création, codes d'accès, lecture, sauvegarde, suppression.

Chaque élève a son fichier `data/eleves/<id>.xlsx` avec 4 onglets :
    profil    : clé / valeur (email, prénom, code, distance, objectif, date de course, fréquences…)
    formules  : ratios propres à l'élève (copiés des formules globales à sa création)
    semaines  : semaines de son plan
    seances   : séances de son plan
"""

from __future__ import annotations

import re
import secrets
import threading
import uuid
from dataclasses import dataclass, field, replace
from datetime import date, datetime

import pandas as pd

from .calculs import clean_ratios, normalize_objective
from .config import DISTANCES, FREQUENCIES, RATIO_CODES
from .plan import Plan
from .referentiel import load_global_ratios, load_template, plan_from_sheets, plan_to_sheets
from .stockage import Store, read_workbook, write_workbook

STUDENTS_DIR = "eleves"
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # sans 0/O, 1/I/L : pas de confusion à la lecture
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class Student:
    id: str
    email: str
    prenom: str
    code: str
    distance: str
    objectif: str                       # « hh:mm:ss »
    date_course: date | None
    frequence_defaut: int               # choisie par le coach
    frequence_eleve: int | None         # choisie par l'élève (None = celle du coach)
    ratios: dict[str, float]
    plan: Plan
    cree_le: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))

    @property
    def frequence(self) -> int:
        return self.frequence_eleve or self.frequence_defaut

    @property
    def display_name(self) -> str:
        return self.prenom or self.email.split("@")[0]

    @property
    def file(self) -> str:
        return f"{STUDENTS_DIR}/{self.id}.xlsx"

    def with_(self, **changes) -> "Student":
        return replace(self, **changes)


# ----------------------------------------------------------------------------
# Codes d'accès
# ----------------------------------------------------------------------------
def normalize_code(code: str) -> str:
    """Majuscules, sans espaces ni tirets : « abcd-2345 » == « ABCD 2345 »."""
    return re.sub(r"[\s\-]", "", str(code or "")).upper()


def generate_code(existing: set[str], length: int = 8) -> str:
    """Code aléatoire lisible, ex. « K7PM-Q2XD », différent des codes existants."""
    existing = {normalize_code(c) for c in existing}
    while True:
        raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))
        if raw not in existing:
            return f"{raw[:4]}-{raw[4:]}"


# ----------------------------------------------------------------------------
# Sérialisation
# ----------------------------------------------------------------------------
def student_to_bytes(s: Student) -> bytes:
    profil = pd.DataFrame([
        ("id", s.id), ("email", s.email), ("prenom", s.prenom), ("code", s.code), ("distance", s.distance),
        ("objectif", s.objectif), ("date_course", s.date_course.isoformat() if s.date_course else ""),
        ("frequence_defaut", s.frequence_defaut), ("frequence_eleve", s.frequence_eleve or ""),
        ("cree_le", s.cree_le),
    ], columns=["cle", "valeur"])
    formules = pd.DataFrame([{"allure": c, "pourcentage": v} for c, v in clean_ratios(s.ratios).items()])
    return write_workbook({"profil": profil, "formules": formules, **plan_to_sheets(s.plan)})


def _to_int(value, default=None):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _to_date(value) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def student_from_bytes(content: bytes) -> Student:
    sheets = read_workbook(content)
    if "profil" not in sheets:
        raise ValueError("Onglet « profil » absent : ce n'est pas un fichier élève.")
    p = {str(k): ("" if pd.isna(v) else v) for k, v in zip(sheets["profil"]["cle"], sheets["profil"]["valeur"])}
    distance = p.get("distance") if p.get("distance") in DISTANCES else "marathon"
    ratios = {}
    if "formules" in sheets:
        ratios = {r["allure"]: r["pourcentage"] for _, r in sheets["formules"].iterrows() if r["allure"] in RATIO_CODES}
    freq_def = _to_int(p.get("frequence_defaut"), 4)
    freq_el = _to_int(p.get("frequence_eleve"))
    try:
        objectif = normalize_objective(str(p.get("objectif", "")), distance)
    except ValueError:
        objectif = DISTANCES[distance].default_objective
    return Student(
        id=str(p.get("id") or uuid.uuid4().hex[:10]), email=str(p.get("email", "")),
        prenom=str(p.get("prenom", "")), code=str(p.get("code", "")), distance=distance,
        objectif=objectif, date_course=_to_date(p.get("date_course")),
        frequence_defaut=freq_def if freq_def in FREQUENCIES else 4,
        frequence_eleve=freq_el if freq_el in FREQUENCIES else None,
        ratios=clean_ratios(ratios), plan=plan_from_sheets(sheets), cree_le=str(p.get("cree_le", "")),
    )


# ----------------------------------------------------------------------------
# Lecture (avec cache par fichier) et écriture
# ----------------------------------------------------------------------------
_cache: dict[str, tuple[tuple[int, int], Student]] = {}
_cache_lock = threading.Lock()


def list_students(store: Store, distance: str | None = None) -> list[Student]:
    """Tous les élèves (ou ceux d'une distance), triés par nom."""
    students = []
    for rel in store.list(STUDENTS_DIR):
        try:
            version = store.version(rel)
        except FileNotFoundError:
            continue
        with _cache_lock:
            cached = _cache.get(rel)
        if cached and cached[0] == version:
            student = cached[1]
        else:
            try:
                student = student_from_bytes(store.read(rel))
            except (ValueError, TypeError, KeyError):
                continue
            with _cache_lock:
                _cache[rel] = (version, student)
        if distance is None or student.distance == distance:
            students.append(student)
    return sorted(students, key=lambda s: (s.display_name.lower(), s.email.lower()))


def get_student(store: Store, student_id: str) -> Student | None:
    return next((s for s in list_students(store) if s.id == student_id), None)


def find_by_code(store: Store, code: str) -> Student | None:
    wanted = normalize_code(code)
    if not wanted:
        return None
    return next((s for s in list_students(store) if normalize_code(s.code) == wanted), None)


def save_student(store: Store, student: Student) -> None:
    student = student.with_(plan=student.plan.normalized(), ratios=clean_ratios(student.ratios))
    store.write(student.file, student_to_bytes(student))


def delete_student(store: Store, student_id: str) -> None:
    rel = f"{STUDENTS_DIR}/{student_id}.xlsx"
    store.delete(rel)
    with _cache_lock:
        _cache.pop(rel, None)


def create_student(store: Store, email: str, prenom: str, distance: str, objectif: str | None = None,
                   date_course: date | None = None, frequence: int = 4,
                   reserved_codes: set[str] | None = None) -> Student:
    """Crée un élève : code unique, formules globales et modèle de référence actuels de la distance."""
    email = (email or "").strip()
    if not EMAIL_RE.match(email):
        raise ValueError("Adresse e-mail invalide.")
    if distance not in DISTANCES:
        raise ValueError("Distance inconnue.")
    existing = list_students(store)
    if any(s.email.lower() == email.lower() and s.distance == distance for s in existing):
        raise ValueError(f"Un élève {DISTANCES[distance].label.lower()} existe déjà avec cet e-mail.")
    code = generate_code({s.code for s in existing} | (reserved_codes or set()))
    student = Student(
        id=uuid.uuid4().hex[:10], email=email, prenom=(prenom or "").strip(), code=code, distance=distance,
        objectif=normalize_objective(objectif or DISTANCES[distance].default_objective, distance),
        date_course=date_course, frequence_defaut=frequence if frequence in FREQUENCIES else 4,
        frequence_eleve=None, ratios=dict(load_global_ratios(store)[distance]),
        plan=load_template(store, distance).copy_with_new_ids(),
    )
    save_student(store, student)
    return student


def regenerate_code(store: Store, student: Student, reserved_codes: set[str] | None = None) -> Student:
    others = {s.code for s in list_students(store) if s.id != student.id} | (reserved_codes or set())
    updated = student.with_(code=generate_code(others | {student.code}))
    save_student(store, updated)
    return updated
