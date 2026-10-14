"""
Gestion des profils élèves : création, codes d'accès, lecture, sauvegarde, suppression.

Chaque élève a son fichier `data/eleves/<id>.xlsx` avec 4 onglets :
    profil    : clé / valeur (email, prénom, code, distance, nom de la course, méthode, objectif, VMA, date…)
    formules  : ratios propres à l'élève (méthode « objectif de temps »)
    vma       : plages de % de VMA propres à l'élève (méthode « VMA »)
    semaines  : semaines de son plan
    seances   : séances de son plan
Un fichier = un programme. Plusieurs programmes peuvent appartenir au même élève (même e-mail) : ils
partagent alors le même code d'accès, et l'élève passe de l'un à l'autre dans son espace.
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
                          plan_to_sheets, vma_pct_value)
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
    course: str = ""                    # nom de la course, ex. « Marathon de Paris 2027 » (facultatif)

    @property
    def frequence(self) -> int:
        return self.frequence_eleve or self.frequence_defaut

    @property
    def display_name(self) -> str:
        return self.prenom or self.email.split("@")[0]

    @property
    def race_name(self) -> str:
        """Nom de la course, ou la distance s'il n'est pas renseigné."""
        return self.course.strip() or DISTANCES[self.distance].label

    @property
    def person(self) -> str:
        """Clé de l'élève (ses programmes partagent le même code d'accès)."""
        return normalize_code(self.code)

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
        ("course", s.course),
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
        vma_pct = {r["allure"]: vma_pct_value(r) for _, r in sheets["vma"].iterrows() if r["allure"] in PACE_CODES}
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
        email_envoye_le=str(p.get("email_envoye_le", "")), course=str(p.get("course", "")).strip(),
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
    """Programme ouvert avec ce code (le programme en cours si l'élève en a plusieurs)."""
    wanted = normalize_code(code)
    if not wanted:
        return None
    progs = [s for s in list_students(store) if s.person == wanted]
    return current_program(store, progs) if progs else None


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


def programs_of(store: Store, student: Student) -> list[Student]:
    """Tous les programmes de l'élève (même code d'accès), du plus ancien au plus récent."""
    progs = [s for s in list_students(store) if s.person == student.person] or [student]
    return sorted(progs, key=lambda s: (s.date_course or date.max, s.cree_le))


def current_program(store: Store, programs: list[Student], today: date | None = None) -> Student:
    """Programme ouvert à la connexion : la prochaine course pas encore courue, sinon la plus récente."""
    from .suivi import load_suivi   # import local : suivi ne dépend pas des profils

    today = today or date.today()
    open_ = [s for s in programs if not load_suivi(store, s.id).temps_realise
             and (s.date_course is None or s.date_course >= today)]
    if open_:
        return min(open_, key=lambda s: (s.date_course or date.max, s.cree_le))
    return max(programs, key=lambda s: (s.date_course or date.min, s.cree_le))


def create_student(store: Store, email: str, prenom: str, distance: str, objectif: str | None = None,
                   date_course: date | None = None, frequence: int = 4,
                   reserved_codes: set[str] | None = None, vma=None, methode: str | None = None,
                   course: str = "") -> Student:
    """Crée un programme : formules et % VMA globaux et modèle de référence actuels de la distance.

    Nouvel e-mail : nouvel élève avec un code unique. E-mail déjà connu : nouveau programme pour cet
    élève, avec le même code d'accès (et son prénom si on n'en donne pas).
    Il faut au moins un objectif de temps ou une VMA. La méthode retenue vaut par défaut celle qui est
    renseignée (ou celle de la distance si les deux le sont).
    """
    email = (email or "").strip()
    course = (course or "").strip()
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
    same_person = sorted((s for s in existing if s.email.lower() == email.lower()), key=lambda s: s.cree_le)
    if any(s.distance == distance and s.course.lower() == course.lower() and s.date_course == date_course
           for s in same_person):
        what = f"« {course} »" if course else DISTANCES[distance].label.lower()
        raise ValueError(f"Cet élève a déjà un programme {what} à cette date : donne un nom de course différent.")
    if same_person:
        code = same_person[-1].code
        prenom = (prenom or "").strip() or same_person[-1].prenom
    else:
        code = generate_code({s.code for s in existing} | (reserved_codes or set()))
    student = Student(
        id=uuid.uuid4().hex[:10], email=email, prenom=(prenom or "").strip(), code=code, distance=distance,
        objectif=objectif, date_course=date_course, frequence_defaut=frequence if frequence in FREQUENCIES else 4,
        frequence_eleve=None, ratios=dict(load_global_ratios(store)[distance]),
        plan=load_template(store, distance).copy_with_new_ids(), methode=methode, vma=vma,
        vma_pct=dict(load_global_vma_pct(store)[distance]), course=course,
    )
    save_student(store, student)
    return student


def update_identity(store: Store, student: Student, email: str, prenom: str) -> Student:
    """Corrige l'e-mail et le prénom d'un élève, sur tous ses programmes.

    Un nouvel e-mail remet « code non envoyé » : le code n'a pas encore été envoyé à cette adresse."""
    email = (email or "").strip()
    if not EMAIL_RE.match(email):
        raise ValueError("Adresse e-mail invalide.")
    others = [s for s in list_students(store) if s.person != student.person and s.email.lower() == email.lower()]
    if others:
        raise ValueError(f"Cette adresse est déjà celle d'un autre élève ({others[0].display_name}).")
    changed = email.lower() != student.email.lower()
    updated = student
    for prog in programs_of(store, student):
        new = prog.with_(email=email, prenom=(prenom or "").strip(),
                         email_envoye_le="" if changed else prog.email_envoye_le)
        save_student(store, new)
        if prog.id == student.id:
            updated = new
    return updated


def regenerate_code(store: Store, student: Student, reserved_codes: set[str] | None = None) -> Student:
    """Nouveau code pour l'élève, sur tous ses programmes (l'ancien ne fonctionne plus)."""
    progs = programs_of(store, student)
    others = {s.code for s in list_students(store) if s.person != student.person} | (reserved_codes or set())
    code = generate_code(others | {student.code})
    updated = student
    for prog in progs:
        new = prog.with_(code=code)
        save_student(store, new)
        if prog.id == student.id:
            updated = new
    return updated
