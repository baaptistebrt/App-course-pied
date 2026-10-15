"""
Modèle d'un plan d'entraînement (semaines + séances) et opérations de structure.

Un `Plan` ne stocke que ce que saisit le coach. Allures, dates et temps spécifiques sont
recalculés à l'affichage (objectif, ratios et date de course de l'élève).
Toutes les opérations renvoient un NOUVEAU Plan (aucune mutation en place).
"""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from .calculs import Pace, format_hms, format_minutes, parse_duration_minutes, parse_km_range
from .config import (DAYS, FREQ_ALWAYS, FREQ_ONLY_4, PACE_CODES, PACE_LABELS, RACE_DAY_LABEL,
                     SESSION_COLUMNS, SESSION_INPUT_COLUMNS, SESSION_TEXT_COLUMNS, SKELETON_WEEK, WEEK_COLUMNS)


# ----------------------------------------------------------------------------
# Normalisation des valeurs saisies
# ----------------------------------------------------------------------------
def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def is_missing(value) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def clean_text(value) -> str:
    if is_missing(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def clean_number(value) -> float:
    if is_missing(value) or (isinstance(value, str) and not value.strip()):
        return math.nan
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return math.nan


def clean_pace_code(value) -> str | None:
    """Un code d'allure valide (Endurance, A1…) ou None. Tolère casse et libellés longs."""
    if is_missing(value):
        return None
    raw = str(value).strip()
    if not raw:
        return None
    for code in PACE_CODES:
        if raw.lower() in (code.lower(), PACE_LABELS[code].lower()):
            return code
    if (m := re.match(r"^\s*(?:a|allure\s*)([1-4])\b", raw, re.IGNORECASE)):
        return f"A{m.group(1)}"
    if raw.lower().startswith("end"):
        return "Endurance"
    if raw.lower().startswith("sprint"):
        return "Sprint"
    return None


def pace_codes(value) -> list[str]:
    """Liste de codes d'allure : « A1,A3 », « A1 A2 », « A1 à A2 », ["A1", "A3"], « sprint »…"""
    if hasattr(value, "tolist") and not isinstance(value, str):      # tableau numpy (éditeur)
        value = value.tolist()
    if isinstance(value, (list, tuple)):
        items = list(value)
    elif is_missing(value):
        return []
    else:
        items = re.split(r"[,;/+\s]+|\bà\b", str(value))
    out = []
    for item in items:
        code = clean_pace_code(item)
        if code and code not in out:
            out.append(code)
    return out


def clean_pace_codes(value) -> str | None:
    """Forme stockée : codes séparés par des virgules (« A1,A3 »), ou None."""
    codes = pace_codes(value)
    return ",".join(codes) if codes else None


def clean_day(value) -> str:
    raw = clean_text(value).lower()[:3]
    return raw if raw in DAYS else ""


def clean_frequency(value) -> str:
    raw = clean_text(value).lower()
    return FREQ_ONLY_4 if raw in ("4", "4.0", "si 4 séances", "4 seulement") else FREQ_ALWAYS


def clean_sessions(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise un tableau de séances. Idempotente. Numérote « sN » les séances sans libellé."""
    src = df.reset_index(drop=True)
    out = pd.DataFrame(index=range(len(src)))
    for col in SESSION_INPUT_COLUMNS:
        values = list(src[col]) if col in src.columns else [None] * len(src)
        if col in SESSION_TEXT_COLUMNS:
            out[col] = pd.Series([clean_text(v) for v in values], dtype=object)
        elif col == "km_spe":
            out[col] = pd.Series([clean_number(v) for v in values], dtype="float64")
        elif col == "allure":
            out[col] = pd.Series([clean_pace_codes(v) for v in values], dtype=object)
        elif col == "frequence":
            out[col] = pd.Series([clean_frequency(v) for v in values], dtype=object)
        elif col == "jour":
            out[col] = pd.Series([clean_day(v) for v in values], dtype=object)
    # Identifiant stable : conservé s'il existe, créé pour une nouvelle séance.
    out["session_id"] = [sid or _new_id() for sid in out["session_id"]]
    numbers = [int(m.group(1)) for v in out["seance"] if (m := re.fullmatch(r"[sS](\d+)", v))]
    next_n = max(numbers, default=0) + 1
    for i in out.index:
        if not out.at[i, "seance"]:
            out.at[i, "seance"] = f"s{next_n}"
            next_n += 1
    return out


def sessions_equal(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    ca, cb = clean_sessions(a), clean_sessions(b)
    if len(ca) != len(cb):
        return False
    rec = lambda d: [tuple(None if is_missing(v) else v for v in row)  # noqa: E731
                     for row in d[SESSION_INPUT_COLUMNS].itertuples(index=False)]
    return rec(ca) == rec(cb)


def is_race_day(seance) -> bool:
    return clean_text(seance).upper().replace(" ", "") == RACE_DAY_LABEL.replace(" ", "")


def is_empty_session(row) -> bool:
    """Séance sans aucun contenu (ni km, ni durée, ni contenu, ni allure)."""
    return not any([clean_text(row.get("km_env")), clean_text(row.get("duree_env")),
                    clean_text(row.get("contenu")), pace_codes(row.get("allure")),
                    not is_missing(row.get("km_spe")), clean_text(row.get("temps_spe"))])


# ----------------------------------------------------------------------------
# Plan
# ----------------------------------------------------------------------------
@dataclass
class Plan:
    weeks: pd.DataFrame
    sessions: pd.DataFrame

    @classmethod
    def empty(cls) -> "Plan":
        return cls(pd.DataFrame(columns=WEEK_COLUMNS), pd.DataFrame(columns=SESSION_COLUMNS))

    @classmethod
    def from_week_list(cls, weeks: list[dict]) -> "Plan":
        """[{phase, sessions: [...]}, …] (ordre chronologique) -> Plan."""
        week_rows, frames = [], []
        for pos, w in enumerate(weeks):
            wid = _new_id()
            week_rows.append({"week_id": wid, "position": pos, "phase": w.get("phase", "")})
            sess = clean_sessions(pd.DataFrame(w.get("sessions", []), columns=SESSION_INPUT_COLUMNS))
            sess.insert(0, "week_id", wid)
            sess.insert(1, "ordre", range(len(sess)))
            frames.append(sess)
        sessions = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=SESSION_COLUMNS)
        return cls(pd.DataFrame(week_rows, columns=WEEK_COLUMNS), sessions).normalized()

    def copy_with_new_ids(self) -> "Plan":
        """Copie indépendante (nouveaux identifiants de semaines), ex. modèle -> plan d'élève."""
        mapping = {wid: _new_id() for wid in self.weeks["week_id"]}
        weeks = self.weeks.copy()
        weeks["week_id"] = weeks["week_id"].map(mapping)
        sessions = self.sessions.copy()
        sessions["week_id"] = sessions["week_id"].map(mapping)
        sessions["session_id"] = [_new_id() for _ in range(len(sessions))]
        return Plan(weeks, sessions).normalized()

    def normalized(self) -> "Plan":
        weeks = self.weeks.copy() if len(self.weeks.columns) else pd.DataFrame(columns=WEEK_COLUMNS)
        for col in WEEK_COLUMNS:
            if col not in weeks.columns:
                weeks[col] = None
        weeks["phase"] = [clean_text(v) for v in weeks["phase"]]
        weeks["week_id"] = weeks["week_id"].astype(str)
        weeks["position"] = pd.to_numeric(weeks["position"], errors="coerce").fillna(0)
        weeks = weeks.sort_values("position", kind="stable").reset_index(drop=True)
        weeks["position"] = range(len(weeks))
        weeks = weeks[WEEK_COLUMNS]

        sessions = self.sessions.copy()
        if len(sessions):
            sessions["week_id"] = sessions["week_id"].astype(str)
        frames = []
        for wid in weeks["week_id"]:
            sub = sessions[sessions["week_id"] == wid] if len(sessions) else sessions
            if "ordre" in sub.columns and len(sub):
                sub = sub.assign(_o=pd.to_numeric(sub["ordre"], errors="coerce")).sort_values("_o", kind="stable")
            sub = clean_sessions(sub)
            sub.insert(0, "week_id", wid)
            sub.insert(1, "ordre", range(len(sub)))
            frames.append(sub)
        sessions = pd.concat(frames, ignore_index=True) if frames else clean_sessions(pd.DataFrame())
        if "week_id" not in sessions.columns:
            sessions.insert(0, "week_id", pd.Series(dtype=object))
            sessions.insert(1, "ordre", pd.Series(dtype=int))
        sessions["km_spe"] = sessions["km_spe"].astype("float64")
        return Plan(weeks, sessions[SESSION_COLUMNS].reset_index(drop=True))

    # ---- lecture -------------------------------------------------------------
    @property
    def n_weeks(self) -> int:
        return len(self.weeks)

    @staticmethod
    def week_label(position: int) -> str:
        """S1, S2… (la dernière semaine est celle de la course)."""
        return f"S{position + 1}"

    def week_start(self, position: int, race_date: date | None) -> date | None:
        """Lundi de la semaine : lundi de la semaine de course − 7 j par semaine d'écart."""
        if race_date is None:
            return None
        race_monday = race_date - timedelta(days=race_date.weekday())
        return race_monday - timedelta(weeks=self.n_weeks - 1 - position)

    def week_position(self, week_id: str) -> int:
        return int(self.weeks.loc[self.weeks["week_id"] == week_id, "position"].iloc[0])

    def sessions_of(self, week_id: str) -> pd.DataFrame:
        sub = self.sessions[self.sessions["week_id"] == week_id].sort_values("ordre")
        return sub[SESSION_INPUT_COLUMNS].reset_index(drop=True)

    # ---- modifications ---------------------------------------------------------
    def replace_week_sessions(self, week_id: str, new_sessions: pd.DataFrame) -> "Plan":
        sub = clean_sessions(new_sessions)
        sub.insert(0, "week_id", week_id)
        sub.insert(1, "ordre", range(len(sub)))
        others = self.sessions[self.sessions["week_id"] != week_id]
        frames = [f for f in (others, sub) if len(f)]
        sessions = pd.concat(frames, ignore_index=True) if frames else sub
        return Plan(self.weeks.copy(), sessions).normalized()

    def set_phase(self, week_id: str, phase: str) -> "Plan":
        weeks = self.weeks.copy()
        weeks.loc[weeks["week_id"] == week_id, "phase"] = clean_text(phase)
        return Plan(weeks, self.sessions.copy()).normalized()

    def insert_week(self, position: int, sessions=None, phase: str = "") -> "Plan":
        """Insère une semaine (squelette de 3 séances par défaut) à `position`."""
        position = max(0, min(position, self.n_weeks))
        wid = _new_id()
        weeks = self.weeks.copy()
        weeks.loc[weeks["position"] >= position, "position"] += 1
        weeks = pd.concat([weeks, pd.DataFrame([{"week_id": wid, "position": position, "phase": phase}])],
                          ignore_index=True)
        sub = clean_sessions(sessions if isinstance(sessions, pd.DataFrame)
                             else pd.DataFrame(sessions if sessions is not None else SKELETON_WEEK))
        sub["session_id"] = [_new_id() for _ in range(len(sub))]
        sub.insert(0, "week_id", wid)
        sub.insert(1, "ordre", range(len(sub)))
        frames = [f for f in (self.sessions, sub) if len(f)]
        return Plan(weeks, pd.concat(frames, ignore_index=True) if frames else sub).normalized()

    def duplicate_week(self, week_id: str) -> "Plan":
        """Copie de la semaine insérée juste avant elle."""
        pos = self.week_position(week_id)
        phase = self.weeks.loc[self.weeks["week_id"] == week_id, "phase"].iloc[0]
        return self.insert_week(pos, self.sessions_of(week_id), phase)

    def delete_week(self, week_id: str) -> "Plan":
        if self.n_weeks <= 1:
            raise ValueError("Le plan doit contenir au moins une semaine.")
        return Plan(self.weeks[self.weeks["week_id"] != week_id].copy(),
                    self.sessions[self.sessions["week_id"] != week_id].copy()).normalized()

    def resize(self, n_weeks: int) -> "Plan":
        """Ajuste la durée en gardant la fin du plan (affûtage + course) : ajoute/retire au début."""
        if n_weeks < 1:
            raise ValueError("Le plan doit contenir au moins une semaine.")
        plan = self
        while plan.n_weeks < n_weeks:
            plan = plan.insert_week(0)
        while plan.n_weeks > n_weeks:
            plan = plan.delete_week(plan.weeks.sort_values("position")["week_id"].iloc[0])
        return plan


# ----------------------------------------------------------------------------
# Tableaux calculés
# ----------------------------------------------------------------------------
def computed_columns(sessions: pd.DataFrame, paces: dict[str, Pace], objective_seconds: int) -> pd.DataFrame:
    """Ajoute allure(s), vitesse et temps spécifique ; durée du JOUR J = objectif (E11 = D4).

    * allure_txt : allure de chaque code (« 4'57" » ou « 4'25"–4'41" / 4'10"–4'25" ») ;
    * temps_spe_min : km spécifiques × 1re allure (colonne H du marathon : =F9*G9) ;
    * temps_aff : temps spécifique saisi s'il existe (plan 10 km), sinon le temps calculé.
    """
    out = sessions.copy().reset_index(drop=True)
    codes = [pace_codes(v) for v in out["allure"]]
    first = [paces.get(c[0]) if c else None for c in codes]
    out["allure_txt"] = [" / ".join(paces[c].pace_str for c in cs if c in paces) for cs in codes]
    out["allure_dec"] = [round(p.min_per_km, 2) if p else math.nan for p in first]
    out["vitesse"] = [round(p.kmh, 1) if p else math.nan for p in first]
    temps = [km * p.min_per_km if (p is not None and not is_missing(km)) else math.nan
             for p, km in zip(first, out["km_spe"])]
    out["temps_spe_min"] = temps
    saisi = out["temps_spe"] if "temps_spe" in out.columns else [""] * len(out)
    out["temps_aff"] = [clean_text(t) or (format_minutes(m) if not is_missing(m) else "")
                        for t, m in zip(saisi, temps)]
    out["duree_env"] = [format_hms(objective_seconds) if is_race_day(s) and not clean_text(d) else d
                        for s, d in zip(out["seance"], out["duree_env"])]
    return out


def session_date(week_start: date | None, jour: str, seance: str, race_date: date | None) -> date | None:
    """Date réelle d'une séance : jour de course pour le JOUR J, sinon lundi de la semaine + jour choisi."""
    if is_race_day(seance) and race_date:
        return race_date
    if week_start and jour in DAYS:
        return week_start + timedelta(days=DAYS.index(jour))
    return None


def select_sessions(sub: pd.DataFrame, n: int) -> pd.DataFrame:
    """Les `n` séances gardées quand l'élève réduit SA semaine (les autres sont seulement masquées).

    Priorité : le jour de course, puis la première et la dernière séance de la semaine, puis les
    séances du milieu (celles marquées « toujours » avant celles « si 4 séances », puis dans l'ordre).
    L'ordre d'origine est conservé ; rien n'est modifié dans le plan."""
    if n >= len(sub):
        return sub
    idx = list(range(len(sub)))
    race = [i for i in idx if is_race_day(sub.iloc[i]["seance"])]
    middle = sorted(idx[1:-1], key=lambda i: (sub.iloc[i]["frequence"] == FREQ_ONLY_4, i))
    keep: list[int] = []
    for i in [*race, idx[0], idx[-1], *middle]:
        if i not in keep:
            keep.append(i)
    return sub.iloc[sorted(keep[:max(n, 0)])]


def full_plan_table(plan: Plan, paces: dict[str, Pace], objective_seconds: int,
                    race_date: date | None = None, frequency: int | None = None,
                    hide_empty: bool = False, week_counts: dict | None = None) -> pd.DataFrame:
    """Plan complet (ordre chronologique) avec colonnes calculées.

    frequency=3 retire les séances marquées « 4 » ; hide_empty retire les séances vides.
    week_counts {week_id: n} : nombre de séances choisi par l'élève pour une semaine précise ; il
    remplace la fréquence pour cette semaine seulement (voir select_sessions).
    """
    frames = []
    for _, w in plan.weeks.sort_values("position").iterrows():
        pos = int(w["position"])
        sub = plan.sessions_of(w["week_id"])
        if hide_empty:
            sub = sub[[not is_empty_session(r) for _, r in sub.iterrows()]]
        n = (week_counts or {}).get(w["week_id"])
        if n:
            sub = select_sessions(sub.reset_index(drop=True), int(n))
        elif frequency == 3:
            sub = sub[sub["frequence"] != FREQ_ONLY_4]
        sub = computed_columns(sub, paces, objective_seconds)
        start = plan.week_start(pos, race_date)
        sub["date"] = [session_date(start, j, se, race_date) for j, se in zip(sub["jour"], sub["seance"])]
        sub.insert(0, "week_id", w["week_id"])
        sub.insert(1, "position", pos)
        sub.insert(2, "semaine", Plan.week_label(pos))
        sub.insert(3, "debut", start)
        sub.insert(4, "fin", start + timedelta(days=6) if start else None)
        sub.insert(5, "phase", w["phase"])
        frames.append(sub)
    frames = [f for f in frames if len(f)]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


ACTIVITY_LABELS = {"course": "Course", "fractionne": "Fractionné", "seuil": "Seuil", "progressif": "Progressif",
                   "allure": "Allure spécifique", "longue": "Sortie longue", "footing": "Footing"}


def activity_kind(row) -> str:
    """Type d'activité d'une séance, déduit de son libellé, de ses allures et de son contenu."""
    if is_race_day(row["seance"]):
        return "course"
    codes = pace_codes(row.get("allure"))
    text = clean_text(row.get("contenu")).lower()
    km = parse_km_range(row.get("km_env"))
    long_run = km is not None and km[0] >= 15
    if "progressi" in text:
        return "progressif"
    if "Sprint" in codes or "A4" in codes or re.search(r"\d+\s*x\s*\(?\d", text):
        return "fractionne"
    if "A3" in codes:
        return "seuil"
    if long_run:
        return "longue"
    if "A1" in codes or "A2" in codes:
        return "allure"
    return "footing"


@dataclass(frozen=True)
class WeekSummary:
    km_min: float
    km_max: float
    minutes: float
    n_sessions: int

    @property
    def km_str(self) -> str:
        if self.km_max <= 0:
            return ""
        fmt = lambda x: f"{x:.1f}".rstrip("0").rstrip(".").replace(".", ",")  # noqa: E731
        if abs(self.km_max - self.km_min) < 0.05:
            return f"{fmt(self.km_min)} km"
        return f"{fmt(self.km_min)} à {fmt(self.km_max)} km"

    @property
    def duration_str(self) -> str:
        return format_minutes(self.minutes) if self.minutes > 0 else ""


def week_summary(computed: pd.DataFrame) -> WeekSummary:
    km_min = km_max = minutes = 0.0
    for km, dur in zip(computed.get("km_env", []), computed.get("duree_env", [])):
        if (rng := parse_km_range(km)):
            km_min += rng[0]
            km_max += rng[1]
        if (m := parse_duration_minutes(dur)):
            minutes += m
    return WeekSummary(km_min, km_max, minutes, len(computed))


def weeks_until(race_date: date, today: date | None = None) -> int:
    """Nombre de semaines de plan possibles d'ici la course (semaine en cours et semaine de course incluses)."""
    today = today or date.today()
    race_monday = race_date - timedelta(days=race_date.weekday())
    this_monday = today - timedelta(days=today.weekday())
    return (race_monday - this_monday).days // 7 + 1
