"""
Suivi de l'élève : séances réalisées, temps réalisé le jour de la course, fréquence choisie.

Ces informations ne sont modifiées QUE par l'élève. Elles sont rangées dans un fichier séparé,
`data/suivi/<id>.xlsx`, que le coach lit sans jamais l'écrire (supervision en lecture seule) :
aucun risque qu'une modification du plan par le coach efface une case cochée par l'élève.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field, replace
from datetime import date, datetime

import pandas as pd

from .calculs import format_race_time
from .config import FREQUENCIES
from .plan import is_race_day
from .stockage import Store, read_workbook, write_workbook

SUIVI_DIR = "suivi"


@dataclass(frozen=True)
class Suivi:
    done: dict = field(default_factory=dict)     # identifiant de séance -> date (AAAA-MM-JJ) de validation
    temps_realise: str = ""                      # « hh:mm:ss »
    frequence: int | None = None                 # 3 ou 4, choisie par l'élève
    maj_le: str = ""

    def with_(self, **changes) -> "Suivi":
        return replace(self, maj_le=datetime.now().strftime("%Y-%m-%d %H:%M"), **changes)


def _file(student_id: str) -> str:
    return f"{SUIVI_DIR}/{student_id}.xlsx"


def parse_race_time(text: str) -> int:
    """Temps réalisé « 3:31:12 », « 44:30 » (mm:ss), « 1h38'20 » -> secondes."""
    raw = str(text or "").strip().replace("h", ":").replace("'", ":").replace('"', "").replace(" ", "")
    parts = [p for p in raw.split(":") if p != ""]
    if not parts or not all(p.isdigit() for p in parts) or len(parts) > 3:
        raise ValueError("Format attendu : hh:mm:ss (ex. 3:31:12) ou mm:ss (ex. 44:30).")
    nums = [int(p) for p in parts]
    if len(nums) == 3:
        h, m, s = nums
    elif len(nums) == 2:
        h, m, s = (0, nums[0], nums[1]) if nums[0] >= 20 else (nums[0], nums[1], 0)
    else:
        h, m, s = 0, nums[0], 0
    if m >= 60 or s >= 60 or not 300 <= h * 3600 + m * 60 + s <= 12 * 3600:
        raise ValueError("Temps invalide (minutes et secondes < 60, entre 5 min et 12 h).")
    return h * 3600 + m * 60 + s


# ----------------------------------------------------------------------------
# Lecture / écriture (avec cache par fichier)
# ----------------------------------------------------------------------------
_cache: dict[str, tuple[tuple[int, int], Suivi]] = {}
_lock = threading.Lock()


def load_suivi(store: Store, student_id: str) -> Suivi:
    rel = _file(student_id)
    if not store.exists(rel):
        return Suivi()
    version = store.version(rel)
    with _lock:
        cached = _cache.get(rel)
    if cached and cached[0] == version:
        return cached[1]
    try:
        sheets = read_workbook(store.read(rel))
    except ValueError:
        return Suivi()
    done = {}
    for _, r in sheets.get("seances", pd.DataFrame()).iterrows():
        if isinstance(r.get("session_id"), str) and r["session_id"]:
            when = r.get("fait_le")
            done[r["session_id"]] = str(when)[:10] if isinstance(when, (str, datetime, date)) else ""
    infos = {str(k): ("" if pd.isna(v) else v) for k, v in
             zip(sheets.get("infos", pd.DataFrame({"cle": [], "valeur": []}))["cle"],
                 sheets.get("infos", pd.DataFrame({"cle": [], "valeur": []}))["valeur"])}
    try:
        freq = int(float(infos.get("frequence"))) if str(infos.get("frequence", "")).strip() else None
    except ValueError:
        freq = None
    suivi = Suivi(done=done, temps_realise=str(infos.get("temps_realise", "")),
                  frequence=freq if freq in FREQUENCIES else None, maj_le=str(infos.get("maj_le", "")))
    with _lock:
        _cache[rel] = (version, suivi)
    return suivi


def save_suivi(store: Store, student_id: str, suivi: Suivi) -> None:
    seances = pd.DataFrame([{"session_id": k, "fait_le": v} for k, v in sorted(suivi.done.items())],
                           columns=["session_id", "fait_le"])
    infos = pd.DataFrame([("temps_realise", suivi.temps_realise), ("frequence", suivi.frequence or ""),
                          ("maj_le", suivi.maj_le)], columns=["cle", "valeur"])
    store.write(_file(student_id), write_workbook({"seances": seances, "infos": infos}))


# ----------------------------------------------------------------------------
# Actions de l'élève
# ----------------------------------------------------------------------------
def set_done(store: Store, student_id: str, session_id: str, done: bool) -> Suivi:
    suivi = load_suivi(store, student_id)
    marks = dict(suivi.done)
    if done:
        marks[session_id] = date.today().isoformat()
    else:
        marks.pop(session_id, None)
    updated = suivi.with_(done=marks)
    save_suivi(store, student_id, updated)
    return updated


def set_race_time(store: Store, student_id: str, text: str) -> Suivi:
    """Enregistre le temps réalisé (texte vide = effacer). Lève ValueError si le format est invalide."""
    value = format_race_time_hms(parse_race_time(text)) if str(text or "").strip() else ""
    updated = load_suivi(store, student_id).with_(temps_realise=value)
    save_suivi(store, student_id, updated)
    return updated


def set_frequency(store: Store, student_id: str, frequency: int) -> Suivi:
    updated = load_suivi(store, student_id).with_(frequence=frequency if frequency in FREQUENCIES else None)
    save_suivi(store, student_id, updated)
    return updated


def format_race_time_hms(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


# ----------------------------------------------------------------------------
# Synthèse (supervision)
# ----------------------------------------------------------------------------
def effective_frequency(student, suivi: Suivi) -> int:
    """Fréquence affichée : choix de l'élève, sinon ancien choix enregistré, sinon celle du coach."""
    return suivi.frequence or student.frequence_eleve or student.frequence_defaut


def is_done(row, suivi: Suivi) -> bool:
    """Une séance est réalisée si l'élève l'a cochée ; le JOUR J, si le temps réalisé est saisi."""
    if is_race_day(row["seance"]):
        return bool(suivi.temps_realise) or row["session_id"] in suivi.done
    return row["session_id"] in suivi.done


@dataclass(frozen=True)
class Progress:
    done: int
    total: int
    last_date: str          # dernière séance cochée (AAAA-MM-JJ)
    race_time: str          # temps réalisé, lisible
    race_gap: str           # écart à l'objectif, ex. « +1'12 » / « −0'45 »

    @property
    def ratio(self) -> float:
        return self.done / self.total if self.total else 0.0


def progress(table: pd.DataFrame, suivi: Suivi, objective_seconds: int | None) -> Progress:
    """Séances réalisées parmi celles affichées à l'élève (selon sa fréquence)."""
    done = sum(1 for _, r in table.iterrows() if is_done(r, suivi)) if not table.empty else 0
    shown = set(table["session_id"]) if not table.empty else set()
    dates = [d for sid, d in suivi.done.items() if sid in shown and d]
    race_time, gap = "", ""
    if suivi.temps_realise:
        try:
            secs = parse_race_time(suivi.temps_realise)
            race_time = format_race_time(secs)
            if objective_seconds:
                diff = secs - objective_seconds
                m, s = divmod(abs(diff), 60)
                gap = f"{'+' if diff > 0 else '−' if diff < 0 else ''}{m}'{s:02d}"
        except ValueError:
            race_time = suivi.temps_realise
    return Progress(done, len(table), max(dates) if dates else "", race_time, gap)
