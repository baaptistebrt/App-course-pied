"""
Blocs de l'espace élève ajoutés en v9 : signaler une douleur ou une absence, réponses du coach à
lire, checklist du jour J, records personnels, ajout à l'agenda, récap du dimanche.
"""

from __future__ import annotations

import html
import re
from datetime import date, timedelta

import streamlit as st

from core import agenda, recap, reglages, reponses, suivi
from core.config import COMMENT_MAX
from core.emails import load_email_config
from core.exports import fr_date
from core.plan import is_race_day
from ui import composants as ui
from ui.design import reply_html, render, session_title

e = html.escape

EXTRAS_CSS = """
.medals { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 0 0 14px; }
.medal { background: #fff; border-radius: 14px; padding: 14px 16px; border-top: 6px solid var(--chrono);
         box-shadow: 0 6px 18px rgba(15,42,74,.08); }
.medal .m-h { display: flex; align-items: center; gap: 8px; font-weight: 600; color: var(--muted); }
.medal .m-h span { font-size: 1.5rem; }
.medal .m-t { font-family: var(--cond); font-weight: 800; font-size: 2.2rem; color: var(--night); line-height: 1.05;
              font-variant-numeric: tabular-nums; }
.medal .m-s { color: var(--muted); font-size: .86rem; }
.medal .m-up { color: #17603F; font-weight: 600; font-size: .86rem; }
.rp { display: flex; gap: 12px; align-items: flex-start; }
.rp .rp-i { font-size: 1.6rem; line-height: 1; }
.rp .rp-t { font-family: var(--cond); font-weight: 700; font-size: 1.3rem; color: var(--night); line-height: 1.1; }
.rp .rp-s { color: var(--muted); font-size: .9rem; }
.rp q { quotes: none; display: block; font-style: italic; color: var(--night); margin-top: 4px; }
[class*="st-key-"][class*="card-report"] { background: #fff; border-radius: 14px; padding: 14px 18px;
    border-left: 8px solid #3D5A80; }
[class*="st-key-"][class*="card-report-douleur"] { border-left-color: #CF2E3F; }
[class*="st-key-"][class*="card-reply"] { background: #FFF8E1; border-radius: 14px; padding: 14px 18px;
    border-left: 8px solid var(--chrono); }
[class*="st-key-"][class*="card-check"] { background: #fff; border-radius: 14px; padding: 14px 18px;
    border-left: 8px solid var(--chrono); }
.ck-h { font-weight: 700; color: var(--track); margin: 6px 0 0; }
"""

_ICONS = {"douleur": "🩹", "absence": "🏖️", "maladie": "🤒"}


def css() -> None:
    st.html(f"<style>{EXTRAS_CSS}</style>")


# ----------------------------------------------------------------------------
# Signaler une douleur, une absence ou une maladie
# ----------------------------------------------------------------------------
def _notify_coach(student, report) -> None:
    """E-mail au coach (si les e-mails sont configurés et l'option activée dans les Réglages)."""
    store = ui.app_store()
    cfg = load_email_config()
    settings = reglages.load_settings(store)
    if cfg is None or not settings.alertes_email:
        return
    ok, _ = recap.send_now(recap.report_email(student, report, cfg, recap.coach_address(cfg, settings),
                                              cfg.app_url), cfg)
    if not ok:
        print(f"[signalement] e-mail au coach non envoyé pour {student.id}", flush=True)


@st.dialog("Signaler à mon coach")
def report_dialog(student) -> None:
    store = ui.app_store()
    today = date.today()
    kind = st.segmented_control("Que veux-tu signaler ?", list(suivi.REPORT_KINDS), default="douleur", required=True,
                                format_func=lambda k: {"douleur": "🩹 Une douleur", "absence": "🏖️ Une absence",
                                                       "maladie": "🤒 Je suis malade"}[k], key="rep_kind")
    zone, level, start, end = "", None, today, None
    if kind == "douleur":
        c1, c2 = st.columns(2)
        zone = c1.selectbox("Où ?", suivi.PAIN_ZONES, key="rep_zone")
        start = c2.date_input("Depuis le", value=today, max_value=today, format="DD/MM/YYYY", key="rep_since")
        level = st.segmented_control("Intensité", list(suivi.PAIN_LEVELS), default=2, required=True,
                                     format_func=lambda n: suivi.PAIN_LEVELS[n].capitalize(), key="rep_level")
        st.caption("Une douleur qui t'empêche de courir normalement ou qui augmente : arrête-toi et consulte un "
                   "médecin.")
    elif kind == "absence":
        period = st.date_input("Du… au…", value=(today, today + timedelta(days=6)), min_value=today - timedelta(days=7),
                               format="DD/MM/YYYY", key="rep_period",
                               help="Vacances, déplacement, travail : tes séances de ces jours-là seront signalées")
        if isinstance(period, (tuple, list)) and len(period) == 2:
            start, end = period
        elif isinstance(period, (tuple, list)) and len(period) == 1:
            start, end = period[0], period[0]
    else:
        c1, c2 = st.columns(2)
        start = c1.date_input("Depuis le", value=today, max_value=today, format="DD/MM/YYYY", key="rep_sick")
        end = c2.date_input("Jusqu'au (si tu sais)", value=None, min_value=start, format="DD/MM/YYYY", key="rep_sick_end")
    comment = st.text_area("Un mot pour ton coach (facultatif)", key="rep_comment", max_chars=COMMENT_MAX, height=90,
                           placeholder="Ce que tu ressens, depuis quand, ce que tu as fait…")
    if st.button("Envoyer à mon coach", type="primary", icon=":material/send:", width="stretch"):
        try:
            report = suivi.add_report(store, student.id, kind, start, end, zone, level, comment)
        except ValueError as exc:
            st.error(str(exc))
            return
        _notify_coach(student, report)
        ui.saved("C'est noté : ton coach est prévenu")
        st.rerun()


def report_button(student, readonly: bool, prefix: str) -> None:
    if st.button("Signaler", icon=":material/healing:", key=f"{prefix}_report", disabled=readonly,
                 help="Une douleur, une absence (vacances…) ou une maladie : ton coach est prévenu"):
        report_dialog(student)


def reports_banner(student, sv: suivi.Suivi, coach: reponses.CoachFile, readonly: bool, prefix: str) -> None:
    """Signalements en cours (ou à venir), avec la réponse du coach et « Je vais mieux » / « Je suis de retour »."""
    store = ui.app_store()
    today = date.today()
    shown = [r for r in sv.reports if not r.closed and (r.kind == "douleur" or r.active(today) or r.upcoming(today))]
    for rep in reversed(shown):
        def close(rid: str = rep.id, label: str = rep.label) -> None:
            suivi.close_report(store, student.id, rid)
            ui.saved(f"{label} : c'est noté, bonne reprise !")

        def delete(rid: str = rep.id) -> None:
            suivi.delete_report(store, student.id, rid)
            ui.saved("Signalement supprimé")

        with st.container(key=f"{prefix}-card-report-{rep.kind}-{rep.id}"):
            quote = f"<q>« {e(rep.comment)} »</q>" if rep.comment else ""
            state = "à venir" if rep.upcoming(today) else "en cours"
            render(f"<div class='rp'><span class='rp-i'>{_ICONS.get(rep.kind, '⚠️')}</span><div>"
                   f"<div class='rp-t'>{e(rep.label)}</div><div class='rp-s'>{e(rep.period)} · {state}, ton coach est "
                   f"prévenu</div>{quote}{reply_html(coach.reply(reponses.signal_key(rep.id)))}</div></div>")
            with st.container(horizontal=True, gap="small"):
                if rep.kind == "douleur":
                    st.button("Je vais mieux", icon=":material/favorite:", key=f"{prefix}_rpclose_{rep.id}",
                              on_click=close, disabled=readonly, type="primary")
                elif rep.active(today):
                    st.button("Je suis de retour", icon=":material/directions_run:", key=f"{prefix}_rpclose_{rep.id}",
                              on_click=close, disabled=readonly, type="primary")
                st.button("Supprimer" if rep.kind != "absence" or rep.active(today) else "Annuler l'absence",
                          type="tertiary", key=f"{prefix}_rpdel_{rep.id}", on_click=delete, disabled=readonly,
                          help="Si tu l'as signalé par erreur")


# ----------------------------------------------------------------------------
# Réponses du coach à lire
# ----------------------------------------------------------------------------
def about_label(key: str, table, sv: suivi.Suivi) -> str:
    if key.startswith("signal:"):
        rep = next((r for r in sv.reports if reponses.signal_key(r.id) == key), None)
        return rep.label.lower() if rep else "ton signalement"
    rows = table[table["session_id"] == key] if not table.empty else table
    if len(rows):
        r = rows.iloc[0]
        return "ta course" if is_race_day(r["seance"]) else session_title(r)
    return "une séance"


def replies_card(student, sv: suivi.Suivi, coach: reponses.CoachFile, table, readonly: bool, prefix: str) -> None:
    unread = reponses.unread(coach, sv.reponses_vues_le)
    if not unread:
        return
    store = ui.app_store()

    def seen() -> None:
        suivi.mark_replies_seen(store, student.id)

    with st.container(key=f"{prefix}-card-reply"):
        n = len(unread)
        render(f"<div class='ask'>💬 Ton coach t'a répondu{f' ({n} messages)' if n > 1 else ''}</div>")
        for key, rep in unread[:3]:
            render(f"<div style='margin-top:8px'><b>À propos de {e(about_label(key, table, sv))}</b> "
                   f"<span style='color:var(--muted);font-size:.85rem'>{rep.le[8:10]}/{rep.le[5:7]}</span>"
                   f"<div style='white-space:pre-wrap'>{e(rep.texte)}</div></div>")
        if n > 3:
            st.caption(f"Et {n - 3} autre(s) : retrouve-les sous tes séances et dans Mon carnet.")
        st.button("OK, j'ai lu", icon=":material/done_all:", key=f"{prefix}_seen", on_click=seen, disabled=readonly)


# ----------------------------------------------------------------------------
# Checklist du jour J
# ----------------------------------------------------------------------------
def checklist(student, sv: suivi.Suivi, readonly: bool, prefix: str, columns: int = 2) -> None:
    store = ui.app_store()
    groups = reglages.checklist_for(reglages.load_checklist(store), student.distance)
    if not groups:
        st.caption("Ton coach n'a pas encore préparé de checklist.")
        return
    total = sum(len(items) for _, items in groups)
    done = sum(1 for _, items in groups for i in items if i.key in sv.checklist)
    st.caption(f"{done} sur {total} : coche au fur et à mesure, c'est enregistré.")

    def toggle(item_key: str, widget_key: str) -> None:
        suivi.set_checklist_item(store, student.id, item_key, bool(st.session_state.get(widget_key)))

    cols = st.columns(columns) if columns > 1 else [st.container()]
    for n, (moment, items) in enumerate(groups):
        with cols[n % len(cols)]:
            render(f"<div class='ck-h'>{e(moment)}</div>")
            for item in items:
                wk = f"{prefix}_ck_{item.key}"
                st.checkbox(item.texte, value=item.key in sv.checklist, key=wk, disabled=readonly,
                            on_change=toggle, args=(item.key, wk))


def checklist_card(student, sv: suivi.Suivi, readonly: bool, prefix: str, days_left: int | None) -> None:
    """Carte « Ta checklist du jour J » la dernière semaine avant la course."""
    if days_left is None or not 0 <= days_left <= 7 or sv.temps_realise:
        return
    with st.container(key=f"{prefix}-card-check"):
        when = "aujourd'hui" if days_left == 0 else ("demain" if days_left == 1 else f"dans {days_left} jours")
        render(f"<div class='ask'>✅ Ta checklist du jour J<small>Ta course, c'est {when} : prépare-toi "
               "sereinement.</small></div>")
        checklist(student, sv, readonly, prefix + "c")


# ----------------------------------------------------------------------------
# Records personnels
# ----------------------------------------------------------------------------
def records_html(prs: list) -> str:
    if not prs:
        return ""
    cards = []
    for p in prs:
        when = f" · {fr_date(p.race_date, True)}" if p.race_date else ""
        up = f"<div class='m-up'>{e(p.improvement)}</div>" if p.improvement else ""
        cards.append(f"<div class='medal'><div class='m-h'><span>🥇</span>Record {e(p.label)}</div>"
                     f"<div class='m-t'>{e(p.time_str)}</div><div class='m-s'>{e(p.pace_str)} · {e(p.course)}{e(when)}"
                     f"</div>{up}</div>")
    return f"<div class='medals'>{''.join(cards)}</div>"


# ----------------------------------------------------------------------------
# Agenda et récap du dimanche
# ----------------------------------------------------------------------------
def agenda_button(student, table, paces, prefix: str) -> None:
    cfg = load_email_config()
    content, count = agenda.ics_calendar(student, table, paces, cfg.app_url if cfg else "")
    name = re.sub(r"[^\w-]+", "_", f"seances_{student.race_name}").strip("_")
    st.download_button(
        "Agenda", content, file_name=f"{name}.ics", mime="text/calendar", icon=":material/calendar_month:",
        key=f"{prefix}_ics", on_click="ignore", disabled=count == 0,
        help=("Ajoute tes séances à venir à l'agenda de ton téléphone, avec un rappel à 8 h le jour même. Ouvre le "
              "fichier téléchargé (iPhone : « Tout ajouter »). Sur Android, si l'agenda ne l'ouvre pas, importe-le "
              "sur calendar.google.com (Paramètres > Importer). Après un changement de ton plan, télécharge-le à "
              "nouveau.") if count else "Ton plan n'a pas encore de dates : il en aura quand la date de ta course sera fixée.")


def recap_toggle(student, sv: suivi.Suivi, readonly: bool, prefix: str) -> None:
    store = ui.app_store()
    if load_email_config() is None or not student.email or not reglages.load_settings(store).recap_eleves:
        return

    def change(key: str) -> None:
        wanted = bool(st.session_state.get(key))
        suivi.set_recap(store, student.id, wanted)
        ui.saved("Récap du dimanche activé" if wanted else "Récap du dimanche désactivé")

    key = f"{prefix}_recap_{int(sv.recap)}"
    st.toggle("Recevoir chaque dimanche soir le récap de ma semaine par e-mail", value=sv.recap, key=key,
              on_change=change, args=(key,), disabled=readonly)
