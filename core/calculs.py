"""
Logique de calcul : conversions de temps et calcul des allures.

Module pur (sans Streamlit), testable seul.

Principe, pour une distance donnée :
  1. l'objectif donne la vitesse de l'allure « ancre » (A1 marathon, A2 semi, A3 10 km) ;
  2. les ratios donnent la vitesse de chaque allure relativement à A1
     (Endurance = A1 × 85 %, A2 = A1 × 105 %, A3 = A2 × 105 %…) ;
  3. on en déduit la vitesse de A1 (vitesse ancre ÷ ratio cumulé de l'ancre), puis toutes les autres.
Pour le marathon avec les ratios par défaut, on retrouve exactement les valeurs de l'Excel.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .config import (DEFAULT_RATIOS, DEFAULT_VMA_PCT, DISTANCES, PACE_CODES, PACE_DEFINITIONS, VMA_MAX, VMA_MIN,
                     Distance)

# ----------------------------------------------------------------------------
# Conversions de durées
# ----------------------------------------------------------------------------
_HMS_RE = re.compile(r"^\s*(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?\s*$")
_HMIN_RE = re.compile(r"^\s*(\d{1,2})\s*h\s*(\d{1,2})?\s*(?:m|mn|min|')?\s*(\d{1,2})?\s*(?:s|\")?\s*$",
                      re.IGNORECASE)
_MIN_RE = re.compile(r"^\s*(\d{1,3})\s*(?:'|mn|min|minutes?)\s*(\d{1,2})?\s*(?:\"|s)?\s*$", re.IGNORECASE)


def _missing(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def parse_objective(text: str, distance: Distance | str = "marathon") -> int:
    """Objectif saisi -> secondes. Lève ValueError (message en français) si invalide.

    Formats : « 03:29:00 », « 3:29:00 », « 3h29 », « 3h29'30 », « 45'30 » (10 km),
    « 3:29 » = h:mm pour marathon et semi, mm:ss pour le 10 km (ex. « 45:30 »).
    """
    dist = DISTANCES[distance] if isinstance(distance, str) else distance
    if text is None or not str(text).strip():
        raise ValueError("Saisis un objectif au format hh:mm:ss (ex. 03:29:00).")
    raw = str(text).strip()
    m = _HMS_RE.match(raw)
    if m:
        a, b, c = int(m.group(1)), int(m.group(2)), m.group(3)
        if c is not None:
            h, mnt, s = a, b, int(c)
        elif dist.key == "10k" and a >= 20:      # « 45:30 » sur 10 km = 45 min 30 s
            h, mnt, s = 0, a, b
        else:                                     # « 3:29 » = 3 h 29
            h, mnt, s = a, b, 0
    elif (m := _HMIN_RE.match(raw)):
        h, mnt, s = int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0)
    elif (m := _MIN_RE.match(raw)):
        h, mnt, s = 0, int(m.group(1)), int(m.group(2) or 0)
        h, mnt = divmod(mnt, 60)
    else:
        raise ValueError(f"« {raw} » n'est pas un temps valide. Format attendu : hh:mm:ss (ex. 03:29:00).")
    if mnt >= 60 or s >= 60:
        raise ValueError("Les minutes et les secondes doivent être inférieures à 60.")
    seconds = h * 3600 + mnt * 60 + s
    if not dist.min_seconds <= seconds <= dist.max_seconds:
        raise ValueError(f"Objectif {dist.label.lower()} hors limites : entre {format_hms(dist.min_seconds)} "
                         f"et {format_hms(dist.max_seconds)}.")
    return seconds


def normalize_objective(text: str, distance: str) -> str:
    """Objectif valide -> forme canonique « hh:mm:ss »."""
    return format_hms(parse_objective(text, distance), pad=True)


def parse_duration_minutes(text) -> float | None:
    """Durée approximative d'une séance -> minutes (None si illisible)."""
    if _missing(text):
        return None
    raw = str(text).strip()
    if not raw:
        return None
    if (m := _HMS_RE.match(raw)):
        return int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3) or 0) / 60
    if (m := _HMIN_RE.match(raw)):
        return int(m.group(1)) * 60 + int(m.group(2) or 0) + int(m.group(3) or 0) / 60
    if (m := _MIN_RE.match(raw)):
        return float(m.group(1)) + int(m.group(2) or 0) / 60
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None


def parse_km_range(text) -> tuple[float, float] | None:
    """« 12 » -> (12, 12) ; « 25 à 30 » -> (25, 30)."""
    if _missing(text):
        return None
    numbers = re.findall(r"\d+(?:[.,]\d+)?", str(text))
    if not numbers:
        return None
    values = [float(n.replace(",", ".")) for n in numbers[:2]]
    return (min(values), max(values))


def format_hms(seconds: float, pad: bool = False) -> str:
    """Secondes -> « 3:29:00 » (ou « 03:29:00 » avec pad=True)."""
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if pad else f"{h}:{m:02d}:{s:02d}"


def format_race_time(seconds: float) -> str:
    """Temps de course lisible : « 3h29'00 », « 1h45'00 », « 48'30 »."""
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}'{s:02d}" if h else f"{m}'{s:02d}"


def format_pace(min_per_km: float | None) -> str:
    """Allure décimale -> « 4'57" » (arrondi à la seconde)."""
    if _missing(min_per_km):
        return ""
    total = int(round(min_per_km * 60))
    m, s = divmod(total, 60)
    return f"{m}'{s:02d}\""


def format_minutes(minutes: float | None) -> str:
    """Minutes -> « 20 min » ou « 3h29 »."""
    if _missing(minutes):
        return ""
    total = int(round(minutes))
    if total < 60:
        return f"{total} min"
    h, m = divmod(total, 60)
    return f"{h}h{m:02d}"


def fr_number(x: float, digits: int = 1) -> str:
    return f"{x:.{digits}f}".replace(".", ",")


# ----------------------------------------------------------------------------
# Ratios
# ----------------------------------------------------------------------------
def clean_ratios(ratios: dict | None) -> dict[str, float]:
    """Ratios complets et valides (valeurs par défaut pour les manquants), en %."""
    out = dict(DEFAULT_RATIOS)
    for code, value in (ratios or {}).items():
        if code in out:
            try:
                v = float(str(value).replace(",", "."))
            except (TypeError, ValueError):
                continue
            if 30 <= v <= 300:
                out[code] = round(v, 2)
    return out


def relative_speeds(ratios: dict[str, float]) -> dict[str, float]:
    """Vitesse de chaque allure divisée par la vitesse de A1 (chaîne de ratios)."""
    ratios = clean_ratios(ratios)
    rel = {"A1": 1.0}
    for d in PACE_DEFINITIONS:
        if d.base is not None:
            rel[d.code] = rel[d.base] * ratios[d.code] / 100
    return rel


def ratio_formula(code: str, ratios: dict[str, float]) -> str:
    """Formule lisible, ex. « A3 = A2 × 105 % »."""
    d = next(p for p in PACE_DEFINITIONS if p.code == code)
    if d.base is None:
        return "A1 = allure marathon"
    pct = f"{clean_ratios(ratios)[code]:g}".replace(".", ",")
    return f"{d.code} = {d.base} × {pct} %"


# ----------------------------------------------------------------------------
# Allures
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Pace:
    """Allure calculée. Méthode « temps » : une valeur. Méthode « VMA » : une plage (kmh_min à kmh_max)."""

    code: str
    label: str
    description: str
    kmh: float            # vitesse de référence (bas de plage pour la VMA) — colonne M de l'Excel
    min_per_km: float     # allure correspondante, minutes décimales — colonne N
    ref_km: float | None
    ref_label: str | None
    is_anchor: bool       # allure de course de la distance préparée
    kmh_min: float = 0.0  # plage (VMA) ; égales à kmh pour la méthode « temps »
    kmh_max: float = 0.0

    @property
    def is_range(self) -> bool:
        return self.kmh_max - self.kmh_min > 1e-9

    @property
    def pace_str(self) -> str:
        """« 4'57" » ou, pour une plage, « 4'25"–4'41" » (du plus rapide au plus lent)."""
        if not self.is_range:
            return format_pace(self.min_per_km)
        return f"{format_pace(60 / self.kmh_max)}–{format_pace(60 / self.kmh_min)}"

    @property
    def kmh_str(self) -> str:
        if not self.is_range:
            return f"{fr_number(self.kmh)} km/h"
        return f"{fr_number(self.kmh_min)}–{fr_number(self.kmh_max)} km/h"

    @property
    def ref_time_minutes(self) -> float | None:
        """Temps d'équivalence sur la distance de référence (colonne Q de l'Excel)."""
        return None if self.ref_km is None else self.ref_km * self.min_per_km


def compute_paces(objective_seconds: int, distance: str = "marathon",
                  ratios: dict | None = None) -> dict[str, Pace]:
    """Méthode « objectif de temps » : toutes les allures pour un objectif, avec des ratios donnés."""
    dist = DISTANCES[distance]
    rel = relative_speeds(ratios or {})
    anchor_speed = dist.km / (objective_seconds / 60) * 60          # km/h
    a1_speed = anchor_speed / rel[dist.anchor]
    out = {}
    for d in PACE_DEFINITIONS:
        v = a1_speed * rel[d.code]
        out[d.code] = Pace(code=d.code, label=d.label, description=d.description, kmh=v, min_per_km=60 / v,
                           ref_km=d.ref_km, ref_label=d.ref_label, is_anchor=(d.code == dist.anchor),
                           kmh_min=v, kmh_max=v)
    return out


# ----------------------------------------------------------------------------
# Méthode VMA
# ----------------------------------------------------------------------------
def parse_vma(text) -> float:
    """VMA saisie (« 16 », « 16,5 », « 16.5 km/h ») -> km/h. Lève ValueError si invalide."""
    if text is None or str(text).strip() == "":
        raise ValueError("Saisis une VMA en km/h (ex. 16 ou 16,5).")
    raw = str(text).lower().replace("km/h", "").replace(",", ".").strip()
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"« {text} » n'est pas une VMA valide (ex. 16 ou 16,5).") from None
    if not VMA_MIN <= value <= VMA_MAX:
        raise ValueError(f"VMA hors limites : entre {VMA_MIN:g} et {VMA_MAX:g} km/h.")
    return round(value, 2)


def clean_vma_pct(pct: dict | None) -> dict[str, tuple[float, float]]:
    """Plages de % de VMA complètes et valides (min ≤ max, entre 30 et 140 %)."""
    out = dict(DEFAULT_VMA_PCT)
    for code, value in (pct or {}).items():
        if code not in out:
            continue
        try:
            lo, hi = (value if isinstance(value, (tuple, list)) else (value, value))
            lo, hi = float(str(lo).replace(",", ".")), float(str(hi).replace(",", "."))
        except (TypeError, ValueError):
            continue
        lo, hi = min(lo, hi), max(lo, hi)
        if 30 <= lo and hi <= 140:
            out[code] = (round(lo, 1), round(hi, 1))
    return out


def format_pct_range(lo: float, hi: float) -> str:
    f = lambda x: f"{x:g}".replace(".", ",")  # noqa: E731
    return f"{f(lo)} %" if abs(hi - lo) < 1e-9 else f"{f(lo)}-{f(hi)} %"


def compute_paces_vma(vma_kmh: float, distance: str = "10k", pct: dict | None = None) -> dict[str, Pace]:
    """Méthode « VMA » : vitesse = VMA × % ; chaque allure est une plage (référence = bas de la plage)."""
    dist = DISTANCES[distance]
    pct = clean_vma_pct(pct)
    out = {}
    for d in PACE_DEFINITIONS:
        lo, hi = pct[d.code]
        v_lo, v_hi = vma_kmh * lo / 100, vma_kmh * hi / 100
        # Référence = bas de la plage, comme les formules de l'Excel (M7 = L10 × 80 %).
        out[d.code] = Pace(code=d.code, label=d.label, description=d.description, kmh=v_lo,
                           min_per_km=60 / v_lo, ref_km=d.ref_km, ref_label=d.ref_label,
                           is_anchor=(d.code == dist.anchor), kmh_min=v_lo, kmh_max=v_hi)
    return out


def race_seconds_from_paces(paces: dict[str, Pace], distance: str) -> int:
    """Temps de course estimé : distance × allure de course (valeur de référence)."""
    dist = DISTANCES[distance]
    return int(round(dist.km * paces[dist.anchor].min_per_km * 60))


def compare_paces(by_time: dict[str, Pace], by_vma: dict[str, Pace]) -> list[dict]:
    """Lignes de comparaison objectif / VMA pour chaque allure (écart en secondes par km)."""
    rows = []
    for code in PACE_CODES:
        t, v = by_time[code], by_vma[code]
        diff = round((v.min_per_km - t.min_per_km) * 60)
        rows.append({"code": code, "label": t.label, "temps": t.pace_str, "vma": v.pace_str,
                     "ecart_s": diff, "is_anchor": t.is_anchor})
    return rows
