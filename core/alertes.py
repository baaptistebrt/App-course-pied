"""
Tableau « À surveiller » du coach : les signaux à regarder, calculés à partir de ce que l'élève a
déjà saisi (aucune saisie en plus pour lui).

* douleur, absence ou maladie signalée par l'élève ;
* commentaire qui parle d'une douleur (genou, tendinite, « j'ai mal »…) ;
* « Très dur » deux fois de suite ;
* séance facile (footing) ressentie « Dur » ou « Très dur » : signe de fatigue ;
* ressentis en baisse sur 3 séances ;
* 2 séances « pas faites » d'affilée ;
* kilomètres de la semaine en forte hausse (+30 % et +8 km au moins par rapport à la moyenne des
  3 semaines d'avant, avec les km réellement courus saisis par l'élève) : principal facteur de blessure ;
* aucune séance cochée depuis 7 jours alors que des séances étaient prévues.

Une alerte a une clé stable : quand le coach la marque « vue » (core/reponses.dismiss_alert), elle
disparaît jusqu'à ce qu'un nouveau signal apparaisse (nouvelle séance, nouveau commentaire…).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

from .agenda import session_days
from .analyse import weekly_frame
from .config import FEELINGS
from .plan import activity_kind, is_race_day
from .reponses import CoachFile, signal_key
from .suivi import is_done, is_skipped

LEVELS = {"rouge": 0, "orange": 1, "info": 2}
WINDOW_DAYS = 14          # un ressenti ou un commentaire de plus de 14 jours ne déclenche plus d'alerte
INACTIVE_DAYS = 7
SPIKE_RATIO, SPIKE_KM = 1.3, 8.0

_PAIN = re.compile(
    r"(douleur|douloureu|j ai mal|j avais mal|mal au|mal aux|mal a la|mal a l |mal a mon|mal a ma|mal dans|"
    r"bless|tendin|tendon|periost|contractur|claquage|entorse|elongation|dechirure|fracture|inflamm|"
    r"boiter|boite un peu|lombalgi|sciatiq|aponevros|fasciite|essuie glace|tfl|genou qui|cheville qui|"
    r"gene au|gene a la|gene aux)")


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return " " + re.sub(r"[^a-z0-9]+", " ", text) + " "


def mentions_pain(text: str) -> bool:
    """Le commentaire parle-t-il d'une douleur ? (« pas mal » ou « sans douleur » ne comptent pas)."""
    plain = _plain(text)
    plain = re.sub(r" (pas|sans|aucune?|plus) (de )?(mal|douleur|gene)s? ", " ", plain)
    return bool(_PAIN.search(plain))


@dataclass(frozen=True)
class Alert:
    key: str
    level: str                  # « rouge », « orange » ou « info »
    title: str
    detail: str = ""
    when: str = ""              # AAAA-MM-JJ, pour trier
    session_id: str = ""        # séance concernée (pour « Répondre »)
    reply_key: str = ""         # clé de réponse du coach (séance ou signalement)

    @property
    def icon(self) -> str:
        return {"rouge": "🔴", "orange": "🟠", "info": "🔵"}[self.level]


def _day(text: str) -> date | None:
    try:
        return date.fromisoformat(str(text)[:10])
    except ValueError:
        return None


def _short(text: str, n: int = 140) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n - 1] + "…"


def program_alerts(state, coach: CoachFile | None = None, today: date | None = None) -> list[Alert]:
    """Alertes d'un programme en cours (celles déjà vues par le coach sont retirées)."""
    today = today or date.today()
    sv, table = state.suivi, state.table
    if table.empty or state.finished(today):
        return []
    rows = {r["session_id"]: r for _, r in table.iterrows()}
    out: list[Alert] = []
    recent = today - timedelta(days=WINDOW_DAYS)

    # -- signalements de l'élève
    for rep in sv.reports:
        if rep.closed:
            continue
        if rep.kind == "douleur":
            out.append(Alert(signal_key(rep.id), "rouge", f"{rep.label} {rep.period}", rep.comment,
                             rep.start.isoformat(), reply_key=signal_key(rep.id)))
        elif rep.active(today) or (rep.upcoming(today) and rep.start - today <= timedelta(days=WINDOW_DAYS)):
            level = "orange" if rep.kind == "maladie" else "info"
            out.append(Alert(signal_key(rep.id), level, f"{rep.label} {rep.period}", rep.comment,
                             rep.start.isoformat(), reply_key=signal_key(rep.id)))

    # -- ressentis et commentaires (du plus ancien au plus récent)
    order = {sid: i for i, sid in enumerate(rows)}
    notes = sorted(((n.le, sid, n) for sid, n in sv.notes.items() if sid in rows and n.le),
                   key=lambda x: (x[0], order[x[1]]))
    for le, sid, n in notes:
        d = _day(le)
        if d and d >= recent and n.commentaire and mentions_pain(n.commentaire):
            out.append(Alert(f"mot:{sid}:{le}", "rouge", "Parle d'une douleur", f"« {_short(n.commentaire)} »",
                             le[:10], sid, sid))
    rated = [(le, sid, n) for le, sid, n in notes if n.ressenti]
    if len(rated) >= 2:
        (_, _, a), (le_b, sid_b, b) = rated[-2], rated[-1]
        if a.ressenti == 1 and b.ressenti == 1 and (_day(le_b) or date.min) >= recent:
            out.append(Alert(f"tresdur:{sid_b}", "orange", "« Très dur » deux fois de suite",
                             f"Dernière : {rows[sid_b]['contenu'] or 'séance'}", le_b[:10], sid_b, sid_b))
    if len(rated) >= 3:
        last3 = rated[-3:]
        values = [n.ressenti for _, _, n in last3]
        le_c, sid_c = last3[-1][0], last3[-1][1]
        if values[0] > values[1] > values[2] and values[2] <= 3 and (_day(le_c) or date.min) >= recent:
            trend = " → ".join(FEELINGS[v][0] for v in values)
            out.append(Alert(f"baisse:{sid_c}", "orange", "Ressentis en baisse sur 3 séances", trend, le_c[:10],
                             sid_c, sid_c))
    for le, sid, n in notes:
        d = _day(le)
        if (n.ressenti in (1, 2) and d and d >= today - timedelta(days=7) and not is_race_day(rows[sid]["seance"])
                and activity_kind(rows[sid]) == "footing"):
            out.append(Alert(f"facile:{sid}", "orange", f"Footing ressenti « {FEELINGS[n.ressenti][1]} »",
                             f"{rows[sid]['contenu'] or 'Footing'} : séance facile vécue comme dure, signe de fatigue",
                             le[:10], sid, sid))

    # -- séances pas faites d'affilée (dans l'ordre du plan)
    marked = [sid for sid in rows if is_done(rows[sid], sv) or is_skipped(rows[sid], sv)]
    if len(marked) >= 2 and all(is_skipped(rows[s], sv) for s in marked[-2:]):
        last = sv.skipped[marked[-1]]
        if (_day(last.le) or date.min) >= recent:
            reasons = ", ".join(r for r in dict.fromkeys(sv.skipped[s].raison for s in marked[-2:]) if r)
            out.append(Alert(f"skip:{marked[-1]}", "orange", "2 séances pas faites d'affilée",
                             f"Raison : {reasons}" if reasons else "", last.le, marked[-1], marked[-1]))

    # -- charge : kilomètres de la semaine en forte hausse
    weekly = weekly_frame(state, today)
    ran = weekly[weekly["statut"].isin(["passee", "en_cours", "sans_date"]) & (weekly["km_courus"] > 0)]
    if len(ran) >= 4:
        last, before = ran.iloc[-1], ran.iloc[-4:-1]
        avg = float(before["km_courus"].mean())
        if avg > 0 and last["km_courus"] >= avg * SPIKE_RATIO and last["km_courus"] - avg >= SPIKE_KM:
            week = table[table["position"] == last["position"]]
            out.append(Alert(f"charge:{week['week_id'].iloc[0]}:{last['km_courus']:.0f}", "orange",
                             "Kilomètres en forte hausse",
                             f"{last['semaine']} : {last['km_courus']:.0f} km courus contre {avg:.0f} km en moyenne les "
                             f"3 semaines d'avant (+{(last['km_courus'] / avg - 1) * 100:.0f} %)".replace(".", ","),
                             today.isoformat()))

    # -- inactivité
    activity = [d for d in sv.done.values() if d] + [s.le for s in sv.skipped.values()] + \
        [n.le[:10] for n in sv.notes.values() if n.le]
    last_activity = max(activity) if activity else ""
    since = today - timedelta(days=INACTIVE_DAYS)
    days = session_days(state.student, table)              # date réelle, ou jour conseillé si non fixé
    dated = [d for sid, d in days.items() if sid in rows]
    away = sv.absence_on(today) is not None
    if dated and not away:
        due = [d for d in dated if since <= d < today]
        started = min(dated) <= since
        if started and due and (not last_activity or last_activity < since.isoformat()):
            days = (today - _day(last_activity)).days if last_activity else None
            title = (f"Aucune séance cochée depuis {days} jours" if days is not None
                     else "N'a encore coché aucune séance")
            out.append(Alert(f"inactif:{last_activity or 'jamais'}", "info", title,
                             f"{len(due)} séance(s) prévue(s) ces 7 derniers jours", last_activity))
    elif not dated and last_activity and not away and last_activity < (today - timedelta(days=10)).isoformat():
        out.append(Alert(f"inactif:{last_activity}", "info",
                         f"Aucune séance cochée depuis {(today - _day(last_activity)).days} jours", "", last_activity))

    seen = coach.seen if coach else {}
    unique: dict[str, Alert] = {}
    for a in out:
        if a.key not in seen and a.key not in unique:
            unique[a.key] = a
    return sorted(unique.values(), key=lambda a: (LEVELS[a.level], -int((a.when or "0000-00-00").replace("-", ""))))
