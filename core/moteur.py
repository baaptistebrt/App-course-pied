"""
Moteur de calcul double d'un élève : objectif de temps (ratios) et/ou VMA (% de VMA).

Le coach peut renseigner les deux, comparer les allures obtenues, puis retenir une méthode :
c'est elle qui alimente le plan de l'élève.
"""

from __future__ import annotations

from dataclasses import dataclass

from .calculs import (Pace, compare_paces, compute_paces, compute_paces_vma, parse_objective,
                      race_seconds_from_paces)
from .config import DISTANCES, VMA_DEFAULT


@dataclass(frozen=True)
class StudentPaces:
    method: str                    # « temps » ou « vma »
    paces: dict[str, Pace]
    race_seconds: int              # objectif, ou temps estimé à partir de la VMA (0 : inconnu, trail/triathlon)
    race_is_estimate: bool
    known: bool = True             # False : allures indicatives (trail/triathlon sans VMA), à ne pas afficher


def paces_by_time(student) -> dict[str, Pace] | None:
    if not student.objectif:
        return None
    return compute_paces(parse_objective(student.objectif, student.distance), student.distance, student.ratios)


def paces_by_vma(student) -> dict[str, Pace] | None:
    if student.vma is None:
        return None
    return compute_paces_vma(student.vma, student.distance, student.vma_pct)


def student_paces(student, method: str | None = None) -> StudentPaces:
    """Allures de l'élève selon la méthode demandée (par défaut : la méthode retenue).

    Trail et triathlon : les allures viennent seulement de la VMA (elle sert aux séances « à x % de VMA ») ;
    l'objectif de temps n'est qu'affiché (pas d'allure de course calculée)."""
    if not DISTANCES[student.distance].uses_paces:
        race = parse_objective(student.objectif, student.distance) if student.objectif else 0
        paces = paces_by_vma(student)
        if paces is None:
            return StudentPaces("vma", compute_paces_vma(VMA_DEFAULT, student.distance), race, False, known=False)
        return StudentPaces("vma", paces, race, False)
    method = method or student.methode
    paces = paces_by_vma(student) if method == "vma" else paces_by_time(student)
    if paces is None:                         # méthode demandée impossible : on prend l'autre
        method = "temps" if method == "vma" else "vma"
        paces = paces_by_vma(student) if method == "vma" else paces_by_time(student)
    if student.objectif:
        race, estimate = parse_objective(student.objectif, student.distance), False
    else:
        race, estimate = race_seconds_from_paces(paces, student.distance), True
    return StudentPaces(method, paces, race, estimate)


def comparison(student) -> list[dict] | None:
    """Tableau de comparaison quand l'objectif ET la VMA sont renseignés, sinon None."""
    if not DISTANCES[student.distance].uses_paces:
        return None
    by_time, by_vma = paces_by_time(student), paces_by_vma(student)
    if by_time is None or by_vma is None:
        return None
    return compare_paces(by_time, by_vma)
