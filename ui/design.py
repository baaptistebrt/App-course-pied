"""
Identité visuelle « piste d'athlétisme » : CSS global et blocs HTML (piste, dossard, couloirs, semaines).

Palette
    piste      #1B4F8C   bleu de piste, couleur de marque
    nuit       #0F2A4A   texte sur fond clair, ombres de la piste
    béton      #E9EEF4   fond de page (gris béton de stade)
    chrono     #FFC629   jaune chronométrage : semaine en cours, allure de course
    zones      vert → bleu → violet → ambre → orange → rouge, de l'endurance au sprint
Typographie : Barlow (texte) et Barlow Condensed (chiffres, titres), au dessin inspiré
de la signalisation routière.
"""

from __future__ import annotations

import html
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from core.calculs import Pace, format_minutes, format_race_time, fr_number
from core.config import DISTANCES, PACE_LABELS, ZONE_COLORS
from core.exports import fr_date
from core.plan import is_race_day, week_summary

TRACK = "#1B4F8C"
NIGHT = "#0F2A4A"
CONCRETE = "#E9EEF4"
CHRONO = "#FFC629"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600;700&family=Barlow+Condensed:wght@500;600;700;800&display=swap');

:root {{ --track:{TRACK}; --night:{NIGHT}; --concrete:{CONCRETE}; --chrono:{CHRONO}; --muted:#5B6B80;
         --line:#D3DCE6; --cond:'Barlow Condensed','Arial Narrow',sans-serif; }}
/* Fond « béton » et police, même sans le fichier .streamlit/config.toml */
.stApp {{ background: var(--concrete); }}
.stApp, .stApp p, .stApp label, .stApp input, .stApp textarea, .stApp button {{ font-family: Barlow, sans-serif; }}
.stApp h1, .stApp h2, .stApp h3 {{ font-family: var(--cond); letter-spacing: .01em; color: var(--night); }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 1.6rem; padding-bottom: 4rem; max-width: 1280px; }}
[data-testid="stSidebar"] {{ background: var(--night); }}
[data-testid="stSidebar"] * {{ color: #E6EDF5; }}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] * {{ color: #A9B8C9; }}
[data-testid="stSidebar"] button {{ background: transparent; border-color: #49617E; }}
[data-testid="stSidebar"] button:hover {{ border-color: var(--chrono); color: var(--chrono); }}
[data-testid="stTab"] p {{ font-family: var(--cond); font-size: 1.3rem; font-weight: 600; }}
[data-testid="stExpander"] details, div[data-testid="stForm"] {{ background: #fff; }}
[class*="st-key-card-"] {{ background: #fff; }}
button[kind="primary"], [data-testid="stBaseButton-primary"] {{ background: var(--track); border-color: var(--track); }}
button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover {{ background: var(--night); border-color: var(--night); }}
:focus-visible {{ outline: 3px solid var(--chrono) !important; outline-offset: 2px; }}

/* ---- La piste : bande bleue avec lignes de couloir --------------------------------- */
.track {{ position: relative; background: var(--track); color: #fff; border-radius: 14px; overflow: hidden;
          padding: 22px 26px; margin: 0 0 18px; box-shadow: 0 1px 0 rgba(15,42,74,.25); }}
.track .strip {{ height: 22px; margin-top: 18px; opacity: .55;
                 background: repeating-linear-gradient(180deg, #fff 0 2px, transparent 2px 10px); }}
.track h1 {{ color: #fff; font-family: var(--cond); font-weight: 800; font-size: clamp(2rem, 4.5vw, 3.2rem);
             line-height: 1; margin: 0 0 6px; padding: 0; }}
.track p {{ margin: 0; color: #D6E2F0; font-size: 1.02rem; max-width: 60ch; }}

/* Couloirs du tableau de bord (une distance par couloir) */
.lanes-board {{ margin-top: 16px; border-top: 2px solid rgba(255,255,255,.55); }}
.lanes-board .row {{ display: grid; grid-template-columns: 44px 1fr auto; align-items: center; gap: 12px;
                     border-bottom: 2px solid rgba(255,255,255,.55); padding: 7px 0; }}
.lanes-board .n {{ font-family: var(--cond); font-weight: 800; font-size: 1.7rem; text-align: center; color: #fff; }}
.lanes-board .name {{ font-family: var(--cond); font-size: 1.35rem; font-weight: 600; }}
.lanes-board .count {{ font-variant-numeric: tabular-nums; color: #D6E2F0; }}

/* ---- Couloirs d'allure ------------------------------------------------------------ */
.paces {{ border-top: 2px solid rgba(255,255,255,.6); }}
.pace {{ display: grid; grid-template-columns: 34px minmax(110px, 1.3fr) auto minmax(70px, .7fr) minmax(110px, 1fr);
         align-items: center; gap: 12px; padding: 6px 0; border-bottom: 2px solid rgba(255,255,255,.6); }}
.pace .z {{ width: 30px; height: 30px; border-radius: 6px; display: grid; place-items: center; font-family: var(--cond);
            font-weight: 800; font-size: 1.15rem; }}
.pace .nm {{ font-weight: 600; line-height: 1.15; }}
.pace .nm small {{ display: block; font-weight: 400; color: #C9D7E8; font-size: .82rem; }}
.pace .v {{ font-family: var(--cond); font-weight: 700; font-size: 1.75rem; font-variant-numeric: tabular-nums;
            line-height: 1; white-space: nowrap; }}
.pace .v small {{ font-family: Barlow, sans-serif; font-size: .8rem; font-weight: 500; color: #C9D7E8; }}
.pace .kmh, .pace .eq {{ color: #D6E2F0; font-variant-numeric: tabular-nums; font-size: .92rem; }}
.pace.anchor .v {{ color: var(--chrono); }}
.pace .nm em {{ display: block; font-style: normal; color: var(--chrono); font-size: .78rem; font-weight: 600; }}

/* ---- Dossard ------------------------------------------------------------------------ */
.hero-grid {{ display: grid; grid-template-columns: minmax(260px, 360px) 1fr; gap: 26px; align-items: center; }}
.bib {{ position: relative; background: #fff; color: var(--night); border-radius: 6px; padding: 0 0 14px;
        box-shadow: 0 10px 24px rgba(5,20,40,.35); text-align: center; transform: rotate(-1.2deg); }}
.bib .band {{ background: var(--chrono); color: var(--night); font-family: var(--cond); font-weight: 700;
              font-size: 1rem; padding: 7px 34px; border-radius: 6px 6px 0 0; }}
.bib .num {{ font-family: var(--cond); font-weight: 800; font-size: clamp(3.6rem, 9vw, 5.2rem); line-height: .95;
             letter-spacing: -.01em; margin: 14px 10px 2px; font-variant-numeric: tabular-nums; }}
.bib .who {{ font-family: var(--cond); font-weight: 700; font-size: 1.45rem; }}
.bib .when {{ color: var(--muted); font-size: .92rem; margin-top: 2px; }}
.bib .pin {{ position: absolute; width: 11px; height: 11px; border-radius: 50%; background: var(--concrete);
             box-shadow: inset 0 1px 2px rgba(0,0,0,.35); }}
.bib .pin.tl {{ top: 40px; left: 10px; }} .bib .pin.tr {{ top: 40px; right: 10px; }}
.bib .pin.bl {{ bottom: 10px; left: 10px; }} .bib .pin.br {{ bottom: 10px; right: 10px; }}

/* ---- Semaines (vue élève) ----------------------------------------------------------- */
.week {{ background: #fff; border-radius: 12px; margin: 0 0 14px; border-left: 6px solid var(--track);
         padding: 14px 18px 8px; }}
.week.current {{ border-left-color: var(--chrono); box-shadow: 0 0 0 2px var(--chrono); }}
.week.past {{ opacity: .62; }}
.week header {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 14px; }}
.week .wn {{ font-family: var(--cond); font-weight: 800; font-size: 1.6rem; color: var(--night); }}
.week .wd {{ color: var(--muted); }}
.week .tag {{ background: var(--chrono); color: var(--night); font-weight: 700; font-size: .8rem; border-radius: 4px;
              padding: 1px 7px; }}
.week .vol {{ margin-left: auto; color: var(--muted); font-variant-numeric: tabular-nums; }}
.week .phase {{ color: var(--track); font-weight: 600; margin: 2px 0 6px; }}
.week ol {{ list-style: none; margin: 4px 0 0; padding: 0; }}
.week li {{ display: grid; grid-template-columns: 62px 1fr auto; gap: 10px; align-items: center;
            padding: 9px 0; border-top: 1px solid #E3E9F0; }}
.week li .id {{ font-family: var(--cond); font-weight: 700; font-size: 1.1rem; color: var(--muted); }}
.week li .what {{ font-weight: 600; }}
.week li .meta {{ color: var(--muted); font-size: .9rem; display: flex; flex-wrap: wrap; gap: 2px 14px; }}
.week li .note {{ font-style: italic; }}
.week li.race {{ background: #FFF6D6; border-radius: 8px; padding-left: 8px; padding-right: 8px; }}
.week li.race .id {{ color: var(--night); }}
.pill {{ display: inline-flex; align-items: baseline; gap: 8px; border-radius: 999px; padding: 4px 12px;
         font-weight: 600; white-space: nowrap; }}
.pill b {{ font-family: var(--cond); font-size: 1.15rem; font-variant-numeric: tabular-nums; }}
.empty {{ background: #fff; border: 2px dashed var(--line); border-radius: 12px; padding: 22px; color: var(--muted); }}

@media (max-width: 760px) {{
  .hero-grid {{ grid-template-columns: 1fr; }}
  .bib {{ transform: none; }}
  .pace {{ grid-template-columns: 30px 1fr auto; }}
  .pace .kmh, .pace .eq {{ display: none; }}
  .week li {{ grid-template-columns: 44px 1fr; }}
  .week li .pill {{ grid-column: 2; justify-self: start; }}
  .week .vol {{ margin-left: 0; }}
  .track {{ padding: 18px 16px; }}
}}
@media (prefers-reduced-motion: no-preference) {{
  .bib {{ animation: pinned .5s ease-out both; }}
  @keyframes pinned {{ from {{ transform: rotate(-6deg) translateY(-8px); opacity: 0; }}
                       to {{ transform: rotate(-1.2deg); opacity: 1; }} }}
}}
</style>
"""

e = html.escape


def inject_css() -> None:
    st.html(CSS)


def render(html_str: str) -> None:
    st.html(html_str)


# ---------------------------------------------------------------------------------------
def login_track() -> str:
    return ("<div class='track'><h1>Ton plan d'entraînement</h1>"
            "<p>Marathon, semi-marathon ou 10 km : entre le code que ton coach t'a donné "
            "pour retrouver ton plan et tes allures.</p><div class='strip'></div></div>")


def editor_track(counts: dict[str, int]) -> str:
    rows = "".join(
        f"<div class='row'><span class='n'>{i}</span><span class='name'>{e(DISTANCES[d].label)}</span>"
        f"<span class='count'>{n} élève{'s' if n > 1 else ''}</span></div>"
        for i, (d, n) in enumerate(counts.items(), start=1))
    return (f"<div class='track'><h1>Tableau de bord du coach</h1>"
            f"<p>Crée un profil par élève, ajuste son plan et ses formules : il retrouve tout avec son code.</p>"
            f"<div class='lanes-board'>{rows}</div></div>")


def pace_lanes(paces: dict[str, Pace], anchor_note: str = "allure de course") -> str:
    rows = []
    for i, p in enumerate(paces.values(), start=1):
        bg, fg = ZONE_COLORS[p.code]
        eq = f"{p.ref_label} en {format_minutes(p.ref_time_minutes)}" if p.ref_time_minutes else ""
        rows.append(
            f"<div class='pace{' anchor' if p.is_anchor else ''}'>"
            f"<span class='z' style='background:{bg};color:{fg}'>{i}</span>"
            f"<span class='nm'>{e(p.label)}<small>{e(p.description)}</small>"
            f"{f'<em>{e(anchor_note)}</em>' if p.is_anchor else ''}</span>"
            f"<span class='v'>{e(p.pace_str)}<small> /km</small></span>"
            f"<span class='kmh'>{e(fr_number(p.kmh))} km/h</span><span class='eq'>{e(eq)}</span></div>")
    return f"<div class='paces'>{''.join(rows)}</div>"


def bib(name: str, distance: str, objective_seconds: int, race_date: date | None, n_weeks: int) -> str:
    dist = DISTANCES[distance]
    if race_date:
        days = (race_date - date.today()).days
        when = (f"Course le {fr_date(race_date, True)}" +
                (f", dans {days} jour{'s' if days > 1 else ''}" if days > 0 else
                 (", c'est aujourd'hui !" if days == 0 else "")))
    else:
        when = f"Plan de {n_weeks} semaines"
    return (f"<div class='bib' role='img' aria-label='Dossard : {e(name)}, objectif {e(format_race_time(objective_seconds))}'>"
            f"<span class='pin tl'></span><span class='pin tr'></span><span class='pin bl'></span><span class='pin br'></span>"
            f"<div class='band'>{e(dist.label)}</div>"
            f"<div class='num'>{e(format_race_time(objective_seconds))}</div>"
            f"<div class='who'>{e(name)}</div><div class='when'>{e(when)}</div></div>")


def student_hero(name: str, distance: str, objective_seconds: int, race_date: date | None, n_weeks: int,
                 paces: dict[str, Pace]) -> str:
    return (f"<div class='track'><div class='hero-grid'>{bib(name, distance, objective_seconds, race_date, n_weeks)}"
            f"<div>{pace_lanes(paces, 'ton allure de course')}</div></div></div>")


def paces_track(paces: dict[str, Pace]) -> str:
    return f"<div class='track' style='padding:10px 22px 14px'>{pace_lanes(paces)}</div>"


def _pill(code: str | None, pace_txt: str) -> str:
    if not code:
        return ""
    bg, fg = ZONE_COLORS[code]
    return (f"<span class='pill' style='background:{bg};color:{fg}'>{e(PACE_LABELS.get(code, code))}"
            f"{f' <b>{e(pace_txt)}</b>' if pace_txt else ''}</span>")


def week_cards(table: pd.DataFrame, today: date | None = None) -> str:
    """Plan en cartes de semaines (lecture seule), semaine en cours mise en évidence."""
    if table.empty:
        return "<div class='empty'>Ce plan ne contient encore aucune séance.</div>"
    today = today or date.today()
    out = []
    for position in sorted(table["position"].unique()):
        sub = table[table["position"] == position]
        first = sub.iloc[0]
        start = first["debut"] if isinstance(first["debut"], date) else None
        current = bool(start and start <= today <= start + timedelta(days=6))
        past = bool(start and start + timedelta(days=6) < today)
        summary = week_summary(sub)
        dates = f"<span class='wd'>du {fr_date(start)} au {fr_date(start + timedelta(days=6))}</span>" if start else ""
        vol = ", ".join(x for x in (summary.km_str, summary.duration_str) if x)
        out.append(f"<section class='week{' current' if current else ''}{' past' if past else ''}'>"
                   f"<header><span class='wn'>Semaine {int(position) + 1}</span>{dates}"
                   f"{'<span class=tag>Cette semaine</span>' if current else ''}"
                   f"<span class='vol'>{e(vol)}</span></header>")
        if first["phase"]:
            out.append(f"<div class='phase'>{e(first['phase'])}</div>")
        out.append("<ol>")
        for _, r in sub.iterrows():
            race = is_race_day(r["seance"])
            what = r["contenu"] or ("Séance à l'allure indiquée" if r["allure"] else "Séance libre")
            meta = [x for x in (f"{r['km_env']} km" if r["km_env"] else "", r["duree_env"],
                                f"dont {r['temps_spe']} à l'allure" if r["temps_spe"] and not race else "") if x]
            meta_html = "".join(f"<span>{e(str(m))}</span>" for m in meta)
            if r["remarque"]:
                meta_html += f"<span class='note'>{e(str(r['remarque']))}</span>"
            out.append(f"<li class='{'race' if race else ''}'><span class='id'>{e(str(r['seance']))}</span>"
                       f"<div><div class='what'>{e(str(what))}</div><div class='meta'>{meta_html}</div></div>"
                       f"{_pill(r['allure'], r['allure_txt'])}</li>")
        out.append("</ol></section>")
    return "".join(out)
