"""
Gestion des profils élèves : création, codes d'accès, lecture, sauvegarde, suppression.

Chaque élève a son fichier `data/eleves/<id>.xlsx` avec 4 onglets :
    profil    : clé / valeur (email, prénom, code, distance, méthode, objectif, VMA, date de course…)
    formules  : ratios propres à l'élève (méthode « objectif de temps »)
    vma       : plages de % de VMA propres à l'élève (méthode « VMA »)
    semaines  : semaines de son plan
    seances   : séances de son plan
Ce fichier n'est écrit que par le coach. Ce que fait l'élève (séances réalisées, temps de course,
fréquence choisie) est dans un fichier séparé : voir suivi.py.
"""

from __future__ import annotations

import re
import secrets
import threading
import uuid
from dataclasses import dataclass, field, replace
from datetime import date, datetime

import pandas as pd

from .calculs import clean_ratios, clean_vma_pct, normalize_objective, parse_vma
from .config import DISTANCES, FREQUENCIES, METHODS, PACE_CODES, RATIO_CODES
from .plan import Plan
from .referentiel import (load_global_ratios, load_global_vma_pct, load_template, plan_from_sheets,
                          plan_to_sheets)
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
    objectif: str                       # « hh:mm:ss » ou "" (facultatif avec la méthode VMA)
    date_course: date | None
    frequence_defaut: int               # choisie par le coach
    frequence_eleve: int | None         # ancien emplacement du choix de l'élève (voir suivi.py)
    ratios: dict[str, float]
    plan: Plan
    cree_le: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))
    methode: str = "temps"              # méthode retenue pour le plan : « temps » ou « vma »
    vma: float | None = None            # km/h
    vma_pct: dict = field(default_factory=dict)   # {allure: (% min, % max)}
    email_envoye_le: str = ""

    @property
    def frequence(self) -> int:
        return self.frequence_eleve or self.frequence_defaut

    @property
    def display_name(self) -> str:
        return self.prenom or self.email.split("@")[0]

    @property
    def file(self) -> str:
        return f"{STUDENTS_DIR}/{self.id}.xlsx"

    @property
    def has_objective(self) -> bool:
        return bool(self.objectif)

    @property
    def has_vma(self) -> bool:
        return self.vma is not None

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
        ("methode", s.methode), ("objectif", s.objectif), ("vma", s.vma if s.vma is not None else ""),
        ("date_course", s.date_course.isoformat() if s.date_course else ""),
        ("frequence_defaut", s.frequence_defaut), ("frequence_eleve", s.frequence_eleve or ""),
        ("cree_le", s.cree_le), ("email_envoye_le", s.email_envoye_le),
    ], columns=["cle", "valeur"])
    formules = pd.DataFrame([{"allure": c, "pourcentage": v} for c, v in clean_ratios(s.ratios).items()])
    vma = pd.DataFrame([{"allure": c, "pct_min": lo, "pct_max": hi} for c, (lo, hi) in clean_vma_pct(s.vma_pct).items()])
    return write_workbook({"profil": profil, "formules": formules, "vma": vma, **plan_to_sheets(s.plan)})


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
    vma_pct = {}
    if "vma" in sheets:
        vma_pct = {r["allure"]: (r["pct_min"], r["pct_max"]) for _, r in sheets["vma"].iterrows()
                   if r["allure"] in PACE_CODES}
    freq_def = _to_int(p.get("frequence_defaut"), 4)
    freq_el = _to_int(p.get("frequence_eleve"))
    try:
        objectif = normalize_objective(str(p.get("objectif", "")), distance) if str(p.get("objectif", "")).strip() else ""
    except ValueError:
        objectif = ""
    try:
        vma = parse_vma(p.get("vma")) if str(p.get("vma", "")).strip() else None
    except ValueError:
        vma = None
    methode = str(p.get("methode") or "temps")          # fichiers d'avant la VMA : « temps »
    if methode not in METHODS or (methode == "vma" and vma is None):
        methode = "temps"
    if methode == "temps" and not objectif:
        if vma is not None:
            methode = "vma"
        else:
            objectif = DISTANCES[distance].default_objective
    return Student(
        id=str(p.get("id") or uuid.uuid4().hex[:10]), email=str(p.get("email", "")),
        prenom=str(p.get("prenom", "")), code=str(p.get("code", "")), distance=distance,
        objectif=objectif, date_course=_to_date(p.get("date_course")),
        frequence_defaut=freq_def if freq_def in FREQUENCIES else 4,
        frequence_eleve=freq_el if freq_el in FREQUENCIES else None,
        ratios=clean_ratios(ratios), plan=plan_from_sheets(sheets), cree_le=str(p.get("cree_le", "")),
        methode=methode, vma=vma, vma_pct=clean_vma_pct(vma_pct),
        email_envoye_le=str(p.get("email_envoye_le", "")),
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
    student = student.with_(plan=student.plan.normalized(), ratios=clean_ratios(student.ratios),
                            vma_pct=clean_vma_pct(student.vma_pct))
    store.write(student.file, student_to_bytes(student))


def delete_student(store: Store, student_id: str) -> None:
    rel = f"{STUDENTS_DIR}/{student_id}.xlsx"
    store.delete(rel)
    store.delete(f"suivi/{student_id}.xlsx")      # suivi de l'élève
    with _cache_lock:
        _cache.pop(rel, None)


def create_student(store: Store, email: str, prenom: str, distance: str, objectif: str | None = None,
                   date_course: date | None = None, frequence: int = 4,
                   reserved_codes: set[str] | None = None, vma=None, methode: str | None = None) -> Student:
    """Crée un élève : code unique, formules et % VMA globaux et modèle de référence actuels de la distance.

    Il faut au moins un objectif de temps ou une VMA. La méthode retenue vaut par défaut celle qui est
    renseignée (ou celle de la distance si les deux le sont).
    """
    email = (email or "").strip()
    if not EMAIL_RE.match(email):
        raise ValueError("Adresse e-mail invalide.")
    if distance not in DISTANCES:
        raise ValueError("Distance inconnue.")
    objectif = normalize_objective(objectif, distance) if objectif and str(objectif).strip() else ""
    vma = parse_vma(vma) if vma not in (None, "") and str(vma).strip() else None
    if not objectif and vma is None:
        raise ValueError("Renseigne un objectif de temps ou une VMA (ou les deux).")
    if methode not in METHODS:
        methode = DISTANCES[distance].default_method if (objectif and vma is not None) else ("temps" if objectif else "vma")
    if methode == "temps" and not objectif:
        raise ValueError("La méthode « objectif de temps » demande un objectif.")
    if methode == "vma" and vma is None:
        raise ValueError("La méthode « VMA » demande une VMA.")
    existing = list_students(store)
    if any(s.email.lower() == email.lower() and s.distance == distance for s in existing):
        raise ValueError(f"Un élève {DISTANCES[distance].label.lower()} existe déjà avec cet e-mail.")
    code = generate_code({s.code for s in existing} | (reserved_codes or set()))
    student = Student(
        id=uuid.uuid4().hex[:10], email=email, prenom=(prenom or "").strip(), code=code, distance=distance,
        objectif=objectif, date_course=date_course, frequence_defaut=frequence if frequence in FREQUENCIES else 4,
        frequence_eleve=None, ratios=dict(load_global_ratios(store)[distance]),
        plan=load_template(store, distance).copy_with_new_ids(), methode=methode, vma=vma,
        vma_pct=dict(load_global_vma_pct(store)[distance]),
    )
    save_student(store, student)
    return student


def regenerate_code(store: Store, student: Student, reserved_codes: set[str] | None = None) -> Student:
    others = {s.code for s in list_students(store) if s.id != student.id} | (reserved_codes or set())
    updated = student.with_(code=generate_code(others | {student.code}))
    save_student(store, updated)
    return updated
