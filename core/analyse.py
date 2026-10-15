"""
Analyse de progression : tableaux calculés à partir des données déjà collectées
(séances cochées, ressentis, temps de course, historique des programmes).

Aucune donnée nouvelle n'est stockée ici : tout est recalculé à l'affichage. Les graphiques
(Plotly) sont dans ui/progression.py.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from . import suivi as sv_mod
from .agenda import session_days
from .calculs import parse_km_range
from .config import DISTANCES, FEELINGS
from .exports import fr_date


def _km(value) -> float:
    rng = parse_km_range(value)
    return rng[0] if rng else 0.0


WEEKLY_COLUMNS = ["position", "semaine", "periode", "statut", "faites", "manquees", "excusees", "a_venir", "prevues",
                  "km_prevus", "km_courus"]


def _excused(sv, r, start, day: date | None) -> bool:
    """Séance non faite pendant une absence ou une maladie signalée par l'élève (jour réel ou conseillé).
    Sans jour connu, la semaine compte comme « absente » si l'absence en couvre au moins 4 jours."""
    if day is not None:
        return sv.absence_on(day) is not None
    if not isinstance(start, date):
        return False
    return sum(1 for i in range(7) if sv.absence_on(start + timedelta(days=i)) is not None) >= 4


def weekly_frame(state, today: date | None = None) -> pd.DataFrame:
    """Une ligne par semaine du plan affiché : séances faites / manquées / excusées / à venir, km prévus
    et km courus (ceux saisis par l'élève, sinon le bas de la fourchette prévue).

    « Manquée » = marquée « pas faite » par l'élève, ou non cochée dans une semaine terminée.
    « Excusée » = non faite pendant une absence ou une maladie signalée : elle ne compte pas contre
    l'assiduité. Sans dates (pas de date de course), une séance non cochée est « à venir »."""
    today = today or date.today()
    table, sv = state.table, state.suivi
    rows = []
    if table.empty:
        return pd.DataFrame(columns=WEEKLY_COLUMNS)
    days = session_days(state.student, table) if sv.reports else {}
    for pos in sorted(table["position"].unique()):
        sub = table[table["position"] == pos]
        first = sub.iloc[0]
        start, end = first["debut"], first["fin"]
        dated = isinstance(start, date)
        status = ("passee" if end < today else "en_cours" if start <= today else "a_venir") if dated else "sans_date"
        done = missed = excused = 0
        km_run = 0.0
        for _, r in sub.iterrows():
            if sv_mod.is_done(r, sv):
                done += 1
                km_run += sv_mod.km_run(r, sv)
            elif _excused(sv, r, start, days.get(r["session_id"])):
                excused += 1
            elif sv_mod.is_skipped(r, sv) or status == "passee":
                missed += 1
        rows.append({
            "position": int(pos), "semaine": f"S{int(pos) + 1}",
            "periode": f"du {fr_date(start)} au {fr_date(end)}" if dated else f"Semaine {int(pos) + 1}",
            "statut": status, "faites": done, "manquees": missed, "excusees": excused,
            "a_venir": len(sub) - done - missed - excused, "prevues": len(sub),
            "km_prevus": round(sum(_km(k) for k in sub["km_env"]), 1),
            "km_courus": round(km_run, 1),
        })
    return pd.DataFrame(rows, columns=WEEKLY_COLUMNS)


def adherence(weekly: pd.DataFrame) -> float | None:
    """Assiduité : séances faites / séances déjà dues (semaines passées et semaine en cours)."""
    if weekly.empty:
        return None
    due = weekly[weekly["statut"].isin(["passee", "en_cours", "sans_date"])]
    if (due["statut"] == "sans_date").all():
        total = int(due["prevues"].sum() - due["excusees"].sum())
        return due["faites"].sum() / total if total else None
    expected = int(due["faites"].sum() + due["manquees"].sum()
                   + due.loc[due["statut"] == "en_cours", "a_venir"].sum())
    return due["faites"].sum() / expected if expected else None


def feelings_frame(state) -> pd.DataFrame:
    """Ressentis notés par l'élève (1 à 5), dans l'ordre chronologique."""
    rows = []
    shown = {r["session_id"]: r for _, r in state.table.iterrows()} if not state.table.empty else {}
    for sid, note in state.suivi.notes.items():
        if sid not in shown or note.ressenti is None:
            continue
        when = state.suivi.done.get(sid) or (note.le[:10] if note.le else "")
        try:
            day = date.fromisoformat(when)
        except ValueError:
            continue
        r = shown[sid]
        rows.append({"date": day, "ressenti": note.ressenti, "libelle": " ".join(FEELINGS[note.ressenti]),
                     "seance": str(r["contenu"] or r["seance"]), "semaine": f"S{int(r['position']) + 1}"})
    return pd.DataFrame(rows, columns=["date", "ressenti", "libelle", "seance", "semaine"]).sort_values("date")


def races_frame(records: list) -> pd.DataFrame:
    """Courses terminées avec un temps saisi : temps, objectif, écart et allure moyenne."""
    rows = []
    for r in records:
        if r.race_seconds is None:
            continue
        km = DISTANCES[r.distance].km
        objective_s = r.race_seconds - r.gap_seconds if r.gap_seconds is not None else None
        rows.append({
            "course": r.course, "distance": DISTANCES[r.distance].label, "date": r.race_date,
            "temps": r.race_time, "temps_s": r.race_seconds, "objectif": r.objective,
            "objectif_s": objective_s, "ecart": r.gap, "ecart_s": r.gap_seconds,
            "ecart_pct": round(100 * r.gap_seconds / objective_s, 1) if objective_s else None,
            "allure_s": r.race_seconds / km, "eleve": r.name,
        })
    df = pd.DataFrame(rows, columns=["course", "distance", "date", "temps", "temps_s", "objectif", "objectif_s",
                                     "ecart", "ecart_s", "ecart_pct", "allure_s", "eleve"])
    return df.sort_values("date", na_position="first") if not df.empty else df
