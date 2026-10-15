"""
Identité visuelle « piste d'athlétisme » : CSS global, page d'accueil, bandeaux, dossard et tour de piste de l'élève,
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
import math
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from core.calculs import Pace, format_minutes, format_race_time
from core.config import DISTANCES, PACE_BY_CODE, PACE_LABELS, ZONE_COLORS
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
[data-testid="stHeader"] { background: transparent; pointer-events: none; }
/* La barre d'outils de Streamlit ne doit pas masquer les boutons placés en haut de page */
[data-testid="stToolbar"] { pointer-events: none; }
[data-testid="stToolbar"] button, [data-testid="stToolbar"] a { pointer-events: auto; }
.block-container { padding-top: 1.6rem; padding-bottom: 4rem; max-width: 1280px; }
[data-testid="stSidebar"] { background: var(--night); }
[data-testid="stSidebar"] * { color: #E6EDF5; }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] * { color: #A9B8C9; }
[data-testid="stSidebar"] button { background: transparent; border-color: #49617E; }
[data-testid="stSidebar"] button:hover { border-color: var(--chrono); color: var(--chrono); }
[data-testid="stTab"] p { font-family: var(--cond); font-size: 1.3rem; font-weight: 600; }
[data-testid="stExpander"] details, div[data-testid="stForm"] { background: #fff; }
[class*="st-key-card-"], [class*="st-key-"][class*="-card-wk"] { background: #fff; }
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

/* ---- Dossard (espace élève) ---------------------------------------------------------- */
.bib { position: relative; background: #fff; color: var(--night); border-radius: 6px; padding: 0 0 14px;
       box-shadow: 0 10px 24px rgba(5,20,40,.35); text-align: center; transform: rotate(-1.2deg); }
.bib .band { background: var(--chrono); color: var(--night); font-family: var(--cond); font-weight: 700;
             font-size: 1rem; padding: 7px 34px; border-radius: 6px 6px 0 0; }
.bib .num { font-family: var(--cond); font-weight: 800; font-size: clamp(2.8rem, 5.2vw, 4.2rem); line-height: .95;
            letter-spacing: -.01em; margin: 14px 10px 2px; font-variant-numeric: tabular-nums; }
.bib .est { color: var(--muted); font-size: .85rem; margin-top: -2px; }
.bib .who { font-family: var(--cond); font-weight: 700; font-size: 1.45rem; }
.bib .when { color: var(--muted); font-size: .92rem; margin: 2px 12px 0; }
.bib .done { margin: 8px 16px 0; background: #E7F6EF; color: #17603F; border-radius: 6px; padding: 4px 8px;
             font-weight: 600; font-size: .92rem; }
.bib .pin { position: absolute; width: 11px; height: 11px; border-radius: 50%; background: var(--concrete);
            box-shadow: inset 0 1px 2px rgba(0,0,0,.35); }
.bib .pin.tl { top: 40px; left: 10px; } .bib .pin.tr { top: 40px; right: 10px; }
.bib .pin.bl { bottom: 10px; left: 10px; } .bib .pin.br { bottom: 10px; right: 10px; }

/* ---- Semaines ------------------------------------------------------------------------ */
.week, [class*="st-key-card-wk"], [class*="st-key-"][class*="-card-wk"] { background: #fff; border-radius: 12px; margin: 0 0 14px;
         border-left: 6px solid var(--track); padding: 14px 18px 8px; }
.week.current, [class*="st-key-card-wkcur"], [class*="st-key-"][class*="-card-wkcur"] { border-left-color: var(--chrono); box-shadow: 0 0 0 2px var(--chrono); }
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
[class*="card-wk"] [data-testid="stCheckbox"] label p { font-weight: 600; font-size: 1rem; }
.empty { background: #fff; border: 2px dashed var(--line); border-radius: 12px; padding: 22px; color: var(--muted); }
.progressline { display: flex; justify-content: space-between; color: var(--muted); font-size: .92rem; margin-top: 2px; }

/* ---- Espace élève : tour de piste, prochaine séance, ressenti, carnet ------------------ */
.lap { display: grid; grid-template-columns: 1fr 1fr; grid-template-areas: "bib oval" "text text";
       gap: 18px 28px; align-items: center; }
.lap .bibcol { grid-area: bib; width: 100%; max-width: 300px; justify-self: center; }
.lap .txt { grid-area: text; display: flex; flex-wrap: wrap; align-items: flex-end; gap: 12px 36px; }
.lap .msg { flex: 1 1 340px; }
.lap .oval { grid-area: oval; position: relative; width: 100%; max-width: 390px; justify-self: center; }
.lap .oval img { width: 100%; height: auto; display: block; }
.lap .center { position: absolute; inset: 0; display: grid; place-content: center; text-align: center; }
.lap .big { font-family: var(--cond); font-weight: 800; font-size: clamp(2.5rem, 7vw, 3.4rem); line-height: .9;
            color: #fff; font-variant-numeric: tabular-nums; }
.lap .small { color: #D6E2F0; font-size: .88rem; margin-top: 5px; }
.lap .hi { color: #D6E2F0; font-size: 1.05rem; margin: 0 0 2px; }
.lap h2 { color: #fff; font-family: var(--cond); font-weight: 800; font-size: clamp(1.9rem, 4.2vw, 2.7rem);
          line-height: 1; margin: 0 0 8px; padding: 0; }
.lap p { color: #D6E2F0; margin: 0; max-width: 58ch; }
.stats { display: flex; flex-wrap: wrap; gap: 10px 26px; border-top: 2px solid rgba(255,255,255,.55); padding-top: 10px;
         flex: 0 1 auto; }
.stat { color: #D6E2F0; font-size: .9rem; }
.stat b { display: block; font-family: var(--cond); color: #fff; font-size: 1.65rem; font-weight: 700; line-height: 1;
          font-variant-numeric: tabular-nums; }
.stat.goal b { color: var(--chrono); }
[class*="st-key-"][class*="card-next"], [class*="st-key-"][class*="card-race"],
[class*="st-key-"][class*="card-feel"] { background: #fff; border-radius: 14px; padding: 18px 20px 20px; }
[class*="st-key-"][class*="card-next"] { border-left: 8px solid var(--chrono); box-shadow: 0 10px 28px rgba(15,42,74,.12); }
[class*="st-key-"][class*="card-race"] { background: #FFF6D6; border: 2px solid var(--chrono); }
[class*="st-key-"][class*="card-feel"] { border-left: 8px solid #2F9E6E; }
.nx .when { color: var(--track); font-weight: 600; font-size: .98rem; }
.nx h3 { font-family: var(--cond); font-weight: 800; font-size: clamp(1.8rem, 5vw, 2.5rem); line-height: 1.02;
         margin: 2px 0 10px; padding: 0; color: var(--night); }
.nx .facts { display: flex; flex-wrap: wrap; gap: 4px 20px; color: var(--muted); align-items: baseline; }
.nx .facts b { color: var(--night); font-family: var(--cond); font-size: 1.3rem; font-weight: 700; }
.nx .note { font-style: italic; color: var(--night); margin-top: 6px; }
.lane { display: grid; grid-template-columns: 9px 1fr auto; gap: 14px; align-items: center; background: var(--concrete);
        border-radius: 9px; padding: 0 16px 0 0; margin-top: 10px; overflow: hidden; min-height: 54px; }
.lane .bar { align-self: stretch; }
.lane .lbl { font-weight: 600; color: var(--night); line-height: 1.2; }
.lane .lbl small { display: block; color: var(--muted); font-weight: 400; }
.lane .pv { font-family: var(--cond); font-weight: 800; font-size: 1.85rem; line-height: 1; color: var(--night);
            font-variant-numeric: tabular-nums; white-space: nowrap; }
.lane .pv small { font-family: Barlow, sans-serif; font-size: .8rem; font-weight: 500; color: var(--muted); }
.ask { font-family: var(--cond); font-weight: 700; font-size: 1.45rem; color: var(--night); line-height: 1.1; }
.ask small { display: block; font-family: Barlow, sans-serif; font-weight: 400; font-size: .92rem; color: var(--muted);
             margin-top: 3px; }
.allset { font-family: var(--cond); font-weight: 700; font-size: 1.5rem; color: var(--night); }
.log { list-style: none; margin: 0 !important; padding: 0 !important; }
[class*="st-key-"][class*="card-log"] { background: #fff; border-radius: 12px; padding: 6px 18px; }
.log li { display: grid; grid-template-columns: 78px 1fr; gap: 14px; padding: 12px 0; margin: 0 !important;
          border-top: 1px solid var(--line); }
.log li:first-child { border-top: 0; }
.log .d { font-family: var(--cond); font-weight: 700; color: var(--track); font-size: 1.08rem; line-height: 1.15; }
.log .t { font-weight: 600; color: var(--night); }
.log .w { color: var(--muted); font-size: .88rem; }
.log .f { display: inline-block; background: var(--concrete); border-radius: 999px; padding: 1px 10px; margin: 5px 0 0;
          font-size: .9rem; }
.log q { display: block; quotes: none; border-left: 3px solid var(--chrono); padding: 2px 0 2px 10px; margin-top: 6px;
         color: var(--night); white-space: pre-wrap; }
.log li.race { background: #FFF6D6; border-radius: 10px; padding: 12px; border-top: 0; margin: 4px 0; }
.log .chrono { font-family: var(--cond); font-weight: 800; font-size: 1.5rem; color: var(--night); }
.log .chrono small { font-family: Barlow, sans-serif; font-size: .9rem; font-weight: 600; color: var(--muted);
                     margin-left: 8px; }
.log .chrono small.faster { color: #17603F; }
.log .skip { display: inline-block; color: #B4532A; font-weight: 600; font-size: .9rem; margin-right: 10px; }
.coach-reply { background: #FFF8E1; border-left: 4px solid var(--chrono); border-radius: 8px; padding: 7px 12px;
               margin-top: 8px; color: var(--night); font-size: .93rem; white-space: pre-wrap; }
.coach-reply b { font-weight: 700; margin-right: 8px; }
.coach-reply .cr-d { color: var(--muted); font-size: .8rem; }
.coach-reply div { margin-top: 2px; }
.feel { color: var(--muted); font-size: .9rem; }
.feel q { quotes: none; font-style: italic; }
[class*="st-key-"][class*="card-race"] [data-testid="stForm"],
[class*="st-key-"][class*="card-feel"] [data-testid="stForm"] { background: transparent; padding: 0; }
[class*="st-key-"][class*="card-chart"] { background: #fff; border-radius: 14px; padding: 6px 10px 2px; }
[class*="st-key-"][class*="card-routes"] { background: #fff; border-radius: 16px; padding: 14px 16px 16px; }
.preview-note { background: var(--night); color: #E6EDF5; border-radius: 10px; padding: 10px 14px; margin-bottom: 12px; }

@media (max-width: 560px) {
  .lap { gap: 14px 12px; }
  .lap .stats { flex: 1 1 100%; }
  .lap .big { font-size: 1.7rem; }
  .lap .small { font-size: .7rem; margin-top: 2px; }
  .bib .band { font-size: .85rem; padding: 5px 20px; }
  .bib .num { font-size: 2.3rem; margin: 10px 6px 2px; }
  .bib .who { font-size: 1.12rem; }
  .bib .when, .bib .est, .bib .done { font-size: .74rem; }
  .bib .pin.tl, .bib .pin.tr { top: 32px; }
  .bib .pin { width: 8px; height: 8px; }
}
@media (prefers-reduced-motion: no-preference) {
  .bib { animation: pinned .5s ease-out both; }
  @keyframes pinned { from { transform: rotate(-6deg) translateY(-8px); opacity: 0; }
                      to { transform: rotate(-1.2deg); opacity: 1; } }
}
@media (max-width: 760px) {
  .pace { grid-template-columns: 30px 1fr auto; }
  .pace .kmh, .pace .eq { display: none; }
  .week li { grid-template-columns: 26px 44px 1fr; }
  .week li .pills { grid-column: 2 / 4; justify-content: flex-start; }
  .wh .vol { margin-left: 0; }
  .track { padding: 18px 16px; }
  .sesmeta { margin-left: 0; }
  .sesmeta .pills { justify-content: flex-start; }
  .log li { grid-template-columns: 1fr; gap: 2px; }
  [class*="st-key-"][class*="card-next"] { padding: 14px 14px 16px; }
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


def week_brief(sub: pd.DataFrame) -> str:
    """Phase et volume d'une semaine (contenu d'une semaine repliée)."""
    first = sub.iloc[0]
    summary = week_summary(sub)
    vol = ", ".join(x for x in (summary.km_str, summary.duration_str) if x)
    phase = f"<div class='wphase'>{e(first['phase'])}</div>" if first["phase"] else ""
    return f"{phase}<div class='wh'><span class='wd'>{e(vol)}</span></div>" if (phase or vol) else ""


def week_cards(table: pd.DataFrame, paces: dict[str, Pace], today: date | None = None,
               status: dict[str, bool] | None = None, race_time: str = "", notes: dict | None = None) -> str:
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
            note = (notes or {}).get(r["session_id"])
            feel = ""
            if note is not None and not note.empty:
                quote = f" <q>{e(note.commentaire)}</q>" if note.commentaire else ""
                feel = f"<div class='feel'>{e(note.label)}{quote}</div>"
            out.append(f"<li class='{'race' if race else ''}'>{mark or '<span></span>'}"
                       f"<span class='id'>{e(str(r['seance']))}</span>"
                       f"<div><div class='what'>{e(title)}</div>{session_meta(r, race)}{feel}</div>"
                       f"{pills(r['allure'], paces)}</li>")
        out.append("</ol></section>")
    return "".join(out)


# =========================================================================== espace élève
def _stadium(cx: float, cy: float, a: float, r: float) -> str:
    """Contour d'une piste (deux lignes droites, deux virages), départ à la ligne d'arrivée,
    dans le sens de course (anti-horaire)."""
    return (f"M{cx + a:.1f},{cy + r:.1f} A{r},{r} 0 0 0 {cx + a:.1f},{cy - r:.1f} L{cx - a:.1f},{cy - r:.1f} "
            f"A{r},{r} 0 0 0 {cx - a:.1f},{cy + r:.1f} Z")


def _stadium_point(cx: float, cy: float, a: float, r: float, t: float) -> tuple[float, float]:
    """Point situé à la fraction t (0 à 1) du tour, sur le contour de rayon r."""
    arc, total = math.pi * r, 2 * math.pi * r + 4 * a
    s = max(0.0, min(1.0, t)) * total
    if s <= arc:
        th = math.pi / 2 - s / r
        return cx + a + r * math.cos(th), cy + r * math.sin(th)
    s -= arc
    if s <= 2 * a:
        return cx + a - s, cy - r
    s -= 2 * a
    if s <= arc:
        th = -math.pi / 2 - s / r
        return cx - a + r * math.cos(th), cy + r * math.sin(th)
    return cx - a + (s - arc), cy + r


def lap_svg(p: float, n_weeks: int, p_from: float | None = None) -> str:
    """Tour de piste vu du dessus : la préparation = un tour ; le tracé jaune = séances faites.
    Renvoyé en data URI (balise <img>), car st.html filtre les balises <svg>."""
    cx, cy, a = 170, 105, 72
    p = max(0.0, min(1.0, p))
    p_from = p if p_from is None else max(0.0, min(1.0, p_from))
    lines = "".join(
        f"<path d='{_stadium(cx, cy, a, r)}' fill='none' stroke='#fff' stroke-width='1.3' "
        f"stroke-opacity='{.8 if r in (58, 98) else .45}'/>" for r in (58, 68, 78, 88, 98))
    ticks = ""
    for k in range(1, max(1, n_weeks)):
        x1, y1 = _stadium_point(cx, cy, a, 92, k / n_weeks)
        x2, y2 = _stadium_point(cx, cy, a, 98, k / n_weeks)
        ticks += f"<line x1='{x1:.1f}' y1='{y1:.1f}' x2='{x2:.1f}' y2='{y2:.1f}' stroke='#fff' stroke-opacity='.7' stroke-width='1.6'/>"
    dx, dy = _stadium_point(cx, cy, a, 63, p)
    anim = ""
    if abs(p - p_from) > 1e-6:
        anim = ("<style>.trail{animation:run 1.3s cubic-bezier(.25,.7,.3,1) both}"
                f"@keyframes run{{from{{stroke-dasharray:{p_from * 100:.2f} 100}}}}"
                ".dot{animation:pop .35s 1.15s both}@keyframes pop{from{opacity:0}}"
                "@media (prefers-reduced-motion: reduce){.trail,.dot{animation:none}}</style>")
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 340 210'>{anim}"
           f"<path d='{_stadium(cx, cy, a, 78)}' fill='none' stroke='#fff' stroke-opacity='.10' stroke-width='40'/>"
           f"{lines}{ticks}"
           f"<line x1='{cx + a}' y1='{cy + 56}' x2='{cx + a}' y2='{cy + 100}' stroke='#fff' stroke-width='3.5'/>"
           f"<path class='trail' d='{_stadium(cx, cy, a, 63)}' pathLength='100' fill='none' stroke='{CHRONO}' "
           f"stroke-width='7' stroke-linecap='round' stroke-dasharray='{p * 100:.2f} 100'/>"
           f"<circle class='dot' cx='{dx:.1f}' cy='{dy:.1f}' r='7.5' fill='#fff' stroke='{CHRONO}' stroke-width='3'/>"
           "</svg>")
    return f"data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}"


def bib(name: str, distance: str, race_seconds: int, estimate: bool, race_date: date | None, n_weeks: int,
        race_time: str = "", course: str = "") -> str:
    """Dossard de l'élève : nom de la course ou distance (bande jaune), objectif, prénom, date."""
    dist = DISTANCES[distance]
    course = (course or "").strip()
    if race_date:
        days = (race_date - date.today()).days
        when = (f"{dist.label if course else 'Course'} le {fr_date(race_date, True)}" +
                (f", dans {days} jour{'s' if days > 1 else ''}" if days > 0 else
                 (", c'est aujourd'hui !" if days == 0 else "")))
    else:
        when = (f"{dist.label}, plan" if course else "Plan") + f" de {n_weeks} semaines"
    done = f"<div class='done'>Réalisé en {e(race_time)}</div>" if race_time else ""
    return (f"<div class='bib' role='img' aria-label='Dossard : {e(name)}, objectif {e(format_race_time(race_seconds))}'>"
            f"<span class='pin tl'></span><span class='pin tr'></span><span class='pin bl'></span><span class='pin br'></span>"
            f"<div class='band'>{e(course or dist.label)}</div>"
            f"<div class='num'>{e(format_race_time(race_seconds))}</div>"
            f"{'<div class=est>temps estimé d’après ta VMA</div>' if estimate else ''}"
            f"<div class='who'>{e(name)}</div><div class='when'>{e(when)}</div>{done}</div>")


def lap_hero(*, bib_html: str, hello: str, title: str, text: str, big: str, small: str,
             stats: list[tuple[str, str, bool]], p: float, n_weeks: int, p_from: float | None, label: str) -> str:
    """Bandeau de l'élève : dossard, tour de piste (progression), message et chiffres clés."""
    items = "".join(f"<div class='stat{' goal' if goal else ''}'><b>{e(v)}</b>{e(k)}</div>" for k, v, goal in stats)
    return (f"<div class='track'><div class='lap'>"
            f"<div class='bibcol'>{bib_html}</div>"
            f"<div class='oval'><img src='{lap_svg(p, n_weeks, p_from)}' alt='{e(label)}'>"
            f"<div class='center'><div class='big'>{e(big)}</div><div class='small'>{e(small)}</div></div></div>"
            f"<div class='txt'><div class='msg'><div class='hi'>{e(hello)}</div><h2>{e(title)}</h2><p>{e(text)}</p></div>"
            f"<div class='stats'>{items}</div></div></div></div>")


def pace_lane_rows(value, paces: dict[str, Pace]) -> str:
    out = []
    for code in pace_codes(value):
        if code not in paces:
            continue
        bg, _ = ZONE_COLORS[code]
        out.append(f"<div class='lane'><span class='bar' style='background:{bg}'></span>"
                   f"<span class='lbl'>{e(PACE_LABELS[code])}<small>{e(PACE_BY_CODE[code].description)}</small></span>"
                   f"<span class='pv'>{e(paces[code].pace_str)}<small> /km</small></span></div>")
    return "".join(out)


def next_session_html(r, paces: dict[str, Pace], when: str) -> str:
    """Carte « Ta prochaine séance » : quoi, combien, à quelle allure."""
    facts = []
    if r["km_env"]:
        facts.append(f"<span><b>{e(str(r['km_env']))}</b> km</span>")
    if r["duree_env"]:
        facts.append(f"<span><b>{e(str(r['duree_env']))}</b></span>")
    if r["temps_aff"]:
        facts.append(f"<span>dont <b>{e(str(r['temps_aff']))}</b> à l'allure</span>")
    note = f"<div class='note'>{e(str(r['remarque']))}</div>" if r["remarque"] else ""
    return (f"<div class='nx'><div class='when'>{e(when)}</div><h3>{e(session_title(r))}</h3>"
            f"<div class='facts'>{''.join(facts)}</div>{note}{pace_lane_rows(r['allure'], paces)}</div>")


def race_card_html(r, paces: dict[str, Pace], when: str, race_time: str) -> str:
    title = f"Ton chrono : {race_time}" if race_time else session_title(r)
    return (f"<div class='nx'><div class='when'>{e(when)}</div><h3>🏁 {e(title)}</h3>"
            f"{pace_lane_rows(r['allure'], paces)}</div>")


def reply_html(reply, who: str = "Ton coach") -> str:
    """Réponse du coach (bloc jaune)."""
    if reply is None:
        return ""
    return (f"<div class='coach-reply'><b>💬 {e(who)}</b>"
            f"<span class='cr-d'>{e(reply.le[8:10] + '/' + reply.le[5:7]) if len(reply.le) >= 10 else ''}</span>"
            f"<div>{e(reply.texte)}</div></div>")


def journal_html(entries: list[dict], race_time: str = "", replies: dict | None = None) -> str:
    """Carnet : séances réalisées, « pas faites » ou commentées, avec ressenti, commentaire, km réels et
    réponse du coach."""
    if not entries:
        return ("<div class='empty'>Ton carnet se remplit au fil des séances : coche une séance faite, puis dis "
                "comment tu l'as sentie.</div>")
    items = []
    for x in entries:
        r, note = x["row"], x["note"]
        d = date.fromisoformat(x["when"]) if x["when"] else None
        title = session_title(r)
        chrono = f"<div class='chrono'>{e(race_time)}</div>" if x["race"] and race_time else ""
        feel = f"<span class='f'>{e(note.label)}</span>" if note.ressenti else ""
        quote = f"<q>{e(note.commentaire)}</q>" if note.commentaire else ""
        skip = x.get("skip")
        km = x.get("km")
        if skip is not None:
            status = f"<span class='skip'>✗ Pas faite{' : ' + e(skip.raison) if skip.raison else ''}</span>"
        elif not x["done"]:
            status = "<span class='w'>pas encore cochée</span>"
        else:
            status = ""
        km_html = (f"<span class='w'>{e(str(km).replace('.', ','))} km courus"
                   f"{' (prévu ' + e(str(r['km_env'])) + ')' if r['km_env'] else ''}</span>") if km else ""
        reply = reply_html((replies or {}).get(r["session_id"]))
        items.append(f"<li class='{'race' if x['race'] else ''}'><div class='d'>{e(fr_date(d, weekday=True)) if d else ''}</div>"
                     f"<div><div class='t'>{'🏁 ' if x['race'] else ''}{e(title)}</div>"
                     f"<div class='w'>Semaine {int(r['position']) + 1}</div>{chrono}{status}{km_html}{feel}{quote}"
                     f"{reply}</div></li>")
    return f"<ul class='log'>{''.join(items)}</ul>"


def recent_notes_html(items: list) -> str:
    """Supervision : derniers ressentis de tous les élèves (le, prénom, séance, note)."""
    out = []
    for le, name, r, note in items:
        d = date.fromisoformat(le[:10]) if le else None
        feel = f"<span class='f'>{e(note.label)}</span>" if note.ressenti else ""
        quote = f"<q>{e(note.commentaire)}</q>" if note.commentaire else ""
        race = is_race_day(r["seance"])
        out.append(f"<li class='{'race' if race else ''}'><div class='d'>{e(fr_date(d, weekday=True)) if d else ''}</div>"
                   f"<div><div class='t'>{e(name)}</div><div class='w'>{'🏁 ' if race else ''}{e(session_title(r))}, "
                   f"semaine {int(r['position']) + 1}</div>{feel}{quote}</div></li>")
    return f"<ul class='log'>{''.join(out)}</ul>"


def history_html(records: list) -> str:
    """Espace élève, « Mes courses » : chaque course terminée avec son chrono et son ressenti."""
    if not records:
        return ("<div class='empty'>Tes courses terminées apparaîtront ici, avec ton chrono, l'écart à ton objectif "
                "et ton ressenti.</div>")
    items = []
    for r in records:
        dist = DISTANCES[r.distance].label
        sub = (f"{dist}, " if r.course != dist else "") + ("temps estimé " if r.objective_is_estimate else "objectif ") + r.objective
        gap = ""
        if r.gap:
            gap = f"<small class='{'faster' if r.gap.startswith('−') else ''}'>{e(r.gap)}</small>"
        chrono = f"<div class='chrono'>{e(r.race_time)}{gap}</div>" if r.race_time else \
            "<div class='w'>Temps non saisi</div>"
        feel = f"<span class='f'>{e(r.feeling)}</span>" if r.feeling else ""
        quote = f"<q>{e(r.comment)}</q>" if r.comment else ""
        km = f"{r.km_done:.0f}".replace(".", ",")
        items.append(f"<li class='race'><div class='d'>{e(fr_date(r.race_date, True)) if r.race_date else ''}</div>"
                     f"<div><div class='t'>🏁 {e(r.course)}</div><div class='w'>{e(sub)}</div>{chrono}{feel}{quote}"
                     f"<div class='w'>Plan réalisé à {r.completion} % ({r.done}/{r.total} séances, {km} km)</div>"
                     f"</div></li>")
    return f"<ul class='log'>{''.join(items)}</ul>"


def preview_note(name: str) -> str:
    return (f"<div class='preview-note'>Voici l'espace de {e(name)}, tel qu'il le voit. Lecture seule : seul l'élève "
            "coche ses séances et écrit ses ressentis.</div>")


def render(html_str: str) -> None:
    st.html(html_str)
