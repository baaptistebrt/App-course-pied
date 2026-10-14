"""
Identité visuelle « piste d'athlétisme » : CSS global, page d'accueil, bandeaux, dossard,
couloirs d'allure et cartes de semaines.

Palette
    piste      #1B4F8C   bleu de piste, couleur de marque
    nuit       #0F2A4A   texte sur fond clair, ombres de la piste
    béton      #E9EEF4   fond de page (gris béton de stade)
    chrono     #FFC629   jaune chronométrage : semaine en cours, allure de course
    zones      vert → bleu → violet → ambre → orange → rouge, de l'endurance au sprint
Typographie : Barlow (texte) et Barlow Condensed (chiffres, titres), au dessin inspiré
de la signalisation routière.
Visuels : illustration de virage de piste (assets/piste.svg) par défaut ; le coach peut la
remplacer par ses propres photos (onglet Réglages), rangées dans data/medias/.
"""

from __future__ import annotations

import base64
import html
import io
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from core.calculs import Pace, format_minutes, format_race_time
from core.config import DISTANCES, PACE_LABELS, ZONE_COLORS
from core.exports import fr_date
from core.plan import is_race_day, pace_codes, week_summary
from core.stockage import Store

ASSETS = Path(__file__).resolve().parent / "assets"
MEDIA_FILES = {"accueil": "medias/accueil.jpg", "banniere": "medias/banniere.jpg"}

TRACK = "#1B4F8C"
NIGHT = "#0F2A4A"
CONCRETE = "#E9EEF4"
CHRONO = "#FFC629"
e = html.escape


# =========================================================================== images
@st.cache_data(show_spinner=False)
def asset_uri(name: str) -> str:
    data = (ASSETS / name).read_bytes()
    return f"data:image/svg+xml;base64,{base64.b64encode(data).decode()}"


@st.cache_data(show_spinner=False, max_entries=8)
def _media_uri(path: str, version: tuple) -> str:
    return f"data:image/jpeg;base64,{base64.b64encode(Path(path).read_bytes()).decode()}"


def media_uri(store: Store, kind: str) -> str | None:
    """Photo choisie par le coach (data URI), ou None pour l'illustration par défaut."""
    rel = MEDIA_FILES[kind]
    if not store.exists(rel):
        return None
    return _media_uri(str(store.path(rel)), store.version(rel))


def prepare_photo(content: bytes, max_width: int = 1920) -> bytes:
    """Redimensionne et compresse une photo importée (JPEG ~200-400 Ko) pour un affichage rapide."""
    from PIL import Image, ImageOps   # Pillow est installé avec Streamlit

    img = ImageOps.exif_transpose(Image.open(io.BytesIO(content))).convert("RGB")
    if img.width > max_width:
        img = img.resize((max_width, round(img.height * max_width / img.width)))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=82, optimize=True, progressive=True)
    return out.getvalue()


def logo_svg(size: int = 44) -> str:
    """Logo (balise <img> : les balises <svg> sont filtrées par st.html)."""
    return f"<img src='{asset_uri('logo.svg')}' width='{size}' height='{size}' alt=''>"


# =========================================================================== CSS
BASE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600;700&family=Barlow+Condensed:wght@500;600;700;800&display=swap');

:root { --track:#1B4F8C; --night:#0F2A4A; --concrete:#E9EEF4; --chrono:#FFC629; --muted:#5B6B80;
        --line:#D3DCE6; --cond:'Barlow Condensed','Arial Narrow',sans-serif; }
/* Fond « béton » et police, même sans le fichier .streamlit/config.toml */
.stApp { background: var(--concrete); }
.stApp, .stApp p, .stApp label, .stApp input, .stApp textarea, .stApp button { font-family: Barlow, sans-serif; }
.stApp h1, .stApp h2, .stApp h3 { font-family: var(--cond); letter-spacing: .01em; color: var(--night); }
[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 1.6rem; padding-bottom: 4rem; max-width: 1280px; }
[data-testid="stSidebar"] { background: var(--night); }
[data-testid="stSidebar"] * { color: #E6EDF5; }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] * { color: #A9B8C9; }
[data-testid="stSidebar"] button { background: transparent; border-color: #49617E; }
[data-testid="stSidebar"] button:hover { border-color: var(--chrono); color: var(--chrono); }
[data-testid="stTab"] p { font-family: var(--cond); font-size: 1.3rem; font-weight: 600; }
[data-testid="stExpander"] details, div[data-testid="stForm"] { background: #fff; }
[class*="st-key-card-"] { background: #fff; }
button[kind="primary"], [data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-primaryFormSubmit"] { background: var(--track); border-color: var(--track); color: #fff; }
button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover,
[data-testid="stBaseButton-primaryFormSubmit"]:hover { background: var(--night); border-color: var(--night); }
:focus-visible { outline: 3px solid var(--chrono) !important; outline-offset: 2px; }

/* ---- La piste : bandeau bleu (illustration ou photo du coach en fond) ------------- */
.track { position: relative; color: #fff; border-radius: 14px; overflow: hidden; padding: 22px 26px;
         margin: 0 0 18px; box-shadow: 0 1px 0 rgba(15,42,74,.25); background-color: var(--track);
         background-size: cover; background-position: center; }
.track h1 { color: #fff; font-family: var(--cond); font-weight: 800; font-size: clamp(2rem, 4.5vw, 3.2rem);
            line-height: 1; margin: 0 0 6px; padding: 0; }
.track p { margin: 0; color: #D6E2F0; font-size: 1.02rem; max-width: 60ch; }
.lanes-board { margin-top: 16px; border-top: 2px solid rgba(255,255,255,.55); }
.lanes-board .row { display: grid; grid-template-columns: 44px 1fr auto; align-items: center; gap: 12px;
                    border-bottom: 2px solid rgba(255,255,255,.55); padding: 7px 0; }
.lanes-board .n { font-family: var(--cond); font-weight: 800; font-size: 1.7rem; text-align: center; }
.lanes-board .name { font-family: var(--cond); font-size: 1.35rem; font-weight: 600; }
.lanes-board .count { font-variant-numeric: tabular-nums; color: #D6E2F0; }

/* ---- Couloirs d'allure ------------------------------------------------------------ */
.paces { border-top: 2px solid rgba(255,255,255,.6); }
.pace { display: grid; grid-template-columns: 34px minmax(110px, 1.2fr) auto minmax(90px, .8fr) minmax(110px, 1fr);
        align-items: center; gap: 12px; padding: 6px 0; border-bottom: 2px solid rgba(255,255,255,.6); }
.pace .z { width: 30px; height: 30px; border-radius: 6px; display: grid; place-items: center; font-family: var(--cond);
           font-weight: 800; font-size: 1.15rem; }
.pace .nm { font-weight: 600; line-height: 1.15; }
.pace .nm small { display: block; font-weight: 400; color: #C9D7E8; font-size: .82rem; }
.pace .nm em { display: block; font-style: normal; color: var(--chrono); font-size: .78rem; font-weight: 600; }
.pace .v { font-family: var(--cond); font-weight: 700; font-size: 1.75rem; font-variant-numeric: tabular-nums;
           line-height: 1; white-space: nowrap; }
.pace .v.range { font-size: 1.4rem; }
.pace .v small { font-family: Barlow, sans-serif; font-size: .8rem; font-weight: 500; color: #C9D7E8; }
.pace .kmh, .pace .eq { color: #D6E2F0; font-variant-numeric: tabular-nums; font-size: .92rem; }
.pace.anchor .v { color: var(--chrono); }
.basis { color: #D6E2F0; font-size: .9rem; margin: 0 0 6px; }

/* ---- Dossard ------------------------------------------------------------------------ */
.hero-grid { display: grid; grid-template-columns: minmax(260px, 360px) 1fr; gap: 26px; align-items: center; }
.bib { position: relative; background: #fff; color: var(--night); border-radius: 6px; padding: 0 0 14px;
       box-shadow: 0 10px 24px rgba(5,20,40,.35); text-align: center; transform: rotate(-1.2deg); }
.bib .band { background: var(--chrono); color: var(--night); font-family: var(--cond); font-weight: 700;
             font-size: 1rem; padding: 7px 34px; border-radius: 6px 6px 0 0; }
.bib .num { font-family: var(--cond); font-weight: 800; font-size: clamp(3.6rem, 9vw, 5.2rem); line-height: .95;
            letter-spacing: -.01em; margin: 14px 10px 2px; font-variant-numeric: tabular-nums; }
.bib .est { color: var(--muted); font-size: .85rem; margin-top: -2px; }
.bib .who { font-family: var(--cond); font-weight: 700; font-size: 1.45rem; }
.bib .when { color: var(--muted); font-size: .92rem; margin-top: 2px; }
.bib .done { margin: 8px 16px 0; background: #E7F6EF; color: #17603F; border-radius: 6px; padding: 4px 8px;
             font-weight: 600; font-size: .92rem; }
.bib .pin { position: absolute; width: 11px; height: 11px; border-radius: 50%; background: var(--concrete);
            box-shadow: inset 0 1px 2px rgba(0,0,0,.35); }
.bib .pin.tl { top: 40px; left: 10px; } .bib .pin.tr { top: 40px; right: 10px; }
.bib .pin.bl { bottom: 10px; left: 10px; } .bib .pin.br { bottom: 10px; right: 10px; }

/* ---- Semaines ------------------------------------------------------------------------ */
.week, [class*="st-key-card-wk"] { background: #fff; border-radius: 12px; margin: 0 0 14px;
         border-left: 6px solid var(--track); padding: 14px 18px 8px; }
.week.current, [class*="st-key-card-wkcur"] { border-left-color: var(--chrono); box-shadow: 0 0 0 2px var(--chrono); }
.week.past, [class*="st-key-card-wkpast"] { opacity: .7; }
.wh { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 14px; }
.wh .wn { font-family: var(--cond); font-weight: 800; font-size: 1.6rem; color: var(--night); }
.wh .wd { color: var(--muted); }
.wh .tag { background: var(--chrono); color: var(--night); font-weight: 700; font-size: .8rem; border-radius: 4px;
           padding: 1px 7px; }
.wh .vol { margin-left: auto; color: var(--muted); font-variant-numeric: tabular-nums; }
.wphase { color: var(--track); font-weight: 600; margin: 2px 0 6px; }
.week ol { list-style: none; margin: 4px 0 0; padding: 0; }
.week li { display: grid; grid-template-columns: 30px 62px 1fr auto; gap: 10px; align-items: center;
           padding: 9px 0; border-top: 1px solid #E3E9F0; }
.week li .st { font-size: 1.15rem; text-align: center; }
.week li .id { font-family: var(--cond); font-weight: 700; font-size: 1.1rem; color: var(--muted); }
.week li .what { font-weight: 600; }
.meta { color: var(--muted); font-size: .9rem; display: flex; flex-wrap: wrap; gap: 2px 14px; align-items: center; }
.meta .note { font-style: italic; }
.week li.race { background: #FFF6D6; border-radius: 8px; padding-left: 8px; padding-right: 8px; }
.pills { display: flex; flex-wrap: wrap; gap: 6px; justify-content: flex-end; }
.pill { display: inline-flex; align-items: baseline; gap: 8px; border-radius: 999px; padding: 4px 12px;
        font-weight: 600; white-space: nowrap; }
.pill b { font-family: var(--cond); font-size: 1.12rem; font-variant-numeric: tabular-nums; }
/* Séance interactive (élève) : la case à cocher porte le titre, la ligne de détail est en dessous */
.sesmeta { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 6px 14px; align-items: center;
           margin: -6px 0 10px 28px; padding-bottom: 10px; border-bottom: 1px solid #E3E9F0; }
.racebox { background: #FFF6D6; border-radius: 10px; padding: 10px 12px; margin: 4px 0 10px; }
.racebox .what { font-family: var(--cond); font-size: 1.35rem; font-weight: 800; color: var(--night); }
[class*="st-key-card-wk"] [data-testid="stCheckbox"] label p { font-weight: 600; font-size: 1rem; }
.empty { background: #fff; border: 2px dashed var(--line); border-radius: 12px; padding: 22px; color: var(--muted); }
.progressline { display: flex; justify-content: space-between; color: var(--muted); font-size: .92rem; margin-top: 2px; }

@media (max-width: 760px) {
  .hero-grid { grid-template-columns: 1fr; }
  .bib { transform: none; }
  .pace { grid-template-columns: 30px 1fr auto; }
  .pace .kmh, .pace .eq { display: none; }
  .week li { grid-template-columns: 26px 44px 1fr; }
  .week li .pills { grid-column: 2 / 4; justify-content: flex-start; }
  .wh .vol { margin-left: 0; }
  .track { padding: 18px 16px; }
  .sesmeta { margin-left: 0; }
}
@media (prefers-reduced-motion: no-preference) {
  .bib { animation: pinned .5s ease-out both; }
  @keyframes pinned { from { transform: rotate(-6deg) translateY(-8px); opacity: 0; }
                      to { transform: rotate(-1.2deg); opacity: 1; } }
}
"""


def inject_css(store: Store) -> None:
    """CSS global + fond des bandeaux (photo du coach ou illustration de piste)."""
    banner = media_uri(store, "banniere") or asset_uri("piste.svg")
    st.html(f"<style>{BASE_CSS}\n.track {{ background-image: linear-gradient(100deg, rgba(27,79,140,.96) 0%, "
            f"rgba(27,79,140,.92) 45%, rgba(15,42,74,.74) 100%), url('{banner}'); }}</style>")


def landing_css(store: Store) -> None:
    """Page d'accueil : photo ou illustration plein écran, carte de connexion au centre."""
    bg = media_uri(store, "accueil") or asset_uri("piste.svg")
    st.html(f"""<style>
.stApp {{ background: radial-gradient(ellipse at 50% 32%, rgba(10,29,56,.82) 0%, rgba(10,29,56,.62) 45%,
                     rgba(10,29,56,.45) 100%), url('{bg}') center / cover no-repeat fixed; }}
.block-container {{ padding-top: 12vh; }}
.landing {{ text-align: center; color: #fff; margin-bottom: 18px; }}
.landing img {{ filter: drop-shadow(0 4px 10px rgba(0,0,0,.35)); }}
.landing h1 {{ color: #fff; font-family: var(--cond); font-weight: 800; font-size: clamp(2.4rem, 7vw, 3.6rem);
              line-height: 1; margin: 10px 0 8px; padding: 0; text-shadow: 0 2px 16px rgba(0,0,0,.35); }}
.landing p {{ color: #E6EDF5; margin: 0 auto; max-width: 36ch; }}
div[data-testid="stForm"] {{ background: rgba(255,255,255,.96); border: 0; border-radius: 16px;
                             box-shadow: 0 18px 40px rgba(5,20,40,.35); }}
</style>""")


def landing_header() -> str:
    return (f"<div class='landing'>{logo_svg(64)}<h1>Ton plan d'entraînement</h1>"
            "<p>Saisis le code d'accès reçu par e-mail.</p></div>")


# =========================================================================== bandeaux
def editor_track(counts: dict[str, int]) -> str:
    rows = "".join(
        f"<div class='row'><span class='n'>{i}</span><span class='name'>{e(DISTANCES[d].label)}</span>"
        f"<span class='count'>{n} élève{'s' if n > 1 else ''}</span></div>"
        for i, (d, n) in enumerate(counts.items(), start=1))
    return (f"<div class='track'><h1>Tableau de bord du coach</h1>"
            f"<p>Crée un profil par élève, ajuste son plan et ses allures, suis ses séances réalisées.</p>"
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
            f"<span class='v{' range' if p.is_range else ''}'>{e(p.pace_str)}<small> /km</small></span>"
            f"<span class='kmh'>{e(p.kmh_str)}</span><span class='eq'>{e(eq)}</span></div>")
    return f"<div class='paces'>{''.join(rows)}</div>"


def bib(name: str, distance: str, race_seconds: int, estimate: bool, race_date: date | None, n_weeks: int,
        race_time: str = "") -> str:
    dist = DISTANCES[distance]
    if race_date:
        days = (race_date - date.today()).days
        when = (f"Course le {fr_date(race_date, True)}" +
                (f", dans {days} jour{'s' if days > 1 else ''}" if days > 0 else
                 (", c'est aujourd'hui !" if days == 0 else "")))
    else:
        when = f"Plan de {n_weeks} semaines"
    done = f"<div class='done'>Réalisé en {e(race_time)}</div>" if race_time else ""
    return (f"<div class='bib' role='img' aria-label='Dossard : {e(name)}, objectif {e(format_race_time(race_seconds))}'>"
            f"<span class='pin tl'></span><span class='pin tr'></span><span class='pin bl'></span><span class='pin br'></span>"
            f"<div class='band'>{e(dist.label)}</div>"
            f"<div class='num'>{e(format_race_time(race_seconds))}</div>"
            f"{'<div class=est>temps estimé d’après ta VMA</div>' if estimate else ''}"
            f"<div class='who'>{e(name)}</div><div class='when'>{e(when)}</div>{done}</div>")


def student_hero(name: str, distance: str, race_seconds: int, estimate: bool, race_date: date | None,
                 n_weeks: int, paces: dict[str, Pace], basis: str, race_time: str = "") -> str:
    return (f"<div class='track'><div class='hero-grid'>"
            f"{bib(name, distance, race_seconds, estimate, race_date, n_weeks, race_time)}"
            f"<div><div class='basis'>{e(basis)}</div>{pace_lanes(paces, 'ton allure de course')}</div></div></div>")


def paces_track(paces: dict[str, Pace], basis: str = "") -> str:
    head = f"<div class='basis'>{e(basis)}</div>" if basis else ""
    return f"<div class='track' style='padding:12px 22px 14px'>{head}{pace_lanes(paces)}</div>"


# =========================================================================== séances
def pills(value, paces: dict[str, Pace]) -> str:
    out = []
    for code in pace_codes(value):
        bg, fg = ZONE_COLORS[code]
        txt = paces[code].pace_str if code in paces else ""
        out.append(f"<span class='pill' style='background:{bg};color:{fg}'>{e(PACE_LABELS[code])}"
                   f"{f' <b>{e(txt)}</b>' if txt else ''}</span>")
    return f"<span class='pills'>{''.join(out)}</span>" if out else ""


def session_title(r) -> str:
    return str(r["contenu"] or ("Séance à l'allure indiquée" if r["allure"] else "Séance libre"))


def session_meta(r, race: bool = False) -> str:
    items = [fr_date(r.get("date"), weekday=True), f"{r['km_env']} km" if r["km_env"] else "", r["duree_env"],
             f"dont {r['temps_aff']} à l'allure" if r["temps_aff"] and not race else ""]
    out = "".join(f"<span>{e(str(x))}</span>" for x in items if x)
    if r["remarque"]:
        out += f"<span class='note'>{e(str(r['remarque']))}</span>"
    return f"<span class='meta'>{out}</span>"


def week_header(sub: pd.DataFrame, position: int, today: date | None = None, extra: str = "") -> tuple[str, str]:
    """(HTML de l'en-tête de semaine, état « current » / « past » / « »)."""
    today = today or date.today()
    first = sub.iloc[0]
    start = first["debut"] if isinstance(first["debut"], date) else None
    state = ""
    if start:
        state = "current" if start <= today <= start + timedelta(days=6) else ("past" if start + timedelta(days=6) < today else "")
    summary = week_summary(sub)
    dates = f"<span class='wd'>du {fr_date(start)} au {fr_date(start + timedelta(days=6))}</span>" if start else ""
    vol = ", ".join(x for x in (summary.km_str, summary.duration_str, extra) if x)
    head = (f"<div class='wh'><span class='wn'>Semaine {int(position) + 1}</span>{dates}"
            f"{'<span class=tag>Cette semaine</span>' if state == 'current' else ''}<span class='vol'>{e(vol)}</span></div>")
    if first["phase"]:
        head += f"<div class='wphase'>{e(first['phase'])}</div>"
    return head, state


def week_cards(table: pd.DataFrame, paces: dict[str, Pace], today: date | None = None,
               status: dict[str, bool] | None = None, race_time: str = "") -> str:
    """Plan en cartes de semaines (lecture seule). `status` : séances réalisées (supervision du coach)."""
    if table.empty:
        return "<div class='empty'>Ce plan ne contient encore aucune séance.</div>"
    out = []
    for position in sorted(table["position"].unique()):
        sub = table[table["position"] == position]
        extra = ""
        if status is not None:
            n_done = sum(1 for sid in sub["session_id"] if status.get(sid))
            extra = f"{n_done}/{len(sub)} réalisée{'s' if n_done > 1 else ''}"
        head, state = week_header(sub, position, today, extra)
        out.append(f"<section class='week {state}'>{head}<ol>")
        for _, r in sub.iterrows():
            race = is_race_day(r["seance"])
            mark = ""
            if status is not None:
                ok = status.get(r["session_id"], False)
                mark = f"<span class='st' title='{'Réalisée' if ok else 'Non réalisée'}'>{'✅' if ok else '⬜'}</span>"
            title = session_title(r) + (f" — réalisé en {race_time}" if race and race_time else "")
            out.append(f"<li class='{'race' if race else ''}'>{mark or '<span></span>'}"
                       f"<span class='id'>{e(str(r['seance']))}</span>"
                       f"<div><div class='what'>{e(title)}</div>{session_meta(r, race)}</div>"
                       f"{pills(r['allure'], paces)}</li>")
        out.append("</ol></section>")
    return "".join(out)


def render(html_str: str) -> None:
    st.html(html_str)
