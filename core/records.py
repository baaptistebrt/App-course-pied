"""
Records personnels de l'élève : son meilleur temps sur chaque distance, tiré de ses courses terminées
(tous ses programmes). Rien n'est stocké : tout est recalculé à partir de l'historique.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .calculs import format_race_time
from .config import DISTANCES


@dataclass(frozen=True)
class PersonalRecord:
    distance: str
    seconds: int
    course: str
    race_date: date | None
    previous: int | None        # record précédent sur la distance (secondes), None si première course
    count: int                  # nombre de courses chronométrées sur la distance

    @property
    def label(self) -> str:
        return DISTANCES[self.distance].label

    @property
    def time_str(self) -> str:
        return format_race_time(self.seconds)

    @property
    def pace_str(self) -> str:
        per_km = self.seconds / DISTANCES[self.distance].km
        m, s = divmod(round(per_km), 60)
        return f"{m}'{s:02d}\" /km"

    @property
    def improvement(self) -> str:
        """« −1'12 sur ton ancien record » (vide si première course)."""
        if self.previous is None or self.previous <= self.seconds:
            return ""
        m, s = divmod(self.previous - self.seconds, 60)
        return f"−{m}'{s:02d} sur ton ancien record" if m else f"−{s} s sur ton ancien record"


def personal_records(records: list) -> list[PersonalRecord]:
    """Meilleur temps par distance (ordre : 10 km, semi, marathon)."""
    out = []
    for dist in DISTANCES:
        timed = sorted((r for r in records if r.distance == dist and r.race_seconds),
                       key=lambda r: (r.race_date or date.min))
        if not timed:
            continue
        best = min(timed, key=lambda r: r.race_seconds)
        before = [r.race_seconds for r in timed if (r.race_date or date.min) < (best.race_date or date.min)]
        out.append(PersonalRecord(dist, best.race_seconds, best.course, best.race_date,
                                  min(before) if before else None, len(timed)))
    order = ["10k", "semi", "marathon"]
    return sorted(out, key=lambda p: order.index(p.distance) if p.distance in order else 9)


def is_record(records: list, student_id: str) -> PersonalRecord | None:
    """Le programme `student_id` détient-il le record de sa distance ? (et ce n'est pas sa seule course)"""
    current = next((r for r in records if r.student_id == student_id and r.race_seconds), None)
    if current is None:
        return None
    for pr in personal_records(records):
        if pr.distance == current.distance and pr.seconds == current.race_seconds and pr.count > 1:
            return pr
    return None
