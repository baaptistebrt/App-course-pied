"""
Graphiques de progression (Plotly), dans l'esprit des outils de suivi sportif :
séances par semaine, volume hebdomadaire, ressentis, écart à l'objectif et allure des courses.

Utilisé par l'espace élève (onglet « Ma progression ») et par le coach (Supervision).
Palette des séries validée (lisible par les daltoniens) : bleu #2A6FDB, orange #EB6834, vert #199E70 ;
gris pour ce qui n'est pas encore fait. Un seul axe par graphique ; chaque graphique a sa table.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import analyse, historique
from core.config import FEELINGS
from ui.design import render

BLUE, ORANGE, GREEN = "#2A6FDB", "#EB6834", "#199E70"
MISSED, UPCOMING = "#A9B6C6", "#E3E9F0"
INK, MUTED, GRID = "#0F2A4A", "#5B6B80", "#E3E9F0"
CONFIG = {"displayModeBar": False, "responsive": True}


def _layout(fig: go.Figure, title: str, height: int = 300, legend: bool = True) -> go.Figure:
    fig.update_layout(
        title={"text": title, "x": 0, "xanchor": "left", "font": {"family": "Barlow Condensed, sans-serif",
                                                                   "size": 20, "color": INK}},
        height=height, margin={"l": 8, "r": 8, "t": 48, "b": 8}, paper_bgcolor="#fff", plot_bgcolor="#fff",
        font={"family": "Barlow, sans-serif", "size": 13, "color": INK}, showlegend=legend,
        legend={"orientation": "h", "y": 1.02, "yanchor": "bottom", "x": 1, "xanchor": "right",
                "font": {"color": MUTED}},
        hoverlabel={"bgcolor": "#fff", "bordercolor": GRID, "font": {"family": "Barlow, sans-serif", "color": INK}},
        bargap=0.45,
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID, tickfont={"color": MUTED}, automargin=True, fixedrange=True)
    fig.update_yaxes(gridcolor=GRID, gridwidth=1, zeroline=False, linecolor=GRID, tickfont={"color": MUTED},
                     automargin=True, fixedrange=True)
    return fig


def _show(fig: go.Figure, key: str) -> None:
    st.plotly_chart(fig, config=CONFIG, theme=None, key=key)


def _mmss(seconds: float) -> str:
    m, s = divmod(int(round(seconds)), 60)
    return f"{m}'{s:02d}"


# =========================================================================== graphiques
def sessions_chart(weekly: pd.DataFrame) -> go.Figure:
    """Séances faites / manquées / à venir par semaine (barres empilées)."""
    fig = go.Figure()
    for col, name, color in (("faites", "Faites", BLUE), ("manquees", "Manquées", MISSED),
                             ("a_venir", "À venir", UPCOMING)):
        if weekly[col].sum() == 0 and col != "faites":
            continue
        fig.add_bar(x=weekly["semaine"], y=weekly[col], name=name, marker={"color": color,
                    "line": {"color": "#fff", "width": 2}}, customdata=weekly["periode"],
                    hovertemplate=f"%{{customdata}}<br>{name} : %{{y}}<extra></extra>")
    fig.update_layout(barmode="stack", barcornerradius=4)
    fig.update_yaxes(title=None, dtick=1, rangemode="tozero")
    return _layout(fig, "Séances par semaine")


def volume_chart(weekly: pd.DataFrame) -> go.Figure:
    """Volume hebdomadaire : km prévus (fond gris) et km courus (barre bleue)."""
    fig = go.Figure()
    fig.add_bar(x=weekly["semaine"], y=weekly["km_prevus"], name="Prévus", marker={"color": UPCOMING},
                width=0.6, customdata=weekly["periode"],
                hovertemplate="%{customdata}<br>Prévus : %{y} km<extra></extra>")
    fig.add_bar(x=weekly["semaine"], y=weekly["km_courus"], name="Courus", marker={"color": BLUE},
                width=0.3, customdata=weekly["periode"],
                hovertemplate="%{customdata}<br>Courus : %{y} km<extra></extra>")
    fig.update_layout(barmode="overlay", barcornerradius=4)
    fig.update_yaxes(title=None, ticksuffix=" km", rangemode="tozero")
    return _layout(fig, "Volume hebdomadaire")


def feelings_chart(feelings: pd.DataFrame) -> go.Figure:
    """Ressenti noté après chaque séance (1 = très dur, 5 = excellent)."""
    fig = go.Figure()
    fig.add_scatter(x=feelings["date"], y=feelings["ressenti"], mode="lines+markers",
                    line={"color": BLUE, "width": 2, "shape": "spline", "smoothing": 0.6},
                    marker={"size": 10, "color": BLUE, "line": {"color": "#fff", "width": 2}},
                    customdata=feelings[["libelle", "seance"]],
                    hovertemplate="%{x|%d/%m}<br>%{customdata[1]}<br>%{customdata[0]}<extra></extra>")
    fig.update_yaxes(range=[0.5, 5.5], tickvals=list(FEELINGS), ticktext=[" ".join(FEELINGS[k]) for k in FEELINGS])
    fig.update_xaxes(tickformat="%d/%m")
    return _layout(fig, "Ressenti des séances", legend=False)


def gap_chart(races: pd.DataFrame) -> go.Figure:
    """Écart à l'objectif, en % du temps visé : à gauche plus rapide, à droite plus lent."""
    data = races.dropna(subset=["ecart_pct"])
    labels = [f"{c}<br><span style='font-size:11px'>{d:%d/%m/%Y}</span>" if pd.notna(d) else c
              for c, d in zip(data["course"], data["date"])]
    colors = [BLUE if v <= 0 else ORANGE for v in data["ecart_pct"]]
    text = [f"{g} ({p:+.1f} %)".replace(".", ",") for g, p in zip(data["ecart"], data["ecart_pct"])]
    fig = go.Figure(go.Bar(
        y=labels, x=data["ecart_pct"], orientation="h", marker={"color": colors}, width=0.32, text=text,
        textposition="outside", textfont={"color": INK}, cliponaxis=False,
        customdata=data[["temps", "objectif"]],
        hovertemplate="Réalisé %{customdata[0]}, objectif %{customdata[1]}<extra></extra>"))
    span = max(3.0, float(data["ecart_pct"].abs().max()) * 1.6) if len(data) else 3.0
    fig.update_layout(barcornerradius=4)
    fig.update_xaxes(range=[-span, span], ticksuffix=" %", zeroline=True, zerolinecolor="#C9D3DF",
                     zerolinewidth=1, showgrid=True, gridcolor=GRID,
                     title={"text": "← plus rapide que l'objectif · plus lent →", "font": {"color": MUTED, "size": 12}})
    return _layout(fig, "Objectif et temps réalisé", height=max(200, 110 + 56 * len(data)), legend=False)


def pace_chart(races: pd.DataFrame) -> go.Figure:
    """Allure moyenne de chaque course (une série par distance) ; plus haut = plus rapide."""
    fig = go.Figure()
    colors = {"10 km": BLUE, "Semi-marathon": ORANGE, "Marathon": GREEN}
    for dist, sub in races.dropna(subset=["date"]).groupby("distance", sort=False):
        fig.add_scatter(x=sub["date"], y=sub["allure_s"], name=dist, mode="lines+markers",
                        line={"color": colors.get(dist, BLUE), "width": 2},
                        marker={"size": 10, "color": colors.get(dist, BLUE), "line": {"color": "#fff", "width": 2}},
                        customdata=sub[["course", "temps"]],
                        text=[_mmss(v) for v in sub["allure_s"]],
                        hovertemplate="%{customdata[0]}<br>%{customdata[1]}, %{text} /km<extra></extra>")
    values = races["allure_s"].dropna()
    if len(values):
        lo, hi = float(values.min()) - 15, float(values.max()) + 15
        ticks = list(range(int(lo // 15 * 15), int(hi) + 15, 15))
        fig.update_yaxes(range=[hi, lo], tickvals=ticks, ticktext=[_mmss(t) + " /km" for t in ticks])
    dates = sorted(races["date"].dropna().unique())
    if len(dates) <= 6:                       # peu de courses : une graduation par course
        fig.update_xaxes(tickvals=dates, ticktext=[pd.Timestamp(d).strftime("%d/%m/%y") for d in dates])
    else:
        fig.update_xaxes(tickformat="%m/%Y")
    return _layout(fig, "Allure moyenne en course", height=300, legend=races["distance"].nunique() > 1)


# =========================================================================== blocs
def _tiles(items: list[tuple[str, str]]) -> None:
    cols = st.columns(len(items))
    for col, (label, value) in zip(cols, items):
        col.metric(label, value, border=True)


def render_program(state, key: str) -> None:
    """Progression d'un programme : chiffres clés, séances et volume par semaine, ressentis."""
    weekly = analyse.weekly_frame(state)
    feelings = analyse.feelings_frame(state)
    if weekly.empty:
        st.caption("Ce plan ne contient encore aucune séance.")
        return
    adh = analyse.adherence(weekly)
    avg = feelings["ressenti"].mean() if not feelings.empty else None
    _tiles([("Séances faites", f"{int(weekly['faites'].sum())} / {int(weekly['prevues'].sum())}"),
            ("Assiduité", f"{round(adh * 100)} %" if adh is not None else "—"),
            ("Km courus", f"{weekly['km_courus'].sum():.0f}".replace(".", ",")),
            ("Ressenti moyen", FEELINGS[round(avg)][0] + f" {avg:.1f}".replace(".", ",") if avg else "—")])
    st.caption("Assiduité : séances faites parmi celles déjà prévues à ce jour.")
    c1, c2 = st.columns(2, gap="medium")
    with c1, st.container(key=f"card-chart-s-{key}"):
        _show(sessions_chart(weekly), f"ch_s_{key}")
    with c2, st.container(key=f"card-chart-v-{key}"):
        _show(volume_chart(weekly), f"ch_v_{key}")
    if not feelings.empty:
        with st.container(key=f"card-chart-f-{key}"):
            _show(feelings_chart(feelings), f"ch_f_{key}")
    with st.expander("Voir les données de la progression"):
        st.dataframe(weekly.rename(columns={
            "semaine": "Semaine", "periode": "Période", "faites": "Faites", "manquees": "Manquées",
            "a_venir": "À venir", "km_prevus": "Km prévus", "km_courus": "Km courus"})[
            ["Semaine", "Période", "Faites", "Manquées", "À venir", "Km prévus", "Km courus"]],
            hide_index=True, width="stretch")
        if not feelings.empty:
            st.dataframe(feelings.rename(columns={"date": "Date", "libelle": "Ressenti", "seance": "Séance",
                                                  "semaine": "Semaine"})[["Date", "Semaine", "Séance", "Ressenti"]],
                         hide_index=True, width="stretch")


def render_races(records: list, key: str) -> None:
    """Courses terminées : écart à l'objectif et allure moyenne au fil des courses."""
    races = analyse.races_frame(records)
    if races.empty:
        render("<div class='empty'>Les graphiques de tes courses apparaîtront ici dès qu'un temps de course "
               "sera saisi.</div>")
        return
    c1, c2 = st.columns(2, gap="medium")
    with c1, st.container(key=f"card-chart-g-{key}"):
        if races["ecart_pct"].notna().any():
            _show(gap_chart(races), f"ch_g_{key}")
        else:
            st.caption("Pas d'objectif de temps pour ces courses : l'écart ne peut pas être calculé.")
    with c2, st.container(key=f"card-chart-p-{key}"):
        _show(pace_chart(races), f"ch_p_{key}")
    with st.expander("Voir les données des courses"):
        st.dataframe(races.assign(allure=[_mmss(v) + " /km" for v in races["allure_s"]]).rename(columns={
            "course": "Course", "distance": "Distance", "date": "Date", "temps": "Temps", "objectif": "Objectif",
            "ecart": "Écart", "allure": "Allure"})[["Course", "Distance", "Date", "Objectif", "Temps", "Écart",
                                                    "Allure"]], hide_index=True, width="stretch")


def completion_overview(states: list) -> go.Figure | None:
    """Supervision : assiduité de chaque programme en cours (barres horizontales, valeur au bout)."""
    rows = []
    for stt in states:
        adh = analyse.adherence(analyse.weekly_frame(stt))
        if adh is not None:
            rows.append((f"{stt.student.display_name} · {stt.student.race_name}", round(adh * 100)))
    if not rows:
        return None
    rows.sort(key=lambda r: r[1])
    fig = go.Figure(go.Bar(y=[r[0] for r in rows], x=[r[1] for r in rows], orientation="h", width=0.35,
                           marker={"color": BLUE}, text=[f"{r[1]} %" for r in rows], textposition="outside",
                           textfont={"color": INK}, cliponaxis=False,
                           hovertemplate="%{y}<br>Assiduité : %{x} %<extra></extra>"))
    fig.update_layout(barcornerradius=4)
    fig.update_xaxes(range=[0, 115], ticksuffix=" %", showgrid=True, gridcolor=GRID)
    return _layout(fig, "Assiduité des programmes en cours", height=max(180, 90 + 40 * len(rows)), legend=False)


def render_person(store, programs: list, key: str) -> None:
    """Coach : progression consolidée d'un élève (tous ses programmes)."""
    by_id = {p.id: p for p in programs}
    states = {p.id: historique.program_state(store, p) for p in programs}
    current = [p.id for p in programs if not states[p.id].finished()] or [programs[-1].id]
    choice = st.selectbox("Programme", list(by_id), index=list(by_id).index(current[0]), key=f"prog_{key}",
                          format_func=lambda i: by_id[i].race_name +
                          (f" ({by_id[i].date_course:%d/%m/%Y})" if by_id[i].date_course else ""))
    render_program(states[choice], f"{key}_{choice}")
    st.markdown("##### Courses terminées")
    render_races([historique.race_record(s) for s in states.values() if s.finished()], key)
