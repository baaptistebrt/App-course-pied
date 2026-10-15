"""
E-mails automatiques :

* récap du dimanche soir à chaque élève : ses séances de la semaine qui arrive, le bilan de la
  semaine écoulée, les réponses du coach à lire ;
* bilan du dimanche au coach : chaque programme en cours (séances faites, km, dernier ressenti) et
  le tableau « À surveiller » ;
* e-mail au coach quand un élève signale une douleur ou une absence ;
* e-mail à l'élève quand le coach lui répond (si le coach le demande).

Le récap du dimanche est envoyé par `tools/recap_hebdo.py`, lancé chaque dimanche par GitHub
(voir le README) ; l'onglet Réglages permet d'en recevoir un aperçu immédiatement.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date, timedelta
from email.message import EmailMessage
from email.utils import formataddr

from . import alertes, historique, profils, reponses
from .agenda import session_days
from .config import PACE_LABELS
from .emails import EmailConfig, send_message
from .exports import fr_date
from .plan import is_race_day, pace_codes
from .reglages import Settings, load_settings
from .stockage import Store
from .suivi import fr_km, is_done, is_skipped

e = html.escape
INK, MUTED, TRACK, CHRONO = "#14233A", "#5B6B80", "#1B4F8C", "#FFC629"


@dataclass(frozen=True)
class Sent:
    to: str
    subject: str
    ok: bool
    message: str


def coach_address(config: EmailConfig, settings: Settings) -> str:
    return settings.coach_email.strip() or config.user


def next_week(today: date) -> tuple[date, date]:
    """Lundi et dimanche de la semaine qui suit `today` (envoi le dimanche soir)."""
    monday = today + timedelta(days=7 - today.weekday())
    return monday, monday + timedelta(days=6)


def _message(config: EmailConfig, to: str, subject: str, text: str, body_html: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((config.sender_name, config.user))
    msg["To"] = to
    msg.set_content(text)
    msg.add_alternative(f"<div style='font-family:Arial,Helvetica,sans-serif;color:{INK};max-width:560px;"
                        f"line-height:1.45'>{body_html}</div>", subtype="html")
    return msg


def _button(url: str, label: str) -> str:
    if not url:
        return ""
    return (f"<p style='margin:20px 0'><a href='{e(url)}' style='background:{TRACK};color:#fff;text-decoration:none;"
            f"padding:11px 18px;border-radius:8px;font-weight:bold'>{e(label)}</a></p>")


def _session_line(r, paces: dict) -> tuple[str, str]:
    """(texte, HTML) d'une séance : titre, km, durée, allures."""
    race = is_race_day(r["seance"])
    title = "🏁 Jour J" if race else str(r["contenu"] or "Séance")
    facts = ", ".join(x for x in (f"{r['km_env']} km" if r["km_env"] else "", r["duree_env"] or "") if x)
    pace = ", ".join(f"{PACE_LABELS[c]} {paces[c].pace_str}" for c in pace_codes(r["allure"]) if c in paces)
    intensity = str(r.get("intensite") or "").strip()
    text = " — ".join(x for x in (title, facts, pace, f"Intensité : {intensity}" if intensity else "") if x)
    sub = " · ".join(x for x in (facts, pace) if x)
    html_ = (f"<b>{e(title)}</b>" + (f"<br><span style='color:{MUTED}'>{e(sub)}</span>" if sub else "")
             + (f"<br><span style='color:{MUTED}'>Intensité : {e(intensity)}</span>" if intensity else ""))
    return text, html_


# ----------------------------------------------------------------------------
# Récap élève
# ----------------------------------------------------------------------------
def student_recap(store: Store, state, config: EmailConfig, app_url: str, today: date | None = None,
                  to: str | None = None) -> EmailMessage | None:
    """Récap de la semaine à venir pour un programme ; None s'il n'y a rien à envoyer."""
    today = today or date.today()
    s, sv, table = state.student, state.suivi, state.table
    if table.empty or state.finished(today) or not s.email:
        return None
    days = session_days(s, table)
    monday, sunday = next_week(today)
    rows = {r["session_id"]: r for _, r in table.iterrows()}
    coming = sorted(((d, rows[sid]) for sid, d in days.items() if monday <= d <= sunday), key=lambda x: x[0])
    if not coming:
        return None
    past = [(d, rows[sid]) for sid, d in days.items() if monday - timedelta(days=7) <= d < monday]
    n_done = sum(1 for _, r in past if is_done(r, sv))
    n_skip = sum(1 for _, r in past if is_skipped(r, sv))
    unread = reponses.unread(reponses.load_coach(store, s.id), sv.reponses_vues_le)
    name = s.prenom or ""
    period = f"du {fr_date(monday)} au {fr_date(sunday)}"
    subject = f"Ta semaine {period} : {len(coming)} séance{'s' if len(coming) > 1 else ''}"

    lines_txt, lines_html = [], []
    for d, r in coming:
        t, h = _session_line(r, state.sp.paces)
        lines_txt.append(f"- {fr_date(d, weekday=True).capitalize()} : {t}")
        lines_html.append(f"<tr><td style='padding:8px 12px 8px 0;vertical-align:top;color:{TRACK};font-weight:bold;"
                          f"white-space:nowrap'>{e(fr_date(d, weekday=True).capitalize())}</td>"
                          f"<td style='padding:8px 0;border-top:1px solid #E3E9F0'>{h}</td></tr>")
    bilan = ""
    if past:
        bilan = f"Cette semaine : {n_done} séance{'s' if n_done > 1 else ''} sur {len(past)}"
        bilan += (" — bravo !" if n_done == len(past) else
                  f" ({n_skip} pas faite{'s' if n_skip > 1 else ''})" if n_skip else
                  ". Si tu en as fait d'autres, pense à les cocher.")
    race = ""
    if s.date_course and 0 <= (s.date_course - today).days <= 49:
        race = f"J-{(s.date_course - today).days} avant {s.race_name}."
    msg_unread = (f"Ton coach t'a répondu ({len(unread)} message{'s' if len(unread) > 1 else ''}) : "
                  "lis-le dans ton espace.") if unread else ""

    hello = f"Bonjour {name}," if name else "Bonjour,"
    text = "\n".join(x for x in (
        hello, "", f"Voici ta semaine {period} :", *lines_txt, "", bilan, race, msg_unread, "",
        f"Ouvre ton plan : {app_url}" if app_url else "", "",
        "Bonne semaine !", config.sender_name, "",
        "Pour ne plus recevoir ce récap : décoche l'option en bas de « Mon Planning ».") if x is not None)
    body = (f"<p>{e(hello)}</p><p>Voici ta semaine <b>{e(period)}</b> :</p>"
            f"<table style='border-collapse:collapse;width:100%'>{''.join(lines_html)}</table>"
            + (f"<p>{e(bilan)}</p>" if bilan else "")
            + (f"<p style='background:{CHRONO};display:inline-block;padding:4px 10px;border-radius:6px;"
               f"font-weight:bold'>{e(race)}</p>" if race else "")
            + (f"<p>💬 <b>{e(msg_unread)}</b></p>" if msg_unread else "")
            + _button(app_url, "Ouvrir mon plan")
            + f"<p>Bonne semaine !<br>{e(config.sender_name)}</p>"
            + f"<p style='color:{MUTED};font-size:12px'>Pour ne plus recevoir ce récap : décoche l'option en bas "
              f"de « Mon Planning ».</p>")
    return _message(config, to or s.email, subject, text, body)


# ----------------------------------------------------------------------------
# Bilan coach
# ----------------------------------------------------------------------------
def coach_digest(store: Store, states: list, config: EmailConfig, app_url: str, to: str,
                 today: date | None = None) -> EmailMessage | None:
    """Bilan de la semaine pour le coach (programmes en cours + « À surveiller »)."""
    today = today or date.today()
    running = [st for st in states if not st.finished(today)]
    if not running:
        return None
    monday = today - timedelta(days=today.weekday())
    rows_txt, rows_html, alerts_txt, alerts_html, notes_html = [], [], [], [], []
    for st in sorted(running, key=lambda x: x.student.display_name.lower()):
        s, sv = st.student, st.suivi
        days = session_days(s, st.table)
        rows = {r["session_id"]: r for _, r in st.table.iterrows()}
        week = [rows[sid] for sid, d in days.items() if monday <= d <= monday + timedelta(days=6)]
        done = sum(1 for r in week if is_done(r, sv))
        skip = sum(1 for r in week if is_skipped(r, sv))
        km = sum(sv.km.get(r["session_id"], _km_low(r["km_env"])) for r in week if is_done(r, sv))
        status = f"{done}/{len(week)} faites" + (f", {skip} pas faite{'s' if skip > 1 else ''}" if skip else "") \
            + (f", {fr_km(km)} km" if km else "") if week else "pas de séance datée cette semaine"
        who = f"{s.display_name} — {s.race_name}"
        rows_txt.append(f"- {who} : {status}")
        rows_html.append(f"<tr><td style='padding:6px 12px 6px 0;border-top:1px solid #E3E9F0'><b>{e(s.display_name)}"
                         f"</b><br><span style='color:{MUTED}'>{e(s.race_name)}</span></td>"
                         f"<td style='padding:6px 0;border-top:1px solid #E3E9F0'>{e(status)}</td></tr>")
        for a in alertes.program_alerts(st, reponses.load_coach(store, s.id), today):
            alerts_txt.append(f"- {a.icon} {s.display_name} : {a.title}" + (f" ({a.detail})" if a.detail else ""))
            alerts_html.append(f"<li>{a.icon} <b>{e(s.display_name)}</b> : {e(a.title)}"
                               + (f" <span style='color:{MUTED}'>({e(a.detail)})</span>" if a.detail else "") + "</li>")
        for sid, n in sv.notes.items():
            if sid in rows and n.le and n.le[:10] >= monday.isoformat():
                quote = f" « {e(n.commentaire)} »" if n.commentaire else ""
                notes_html.append(f"<li><b>{e(s.display_name)}</b>, {e(str(rows[sid]['contenu'] or 'séance'))} : "
                                  f"{e(n.label)}{quote}</li>")
    subject = f"Bilan de la semaine : {len(running)} élève{'s' if len(running) > 1 else ''}" + \
        (f", {len(alerts_txt)} point{'s' if len(alerts_txt) > 1 else ''} à surveiller" if alerts_txt else "")
    text = "\n".join(["Bonjour,", "", "Cette semaine :", *rows_txt, "",
                      "À surveiller :" if alerts_txt else "Rien à signaler dans « À surveiller ».", *alerts_txt, "",
                      f"Ouvrir l'application : {app_url}" if app_url else ""])
    body = ("<p>Bonjour,</p><p><b>Cette semaine</b></p>"
            f"<table style='border-collapse:collapse;width:100%'>{''.join(rows_html)}</table>"
            + (f"<p><b>À surveiller</b></p><ul>{''.join(alerts_html)}</ul>" if alerts_html else
               "<p>Rien à signaler dans « À surveiller ». 👍</p>")
            + (f"<p><b>Ressentis de la semaine</b></p><ul>{''.join(notes_html[:15])}</ul>" if notes_html else "")
            + _button(app_url, "Ouvrir l'application"))
    return _message(config, to, subject, text, body)


def _km_low(value) -> float:
    from .calculs import parse_km_range
    rng = parse_km_range(value)
    return rng[0] if rng else 0.0


# ----------------------------------------------------------------------------
# Envoi
# ----------------------------------------------------------------------------
def _send(msg: EmailMessage, config: EmailConfig, dry_run: bool) -> Sent:
    if dry_run:
        return Sent(msg["To"], msg["Subject"], True, "non envoyé (essai)")
    try:
        send_message(msg, config)
    except Exception as exc:   # adresse refusée, réseau…
        return Sent(msg["To"], msg["Subject"], False, str(exc))
    return Sent(msg["To"], msg["Subject"], True, "envoyé")


def run_weekly(store: Store, config: EmailConfig, app_url: str = "", today: date | None = None,
               dry_run: bool = False, preview_to: str | None = None) -> list[Sent]:
    """Envoie le récap du dimanche. `preview_to` : tout envoyer à cette adresse (aperçu pour le coach :
    le bilan du coach et UN récap élève d'exemple)."""
    today = today or date.today()
    settings = load_settings(store)
    url = config.app_url or app_url
    states = [historique.program_state(store, s) for s in profils.list_students(store)]
    out: list[Sent] = []
    if preview_to:
        digest = coach_digest(store, states, config, url, preview_to, today)
        if digest is not None:
            out.append(_send(digest, config, dry_run))
        for st in states:
            sample = student_recap(store, st, config, url, today, to=preview_to)
            if sample is not None:
                sample.replace_header("Subject", f"[Aperçu élève : {st.student.display_name}] {sample['Subject']}")
                out.append(_send(sample, config, dry_run))
                break
        return out
    if settings.recap_eleves:
        for st in states:
            if not st.suivi.recap:
                continue
            msg = student_recap(store, st, config, url, today)
            if msg is not None:
                out.append(_send(msg, config, dry_run))
    if settings.recap_coach:
        digest = coach_digest(store, states, config, url, coach_address(config, settings), today)
        if digest is not None:
            out.append(_send(digest, config, dry_run))
    return out


# ----------------------------------------------------------------------------
# Notifications immédiates
# ----------------------------------------------------------------------------
def report_email(student, report, config: EmailConfig, to: str, app_url: str = "") -> EmailMessage:
    """E-mail au coach : un élève signale une douleur, une absence ou une maladie."""
    subject = f"{student.display_name} signale : {report.label} {report.period}"
    text = (f"{student.display_name} ({student.race_name}) a signalé : {report.label} {report.period}.\n"
            + (f"Son message : « {report.comment} »\n" if report.comment else "")
            + "\nTu peux lui répondre depuis la Supervision (« À surveiller »).\n"
            + (f"{app_url}\n" if app_url else ""))
    body = (f"<p><b>{e(student.display_name)}</b> ({e(student.race_name)}) a signalé :</p>"
            f"<p style='font-size:18px;font-weight:bold'>{e(report.label)} {e(report.period)}</p>"
            + (f"<p style='border-left:3px solid {CHRONO};padding-left:10px'>« {e(report.comment)} »</p>"
               if report.comment else "")
            + "<p>Tu peux lui répondre depuis la Supervision, dans « À surveiller ».</p>"
            + _button(app_url, "Ouvrir l'application"))
    return _message(config, to, subject, text, body)


def reply_email(student, about: str, texte: str, config: EmailConfig, app_url: str = "") -> EmailMessage:
    """E-mail à l'élève : son coach lui a répondu."""
    name = student.prenom or ""
    subject = "Ton coach t'a répondu"
    text = (f"Bonjour {name},\n\n" if name else "Bonjour,\n\n") + \
        f"Ton coach t'a répondu à propos de « {about} » :\n\n« {texte} »\n\n" + \
        (f"Ouvre ton plan : {app_url}\n" if app_url else "") + f"\n{config.sender_name}\n"
    body = (f"<p>{'Bonjour ' + e(name) + ',' if name else 'Bonjour,'}</p>"
            f"<p>Ton coach t'a répondu à propos de <b>{e(about)}</b> :</p>"
            f"<p style='border-left:3px solid {CHRONO};padding-left:10px;white-space:pre-wrap'>{e(texte)}</p>"
            + _button(app_url, "Ouvrir mon plan") + f"<p>{e(config.sender_name)}</p>")
    return _message(config, student.email, subject, text, body)


def send_now(msg: EmailMessage, config: EmailConfig | None) -> tuple[bool, str]:
    if config is None:
        return False, "e-mails non configurés"
    sent = _send(msg, config, dry_run=False)
    return sent.ok, sent.message
