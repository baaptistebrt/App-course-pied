"""
Jour de chaque séance dans la semaine et export vers l'agenda du téléphone (fichier .ics,
lu par Google Agenda, Apple Calendrier, Outlook…).

Le jour vient de la colonne « Jour » du plan ; sans jour, la séance est placée à un jour conseillé
(mêmes règles que « Mon Planning »). Chaque séance devient un événement « journée entière » avec un
rappel à 8 h le jour même. Un identifiant stable par séance permet de réimporter le fichier après
une modification du plan sans créer de doublons (selon l'agenda).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pandas as pd

from .config import DAYS, PACE_LABELS
from .plan import is_empty_session, is_race_day, pace_codes

# Jours conseillés quand le coach n'a pas fixé le jour d'une séance (0 = lundi), selon le nombre de séances.
SUGGESTED_DAYS = {1: [5], 2: [1, 5], 3: [1, 3, 6], 4: [1, 3, 5, 6], 5: [0, 1, 3, 5, 6], 6: [0, 1, 2, 3, 5, 6]}


def suggested_days(full: pd.DataFrame, race_date: date | None = None) -> dict[str, int]:
    """Jour (0 = lundi) de chaque séance de la semaine COMPLÈTE prévue par le coach : le jour fixé, sinon
    un jour conseillé. Calculé sur toutes les séances, pour qu'une séance garde son jour quand l'élève
    masque les autres."""
    out = {}
    for _, r in full.iterrows():
        if is_race_day(r["seance"]) and race_date:
            out[r["session_id"]] = race_date.weekday()
        elif r["jour"] in DAYS:
            out[r["session_id"]] = DAYS.index(r["jour"])
    taken = set(out.values())
    free = [d for d in SUGGESTED_DAYS.get(len(full), list(range(7))) if d not in taken]
    free += [d for d in range(7) if d not in taken and d not in free]
    for _, r in full.iterrows():
        if r["session_id"] not in out:
            out[r["session_id"]] = free.pop(0) if free else 6
    return out


def place_sessions(sub: pd.DataFrame, days: dict[str, int]) -> tuple[list[tuple[int, date | None, pd.Series]], bool]:
    """Séances visibles placées sur leur jour. Renvoie ([(jour 0-6, date, séance)], un jour est-il conseillé ?)."""
    first = sub.iloc[0]
    start = first["debut"] if isinstance(first["debut"], date) else None
    placed, suggested = [], False
    for _, r in sub.iterrows():
        if isinstance(r["date"], date):
            wd = r["date"].weekday()
        elif r["jour"] in DAYS:
            wd = DAYS.index(r["jour"])
        else:
            wd = days.get(r["session_id"], 6)
            suggested = True
        placed.append((wd, start + timedelta(days=wd) if start else None, r))
    placed.sort(key=lambda x: x[0])
    return placed, suggested


def week_plan_sessions(student, week_id: str) -> pd.DataFrame:
    """Toutes les séances prévues par le coach pour cette semaine (hors séances vides)."""
    sub = student.plan.sessions_of(week_id)
    return sub[[not is_empty_session(r) for _, r in sub.iterrows()]]


def session_days(student, table: pd.DataFrame) -> dict[str, date]:
    """Date (réelle ou conseillée) de chaque séance affichée ; les séances sans date sont absentes."""
    out: dict[str, date] = {}
    if table.empty:
        return out
    for _, sub in table.groupby("position", sort=True):
        week_id = sub["week_id"].iloc[0]
        placed, _ = place_sessions(sub, suggested_days(week_plan_sessions(student, week_id), student.date_course))
        for _, day, r in placed:
            if isinstance(day, date):
                out[r["session_id"]] = day
    return out


# ----------------------------------------------------------------------------
# Fichier .ics
# ----------------------------------------------------------------------------
def _escape(text: str) -> str:
    return (str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _fold(line: str) -> str:
    """Coupe les lignes à 75 octets (norme iCalendar), sans couper un caractère UTF-8."""
    out, current = [], ""
    for ch in line:
        if len((current + ch).encode()) > (75 if not out else 74):
            out.append(current)
            current = ch
        else:
            current += ch
    out.append(current)
    return "\r\n ".join(out)


def _title(r) -> str:
    if is_race_day(r["seance"]):
        return "Jour J"
    return str(r["contenu"] or "Séance").strip()


def ics_calendar(student, table: pd.DataFrame, paces: dict, app_url: str = "", today: date | None = None,
                 now: datetime | None = None) -> tuple[bytes, int]:
    """(contenu du fichier .ics, nombre de séances) pour les séances datées d'aujourd'hui à la course."""
    today = today or date.today()
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    days = session_days(student, table)
    name = getattr(student, "race_name", "") or "mon plan"
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Coach running//Plan d'entrainement//FR",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", f"X-WR-CALNAME:{_escape('Entraînement ' + name)}"]
    count = 0
    for _, r in table.iterrows():
        day = days.get(r["session_id"])
        if day is None or day < today:
            continue
        race = is_race_day(r["seance"])
        summary = f"🏁 Jour J : {name}" if race else f"🏃 {_title(r)}"
        desc = []
        if str(r.get("intensite") or "").strip():
            desc.append(f"Intensité : {str(r['intensite']).strip()}")
        facts = [f"{r['km_env']} km" if r["km_env"] else "", r["duree_env"] or "",
                 f"dont {r['temps_aff']} à l'allure" if r["temps_aff"] and not race else ""]
        if any(facts):
            desc.append(", ".join(f for f in facts if f))
        for code in pace_codes(r["allure"]):
            if code in paces:
                desc.append(f"{PACE_LABELS[code]} : {paces[code].pace_str} /km")
        if r["remarque"]:
            desc.append(str(r["remarque"]))
        if app_url:
            desc.append(f"Coche ta séance : {app_url}")
        lines += ["BEGIN:VEVENT", f"UID:{r['session_id']}@coach-running", f"DTSTAMP:{stamp}",
                  f"DTSTART;VALUE=DATE:{day:%Y%m%d}", f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}",
                  f"SUMMARY:{_escape(summary)}", f"DESCRIPTION:{_escape(chr(10).join(desc))}",
                  "TRANSP:TRANSPARENT"]
        if app_url:
            lines.append(f"URL:{app_url}")
        lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_escape(summary)}", "TRIGGER:PT8H",
                  "END:VALARM", "END:VEVENT"]
        count += 1
    lines.append("END:VCALENDAR")
    return ("\r\n".join(_fold(x) for x in lines) + "\r\n").encode("utf-8"), count
