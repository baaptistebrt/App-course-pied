"""
Ce que le coach écrit à propos d'un programme : ses réponses aux ressentis et aux signalements de
l'élève, et les alertes qu'il a déjà vues (tableau « À surveiller »).

Fichier `data/coach/<id>.xlsx`, écrit UNIQUEMENT par le coach (le suivi de l'élève reste dans
`data/suivi/<id>.xlsx`, écrit uniquement par l'élève) :
    onglet « reponses »      cle, texte, le      (cle = identifiant de séance, ou « signal:<id> »)
    onglet « alertes_vues »  cle, vu_le
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from .config import COMMENT_MAX
from .stockage import Store, read_workbook, write_workbook

COACH_DIR = "coach"


@dataclass(frozen=True)
class Reply:
    texte: str
    le: str                     # AAAA-MM-JJ HH:MM


@dataclass(frozen=True)
class CoachFile:
    replies: dict = field(default_factory=dict)     # cle -> Reply
    seen: dict = field(default_factory=dict)        # clé d'alerte -> AAAA-MM-JJ HH:MM

    def reply(self, key: str) -> Reply | None:
        return self.replies.get(key)


def signal_key(report_id: str) -> str:
    return f"signal:{report_id}"


def _file(student_id: str) -> str:
    return f"{COACH_DIR}/{student_id}.xlsx"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


_cache: dict[str, tuple[tuple[int, int], CoachFile]] = {}
_lock = threading.Lock()


def load_coach(store: Store, student_id: str) -> CoachFile:
    rel = _file(student_id)
    if not store.exists(rel):
        return CoachFile()
    version = store.version(rel)
    with _lock:
        cached = _cache.get(rel)
    if cached and cached[0] == version:
        return cached[1]
    try:
        sheets = read_workbook(store.read(rel))
    except ValueError:
        return CoachFile()
    replies = {}
    for _, r in sheets.get("reponses", pd.DataFrame()).iterrows():
        key, texte = _text(r.get("cle")), _text(r.get("texte"))
        if key and texte:
            replies[key] = Reply(texte[:COMMENT_MAX], _text(r.get("le")))
    seen = {_text(r.get("cle")): _text(r.get("vu_le")) for _, r in sheets.get("alertes_vues", pd.DataFrame()).iterrows()
            if _text(r.get("cle"))}
    data = CoachFile(replies, seen)
    with _lock:
        _cache[rel] = (version, data)
    return data


def save_coach(store: Store, student_id: str, data: CoachFile) -> None:
    replies = pd.DataFrame([{"cle": k, "texte": v.texte, "le": v.le} for k, v in sorted(data.replies.items())],
                           columns=["cle", "texte", "le"])
    seen = pd.DataFrame([{"cle": k, "vu_le": v} for k, v in sorted(data.seen.items())], columns=["cle", "vu_le"])
    store.write(_file(student_id), write_workbook({"reponses": replies, "alertes_vues": seen}))


def set_reply(store: Store, student_id: str, key: str, texte: str) -> CoachFile:
    """Réponse du coach (texte vide = réponse effacée)."""
    data = load_coach(store, student_id)
    replies = dict(data.replies)
    texte = str(texte or "").strip()[:COMMENT_MAX]
    if texte:
        replies[key] = Reply(texte, _now())
    else:
        replies.pop(key, None)
    updated = CoachFile(replies, dict(data.seen))
    save_coach(store, student_id, updated)
    return updated


def dismiss_alert(store: Store, student_id: str, alert_key: str) -> CoachFile:
    """Le coach a vu l'alerte : elle disparaît du tableau « À surveiller »."""
    data = load_coach(store, student_id)
    seen = dict(data.seen)
    seen[alert_key] = _now()
    updated = CoachFile(dict(data.replies), seen)
    save_coach(store, student_id, updated)
    return updated


def unread(data: CoachFile, seen_until: str) -> list[tuple[str, Reply]]:
    """Réponses du coach écrites après la dernière lecture de l'élève, de la plus récente à la plus ancienne."""
    items = [(k, r) for k, r in data.replies.items() if r.le and r.le > (seen_until or "")]
    return sorted(items, key=lambda x: x[1].le, reverse=True)


def delete_coach_file(store: Store, student_id: str) -> None:
    store.delete(_file(student_id))
    with _lock:
        _cache.pop(_file(student_id), None)
