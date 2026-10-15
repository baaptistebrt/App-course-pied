"""
Onglet élève « Mon Planning » : navigation par semaine en haut, puis les séances de la semaine
choisie en cartes colorées groupées par jour (« AUJOURD'HUI », « MERCREDI 27 »…), et en bas le
bouton « Modifier ma semaine » (2, 3 ou 4 séances pour cette semaine seulement).

Chaque carte : une icône selon le type d'activité, le titre de la séance et « Intensité : … »
(texte libre saisi par le coach dans le plan, reproduit tel quel).
Les séances retirées d'une semaine sont seulement masquées (core/plan.select_sessions) : elles
réapparaissent intactes, avec leur suivi, si l'élève remet des séances.
"""

from __future__ import annotations

import base64
import html
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from core import suivi
from core.config import DAYS, PACE_CODES, WEEK_COUNTS, ZONE_COLORS
from core.plan import ACTIVITY_LABELS, FREQ_ONLY_4, activity_kind, is_empty_session, is_race_day, pace_codes
from ui import composants as ui
from ui.design import CHRONO, render, session_title

e = html.escape
WEEKDAYS_FULL = ["LUNDI", "MARDI", "MERCREDI", "JEUDI", "VENDREDI", "SAMEDI", "DIMANCHE"]
# Jours conseillés quand le coach n'a pas fixé le jour d'une séance (0 = lundi), selon le nombre de séances.
SUGGESTED_DAYS = {1: [5], 2: [1, 5], 3: [1, 3, 6], 4: [1, 3, 5, 6], 5: [0, 1, 3, 5, 6], 6: [0, 1, 2, 3, 5, 6]}

# Icônes (traits blancs, 24 × 24), d'après les jeux libres Feather / Lucide.
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
/* Jours et cartes de séance */
.pl-day { font-weight: 600; font-size: .78rem; letter-spacing: .05em; color: #7A8899; margin: 18px 2px 8px; }
.pl-card { display: flex; align-items: center; gap: 14px; background: #fff; border: 1px solid #E3E9F0;
           border-radius: 14px; padding: 12px 14px; margin: 0 0 10px; }
.pl-ico { flex: 0 0 38px; width: 38px; height: 38px; border-radius: 50%; display: grid; place-items: center; }
.pl-ico img { width: 22px; height: 22px; }
.pl-title { font-weight: 600; font-size: 1rem; color: var(--night); line-height: 1.3; }
.pl-int { font-size: .88rem; color: var(--muted); margin-top: 2px; }
.pl-note { color: var(--muted); font-size: .82rem; margin: 6px 2px 0; }
[class*="st-key-"][class*="card-planning"] { background: #fff; border-radius: 16px; padding: 10px 16px 14px; }
/* « Modifier ma semaine » : lien souligné, centré */
[class*="st-key-"][class*="plan-edit"] button { border: 0 !important; border-bottom: 3px solid var(--track) !important;
    border-radius: 0 !important; background: transparent !important; padding: 6px 2px !important; }
[class*="st-key-"][class*="plan-edit"] button p { font-weight: 600; color: var(--night); font-size: .98rem; }
"""
NAV_MONTHS = ["janv", "févr", "mars", "avr", "mai", "juin", "juil", "août", "sept", "oct", "nov", "déc"]


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


def suggested_days(full: pd.DataFrame, race_date: date | None = None) -> dict[str, int]:
    """Jour (0 = lundi) de chaque séance de la semaine COMPLÈTE prévue par le coach : le jour fixé, sinon
    un jour conseillé. Calculé sur toutes les séances, pour qu'une séance garde son jour quand l'élève
    masque les autres."""
    taken, out = set(), {}
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


def week_html(sub: pd.DataFrame, today: date, days: dict[str, int]) -> str:
    """Séances de la semaine, groupées par jour. La séance du jour est mise en avant (fond teinté,
    icône pleine) ; les autres sont des cartes blanches avec l'icône dans la couleur de l'allure."""
    placed, suggested = place_sessions(sub, days)
    out, current = [], None
    for wd, day, r in placed:
        is_today = day == today
        if wd != current:
            current = wd
            out.append("<div class='pl-day'>AUJOURD'HUI</div>" if is_today else
                       f"<div class='pl-day'>{WEEKDAYS_FULL[wd]}{f' {day.day}' if day else ''}</div>")
        kind = activity_kind(r)
        color, _ = _color(r, kind)
        intensity = str(r.get("intensite") or "").strip()
        int_html = f"<div class='pl-int'>Intensité : {e(intensity)}</div>" if intensity else ""
        if is_today:
            card = f"<div class='pl-card' style='background:{_tint(color, .12)};border-color:{color}'>"
            ico = f"<span class='pl-ico' style='background:{color}'>{_icon(kind)}</span>"
        else:
            card = "<div class='pl-card'>"
            ico = f"<span class='pl-ico'>{_icon(kind, color)}</span>"
        out.append(f"{card}<span title='{e(ACTIVITY_LABELS[kind])}' style='display:contents'>{ico}</span>"
                   f"<div><div class='pl-title'>{e(session_title(r))}</div>{int_html}</div></div>")
    if suggested:
        out.append("<div class='pl-note'>Ton coach n'a pas fixé le jour de certaines séances : elles sont placées "
                   "dans la semaine à titre indicatif.</div>")
    return "".join(out)


def _plan_week_sessions(student, week_id: str) -> pd.DataFrame:
    """Toutes les séances prévues par le coach pour cette semaine (hors séances vides)."""
    sub = student.plan.sessions_of(week_id)
    return sub[[not is_empty_session(r) for _, r in sub.iterrows()]]


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


def render_planning(student, state, readonly: bool, prefix: str) -> None:
    """Contenu de l'onglet « Mon Planning »."""
    table, sv = state.table, state.suivi
    today = date.today()
    st.html(f"<style>{PLANNING_CSS}</style>")
    if table.empty:
        render("<div class='empty'>Ton plan ne contient encore aucune séance : ton coach le prépare.</div>")
        return
    positions = [int(p) for p in sorted(table["position"].unique())]
    labels = {p: week_label(table[table["position"] == p], today) for p in positions}
    default = next((p for p in positions if labels[p] == "Cette semaine"), None)
    if default is None:
        pending = [int(r["position"]) for _, r in table.iterrows() if not suivi.is_done(r, sv)]
        default = pending[0] if pending else positions[-1]
    key = f"{prefix}-plan-week"
    with st.container(key=f"{prefix}-card-planning"):
        pos = st.pills("Semaine", positions, default=default, format_func=labels.get, key=key, required=True,
                       label_visibility="collapsed")
        sub = table[table["position"] == pos]
        week_id = sub["week_id"].iloc[0]
        plan_sessions = _plan_week_sessions(student, week_id)
        render(week_html(sub, today, suggested_days(plan_sessions, student.date_course)))
        available = len(plan_sessions)
        natural = len(plan_sessions) if state.frequency == 4 else int((plan_sessions["frequence"] != FREQ_ONLY_4).sum())
        overridden = week_id in sv.semaines
        if overridden:
            st.caption(f"Semaine modifiée : {len(sub)} séances au lieu de {natural} prévues.")
        with st.container(horizontal=True, horizontal_alignment="center", key=f"{prefix}-plan-edit"):
            if st.button("Modifier ma semaine", type="tertiary", key=f"{prefix}_editweek_{week_id}",
                         disabled=readonly or available < min(WEEK_COUNTS),
                         help=None if available >= min(WEEK_COUNTS) else "Cette semaine ne compte qu'une séance"):
                _edit_week(student.id, week_id, labels[pos], available, len(sub), natural, overridden)
    # Garde la semaine choisie visible dans la barre de navigation (défilement horizontal sur téléphone).
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
