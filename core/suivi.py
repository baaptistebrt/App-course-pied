"""
Suivi de l'élève : séances réalisées, ressenti et commentaire de chaque séance (course comprise),
temps réalisé le jour de la course, fréquence choisie.

Ces informations ne sont modifiées QUE par l'élève. Elles sont rangées dans un fichier séparé,
`data/suivi/<id>.xlsx`, que le coach lit sans jamais l'écrire (supervision en lecture seule) :
aucun risque qu'une modification du plan par le coach efface une case cochée ou un commentaire.

Onglet « seances » : une ligne par séance cochée, commentée ou marquée « pas faite »
    session_id, fait (1/0), fait_le (AAAA-MM-JJ), ressenti (1 à 5), commentaire, note_le,
    pas_faite_le (AAAA-MM-JJ, séance marquée « pas faite »), raison, km_reels (km réellement courus)
Onglet « infos » : temps_realise, frequence, maj_le, reponses_vues_le, checklist, recap
Onglet « semaines » : week_id, seances (nombre de séances choisi par l'élève pour cette semaine)
Onglet « signalements » : douleurs et absences signalées par l'élève
    id, type, debut, fin, zone, niveau, commentaire, cree_le, clos_le
Les fichiers d'avant les ressentis n'ont que session_id et fait_le : toutes leurs lignes sont des
séances réalisées. Les colonnes et onglets absents des anciens fichiers sont simplement vides.
"""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta

import pandas as pd

from .calculs import format_race_time, parse_km_range
from .config import COMMENT_MAX, FEELINGS, FREQUENCIES, WEEK_COUNTS
from .plan import is_race_day
from .stockage import Store, read_workbook, write_workbook

SUIVI_DIR = "suivi"
SKIP_REASONS = ["Fatigue", "Douleur", "Malade", "Manque de temps", "Météo", "Autre"]
REPORT_KINDS = {"douleur": "Douleur", "absence": "Absence", "maladie": "Maladie"}
PAIN_LEVELS = {1: "légère", 2: "gênante", 3: "forte"}
PAIN_ZONES = ["Pied", "Cheville", "Mollet", "Tibia", "Genou", "Cuisse", "Ischios", "Hanche", "Dos", "Autre"]


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
class Skip:
    """Séance marquée « pas faite » par l'élève."""

    le: str                       # AAAA-MM-JJ
    raison: str = ""


@dataclass(frozen=True)
class Report:
    """Douleur, absence ou maladie signalée par l'élève."""

    id: str
    kind: str                     # clé de REPORT_KINDS
    start: date
    end: date | None = None       # absence : dernier jour ; douleur : None tant qu'elle n'est pas close
    zone: str = ""
    level: int | None = None      # douleur : 1 à 3 (PAIN_LEVELS)
    comment: str = ""
    created: str = ""             # AAAA-MM-JJ HH:MM
    closed: str = ""              # AAAA-MM-JJ HH:MM (« je vais mieux »), vide si en cours

    @property
    def label(self) -> str:
        if self.kind == "douleur":
            zone = f" ({self.zone.lower()})" if self.zone else ""
            level = f", {PAIN_LEVELS[self.level]}" if self.level in PAIN_LEVELS else ""
            return f"Douleur{zone}{level}"
        return REPORT_KINDS.get(self.kind, "Signalement")

    @property
    def period(self) -> str:
        fmt = lambda d: f"{d:%d/%m}"  # noqa: E731
        if self.end and self.end != self.start:
            return f"du {fmt(self.start)} au {fmt(self.end)}"
        if self.kind == "douleur" and not self.end:
            return f"depuis le {fmt(self.start)}"
        return f"le {fmt(self.start)}"

    def active(self, today: date | None = None) -> bool:
        """En cours aujourd'hui (une absence à venir n'est pas encore « en cours »)."""
        today = today or date.today()
        if self.closed:
            return False
        return self.start <= today and (self.end is None or today <= self.end)

    def upcoming(self, today: date | None = None) -> bool:
        today = today or date.today()
        return not self.closed and self.start > today

    def covers(self, day: date | None) -> bool:
        """Le jour `day` tombe-t-il dans cette absence (ou maladie) ?"""
        if day is None or self.kind == "douleur" or self.closed and self.closed[:10] < day.isoformat():
            return False
        return self.start <= day and (self.end is None or day <= self.end)


@dataclass(frozen=True)
class Suivi:
    done: dict = field(default_factory=dict)     # identifiant de séance -> date (AAAA-MM-JJ) de validation
    temps_realise: str = ""                      # « hh:mm:ss »
    frequence: int | None = None                 # 2, 3 ou 4, choisie par l'élève
    maj_le: str = ""
    notes: dict = field(default_factory=dict)    # identifiant de séance -> Note
    semaines: dict = field(default_factory=dict) # identifiant de semaine -> nombre de séances choisi (2 à 4)
    skipped: dict = field(default_factory=dict)  # identifiant de séance -> Skip (« pas faite »)
    reports: tuple = ()                          # Report, du plus ancien au plus récent
    reponses_vues_le: str = ""                   # dernière fois que l'élève a lu les réponses du coach
    checklist: frozenset = frozenset()           # éléments cochés de la checklist du jour J
    recap: bool = True                           # reçoit le récap du dimanche par e-mail
    km: dict = field(default_factory=dict)       # identifiant de séance -> km réellement courus (si différent)

    def with_(self, **changes) -> "Suivi":
        return replace(self, maj_le=_now(), **changes)

    def note(self, session_id: str) -> Note:
        return self.notes.get(session_id, Note())

    def absence_on(self, day: date | None) -> Report | None:
        """Absence ou maladie signalée qui couvre ce jour, sinon None."""
        return next((r for r in reversed(self.reports) if r.covers(day)), None)


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


MAX_KM = 100.0


def parse_km(value) -> float | None:
    """« 8 », « 8,5 », « 8.5 km » -> 8.5 ; vide -> None. Lève ValueError si invalide."""
    raw = _text(value).lower().replace("km", "").replace(",", ".").replace(" ", "")
    if not raw:
        return None
    try:
        km = float(raw)
    except ValueError as exc:
        raise ValueError("Distance invalide : écris un nombre de km, par exemple 8 ou 8,5.") from exc
    if not 0 < km <= MAX_KM:
        raise ValueError(f"Distance invalide : entre 0 et {MAX_KM:.0f} km.")
    return round(km, 2)


def fr_km(km: float) -> str:
    return f"{km:.2f}".rstrip("0").rstrip(".").replace(".", ",")


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
    done, notes, skipped, kms = {}, {}, {}, {}
    for _, r in rows.iterrows():
        sid = r.get("session_id")
        if not isinstance(sid, str) or not sid:
            continue
        try:
            km = parse_km(r.get("km_reels"))
        except ValueError:
            km = None
        if km is not None:
            kms[sid] = km
        if not has_flag or _truthy(r.get("fait")):
            when = r.get("fait_le")
            done[sid] = str(when)[:10] if isinstance(when, (str, datetime, date)) else ""
        elif _text(r.get("pas_faite_le")):
            skipped[sid] = Skip(_text(r.get("pas_faite_le"))[:10], _text(r.get("raison")))
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
    reports = []
    for _, r in sheets.get("signalements", pd.DataFrame()).iterrows():
        report = _report_from_row(r)
        if report is not None:
            reports.append(report)
    checked = frozenset(x for x in _text(infos.get("checklist")).split("|") if x)
    suivi = Suivi(done=done, temps_realise=_text(infos.get("temps_realise")),
                  frequence=freq if freq in FREQUENCIES else None, maj_le=_text(infos.get("maj_le")),
                  notes=notes, semaines=weeks, skipped=skipped, reports=tuple(reports),
                  reponses_vues_le=_text(infos.get("reponses_vues_le")), checklist=checked,
                  recap=_text(infos.get("recap")) not in ("0", "0.0", "non"), km=kms)
    with _lock:
        _cache[rel] = (version, suivi)
    return suivi


def _to_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(_text(value)[:10])
    except ValueError:
        return None


def _report_from_row(r) -> Report | None:
    start = _to_date(r.get("debut"))
    kind = _text(r.get("type"))
    if start is None or kind not in REPORT_KINDS:
        return None
    try:
        level = int(float(r.get("niveau")))
    except (TypeError, ValueError):
        level = None
    return Report(id=_text(r.get("id")) or secrets.token_hex(4), kind=kind, start=start, end=_to_date(r.get("fin")),
                  zone=_text(r.get("zone")), level=level if level in PAIN_LEVELS else None,
                  comment=_text(r.get("commentaire"))[:COMMENT_MAX], created=_text(r.get("cree_le")),
                  closed=_text(r.get("clos_le")))


SEANCES_COLUMNS = ["session_id", "fait", "fait_le", "ressenti", "commentaire", "note_le", "pas_faite_le", "raison",
                   "km_reels"]
REPORT_COLUMNS = ["id", "type", "debut", "fin", "zone", "niveau", "commentaire", "cree_le", "clos_le"]


def save_suivi(store: Store, student_id: str, suivi: Suivi) -> None:
    ids = sorted(set(suivi.done) | set(suivi.notes) | set(suivi.skipped) | set(suivi.km))
    seances = pd.DataFrame([{
        "session_id": sid, "fait": 1 if sid in suivi.done else 0, "fait_le": suivi.done.get(sid, ""),
        "ressenti": suivi.note(sid).ressenti or "", "commentaire": suivi.note(sid).commentaire,
        "note_le": suivi.note(sid).le,
        "pas_faite_le": suivi.skipped[sid].le if sid in suivi.skipped and sid not in suivi.done else "",
        "raison": suivi.skipped[sid].raison if sid in suivi.skipped and sid not in suivi.done else "",
        "km_reels": suivi.km.get(sid, ""),
    } for sid in ids], columns=SEANCES_COLUMNS)
    infos = pd.DataFrame([("temps_realise", suivi.temps_realise), ("frequence", suivi.frequence or ""),
                          ("maj_le", suivi.maj_le), ("reponses_vues_le", suivi.reponses_vues_le),
                          ("checklist", "|".join(sorted(suivi.checklist))), ("recap", "1" if suivi.recap else "0")],
                         columns=["cle", "valeur"])
    semaines = pd.DataFrame([{"week_id": k, "seances": v} for k, v in sorted(suivi.semaines.items())],
                            columns=["week_id", "seances"])
    reports = pd.DataFrame([{
        "id": r.id, "type": r.kind, "debut": r.start.isoformat(), "fin": r.end.isoformat() if r.end else "",
        "zone": r.zone, "niveau": r.level or "", "commentaire": r.comment, "cree_le": r.created, "clos_le": r.closed,
    } for r in suivi.reports], columns=REPORT_COLUMNS)
    store.write(_file(student_id), write_workbook({"seances": seances, "infos": infos, "semaines": semaines,
                                                   "signalements": reports}))


# ----------------------------------------------------------------------------
# Actions de l'élève
# ----------------------------------------------------------------------------
def set_done(store: Store, student_id: str, session_id: str, done: bool) -> Suivi:
    """Coche / décoche une séance. Décocher garde le ressenti et le commentaire."""
    suivi = load_suivi(store, student_id)
    marks, skipped = dict(suivi.done), dict(suivi.skipped)
    if done:
        marks[session_id] = date.today().isoformat()
        skipped.pop(session_id, None)             # faite : n'est plus « pas faite »
    else:
        marks.pop(session_id, None)
    updated = suivi.with_(done=marks, skipped=skipped)
    save_suivi(store, student_id, updated)
    return updated


def set_skipped(store: Store, student_id: str, session_id: str, raison: str | None) -> Suivi:
    """Marque une séance « pas faite » (avec une raison) ; raison None enlève la marque.
    Une séance « pas faite » n'est plus cochée ; son ressenti et son commentaire sont gardés."""
    suivi = load_suivi(store, student_id)
    marks, skipped = dict(suivi.done), dict(suivi.skipped)
    if raison is None:
        skipped.pop(session_id, None)
    else:
        skipped[session_id] = Skip(date.today().isoformat(), str(raison).strip()[:60])
        marks.pop(session_id, None)
    updated = suivi.with_(done=marks, skipped=skipped)
    save_suivi(store, student_id, updated)
    return updated


def add_report(store: Store, student_id: str, kind: str, start: date, end: date | None = None, zone: str = "",
               level: int | None = None, comment: str = "") -> Report:
    """Enregistre une douleur, une absence ou une maladie signalée par l'élève."""
    if kind not in REPORT_KINDS:
        raise ValueError("Type de signalement inconnu.")
    if not isinstance(start, date):
        raise ValueError("Indique la date de début.")
    if end is not None and end < start:
        raise ValueError("La date de fin est avant la date de début.")
    if kind == "absence" and end is None:
        raise ValueError("Indique la date de retour (dernier jour d'absence).")
    report = Report(id=secrets.token_hex(4), kind=kind, start=start, end=end, zone=zone if kind == "douleur" else "",
                    level=level if kind == "douleur" and level in PAIN_LEVELS else None,
                    comment=str(comment or "").strip()[:COMMENT_MAX], created=_now())
    suivi = load_suivi(store, student_id)
    save_suivi(store, student_id, suivi.with_(reports=(*suivi.reports, report)))
    return report


def close_report(store: Store, student_id: str, report_id: str) -> Suivi:
    """« Je vais mieux » / « Je suis de retour » : le signalement est clos (il reste dans l'historique)."""
    suivi = load_suivi(store, student_id)
    today = date.today()

    def closed(r: Report) -> Report:
        if r.id != report_id or r.closed:
            return r
        end = r.end
        if r.kind == "douleur" and end is None:
            end = today                                   # fin de la douleur
        elif r.start <= today and (end is None or today < end):
            end = today                                   # retour plus tôt que prévu
        return replace(r, closed=_now(), end=end)

    updated = suivi.with_(reports=tuple(closed(r) for r in suivi.reports))
    save_suivi(store, student_id, updated)
    return updated


def delete_report(store: Store, student_id: str, report_id: str) -> Suivi:
    """Supprime un signalement saisi par erreur."""
    suivi = load_suivi(store, student_id)
    updated = suivi.with_(reports=tuple(r for r in suivi.reports if r.id != report_id))
    save_suivi(store, student_id, updated)
    return updated


def mark_replies_seen(store: Store, student_id: str) -> Suivi:
    updated = load_suivi(store, student_id).with_(reponses_vues_le=_now())
    save_suivi(store, student_id, updated)
    return updated


def set_checklist_item(store: Store, student_id: str, key: str, checked: bool) -> Suivi:
    suivi = load_suivi(store, student_id)
    items = set(suivi.checklist)
    (items.add if checked else items.discard)(key)
    updated = suivi.with_(checklist=frozenset(items))
    save_suivi(store, student_id, updated)
    return updated


def set_recap(store: Store, student_id: str, wanted: bool) -> Suivi:
    updated = load_suivi(store, student_id).with_(recap=bool(wanted))
    save_suivi(store, student_id, updated)
    return updated


_KEEP = object()


def set_note(store: Store, student_id: str, session_id: str, ressenti, commentaire: str, km=_KEEP) -> Suivi:
    """Enregistre le ressenti (1 à 5, ou None) et le commentaire d'une séance ; vides = effacés.
    `km` (facultatif) : km réellement courus, texte ou nombre (« 8,5 ») ; vide = effacés. Lève
    ValueError si la distance est invalide (rien n'est enregistré)."""
    km_value = parse_km(km) if km is not _KEEP else _KEEP
    suivi = load_suivi(store, student_id)
    notes = dict(suivi.notes)
    note = Note(clean_feeling(ressenti), str(commentaire or "").strip()[:COMMENT_MAX], _now())
    if note.empty:
        notes.pop(session_id, None)
    else:
        notes[session_id] = note
    kms = dict(suivi.km)
    if km_value is not _KEEP:
        if km_value is None:
            kms.pop(session_id, None)
        else:
            kms[session_id] = km_value
    updated = suivi.with_(notes=notes, km=kms)
    save_suivi(store, student_id, updated)
    return updated


def set_km(store: Store, student_id: str, session_id: str, km) -> Suivi:
    """Km réellement courus pour une séance (vide = on garde les km prévus)."""
    value = parse_km(km)
    suivi = load_suivi(store, student_id)
    kms = dict(suivi.km)
    if value is None:
        kms.pop(session_id, None)
    else:
        kms[session_id] = value
    updated = suivi.with_(km=kms)
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


def is_skipped(row, suivi: Suivi) -> bool:
    """Séance marquée « pas faite » par l'élève (et pas cochée depuis)."""
    return row["session_id"] in suivi.skipped and not is_done(row, suivi)


def km_run(row, suivi: Suivi) -> float:
    """Km d'une séance réalisée : ceux saisis par l'élève, sinon le bas de la fourchette prévue."""
    return suivi.km.get(row["session_id"], _km(row["km_env"]))


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
    km = sum(km_run(r, suivi) for (_, r), ok in zip(table.iterrows(), flags) if ok) if flags else 0.0
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
        if is_done(r, suivi) or is_skipped(r, suivi):
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
    """Carnet : séances réalisées, commentées ou « pas faites », de la plus récente à la plus ancienne."""
    out = []
    for _, r in table.iterrows():
        sid = r["session_id"]
        note = suivi.note(sid)
        race = is_race_day(r["seance"])
        done = is_done(r, suivi)
        skip = suivi.skipped.get(sid) if not done else None
        if not done and note.empty and skip is None:
            continue
        when = suivi.done.get(sid, "") or (skip.le if skip else "") or (note.le[:10] if note.le else "")
        if race and isinstance(r.get("date"), date):
            when = r["date"].isoformat()
        out.append({"row": r, "note": note, "when": when, "race": race, "done": done, "skip": skip,
                    "km": suivi.km.get(sid)})
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
