"""
Onglet élève « Mon Planning » (il remplace aussi l'ancien onglet « Mon plan ») :

* navigation par semaine en haut (onglets soulignés ; ✓ = semaine bouclée) ;
* en-tête de la semaine : numéro, dates, « Cette semaine », volume, séances faites, phase, barre
  de progression ;
* les séances groupées par jour (« AUJOURD'HUI », « MERCREDI 27 »…), une carte par séance :
  icône du type d'activité, case à cocher avec le titre, bouton « Ressenti », puis « Intensité : … »
  (texte libre du coach), kilomètres, durée, temps à l'allure, remarque et pastilles d'allure ;
  le jour J a sa carte jaune avec « Mon chrono » ;
* en bas, « Modifier ma semaine » (2, 3 ou 4 séances pour cette semaine seulement).

Les cases et boutons sont fournis par l'espace élève (ui/eleve.py, `Controls`) : ce module ne fait
que la mise en page. Les séances retirées d'une semaine sont seulement masquées
(core/plan.select_sessions) : elles réapparaissent intactes, avec leur suivi, si l'élève remet des séances.
"""

from __future__ import annotations

import base64
import html
from datetime import date
from typing import Callable, NamedTuple

import pandas as pd
import streamlit as st

from core import suivi
from core.agenda import place_sessions, suggested_days, week_plan_sessions  # noqa: F401 (réexportés)
from core.config import PACE_CODES, WEEK_COUNTS, ZONE_COLORS
from core.plan import ACTIVITY_LABELS, FREQ_ONLY_4, activity_kind, is_race_day, pace_codes, select_sessions
from ui import composants as ui
from ui.design import CHRONO, pills, render, reply_html, session_title, week_header

e = html.escape
WEEKDAYS_FULL = ["LUNDI", "MARDI", "MERCREDI", "JEUDI", "VENDREDI", "SAMEDI", "DIMANCHE"]
DONE_GREEN = "#2F9E6E"

# Icônes (traits, 24 × 24), d'après les jeux libres Feather / Lucide.
_ICONS = {
    "course": "<path d='M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z'/><line x1='4' y1='22' x2='4' y2='15'/>",
    "fractionne": "<polygon points='13 2 3 14 12 14 11 22 21 10 12 10 13 2'/>",
    "seuil": ("<path d='M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.07-2.14-.22-4.05 2-6 .5 2.5 2 4.9 4 6.5 "
              "2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.15.43-2.29 1-3a2.5 2.5 0 0 0 2.5 2.5z'/>"),
    "progressif": "<polyline points='23 6 13.5 15.5 8.5 10.5 1 18'/><polyline points='17 6 23 6 23 12'/>",
    "allure": "<circle cx='12' cy='13' r='8'/><polyline points='12 9 12 13 14.5 15.5'/><line x1='9' y1='2' x2='15' y2='2'/>",
    "longue": ("<polygon points='1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6'/><line x1='8' y1='2' x2='8' y2='18'/>"
               "<line x1='16' y1='6' x2='16' y2='22'/>"),
    "footing": ("<path d='M9.59 4.59A2 2 0 1 1 11 8H2m10.59 11.41A2 2 0 1 0 14 16H2m15.73-8.27A2.5 2.5 0 1 1 "
                "19.5 12H2'/>"),
}

PLANNING_CSS = """
/* Navigation par semaine : onglets texte soulignés, défilement horizontal */
[class*="st-key-"][class*="plan-week"] [role="radiogroup"] { flex-wrap: nowrap; overflow-x: auto; scrollbar-width: none;
    position: relative; gap: 0; border-bottom: 1px solid #E3E9F0; padding: 0; }
[class*="st-key-"][class*="plan-week"] [role="radiogroup"]::-webkit-scrollbar { display: none; }
[class*="st-key-"][class*="plan-week"] [role="radiogroup"] button { flex: 0 0 auto; background: transparent !important;
    border: 0 !important; border-bottom: 3px solid transparent !important; border-radius: 0 !important;
    box-shadow: none !important; padding: 8px 14px 7px !important; color: #8A97A8 !important; }
[class*="st-key-"][class*="plan-week"] [role="radiogroup"] button p { font-size: .95rem; }
[class*="st-key-"][class*="plan-week"] [role="radiogroup"] button[aria-checked="true"] {
    color: var(--night) !important; border-bottom-color: var(--track) !important; }
[class*="st-key-"][class*="plan-week"] [role="radiogroup"] button[aria-checked="true"] p { font-weight: 600; }
[class*="st-key-"][class*="card-planning"] { background: #fff; border-radius: 16px; padding: 10px 16px 14px; }
[class*="st-key-"][class*="card-planning"] .wh { margin-top: 10px; }
.pl-prog { height: 7px; background: var(--concrete); border-radius: 4px; margin: 6px 0 2px; overflow: hidden; }
.pl-prog span { display: block; height: 100%; background: var(--chrono); border-radius: 4px; }
/* Jours et cartes de séance */
.pl-day { font-weight: 600; font-size: .78rem; letter-spacing: .05em; color: #7A8899; margin: 14px 2px 0; }
.pl-day.today { color: var(--track); }
[class*="st-key-"][class*="-plc-"] { background: #fff; border: 1px solid #E3E9F0; border-radius: 14px;
    padding: 10px 14px 12px; gap: .2rem; }
[class*="st-key-"][class*="-plc-"] [data-testid="stCheckbox"] label p { font-weight: 600; font-size: 1rem;
    color: var(--night); line-height: 1.3; }
[class*="st-key-"][class*="-plc-"] [data-testid="stPopover"] button { white-space: nowrap; }
.pl-ico { width: 38px; height: 38px; border-radius: 50%; display: grid; place-items: center; }
.pl-ico img { width: 22px; height: 22px; }
.pl-title { font-family: var(--cond); font-weight: 800; font-size: 1.3rem; color: var(--night); line-height: 1.15; }
.pl-body { margin-left: 50px; }
.pl-int { font-size: .9rem; color: var(--night); }
.pl-int span { color: var(--muted); }
.pl-meta { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 6px 14px; align-items: center;
           margin-top: 4px; }
.pl-note { color: var(--muted); font-size: .82rem; margin: 6px 2px 0; }
.pl-run { color: #17603F; font-weight: 600; font-size: .9rem; margin-top: 6px; }
.pl-skip { color: #B4532A; font-weight: 600; font-size: .9rem; margin-top: 6px; }
.pl-away { color: #3D5A80; font-size: .9rem; margin-top: 6px; }
[class*="st-key-"][class*="-plf-"] { padding-left: 50px; min-height: 0; }
[class*="st-key-"][class*="-plf-"] [data-testid="stPopover"] button { min-height: 2rem; padding-top: .15rem;
    padding-bottom: .15rem; }
/* « Modifier ma semaine » : lien souligné, centré */
[class*="st-key-"][class*="plan-edit"] button { border: 0 !important; border-bottom: 3px solid var(--track) !important;
    border-radius: 0 !important; background: transparent !important; padding: 6px 2px !important; }
[class*="st-key-"][class*="plan-edit"] button p { font-weight: 600; color: var(--night); font-size: .98rem; }
@media (max-width: 640px) {
  .pl-body { margin-left: 0; }
  [class*="st-key-"][class*="-plf-"] { padding-left: 0; }
  .pl-meta .pills { justify-content: flex-start; }
  [class*="st-key-"][class*="card-planning"] { padding: 8px 10px 12px; }
  [class*="st-key-"][class*="-plc-"] { padding: 10px 10px 12px; }
}
"""
NAV_MONTHS = ["janv", "févr", "mars", "avr", "mai", "juin", "juil", "août", "sept", "oct", "nov", "déc"]


class Controls(NamedTuple):
    """Boutons d'une séance, fournis par l'espace élève (ils enregistrent dans le suivi de l'élève)."""
    check: Callable[[pd.Series], None]      # case à cocher « faite », avec le titre de la séance
    feel: Callable[[pd.Series], None]       # bouton « Ressenti » (ressenti, km réels, commentaire)
    race: Callable[[pd.Series], None]       # bouton « Mon chrono » du jour J
    skip: Callable[[pd.Series], None] | None = None        # bouton « Pas faite »
    checklist: Callable[[pd.Series], None] | None = None   # bouton « Ma checklist » du jour J


def _icon(kind: str, stroke: str = "white") -> str:
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' "
           f"stroke='{stroke}' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>{_ICONS[kind]}</svg>")
    return f"<img src='data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}' alt=''>"


def _tint(hex_color: str, keep: float = 0.16) -> str:
    """Couleur très claire (fond de carte) : la couleur mélangée au blanc."""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    mix = lambda c: round(255 - (255 - c) * keep)  # noqa: E731
    return f"#{mix(r):02X}{mix(g):02X}{mix(b):02X}"


def _color(row, kind: str) -> tuple[str, str]:
    """(couleur pleine, texte sur cette couleur) : jour de course en jaune, sinon l'allure la plus intense."""
    if kind == "course":
        return CHRONO, "#1A1A1A"
    codes = pace_codes(row["allure"])
    if not codes:
        return ZONE_COLORS["Endurance"]
    return ZONE_COLORS[max(codes, key=PACE_CODES.index)]


def week_label(sub: pd.DataFrame, today: date) -> str:
    first = sub.iloc[0]
    start, end = first["debut"], first["fin"]
    if not isinstance(start, date):
        return f"Semaine {int(first['position']) + 1}"
    if start <= today <= end:
        return "Cette semaine"
    return f"{start.day} {NAV_MONTHS[start.month - 1]}-{end.day} {NAV_MONTHS[end.month - 1]}"


def day_label(wd: int, day: date | None, today: date) -> str:
    if day == today:
        return "<div class='pl-day today'>AUJOURD'HUI</div>"
    return f"<div class='pl-day'>{WEEKDAYS_FULL[wd]}{f' {day.day}' if day else ''}</div>"


def session_details(r, paces: dict, race_time: str = "") -> str:
    """Sous le titre : « Intensité : … », kilomètres, durée, temps à l'allure, remarque et pastilles."""
    race = is_race_day(r["seance"])
    intensity = str(r.get("intensite") or "").strip()
    items = [f"{r['km_env']} km" if r["km_env"] else "", r["duree_env"],
             f"dont {r['temps_aff']} à l'allure" if r["temps_aff"] and not race else ""]
    meta = "".join(f"<span>{e(str(x))}</span>" for x in items if x)
    if r["remarque"]:
        meta += f"<span class='note'>{e(str(r['remarque']))}</span>"
    out = f"<div class='pl-int'><span>Intensité :</span> {e(intensity)}</div>" if intensity else ""
    tags = pills(r["allure"], paces)
    if meta or tags:
        out += f"<div class='pl-meta'><span class='meta'>{meta}</span>{tags}</div>"
    return f"<div class='pl-body'>{out}</div>" if out else ""


def status_html(r, state, day: date | None, coach=None, who: str = "Ton coach", show_skip: bool = True) -> str:
    """Sous les détails : km réellement courus, « pas faite », absence signalée, réponse du coach."""
    sv = state.suivi
    sid = r["session_id"]
    done = suivi.is_done(r, sv)
    parts = []
    km = sv.km.get(sid)
    if km and done:
        planned = f" (prévu {e(str(r['km_env']))} km)" if r["km_env"] else ""
        parts.append(f"<div class='pl-run'>✓ {suivi.fr_km(km)} km courus{planned}</div>")
    skip = sv.skipped.get(sid) if not done else None
    if skip is not None and show_skip:
        parts.append(f"<div class='pl-skip'>✗ Pas faite{' : ' + e(skip.raison) if skip.raison else ''}</div>")
    away = sv.absence_on(day) if (day is not None and not done) else None
    if away is not None:
        parts.append(f"<div class='pl-away'>🏖️ {e(away.label)} signalée {e(away.period)}</div>")
    reply = coach.reply(sid) if coach is not None else None
    if reply is not None:
        parts.append(reply_html(reply, who))
    return f"<div class='pl-body'>{''.join(parts)}</div>" if parts else ""


def card_style(key: str, kind: str, color: str, is_today: bool, done: bool, skipped: bool = False,
               away: bool = False) -> str:
    """Couleurs d'une carte : jour J en jaune, séance faite en vert pâle, « pas faite » en rouge pâle,
    absence en gris, séance du jour teintée."""
    sel = f'[class*="st-key-"][class*="{key}"]'
    if kind == "course":
        return f"{sel} {{ background: #FFF6D6; border: 2px solid {CHRONO}; }}"
    if done:
        return f"{sel} {{ background: #F3FAF6; border-color: #BFE3D0; }}"
    if skipped:
        return f"{sel} {{ background: #FDF4F1; border-color: #F1C9BC; }}"
    if away:
        return f"{sel} {{ background: #F6F8FB; border-style: dashed; }}"
    if is_today:
        return f"{sel} {{ background: {_tint(color, .12)}; border-color: {color}; box-shadow: 0 0 0 1px {color}; }}"
    return ""


def icon_html(kind: str, color: str, filled: bool) -> str:
    label = e(ACTIVITY_LABELS[kind])
    if filled:
        return (f"<span class='pl-ico' title='{label}' style='background:{color}'>"
                f"{_icon(kind, '#1A1A1A' if kind == 'course' else 'white')}</span>")
    return f"<span class='pl-ico' title='{label}' style='background:{_tint(color, .14)}'>{_icon(kind, color)}</span>"


_plan_week_sessions = week_plan_sessions      # ancien nom, gardé pour compatibilité


def natural_count(plan_sessions: pd.DataFrame, frequency: int) -> int:
    """Nombre de séances de la semaine selon la fréquence choisie (sans modification de la semaine)."""
    if frequency >= 4:
        return len(plan_sessions)
    kept = plan_sessions[plan_sessions["frequence"] != FREQ_ONLY_4]
    if frequency == 2:
        kept = select_sessions(kept.reset_index(drop=True), 2)
    return len(kept)


@st.dialog("Modifier ma semaine")
def _edit_week(student_id: str, week_id: str, label: str, available: int, current: int, natural: int,
               overridden: bool) -> None:
    store = ui.app_store()
    options = [n for n in WEEK_COUNTS if n <= available] + ([available] if available > max(WEEK_COUNTS) else [])
    st.markdown(f"**{label}** : choisis combien de séances tu fais cette semaine. Les autres semaines de ton plan "
                "ne changent pas.")
    choice = st.segmented_control("Séances cette semaine", options, default=current if current in options
                                  else max(options), format_func=lambda n: f"{n} séances", required=True,
                                  key=f"wk_choice_{week_id}")
    st.caption("En réduisant, ce sont les séances du milieu de semaine qui sont masquées : la première et la "
               "dernière restent. Elles réapparaissent telles quelles si tu en remets.")
    if available < max(WEEK_COUNTS):
        st.caption(f"Ton plan prévoit {available} séances au plus cette semaine : tu peux en faire moins, pas plus.")
    c1, c2 = st.columns(2)
    if c1.button("Enregistrer", type="primary", icon=":material/check:", width="stretch"):
        suivi.set_week_count(store, student_id, week_id, None if choice == natural else choice)
        ui.saved(f"{label} : {choice} séances")
        st.rerun()
    if overridden and c2.button("Revenir au plan prévu", width="stretch"):
        suivi.set_week_count(store, student_id, week_id, None)
        ui.saved(f"{label} : plan prévu rétabli")
        st.rerun()


def _session_card(r, day: date | None, today: date, state, prefix: str, controls: Controls, coach=None) -> str:
    """Une carte de séance (widgets Streamlit). Renvoie sa règle de style.

    En haut : icône + case « faite » avec le titre (jour J : titre + « Mon chrono ») ; au milieu : intensité,
    km, durée, allures, puis km réels, « pas faite », absence, réponse du coach ; en bas : « Pas faite »
    et « Ressenti » (jour J : « Ma checklist »)."""
    sid = r["session_id"]
    kind = activity_kind(r)
    color, _ = _color(r, kind)
    is_today = day == today
    sv = state.suivi
    done = suivi.is_done(r, sv)
    skipped = suivi.is_skipped(r, sv)
    away = day is not None and not done and sv.absence_on(day) is not None
    key = f"{prefix}-plc-{sid}"
    with st.container(key=key):
        with st.container(horizontal=True, vertical_alignment="center", gap="small", wrap=False):
            st.html(icon_html(kind, color, filled=is_today or kind == "course"), width=38)
            if kind == "course":
                chrono = state.progress.race_time
                st.html(f"<div class='pl-title'>🏁 Jour J{f' : {e(chrono)}' if chrono else ''}</div>")
                controls.race(r)
            else:
                controls.check(r)
        details = session_details(r, state.sp.paces) + status_html(r, state, day, coach)
        if details:
            render(details)
        with st.container(horizontal=True, gap="small", vertical_alignment="center", key=f"{prefix}-plf-{sid}"):
            if kind == "course":
                if controls.checklist is not None:
                    controls.checklist(r)
            else:
                if controls.skip is not None and not done:
                    controls.skip(r)
                controls.feel(r)
    return card_style(f"-plc-{sid}", kind, color, is_today, done, skipped, away)


def week_nav(table: pd.DataFrame, sv, today: date, key: str) -> tuple[int, pd.DataFrame, int]:
    """Barre de navigation par semaine (✓ = semaine bouclée). Renvoie (position, séances, nb faites)."""
    positions = [int(p) for p in sorted(table["position"].unique())]
    weeks = {p: table[table["position"] == p] for p in positions}
    done_in = {p: sum(1 for _, r in w.iterrows() if suivi.is_done(r, sv)) for p, w in weeks.items()}
    labels = {p: week_label(w, today) + (" ✓" if done_in[p] == len(w) else "") for p, w in weeks.items()}
    default = next((p for p in positions if labels[p].startswith("Cette semaine")), None)
    if default is None:
        pending = [int(r["position"]) for _, r in table.iterrows() if not suivi.is_done(r, sv)]
        default = pending[0] if pending else positions[-1]
    if key in st.session_state and st.session_state[key] not in positions:     # semaine disparue
        del st.session_state[key]
    pos = st.pills("Semaine", positions, default=default, format_func=labels.get, key=key, required=True,
                   label_visibility="collapsed")
    return pos, weeks[pos], done_in[pos]


def week_head_html(sub: pd.DataFrame, pos: int, today: date, n_done: int, extra: str = "") -> str:
    """En-tête de la semaine (numéro, dates, volume, séances faites, phase) et barre de progression."""
    count = f"{n_done}/{len(sub)} faite{'s' if n_done > 1 else ''}"
    head, _ = week_header(sub, pos, today, f"{count}{extra}")
    pct = round(100 * n_done / len(sub)) if len(sub) else 0
    return (f"{head}<div class='pl-prog' role='img' aria-label='{n_done} séance(s) faite(s) sur {len(sub)}'>"
            f"<span style='width:{pct}%'></span></div>")


def center_nav(key: str) -> None:
    """Garde la semaine choisie visible dans la barre de navigation (défilement horizontal sur téléphone)."""
    st.html(f"""<script>
(function () {{
  const run = () => {{
    const nav = document.querySelector('.st-key-{key} [role="radiogroup"]');
    if (!nav) return setTimeout(run, 150);
    const center = () => {{
      const sel = nav.querySelector('[aria-checked="true"]');
      if (sel && nav.clientWidth) nav.scrollLeft = sel.offsetLeft - nav.clientWidth / 2 + sel.clientWidth / 2;
    }};
    center();
    if (!nav.dataset.watch) {{
      nav.dataset.watch = "1";
      new IntersectionObserver(es => es.forEach(x => x.isIntersecting && center())).observe(nav);
    }}
  }};
  run();
}})();
</script>""", unsafe_allow_javascript=True)


def render_planning(student, state, readonly: bool, prefix: str, controls: Controls, coach=None) -> None:
    """Contenu de l'onglet « Mon Planning ». `coach` : réponses du coach (core/reponses.CoachFile)."""
    table, sv = state.table, state.suivi
    today = date.today()
    st.html(f"<style>{PLANNING_CSS}</style>")
    if table.empty:
        render("<div class='empty'>Ton plan ne contient encore aucune séance : ton coach le prépare.</div>")
        return
    key = f"{prefix}-plan-week"
    with st.container(key=f"{prefix}-card-planning"):
        pos, sub, n_done = week_nav(table, sv, today, key)
        week_id = sub["week_id"].iloc[0]
        render(week_head_html(sub, pos, today, n_done))

        plan_sessions = _plan_week_sessions(student, week_id)
        placed, suggested = place_sessions(sub, suggested_days(plan_sessions, student.date_course))
        styles, current = [], None
        for wd, day, r in placed:
            if wd != current:
                current = wd
                render(day_label(wd, day, today))
            styles.append(_session_card(r, day, today, state, prefix, controls, coach))
        st.html(f"<style>{''.join(s for s in styles if s)}</style>")
        if suggested:
            render("<div class='pl-note'>Ton coach n'a pas fixé le jour de certaines séances : elles sont placées "
                   "dans la semaine à titre indicatif.</div>")

        available = len(plan_sessions)
        natural = natural_count(plan_sessions, state.frequency)
        overridden = week_id in sv.semaines
        if overridden:
            st.caption(f"Semaine modifiée : {len(sub)} séance{'s' if len(sub) > 1 else ''} au lieu de {natural} "
                       "prévues.")
        with st.container(horizontal=True, horizontal_alignment="center", key=f"{prefix}-plan-edit"):
            if st.button("Modifier ma semaine", type="tertiary", key=f"{prefix}_editweek_{week_id}",
                         disabled=readonly or available < min(WEEK_COUNTS),
                         help=None if available >= min(WEEK_COUNTS) else "Cette semaine ne compte qu'une séance"):
                _edit_week(student.id, week_id, week_label(sub, today), available, len(sub), natural, overridden)
    center_nav(key)


# =========================================================================== vue du coach (lecture seule)
def _fr_day(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}" if len(iso) >= 10 else ""


def coach_card_html(r, day: date | None, today: date, state, coach=None) -> str:
    """Carte d'une séance pour le coach : statut (faite le…, pas faite, non cochée, à venir), contenu,
    ressenti, km réels, absence et sa propre réponse."""
    sv = state.suivi
    sid = r["session_id"]
    kind = activity_kind(r)
    color, _ = _color(r, kind)
    race = kind == "course"
    done = suivi.is_done(r, sv)
    skip = sv.skipped.get(sid) if not done else None
    if race and sv.temps_realise:
        status, cls = f"🏁 {state.progress.race_time}", "ok"
    elif done:
        when = _fr_day(str(sv.done.get(sid, "")))
        status, cls = f"✓ Faite{f' le {when}' if when else ''}", "ok"
    elif skip is not None:
        status, cls = f"✗ Pas faite{f' ({skip.raison})' if skip.raison else ''}", "miss"
    elif day is not None and day < today:
        status, cls = "Non cochée", "miss"
    elif day == today:
        status, cls = "Aujourd'hui", "now"
    else:
        status, cls = "À venir", ""
    title = "🏁 Jour J" if race else e(session_title(r))
    note = sv.note(sid)
    feel = ""
    if not note.empty:
        quote = f" <q>{e(note.commentaire)}</q>" if note.commentaire else ""
        feel = f"<div class='pl-feel'>{e(note.label) or '💬'}{quote}</div>"
    extra = status_html(r, state, day, coach, who="Ta réponse", show_skip=False).replace("pl-body", "pl-body flat")
    card_cls = "race" if race else ("done" if done else ("miss" if cls == "miss" else ""))
    return (f"<div class='pl-card {card_cls}'>{icon_html(kind, color, filled=race or day == today)}"
            f"<div class='pl-main'><div class='pl-top'><span class='pl-title'>{title}</span>"
            f"<span class='pl-status {cls}'>{e(status)}</span></div>"
            f"{session_details(r, state.sp.paces).replace('pl-body', 'pl-body flat')}{feel}{extra}</div></div>")


COACH_CSS = """
.pl-card { display: flex; gap: 12px; align-items: flex-start; background: #fff; border: 1px solid #E3E9F0;
           border-radius: 14px; padding: 10px 14px 12px; margin: 8px 0 0; }
.pl-card.done { background: #F3FAF6; border-color: #BFE3D0; }
.pl-card.miss { background: #FBFBFC; border-style: dashed; }
.pl-card.race { background: #FFF6D6; border: 2px solid #FFC629; }
.pl-card .pl-ico { flex: 0 0 38px; }
.pl-main { flex: 1; min-width: 0; }
.pl-top { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 2px 12px; align-items: baseline; }
.pl-card .pl-title { font-family: Barlow, sans-serif; font-weight: 600; font-size: 1rem; }
.pl-card.race .pl-title { font-family: var(--cond); font-weight: 800; font-size: 1.25rem; }
.pl-status { font-size: .85rem; font-weight: 600; color: var(--muted); white-space: nowrap; }
.pl-status.ok { color: #17603F; }
.pl-status.miss { color: #B4532A; }
.pl-status.now { color: var(--track); }
.pl-body.flat { margin-left: 0; }
.pl-feel { margin-top: 6px; font-size: .92rem; color: var(--night); }
.pl-feel q { quotes: none; display: block; border-left: 3px solid var(--chrono); padding: 1px 0 1px 10px; margin-top: 4px;
             white-space: pre-wrap; font-style: italic; }
[class*="st-key-"][class*="-ccr-"] { margin-top: -6px; }
"""


def render_coach_week(student, state, key: str, coach=None) -> None:
    """Suivi du coach, semaine par semaine : même présentation que le planning de l'élève, avec le statut
    de chaque séance, les ressentis, les km réels, et un bouton « Répondre » sous chaque séance."""
    from ui.coach_reply import reply_popover      # import local : évite un import circulaire

    table, sv = state.table, state.suivi
    today = date.today()
    st.html(f"<style>{PLANNING_CSS}{COACH_CSS}</style>")
    if table.empty:
        render("<div class='empty'>Ce plan ne contient encore aucune séance.</div>")
        return
    nav_key = f"{key}-plan-week"
    with st.container(key=f"{key}-card-planning"):
        pos, sub, n_done = week_nav(table, sv, today, nav_key)
        week_id = sub["week_id"].iloc[0]
        plan_sessions = _plan_week_sessions(student, week_id)
        extra = ""
        if week_id in sv.semaines:
            extra = f", semaine réduite par l'élève à {len(sub)} (au lieu de {natural_count(plan_sessions, state.frequency)})"
        render(week_head_html(sub, pos, today, n_done, extra))
        placed, suggested = place_sessions(sub, suggested_days(plan_sessions, student.date_course))
        current = None
        for wd, day, r in placed:
            if wd != current:
                current = wd
                render(day_label(wd, day, today))
            sid = r["session_id"]
            render(coach_card_html(r, day, today, state, coach))
            with st.container(horizontal=True, horizontal_alignment="right", key=f"{key}-ccr-{sid}"):
                about = "ta course" if is_race_day(r["seance"]) else session_title(r)
                reply_popover(student, sid, about, f"{key}_rep_{sid}")
        if suggested:
            render("<div class='pl-note'>Jour non fixé dans le plan pour certaines séances : placées à titre "
                   "indicatif, comme dans l'espace de l'élève.</div>")
    center_nav(nav_key)
