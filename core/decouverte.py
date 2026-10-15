"""
Découverte automatique de parcours existants autour d'une ville, à partir d'OpenStreetMap (données
ouvertes, gratuites, sans compte ni clé) :

* Nominatim situe la ville (latitude, longitude) ;
* Overpass renvoie, dans un rayon donné :
    - les parcours balisés : relations route=running (course), route=fitness_trail (parcours
      sportif / de santé), route=foot et route=hiking (sentiers PR…) ;
    - les parcs nommés (leisure=park), avec la longueur de leur tour ;
    - les pistes d'athlétisme (leisure=track + sport=athletics/running).

La longueur est calculée sur le tracé réel. Les très longs itinéraires (GR nationaux de centaines
de km) sont écartés. Les données © contributeurs OpenStreetMap (licence ODbL) : l'attribution est
affichée avec les résultats.

Les appels réseau passent par `fetch` (remplaçable dans les tests).
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

OVERPASS_URLS = [u for u in (os.environ.get("PLAN_OSM_OVERPASS_URL"),
                             "https://overpass-api.de/api/interpreter",
                             "https://overpass.kumi.systems/api/interpreter") if u]
NOMINATIM_URL = os.environ.get("PLAN_OSM_NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
USER_AGENT = "CoachRunningApp/1.0 (plans d'entrainement course a pied; +https://github.com/baaptistebrt/App-course-pied)"
ATTRIBUTION = "Parcours et cartes : © les contributeurs d'OpenStreetMap (licence ODbL)"

KINDS = {   # ordre d'affichage
    "course": "Parcours de course balisé",
    "sportif": "Parcours sportif",
    "sentier": "Sentier balisé",
    "parc": "Tour de parc",
    "piste": "Piste d'athlétisme",
}
ROUTE_KIND = {"running": "course", "fitness_trail": "sportif", "foot": "sentier", "hiking": "sentier"}
DISTANCE_BANDS = {"Toutes": (0, 1000), "Moins de 5 km": (0, 5), "5 à 10 km": (5, 10),
                  "10 à 21 km": (10, 21.1), "Plus de 21 km": (21.1, 1000)}
MAX_ROUTE_KM, MIN_ROUTE_KM = 60.0, 1.0
MAX_RELATIONS = 40


class DiscoveryError(Exception):
    """Service OpenStreetMap injoignable ou réponse inattendue (message lisible pour l'élève)."""


@dataclass(frozen=True)
class Place:
    name: str
    lat: float
    lon: float
    label: str


@dataclass(frozen=True)
class FoundRoute:
    osm_type: str               # « relation » ou « way »
    osm_id: int
    name: str
    kind: str                   # clé de KINDS
    length_km: float
    loop: bool
    center_km: float            # distance au centre de la ville
    lat: float
    lon: float
    lines: tuple = field(default=(), compare=False, repr=False)   # ((lat, lon), …) par tronçon

    @property
    def kind_label(self) -> str:
        return KINDS[self.kind]

    @property
    def url(self) -> str:
        return f"https://www.openstreetmap.org/{self.osm_type}/{self.osm_id}"

    @property
    def length_str(self) -> str:
        if self.length_km < 1:
            return f"{round(self.length_km * 1000, -1):.0f} m"
        return f"{self.length_km:.1f}".rstrip("0").rstrip(".").replace(".", ",") + " km"


# ----------------------------------------------------------------------------
# Réseau
# ----------------------------------------------------------------------------
def fetch(url: str, *, params: dict | None = None, data: dict | None = None, timeout: float = 45):
    """GET (params) ou POST (data) ; renvoie le JSON. Lève DiscoveryError en cas d'échec."""
    import requests   # dépendance de Streamlit, toujours disponible

    try:
        headers = {"User-Agent": USER_AGENT, "Accept-Language": "fr"}
        if data is not None:
            resp = requests.post(url, data=data, headers=headers, timeout=timeout)
        else:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        raise DiscoveryError("Le service de cartes OpenStreetMap ne répond pas. Réessaie dans un instant.") from exc
    if resp.status_code == 429:
        raise DiscoveryError("Le service de cartes est très sollicité. Réessaie dans une minute.")
    if resp.status_code != 200:
        raise DiscoveryError(f"Le service de cartes a répondu une erreur ({resp.status_code}). Réessaie plus tard.")
    try:
        return resp.json()
    except ValueError as exc:
        raise DiscoveryError("Réponse inattendue du service de cartes. Réessaie plus tard.") from exc


def overpass(query: str, fetcher=fetch) -> list[dict]:
    """Exécute une requête Overpass, avec un serveur de secours."""
    last = None
    for url in OVERPASS_URLS:
        try:
            return fetcher(url, data={"data": query}).get("elements", [])
        except DiscoveryError as exc:
            last = exc
    raise last or DiscoveryError("Aucun serveur OpenStreetMap disponible.")


# ----------------------------------------------------------------------------
# Géométrie
# ----------------------------------------------------------------------------
def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def line_km(points) -> float:
    return sum(haversine_km(points[i], points[i + 1]) for i in range(len(points) - 1))


def area_km2(points) -> float:
    """Aire d'un polygone (projection locale), en km²."""
    if len(points) < 3:
        return 0.0
    lat0 = math.radians(sum(p[0] for p in points) / len(points))
    xy = [(math.radians(p[1]) * 6371 * math.cos(lat0), math.radians(p[0]) * 6371) for p in points]
    return abs(sum(xy[i][0] * xy[i - 1][1] - xy[i - 1][0] * xy[i][1] for i in range(len(xy)))) / 2


def _geom(element: dict) -> list[tuple[float, float]]:
    return [(g["lat"], g["lon"]) for g in element.get("geometry") or [] if g]


def _bbox_diag_km(bounds: dict | None) -> float:
    if not bounds:
        return 0.0
    return haversine_km((bounds["minlat"], bounds["minlon"]), (bounds["maxlat"], bounds["maxlon"]))


def _bbox_center(bounds: dict) -> tuple[float, float]:
    return ((bounds["minlat"] + bounds["maxlat"]) / 2, (bounds["minlon"] + bounds["maxlon"]) / 2)


# ----------------------------------------------------------------------------
# Recherche
# ----------------------------------------------------------------------------
def geocode(city: str, fetcher=fetch) -> Place | None:
    """Situe une ville (en France en priorité). None si elle est introuvable."""
    city = (city or "").strip()
    if not city:
        return None
    for extra in ({"countrycodes": "fr"}, {}):
        found = fetcher(NOMINATIM_URL, params={"q": city, "format": "jsonv2", "limit": 1, "accept-language": "fr",
                                               **extra})
        if found:
            hit = found[0]
            label = str(hit.get("display_name", city))
            return Place(name=str(hit.get("name") or city), lat=float(hit["lat"]), lon=float(hit["lon"]),
                         label=label)
    return None


def _query_overview(place: Place, radius_km: float) -> str:
    r, lat, lon = int(radius_km * 1000), place.lat, place.lon
    around = f"(around:{r},{lat:.6f},{lon:.6f})"
    return (f"[out:json][timeout:40];"
            f"relation[\"type\"=\"route\"][\"route\"~\"^(running|fitness_trail|foot|hiking)$\"]{around};out tags bb;"
            f"way[\"leisure\"=\"park\"][\"name\"]{around};out tags geom;"
            f"way[\"leisure\"=\"track\"][\"sport\"~\"athletics|running\"]{around};out tags geom;")


def _route_name(tags: dict) -> str:
    name = (tags.get("name") or "").strip()
    ref = (tags.get("ref") or "").strip()
    if name and ref and ref not in name:
        return f"{name} ({ref})"
    return name or ref


def discover(place: Place, radius_km: float = 10, fetcher=fetch) -> list[FoundRoute]:
    """Parcours existants autour de `place`, triés par type puis par proximité."""
    center = (place.lat, place.lon)
    elements = overpass(_query_overview(place, radius_km), fetcher)
    results: list[FoundRoute] = []

    # -- parcours balisés : on écarte les grands itinéraires et on garde les plus proches
    candidates = []
    for el in elements:
        if el.get("type") != "relation":
            continue
        tags = el.get("tags", {})
        kind = ROUTE_KIND.get(tags.get("route", ""))
        name = _route_name(tags)
        bounds = el.get("bounds")
        if not kind or not name or not bounds:
            continue
        if tags.get("network") in ("iwn", "nwn") or _bbox_diag_km(bounds) > 35:
            continue
        candidates.append((haversine_km(center, _bbox_center(bounds)), el["id"], kind, name, tags))
    candidates.sort()
    candidates = candidates[:MAX_RELATIONS]
    if candidates:
        ids = ",".join(str(c[1]) for c in candidates)
        detailed = {el["id"]: el for el in overpass(f"[out:json][timeout:40];relation(id:{ids});out geom;", fetcher)
                    if el.get("type") == "relation"}
        for dist, rel_id, kind, name, tags in candidates:
            el = detailed.get(rel_id)
            if not el:
                continue
            lines = [tuple((g["lat"], g["lon"]) for g in m.get("geometry") or [] if g)
                     for m in el.get("members", []) if m.get("type") == "way"
                     and m.get("role", "") in ("", "main", "forward", "backward")]
            lines = [ln for ln in lines if len(ln) >= 2]
            length = sum(line_km(ln) for ln in lines)
            if length <= 0:
                continue
            if not MIN_ROUTE_KM <= length <= MAX_ROUTE_KM:
                continue
            ends = [p for ln in lines for p in (ln[0], ln[-1])]
            loop = tags.get("roundtrip") == "yes" or (len(ends) >= 2 and haversine_km(ends[0], ends[-1]) < 0.3)
            pts = [p for ln in lines for p in ln]
            nearest = min(pts, key=lambda p: haversine_km(center, p))
            results.append(FoundRoute("relation", rel_id, name, kind, round(length, 2), loop,
                                      round(haversine_km(center, nearest), 1), nearest[0], nearest[1], tuple(lines)))

    # -- parcs : tour du parc (périmètre), pour les parcs d'au moins 8 ha
    parks = []
    for el in elements:
        tags = el.get("tags", {})
        if el.get("type") != "way" or tags.get("leisure") != "park":
            continue
        pts = _geom(el)
        if len(pts) < 4:
            continue
        if area_km2(pts) < 0.08:
            continue
        perim = line_km(pts if pts[0] == pts[-1] else [*pts, pts[0]])
        if not 0.8 <= perim <= 15:
            continue
        mid = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        parks.append(FoundRoute("way", el["id"], tags["name"].strip(), "parc", round(perim, 2), True,
                                round(haversine_km(center, mid), 1), mid[0], mid[1],
                                (tuple(pts if pts[0] == pts[-1] else [*pts, pts[0]]),)))
    parks.sort(key=lambda r: -r.length_km)
    results += parks[:15]

    # -- pistes d'athlétisme
    tracks = []
    for el in elements:
        tags = el.get("tags", {})
        if el.get("type") != "way" or tags.get("leisure") != "track":
            continue
        pts = _geom(el)
        if len(pts) < 2:
            continue
        length = line_km(pts)
        if not 0.15 <= length <= 1.0:
            continue
        mid = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        name = (tags.get("name") or "").strip() or "Piste d'athlétisme"
        tracks.append(FoundRoute("way", el["id"], name, "piste", round(length, 3), pts[0] == pts[-1],
                                 round(haversine_km(center, mid), 1), mid[0], mid[1], (tuple(pts),)))
    tracks.sort(key=lambda r: r.center_km)
    results += tracks[:8]

    # dédoublonnage (même nom, même type, longueurs proches)
    unique: list[FoundRoute] = []
    for r in results:
        if not any(u.kind == r.kind and u.name.lower() == r.name.lower() and abs(u.length_km - r.length_km) < 0.3
                   for u in unique):
            unique.append(r)
    order = list(KINDS)
    return sorted(unique, key=lambda r: (order.index(r.kind), r.center_km, r.name.lower()))


def filter_by_length(routes: list[FoundRoute], band: str) -> list[FoundRoute]:
    lo, hi = DISTANCE_BANDS.get(band, (0, 1000))
    return [r for r in routes if r.kind == "piste" or lo <= r.length_km < hi] if band != "Toutes" else list(routes)
