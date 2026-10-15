"""
Découverte de parcours.

Élève : il saisit sa ville ; l'appli affiche les parcours conseillés par son coach, puis les parcours
existants trouvés automatiquement autour de la ville dans OpenStreetMap (core/decouverte.py) :
parcours de course et parcours sportifs balisés, sentiers, tours de parcs, pistes d'athlétisme,
avec leur distance, un lien vers la carte et le tracé affiché sur une carte.
Coach : onglet « Parcours » pour ajouter ses parcours conseillés, à la main ou depuis la recherche.
"""

from __future__ import annotations

import base64
import html
import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import decouverte, parcours
from ui import composants as ui
from ui.design import render

e = html.escape
_MAP = ("<polygon points='1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6'/>"
        "<line x1='8' y1='2' x2='8' y2='18'/><line x1='16' y1='6' x2='16' y2='22'/>")
_ICONS = {
    "coach": "<path d='M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z'/>",
    "course": "<polyline points='22 12 18 12 15 21 9 3 6 12 2 12'/>",
    "sportif": ("<path d='M6.5 6.5h11'/><path d='M6.5 17.5h11'/><path d='M3 9v6'/><path d='M21 9v6'/>"
                "<path d='M6.5 4v16'/><path d='M17.5 4v16'/>"),
    "sentier": _MAP,
    "parc": ("<path d='M12 22v-6'/><path d='M12 16l-5-1 2-3-3-1 6-9 6 9-3 1 2 3z'/>"),
    "piste": "<rect x='3' y='6' width='18' height='12' rx='6'/><rect x='7' y='9.5' width='10' height='5' rx='2.5'/>",
}
KIND_COLORS = {"coach": "#FFC629", "course": "#1B4F8C", "sportif": "#2F9E6E", "sentier": "#6E56CF",
               "parc": "#199E70", "piste": "#E2611B"}
ROUTES_CSS = """
.rt-h { font-family: var(--cond); font-weight: 700; font-size: 1.25rem; color: var(--night); margin: 16px 0 8px; }
.rt-card { display: flex; align-items: center; gap: 14px; background: #fff; border: 1px solid #E3E9F0;
           border-radius: 14px; padding: 12px 14px; margin: 0 0 10px; }
.rt-card.coach { background: #FFF8E1; border-color: #F6D77A; }
.rt-ico { flex: 0 0 38px; width: 38px; height: 38px; border-radius: 50%; display: grid; place-items: center; }
.rt-ico img { width: 21px; height: 21px; }
.rt-body { flex: 1; min-width: 0; }
.rt-name { font-weight: 600; font-size: 1rem; color: var(--night); line-height: 1.3; }
.rt-meta { font-size: .86rem; color: var(--muted); }
.rt-km { font-family: var(--cond); font-weight: 700; font-size: 1.35rem; color: var(--night); white-space: nowrap; }
.rt-link { font-size: .88rem; font-weight: 600; color: var(--track); }
.rt-src { color: var(--muted); font-size: .8rem; margin-top: 6px; }
"""


def _icon(kind: str) -> str:
    color = "#1A1A1A" if kind == "coach" else "white"
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' "
           f"stroke='{color}' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>{_ICONS[kind]}</svg>")
    img = f"<img src='data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}' alt=''>"
    return f"<span class='rt-ico' style='background:{KIND_COLORS[kind]}'>{img}</span>"


def routes_html(routes: list[parcours.Route]) -> str:
    """Parcours conseillés par le coach."""
    out = []
    for r in routes:
        link = (f"<a class='rt-link' href='{e(r.lien)}' target='_blank' rel='noopener noreferrer'>Voir la carte</a>"
                if r.lien else "")
        out.append(f"<div class='rt-card coach'>{_icon('coach')}<div class='rt-body'>"
                   f"<div class='rt-name'>{e(r.nom)}</div><div class='rt-meta'>Conseillé par ton coach, {e(r.ville)}</div>"
                   f"{link}</div><span class='rt-km'>{e(r.distance_str)}</span></div>")
    return "".join(out)


def found_html(routes: list[decouverte.FoundRoute], origin: str = "du centre") -> str:
    """Parcours trouvés dans OpenStreetMap."""
    out = []
    near = "passe tout près" if origin != "du centre" else "passe près du centre"
    for r in routes:
        meta = [("boucle" if r.loop else "aller simple") if r.kind != "piste" else "",
                near if r.center_km < 0.3 else f"à {str(r.center_km).replace('.', ',')} km {origin}"]
        out.append(f"<div class='rt-card'>{_icon(r.kind)}<div class='rt-body'>"
                   f"<div class='rt-name'>{e(r.name)}</div><div class='rt-meta'>{e(', '.join(m for m in meta if m))}</div>"
                   f"<a class='rt-link' href='{e(r.url)}' target='_blank' rel='noopener noreferrer'>Ouvrir la carte</a>"
                   f"</div><span class='rt-km'>{e(r.length_str)}</span></div>")
    return "".join(out)


def route_map(route: decouverte.FoundRoute) -> go.Figure:
    """Tracé du parcours sur fond OpenStreetMap."""
    lats, lons = [], []
    for line in route.lines:
        lats += [p[0] for p in line] + [None]
        lons += [p[1] for p in line] + [None]
    pts = [p for line in route.lines for p in line] or [(route.lat, route.lon)]
    la = [p[0] for p in pts]
    lo = [p[1] for p in pts]
    span = max(max(la) - min(la), (max(lo) - min(lo)) * math.cos(math.radians(sum(la) / len(la))), 0.002)
    zoom = max(9.0, min(16.5, math.log2(360 / span) - 1.6))
    fig = go.Figure(go.Scattermap(lat=lats, lon=lons, mode="lines", line={"width": 4, "color": "#1B4F8C"},
                                  hoverinfo="skip", name=route.name))
    fig.update_layout(map={"style": "open-street-map", "zoom": zoom,
                           "center": {"lat": (max(la) + min(la)) / 2, "lon": (max(lo) + min(lo)) / 2}},
                      margin={"l": 0, "r": 0, "t": 0, "b": 0}, height=360, showlegend=False)
    return fig


@st.cache_data(ttl=7 * 24 * 3600, show_spinner=False, max_entries=300)
def _geocode(city_key: str, address: bool = False):
    return decouverte.geocode(city_key, address=address)


class _Partial(Exception):
    """Résultats incomplets : renvoyés par une exception pour ne PAS les garder en mémoire 7 jours."""

    def __init__(self, found: list, notes: list[str]):
        super().__init__("partiel")
        self.found, self.notes = found, notes


@st.cache_data(ttl=7 * 24 * 3600, show_spinner=False, max_entries=200)
def _discover(lat: float, lon: float, name: str, label: str, radius: int, kind: str = "ville"):
    notes: list[str] = []
    found = decouverte.discover(decouverte.Place(name, lat, lon, label, kind), radius, notes=notes)
    if notes:
        raise _Partial(found, notes)
    return found


def find_routes(city: str, radius: int) -> tuple[decouverte.Place | None, list[decouverte.FoundRoute], list[str]]:
    """(ville, parcours trouvés, messages si les résultats sont incomplets). Les résultats complets sont
    gardés en mémoire 7 jours. Lève DiscoveryError si aucun service ne répond."""
    place = _geocode(parcours.normalize(city))
    if place is None:
        return None, [], []
    found, notes = routes_around(place, radius)
    return place, found, notes


def routes_around(place: decouverte.Place, radius: int) -> tuple[list[decouverte.FoundRoute], list[str]]:
    """Parcours autour d'un lieu précis (ville ou adresse). Lève DiscoveryError."""
    lat, lon = round(place.lat, 4), round(place.lon, 4)      # ~10 m : même cache pour une même adresse
    try:
        return _discover(lat, lon, place.name, place.label, radius, place.kind), []
    except _Partial as partial:
        return partial.found, partial.notes


def discovery_error(exc: decouverte.DiscoveryError) -> None:
    """Message d'erreur lisible + détail technique discret (utile pour le diagnostic)."""
    st.warning(str(exc), icon="🗺️")
    if exc.detail:
        st.caption(f"Détail technique : {exc.detail}")


def show_found(place: decouverte.Place, found: list[decouverte.FoundRoute], key: str) -> None:
    """Résultats groupés par type, filtre de distance et tracé sur la carte."""
    band = st.pills("Distance", list(decouverte.DISTANCE_BANDS), default="Toutes", key=f"{key}_band",
                    required=True)
    shown = decouverte.filter_by_length(found, band)
    if not shown:
        render("<div class='empty'>Aucun parcours de cette distance autour de cette ville : essaie une autre "
               "distance ou un rayon plus grand.</div>")
        return
    for kind, label in decouverte.KINDS.items():
        group = [r for r in shown if r.kind == kind]
        if not group:
            continue
        title = {"course": "Parcours de course", "sportif": "Parcours sportifs", "sentier": "Sentiers balisés",
                 "parc": "Tours de parcs", "piste": "Pistes d'athlétisme"}[kind]
        render(f"<div class='rt-h'>{title} ({len(group)})</div>" + found_html(group[:8], place.origin))
        if len(group) > 8:
            with st.expander(f"Voir les {len(group) - 8} autres"):
                render(found_html(group[8:], place.origin))
    by_key = {f"{r.osm_type}/{r.osm_id}": r for r in shown if r.lines}
    if by_key:
        pick = st.selectbox("Voir le tracé sur la carte", list(by_key), key=f"{key}_map",
                            format_func=lambda k: f"{by_key[k].name} ({by_key[k].length_str})")
        st.plotly_chart(route_map(by_key[pick]), config={"displayModeBar": False, "scrollZoom": True},
                        theme=None, key=f"{key}_fig_{pick}")
    render(f"<div class='rt-src'>{e(decouverte.ATTRIBUTION)}. Parcours trouvés autour de {e(place.label)}.</div>")


def render_student_routes(prefix: str) -> None:
    """Onglet élève « Découverte de parcours »."""
    st.html(f"<style>{ROUTES_CSS}</style>")
    _student_routes(prefix)


def _place_from(chosen: dict) -> decouverte.Place | None:
    """Lieu choisi dans le champ adresse : suggestion (position connue) ou texte tapé (à situer)."""
    if chosen.get("lat") is not None and chosen.get("lon") is not None:
        label = str(chosen.get("label") or "")
        city = str(chosen.get("city") or label.split(",")[-1]).strip()
        return decouverte.Place(city or label, float(chosen["lat"]), float(chosen["lon"]), label,
                                "adresse" if chosen.get("kind") == "adresse" else "ville")
    query = str(chosen.get("query") or chosen.get("label") or "").strip()
    return _geocode(parcours.normalize(query), address=True) if query else None


@st.fragment
def _student_routes(prefix: str) -> None:
    """Recherche par adresse (suggestions pendant la frappe) ; seule cette partie se recharge."""
    from ui.adresse import address_input

    store = ui.app_store()
    routes = parcours.load_routes(store)
    addr_key, pick_key = f"{prefix}_rt_addr", f"{prefix}_rt_pick"

    def typed() -> None:
        st.session_state[pick_key] = None          # une adresse tapée remplace la ville choisie

    with st.container(key=f"{prefix}-card-routes"):
        c_addr, c_radius = st.columns([3, 1.7], vertical_alignment="bottom")
        with c_addr:
            chosen = address_input(addr_key, on_change=typed)
        radius = c_radius.segmented_control("Rayon", [2, 5, 10, 20], default=5, key=f"{prefix}_rt_radius",
                                            format_func=lambda r: f"{r} km", required=True)
        towns = parcours.cities(routes)
        if towns:
            st.pills("Villes où ton coach conseille des parcours", towns, key=pick_key)
        pick = st.session_state.get(pick_key)
        if not pick and not chosen:
            st.caption("Commence à taper ton adresse ou ta ville : choisis une proposition, l'appli cherche les "
                       "parcours qui existent autour (parcours balisés, parcs, pistes d'athlétisme) et ceux que ton "
                       "coach te conseille. Ton adresse reste sur ton appareil.")
            return
        try:
            with st.spinner("Recherche des parcours…"):
                place = _geocode(parcours.normalize(pick)) if pick else _place_from(chosen)
                if place is None:
                    what = pick or (chosen or {}).get("label", "")
                    render(f"<div class='empty'>« {e(what)} » introuvable. Vérifie l'orthographe ou choisis une "
                           "des propositions.</div>")
                    return
                coach = parcours.search(routes, place.name)
                if coach:
                    render("<div class='rt-h'>Conseillés par ton coach</div>" + routes_html(coach))
                found, notes = routes_around(place, radius)
        except decouverte.DiscoveryError as exc:
            discovery_error(exc)
            return
        for note in notes:
            st.info(note, icon="ℹ️")
        if not found:
            render(f"<div class='empty'>Aucun parcours trouvé dans un rayon de {radius} km autour de "
                   f"{e(place.label)}. Essaie un rayon plus grand.</div>")
            return
        show_found(place, found, f"{prefix}_rt")


def render_editor_routes() -> None:
    """Onglet coach « Parcours » : ajout, modification et suppression des parcours."""
    store = ui.app_store()
    key = "routes"
    ver = ui.version(key)

    def add() -> None:
        g = lambda k: st.session_state.get(f"rt_new_{k}", "")  # noqa: E731
        try:
            route = parcours.add_route(store, g("ville"), g("nom"), g("km"), g("lien"))
        except ValueError as exc:
            ui.notify(str(exc), "error")
            return
        for k in ("nom", "km", "lien"):
            st.session_state[f"rt_new_{k}"] = ""
        ui.saved(f"Parcours « {route.nom} » ajouté pour {route.ville}")
        ui.bump(key)

    st.markdown("#### Parcours conseillés aux élèves")
    st.caption("Les élèves voient automatiquement les parcours existants autour de leur ville (OpenStreetMap). "
               "Ceux de cette liste apparaissent en premier, « conseillés par ton coach ». Tu peux les ajouter "
               "depuis la recherche ci-dessous ou à la main ; le lien peut pointer vers n'importe quelle carte.")
    with st.expander("Trouver des parcours existants et les ajouter à ta liste", icon=":material/travel_explore:",
                     expanded=True):
        c_city, c_radius = st.columns([3, 1.4], vertical_alignment="bottom")
        city = c_city.text_input("Ville", key="rt_find_city", placeholder="ex. Bordeaux")
        radius = c_radius.segmented_control("Rayon", [5, 10, 20], default=10, key="rt_find_radius",
                                            format_func=lambda r: f"{r} km", required=True)
        if city.strip():
            try:
                with st.spinner(f"Recherche autour de {city.strip()}…"):
                    place, found, notes = find_routes(city, radius)
            except decouverte.DiscoveryError as exc:
                discovery_error(exc)
                place, found, notes, failed = None, [], [], True
            else:
                failed = False
            for note in notes:
                st.info(note, icon="ℹ️")
            if place is not None and found:
                table = pd.DataFrame([{"Nom": r.name, "Type": r.kind_label, "Distance (km)": r.length_km,
                                       "Boucle": "oui" if r.loop else "non", "Du centre (km)": r.center_km}
                                      for r in found])
                st.caption(f"{len(found)} parcours autour de {place.label}. Sélectionne ceux à conseiller à tes élèves.")
                picked = st.dataframe(table, hide_index=True, width="stretch", on_select="rerun",
                                      selection_mode="multi-row", key=f"rt_find_table_{ver}")
                rows = picked.selection.rows if picked else []
                if st.button(f"Ajouter la sélection à ma liste ({len(rows)})", type="primary", disabled=not rows,
                             icon=":material/playlist_add:", key=f"rt_find_add_{ver}"):
                    added, skipped = 0, 0
                    for i in rows:
                        r = found[i]
                        try:
                            parcours.add_route(store, place.name, r.name, r.length_km, r.url)
                            added += 1
                        except ValueError:
                            skipped += 1
                    ui.saved(f"{added} parcours ajouté(s) pour {place.name}" + (f", {skipped} déjà présent(s)"
                                                                                if skipped else ""))
                    ui.bump(key)
                    st.rerun()
                st.caption(decouverte.ATTRIBUTION)
            elif place is not None:
                st.caption("Aucun parcours trouvé : essaie un rayon plus grand.")
            elif not failed:
                st.caption("Ville introuvable.")

    st.markdown("##### Ajouter un parcours à la main")
    with st.container(border=True, key="card-route-new"):
        with st.form("route_new", border=False):
            c1, c2, c3 = st.columns([1.2, 2, 0.8])
            c1.text_input("Ville", key="rt_new_ville", placeholder="ex. Lyon")
            c2.text_input("Nom du parcours", key="rt_new_nom", placeholder="ex. Boucle du parc de la Tête d'Or")
            c3.text_input("Distance (km)", key="rt_new_km", placeholder="ex. 7,5")
            st.text_input("Lien vers la carte (facultatif)", key="rt_new_lien", placeholder="https://…")
            st.form_submit_button("Ajouter le parcours", type="primary", icon=":material/add_location_alt:",
                                  on_click=add)

    routes = parcours.load_routes(store)
    if not routes:
        st.caption("Aucun parcours conseillé pour l'instant.")
        return
    df = pd.DataFrame([{"id": r.id, "Ville": r.ville, "Nom": r.nom, "Distance (km)": r.distance_km,
                        "Lien": r.lien, "ajoute_le": r.ajoute_le} for r in routes])
    st.caption(f"{len(routes)} parcours, {len(parcours.cities(routes))} villes. Double-clique sur une case pour la "
               "modifier ; coche une ligne puis la corbeille pour la supprimer.")
    edited = st.data_editor(
        df, key=f"routes_ed_{ver}", hide_index=True, width="stretch", num_rows="dynamic",
        column_order=["Ville", "Nom", "Distance (km)", "Lien"],
        column_config={
            "Distance (km)": st.column_config.NumberColumn(min_value=0.1, max_value=500.0, step=0.1, format="%.1f"),
            "Lien": st.column_config.LinkColumn(display_text="Voir la carte", validate=r"^https?://.+"),
        })
    if not edited.equals(df):
        try:
            new = [parcours.make_route(r["Ville"], r["Nom"], r["Distance (km)"], r["Lien"] or "",
                                       route_id=r["id"] if isinstance(r["id"], str) and r["id"] else None,
                                       ajoute_le=r["ajoute_le"] if isinstance(r["ajoute_le"], str) else None)
                   for _, r in edited.iterrows()
                   if any(str(r[c]).strip() not in ("", "nan", "None") for c in ("Ville", "Nom"))]
        except ValueError as exc:
            st.warning(f"Modification non enregistrée : {exc}", icon="⚠️")
            return
        parcours.save_routes(store, new)
        ui.saved("Parcours enregistrés")
        ui.bump(key)
        st.rerun()
