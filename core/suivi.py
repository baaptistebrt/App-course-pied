"""
Suivi de l'élève : séances réalisées, ressenti et commentaire de chaque séance (course comprise),
temps réalisé le jour de la course, fréquence choisie.

Ces informations ne sont modifiées QUE par l'élève. Elles sont rangées dans un fichier séparé,
`data/suivi/<id>.xlsx`, que le coach lit sans jamais l'écrire (supervision en lecture seule) :
aucun risque qu'une modification du plan par le coach efface une case cochée ou un commentaire.

Onglet « seances » : une ligne par séance cochée ou commentée
    session_id, fait (1/0), fait_le (AAAA-MM-JJ), ressenti (1 à 5), commentaire, note_le
Onglet « infos » : temps_realise, frequence, maj_le
Onglet « semaines » : week_id, seances (nombre de séances choisi par l'élève pour cette semaine)
Les fichiers d'avant les ressentis n'ont que session_id et fait_le : toutes leurs lignes sont des
séances réalisées.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta

import pandas as pd

from .calculs import format_race_time, parse_km_range
from .config import COMMENT_MAX, FEELINGS, FREQUENCIES, WEEK_COUNTS
from .plan import is_race_day
from .stockage import Store, read_workbook, write_workbook

SUIVI_DIR = "suivi"


@dataclass(frozen=True)
class Note:
    """Ressenti de l'élève sur une séance (ou sur la course)."""

    ressenti: int | None = None     # 1 (très dur) à 5 (excellent)
    commentaire: str = ""
    le: str = ""                    # AAAA-MM-JJ HH:MM, dernière modification

    @property
    def empty(self) -> bool:
        return self.ressenti is None and not self.commentaire.strip()

    @property
    def emoji(self) -> str:
        return FEELINGS[self.ressenti][0] if self.ressenti in FEELINGS else ""

    @property
    def label(self) -> str:
        return " ".join(FEELINGS[self.ressenti]) if self.ressenti in FEELINGS else ""


@dataclass(frozen=True)
class Suivi:
    done: dict = field(default_factory=dict)     # identifiant de séance -> date (AAAA-MM-JJ) de validation
    temps_realise: str = ""                      # « hh:mm:ss »
    frequence: int | None = None                 # 3 ou 4, choisie par l'élève
    maj_le: str = ""
    notes: dict = field(default_factory=dict)    # identifiant de séance -> Note
    semaines: dict = field(default_factory=dict) # identifiant de semaine -> nombre de séances choisi (2 à 4)

    def with_(self, **changes) -> "Suivi":
        return replace(self, maj_le=_now(), **changes)

    def note(self, session_id: str) -> Note:
        return self.notes.get(session_id, Note())


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


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


def clean_feeling(value) -> int | None:
    try:
        v = int(float(value))
    except (TypeError, ValueError):
        return None
    return v if v in FEELINGS else None


def _text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _truthy(value) -> bool:
    return _text(value).lower() in ("1", "1.0", "true", "vrai", "oui", "x")


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
    rows = sheets.get("seances", pd.DataFrame())
    has_flag = "fait" in rows.columns
    done, notes = {}, {}
    for _, r in rows.iterrows():
        sid = r.get("session_id")
        if not isinstance(sid, str) or not sid:
            continue
        if not has_flag or _truthy(r.get("fait")):
            when = r.get("fait_le")
            done[sid] = str(when)[:10] if isinstance(when, (str, datetime, date)) else ""
        note = Note(clean_feeling(r.get("ressenti")), _text(r.get("commentaire"))[:COMMENT_MAX], _text(r.get("note_le")))
        if not note.empty:
            notes[sid] = note
    info_df = sheets.get("infos", pd.DataFrame({"cle": [], "valeur": []}))
    infos = {str(k): ("" if pd.isna(v) else v) for k, v in zip(info_df["cle"], info_df["valeur"])}
    try:
        freq = int(float(infos.get("frequence"))) if str(infos.get("frequence", "")).strip() else None
    except ValueError:
        freq = None
    weeks = {}
    for _, r in sheets.get("semaines", pd.DataFrame()).iterrows():
        try:
            n = int(float(r.get("seances")))
        except (TypeError, ValueError):
            continue
        if isinstance(r.get("week_id"), str) and n in WEEK_COUNTS:
            weeks[r["week_id"]] = n
    suivi = Suivi(done=done, temps_realise=str(infos.get("temps_realise", "")),
                  frequence=freq if freq in FREQUENCIES else None, maj_le=str(infos.get("maj_le", "")),
                  notes=notes, semaines=weeks)
    with _lock:
        _cache[rel] = (version, suivi)
    return suivi


def save_suivi(store: Store, student_id: str, suivi: Suivi) -> None:
    ids = sorted(set(suivi.done) | set(suivi.notes))
    seances = pd.DataFrame([{
        "session_id": sid, "fait": 1 if sid in suivi.done else 0, "fait_le": suivi.done.get(sid, ""),
        "ressenti": suivi.note(sid).ressenti or "", "commentaire": suivi.note(sid).commentaire,
        "note_le": suivi.note(sid).le,
    } for sid in ids], columns=["session_id", "fait", "fait_le", "ressenti", "commentaire", "note_le"])
    infos = pd.DataFrame([("temps_realise", suivi.temps_realise), ("frequence", suivi.frequence or ""),
                          ("maj_le", suivi.maj_le)], columns=["cle", "valeur"])
    semaines = pd.DataFrame([{"week_id": k, "seances": v} for k, v in sorted(suivi.semaines.items())],
                            columns=["week_id", "seances"])
    store.write(_file(student_id), write_workbook({"seances": seances, "infos": infos, "semaines": semaines}))


# ----------------------------------------------------------------------------
# Actions de l'élève
# ----------------------------------------------------------------------------
def set_done(store: Store, student_id: str, session_id: str, done: bool) -> Suivi:
    """Coche / décoche une séance. Décocher garde le ressenti et le commentaire."""
    suivi = load_suivi(store, student_id)
    marks = dict(suivi.done)
    if done:
        marks[session_id] = date.today().isoformat()
    else:
        marks.pop(session_id, None)
    updated = suivi.with_(done=marks)
    save_suivi(store, student_id, updated)
    return updated


def set_note(store: Store, student_id: str, session_id: str, ressenti, commentaire: str) -> Suivi:
    """Enregistre le ressenti (1 à 5, ou None) et le commentaire d'une séance ; vides = effacés."""
    suivi = load_suivi(store, student_id)
    notes = dict(suivi.notes)
    note = Note(clean_feeling(ressenti), str(commentaire or "").strip()[:COMMENT_MAX], _now())
    if note.empty:
        notes.pop(session_id, None)
    else:
        notes[session_id] = note
    updated = suivi.with_(notes=notes)
    save_suivi(store, student_id, updated)
    return updated


def set_race_time(store: Store, student_id: str, text: str) -> Suivi:
    """Enregistre le temps réalisé (texte vide = effacer). Lève ValueError si le format est invalide."""
    value = format_race_time_hms(parse_race_time(text)) if str(text or "").strip() else ""
    updated = load_suivi(store, student_id).with_(temps_realise=value)
    save_suivi(store, student_id, updated)
    return updated


def set_week_count(store: Store, student_id: str, week_id: str, count: int | None) -> Suivi:
    """Nombre de séances choisi pour UNE semaine (2, 3 ou 4) ; None revient au plan prévu.
    Les séances retirées sont seulement masquées : elles réapparaissent intactes si on en remet."""
    suivi = load_suivi(store, student_id)
    weeks = dict(suivi.semaines)
    if count in WEEK_COUNTS:
        weeks[week_id] = int(count)
    else:
        weeks.pop(week_id, None)
    updated = suivi.with_(semaines=weeks)
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
# Synthèse (espace élève et supervision)
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
    km_done: float = 0.0    # kilomètres des séances réalisées (bas de fourchette)

    @property
    def ratio(self) -> float:
        return self.done / self.total if self.total else 0.0


def _km(value) -> float:
    rng = parse_km_range(value)
    return rng[0] if rng else 0.0


def progress(table: pd.DataFrame, suivi: Suivi, objective_seconds: int | None) -> Progress:
    """Séances réalisées parmi celles affichées à l'élève (selon sa fréquence)."""
    flags = [is_done(r, suivi) for _, r in table.iterrows()] if not table.empty else []
    km = sum(_km(r["km_env"]) for (_, r), ok in zip(table.iterrows(), flags) if ok) if flags else 0.0
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
    return Progress(sum(flags), len(table), max(dates) if dates else "", race_time, gap, km)


def ordered(table: pd.DataFrame) -> pd.DataFrame:
    """Séances dans l'ordre du plan (semaine, puis ordre choisi par le coach dans la semaine)."""
    if table.empty:
        return table
    return table.sort_values("position", kind="stable")


def next_session(table: pd.DataFrame, suivi: Suivi, today: date | None = None):
    """Prochaine séance à faire (ligne du tableau) ou None si tout est fait.

    Avec des dates : première séance non réalisée de la semaine en cours ou des suivantes (les
    séances oubliées des semaines passées ne bloquent pas). Sans dates : première non réalisée."""
    if table.empty:
        return None
    today = today or date.today()
    rows = ordered(table)
    dated = any(isinstance(d, date) for d in rows["debut"])
    for _, r in rows.iterrows():
        if is_done(r, suivi):
            continue
        if dated and isinstance(r["fin"], date) and r["fin"] < today:
            continue
        return r
    return None


def pending_feedback(table: pd.DataFrame, suivi: Suivi, today: date | None = None, days: int = 7):
    """Dernière séance réalisée (moins de `days` jours) sans ressenti ni commentaire, ou None."""
    if table.empty:
        return None
    today = today or date.today()
    best = None
    for _, r in table.iterrows():
        sid = r["session_id"]
        when = suivi.done.get(sid, "")
        if not when or is_race_day(r["seance"]) or not suivi.note(sid).empty:
            continue
        try:
            d = date.fromisoformat(when)
        except ValueError:
            continue
        if today - d <= timedelta(days=days) and (best is None or d >= best[0]):
            best = (d, r)
    return best[1] if best else None


def journal(table: pd.DataFrame, suivi: Suivi) -> list[dict]:
    """Carnet : séances réalisées ou commentées, de la plus récente à la plus ancienne."""
    out = []
    for _, r in table.iterrows():
        sid = r["session_id"]
        note = suivi.note(sid)
        race = is_race_day(r["seance"])
        done = is_done(r, suivi)
        if not done and note.empty:
            continue
        when = suivi.done.get(sid, "") or (note.le[:10] if note.le else "")
        if race and isinstance(r.get("date"), date):
            when = r["date"].isoformat()
        out.append({"row": r, "note": note, "when": when, "race": race, "done": done})
    out.sort(key=lambda x: (x["when"] or "", x["row"]["position"]), reverse=True)
    return out


def last_note(table: pd.DataFrame, suivi: Suivi) -> tuple[pd.Series, Note] | None:
    """Ressenti le plus récent (pour la supervision du coach)."""
    shown = {r["session_id"]: r for _, r in table.iterrows()} if not table.empty else {}
    notes = [(n.le, sid, n) for sid, n in suivi.notes.items() if sid in shown]
    if not notes:
        return None
    _, sid, note = max(notes)
    return shown[sid], note
