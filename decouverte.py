"""
Découverte automatique de parcours existants autour d'une ville, à partir d'OpenStreetMap (données
ouvertes, gratuites, sans compte ni clé).

1. La ville est située par le service de géocodage de l'IGN (Géoplateforme, gratuit, pour la France),
   ou par Nominatim (OpenStreetMap) si l'IGN ne la trouve pas ou ne répond pas.
2. Les parcours sont cherchés dans un carré autour de la ville :
    - parcours balisés : relations route=running (course), route=fitness_trail (parcours sportif /
      de santé), route=foot et route=hiking (sentiers PR…) ;
    - parcs nommés (leisure=park), avec la longueur de leur tour ;
    - pistes d'athlétisme (leisure=track + sport=athletics/running).

Les serveurs publics d'OpenStreetMap sont gratuits et souvent saturés : la recherche essaie
plusieurs services l'un après l'autre (Overpass principal, Postpass de Geofabrik, puis d'autres
serveurs Overpass), écarte quelques minutes un service qui vient d'échouer, et s'arrête au bout
d'un temps maximal. Chaque échec est écrit dans les journaux de l'application (Streamlit Cloud :
« Manage app » > logs) pour faciliter le diagnostic.

La longueur est calculée sur le tracé réel. Les très longs itinéraires (GR nationaux de centaines
de km) sont écartés. Données © contributeurs OpenStreetMap (licence ODbL) : l'attribution est
affichée avec les résultats.

Les appels réseau passent par `fetch` (remplaçable dans les tests ; voir tests/fake_osm.py).
"""

from __future__ import annotations

import math
import os
import sys
import time
from dataclasses import dataclass, field

# Services (les variables d'environnement servent aux tests et à un serveur personnel éventuel).
IGN_URL = os.environ.get("PLAN_GEO_IGN_URL", "https://data.geopf.fr/geocodage/search")
# Suggestions pendant la frappe (adresses et villes), appelées directement par le navigateur.
IGN_COMPLETION_URL = os.environ.get("PLAN_GEO_IGN_COMPLETION_URL", "https://data.geopf.fr/geocodage/completion")
NOMINATIM_URL = os.environ.get("PLAN_OSM_NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
OVERPASS_URLS = [u for u in (os.environ.get("PLAN_OSM_OVERPASS_URL"),
                             "https://overpass-api.de/api/interpreter",
                             "https://overpass.private.coffee/api/interpreter",
                             "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
                             "https://overpass.kumi.systems/api/interpreter") if u]
POSTPASS_URLS = [u for u in (os.environ.get("PLAN_OSM_POSTPASS_URL"),
                             "https://postpass.geofabrik.de/api/0.2/interpreter") if u]
USER_AGENT = "CoachRunningApp/1.1 (plans d'entrainement course a pied; +https://github.com/baaptistebrt/App-course-pied)"
ATTRIBUTION = "Parcours et cartes : © les contributeurs d'OpenStreetMap (licence ODbL)"

TIME_BUDGET = 80.0          # secondes au plus pour une recherche, tous services confondus
REQUEST_TIMEOUT = 35.0      # secondes au plus par requête
COOL_DOWN = 300.0           # un service qui vient d'échouer est mis de côté 5 minutes

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
MAX_PARKS, MAX_TRACKS = 15, 8

UNAVAILABLE = ("Les serveurs de cartes OpenStreetMap ne répondent pas pour l'instant : ils sont gratuits et "
               "parfois saturés. Réessaie dans quelques minutes.")


class DiscoveryError(Exception):
    """Service injoignable ou réponse inattendue. Le message est lisible par l'élève ; `detail`
    résume les erreurs techniques (service et code), pour le diagnostic."""

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.detail = detail


@dataclass(frozen=True)
class Place:
    name: str
    lat: float
    lon: float
    label: str
    kind: str = "ville"         # « ville » ou « adresse » (rue, numéro, lieu précis)

    @property
    def origin(self) -> str:
        """« du centre » / « de ton adresse » (distance d'un parcours)."""
        return "de ton adresse" if self.kind == "adresse" else "du centre"


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
_DOWN: dict[str, float] = {}     # service -> heure du dernier échec


def log(message: str) -> None:
    """Trace dans les journaux de l'application (Streamlit Cloud : Manage app > logs)."""
    print(f"[decouverte] {message}", file=sys.stderr, flush=True)


def _host(url: str) -> str:
    return url.split("//", 1)[-1].split("/", 1)[0]


def fetch(url: str, *, params: dict | None = None, data: dict | None = None, timeout: float = REQUEST_TIMEOUT):
    """GET (params) ou POST (data) ; renvoie le JSON. Lève DiscoveryError (detail = service et code)."""
    import requests   # dépendance de Streamlit, toujours disponible

    host = _host(url)
    try:
        headers = {"User-Agent": USER_AGENT, "Accept-Language": "fr", "Accept": "application/json"}
        if data is not None:
            resp = requests.post(url, data=data, headers=headers, timeout=(6, timeout))
        else:
            resp = requests.get(url, params=params, headers=headers, timeout=(6, timeout))
    except requests.Timeout as exc:
        raise DiscoveryError(UNAVAILABLE, f"{host} : délai dépassé") from exc
    except requests.RequestException as exc:
        raise DiscoveryError(UNAVAILABLE, f"{host} : injoignable ({type(exc).__name__})") from exc
    if resp.status_code != 200:
        raise DiscoveryError(UNAVAILABLE, f"{host} : erreur {resp.status_code}")
    try:
        return resp.json()
    except ValueError as exc:
        raise DiscoveryError(UNAVAILABLE, f"{host} : réponse illisible") from exc


def _available(urls: list[str]) -> list[str]:
    """Services à essayer : ceux qui n'ont pas échoué récemment d'abord, les autres ensuite."""
    now = time.monotonic()
    fresh = [u for u in urls if now - _DOWN.get(u, -COOL_DOWN) >= COOL_DOWN]
    return fresh + [u for u in urls if u not in fresh]


def _failed(url: str, exc: DiscoveryError) -> None:
    _DOWN[url] = time.monotonic()
    log(f"échec {exc.detail or exc}")


def _succeeded(url: str) -> None:
    _DOWN.pop(url, None)


# ----------------------------------------------------------------------------
# Géométrie
# ----------------------------------------------------------------------------
def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(min(1.0, h)))


def line_km(points) -> float:
    return sum(haversine_km(points[i], points[i + 1]) for i in range(len(points) - 1))


def area_km2(points) -> float:
    """Aire d'un polygone (projection locale), en km²."""
    if len(points) < 3:
        return 0.0
    lat0 = math.radians(sum(p[0] for p in points) / len(points))
    xy = [(math.radians(p[1]) * 6371 * math.cos(lat0), math.radians(p[0]) * 6371) for p in points]
    return abs(sum(xy[i][0] * xy[i - 1][1] - xy[i - 1][0] * xy[i][1] for i in range(len(xy)))) / 2


def bbox(place: Place, radius_km: float) -> tuple[float, float, float, float]:
    """Carré (sud, ouest, nord, est) qui contient le cercle de rayon `radius_km` autour de la ville."""
    dlat = radius_km / 111.2
    dlon = radius_km / (111.2 * max(math.cos(math.radians(place.lat)), 0.2))
    return place.lat - dlat, place.lon - dlon, place.lat + dlat, place.lon + dlon


def _diag_km(points) -> float:
    if not points:
        return 0.0
    return haversine_km((min(p[0] for p in points), min(p[1] for p in points)),
                        (max(p[0] for p in points), max(p[1] for p in points)))


def _closed(ring: list) -> list:
    return ring if ring and ring[0] == ring[-1] else [*ring, ring[0]]


def _centroid(points) -> tuple[float, float]:
    return sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points)


# ----------------------------------------------------------------------------
# Géocodage
# ----------------------------------------------------------------------------
def _simple(text: str) -> str:
    import unicodedata
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    return "".join(c for c in text.replace("saint", "st") if c.isalnum())


def _geocode_ign(city: str, fetcher, address: bool = False) -> tuple[Place | None, bool]:
    """(lieu trouvé par l'IGN, la correspondance est-elle sûre ?). `address` : adresse précise acceptée
    (numéro, rue), sinon seulement une commune."""
    params = {"q": city, "index": "address", "limit": 1}
    if not address:
        params["type"] = "municipality"
    data = fetcher(IGN_URL, params=params)
    for feat in (data or {}).get("features") or []:
        props = feat.get("properties") or feat
        coords = (feat.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2:
            continue
        precise = str(props.get("type") or "municipality") != "municipality"
        name = str(props.get("name") or props.get("city") or city)
        context = str(props.get("context") or "")
        q, n = _simple(city), _simple(name)
        score = float(props.get("score") or 1)
        sure = score >= (0.5 if precise else 0.6) or (bool(q) and (q in n or n in q))
        if precise:
            label = str(props.get("label") or name)
            return Place(name=str(props.get("city") or name), lat=float(coords[1]), lon=float(coords[0]),
                         label=label, kind="adresse"), sure
        return Place(name=name, lat=float(coords[1]), lon=float(coords[0]),
                     label=f"{name} ({context})" if context else name), sure
    return None, False


def complete(text: str, fetcher=fetch, limit: int = 6) -> list[dict]:
    """Suggestions pour un début d'adresse ou de ville (IGN) : [{label, lat, lon, kind}]. Utilisé côté
    serveur quand le navigateur ne peut pas appeler l'IGN lui-même."""
    text = (text or "").strip()
    if len(text) < 3:
        return []
    data = fetcher(IGN_COMPLETION_URL, params={"text": text, "type": "StreetAddress,PositionOfInterest",
                                               "maximumResponses": limit})
    out = []
    for r in (data or {}).get("results") or []:
        try:
            out.append({"label": str(r.get("fulltext") or ""), "lat": float(r["y"]), "lon": float(r["x"]),
                        "kind": "adresse" if r.get("kind") in ("housenumber", "street") else "ville",
                        "city": str(r.get("city") or r.get("fulltext") or "")})
        except (KeyError, TypeError, ValueError):
            continue
    return [x for x in out if x["label"]]


def _geocode_nominatim(city: str, fetcher) -> Place | None:
    for extra in ({"countrycodes": "fr"}, {}):
        found = fetcher(NOMINATIM_URL, params={"q": city, "format": "jsonv2", "limit": 1, "accept-language": "fr",
                                               **extra})
        if found:
            hit = found[0]
            return Place(name=str(hit.get("name") or city), lat=float(hit["lat"]), lon=float(hit["lon"]),
                         label=str(hit.get("display_name", city)))
    return None


def geocode(city: str, fetcher=fetch, address: bool = False) -> Place | None:
    """Situe une ville, ou une adresse si `address` (IGN, puis Nominatim). None si elle est introuvable ;
    DiscoveryError si aucun service de géocodage ne répond."""
    city = (city or "").strip()
    if not city:
        return None
    errors, maybe = [], None
    ign = (lambda q, f: _geocode_ign(q, f, address)) if address else _geocode_ign
    for name, finder in (("IGN", ign), ("Nominatim", _geocode_nominatim)):
        try:
            place = finder(city, fetcher)
        except (DiscoveryError, KeyError, TypeError, ValueError, AttributeError) as exc:
            detail = getattr(exc, "detail", "") or f"{name} : réponse inattendue"
            log(f"géocodage « {city} » : {detail}")
            errors.append(detail)
            continue
        if isinstance(place, tuple):          # IGN : une commune approchante n'est gardée qu'en dernier recours
            place, sure = place
            if place is not None and not sure:
                maybe, place = place, None
        if place is not None:
            return place
    if maybe is not None:
        return maybe
    if len(errors) == 2:
        raise DiscoveryError("Impossible de situer la ville pour l'instant : le service de localisation ne "
                             "répond pas. Réessaie dans quelques minutes.", " ; ".join(errors))
    return None


# ----------------------------------------------------------------------------
# Construction des résultats (commune aux services)
# ----------------------------------------------------------------------------
def _route_name(tags: dict) -> str:
    name = str(tags.get("name") or "").strip()
    ref = str(tags.get("ref") or "").strip()
    if name and ref and ref not in name:
        return f"{name} ({ref})"
    return name or ref


def _marked_route(osm_type: str, osm_id: int, tags: dict, lines: list, center, length_km: float = 0.0):
    """Parcours balisé (relation) ; None s'il est hors critères (grand itinéraire, trop court ou trop long)."""
    kind = ROUTE_KIND.get(str(tags.get("route") or ""))
    name = _route_name(tags)
    lines = [tuple(ln) for ln in lines if len(ln) >= 2]
    if not kind or not name or not lines or tags.get("network") in ("iwn", "nwn"):
        return None
    pts = [p for ln in lines for p in ln]
    if _diag_km(pts) > 35:
        return None
    length = length_km or sum(line_km(ln) for ln in lines)
    if not MIN_ROUTE_KM <= length <= MAX_ROUTE_KM:
        return None
    ends = [p for ln in lines for p in (ln[0], ln[-1])]
    loop = str(tags.get("roundtrip") or "") == "yes" or (len(ends) >= 2 and haversine_km(ends[0], ends[-1]) < 0.3)
    nearest = min(pts, key=lambda p: haversine_km(center, p))
    return FoundRoute(osm_type, int(osm_id), name, kind, round(length, 2), loop,
                      round(haversine_km(center, nearest), 1), nearest[0], nearest[1], tuple(lines))


def _park(osm_type: str, osm_id: int, name: str, ring: list, center):
    """Tour d'un parc d'au moins 8 ha (0,8 à 15 km)."""
    name = str(name or "").strip()
    if not name or len(ring) < 4 or area_km2(ring) < 0.08:
        return None
    ring = _closed(ring)
    perim = line_km(ring)
    if not 0.8 <= perim <= 15:
        return None
    mid = _centroid(ring)
    return FoundRoute(osm_type, int(osm_id), name, "parc", round(perim, 2), True,
                      round(haversine_km(center, mid), 1), mid[0], mid[1], (tuple(ring),))


def _track(osm_type: str, osm_id: int, name: str, pts: list, center):
    """Piste d'athlétisme (150 m à 1 km)."""
    if len(pts) < 2:
        return None
    length = line_km(pts)
    if not 0.15 <= length <= 1.0:
        return None
    mid = _centroid(pts)
    return FoundRoute(osm_type, int(osm_id), str(name or "").strip() or "Piste d'athlétisme", "piste",
                      round(length, 3), pts[0] == pts[-1], round(haversine_km(center, mid), 1), mid[0], mid[1],
                      (tuple(pts),))


def _finish(results: list[FoundRoute], radius_km: float) -> list[FoundRoute]:
    """Garde ce qui est dans le rayon, limite le nombre de parcs et de pistes, dédoublonne et trie."""
    results = [r for r in results if r.center_km <= radius_km + 0.5]
    parks = sorted((r for r in results if r.kind == "parc"), key=lambda r: -r.length_km)[:MAX_PARKS]
    tracks = sorted((r for r in results if r.kind == "piste"), key=lambda r: r.center_km)[:MAX_TRACKS]
    marked = [r for r in results if r.kind not in ("parc", "piste")]
    unique: list[FoundRoute] = []
    for r in [*marked, *parks, *tracks]:
        if not any(u.kind == r.kind and u.name.lower() == r.name.lower() and abs(u.length_km - r.length_km) < 0.3
                   for u in unique):
            unique.append(r)
    order = list(KINDS)
    return sorted(unique, key=lambda r: (order.index(r.kind), r.center_km, r.name.lower()))


# ----------------------------------------------------------------------------
# Service 1 : Overpass (langage Overpass QL)
# ----------------------------------------------------------------------------
def _overpass_json(url: str, query: str, fetcher, timeout: float) -> list[dict]:
    data = fetcher(url, data={"data": query}, timeout=timeout)
    if not isinstance(data, dict) or not isinstance(data.get("elements"), list):
        raise DiscoveryError(UNAVAILABLE, f"{_host(url)} : réponse inattendue")
    remark = str(data.get("remark") or "")
    if remark and any(w in remark.lower() for w in ("error", "timed out", "out of memory", "erreur")):
        raise DiscoveryError(UNAVAILABLE, f"{_host(url)} : {remark[:80]}")
    return data["elements"]


def overpass(query: str, fetcher=fetch) -> list[dict]:
    """Exécute une requête Overpass sur le premier serveur qui répond."""
    errors = []
    for url in _available(OVERPASS_URLS):
        try:
            elements = _overpass_json(url, query, fetcher, REQUEST_TIMEOUT)
        except DiscoveryError as exc:
            _failed(url, exc)
            errors.append(exc.detail)
            continue
        _succeeded(url)
        return elements
    raise DiscoveryError(UNAVAILABLE, " ; ".join(errors))


def _overview_query(place: Place, radius_km: float) -> str:
    s, w, n, e = bbox(place, radius_km)
    b = f"({s:.5f},{w:.5f},{n:.5f},{e:.5f})"
    return ("[out:json][timeout:25];"
            f"relation[\"type\"=\"route\"][\"route\"~\"^(running|fitness_trail|foot|hiking)$\"]{b};out tags bb;"
            f"way[\"leisure\"=\"park\"][\"name\"]{b};out tags geom;"
            f"way[\"leisure\"=\"track\"][\"sport\"~\"athletics|running\"]{b};out tags geom;")


def _via_overpass(url: str, place: Place, radius_km: float, fetcher, timeout: float, notes: list) -> list[FoundRoute]:
    center = (place.lat, place.lon)
    elements = _overpass_json(url, _overview_query(place, radius_km), fetcher, timeout)
    results: list[FoundRoute] = []

    # parcours balisés : on écarte d'abord les grands itinéraires, puis on charge le tracé des plus proches
    candidates = []
    for el in elements:
        tags, bounds = el.get("tags", {}), el.get("bounds")
        if el.get("type") != "relation" or not bounds or not ROUTE_KIND.get(tags.get("route", "")):
            continue
        if not _route_name(tags) or tags.get("network") in ("iwn", "nwn"):
            continue
        corners = [(bounds["minlat"], bounds["minlon"]), (bounds["maxlat"], bounds["maxlon"])]
        if _diag_km(corners) > 35:
            continue
        candidates.append((haversine_km(center, _centroid(corners)), el["id"], tags))
    candidates.sort(key=lambda c: c[0])
    candidates = candidates[:MAX_RELATIONS]
    if candidates:
        ids = ",".join(str(c[1]) for c in candidates)
        try:
            detailed = {el["id"]: el for el in
                        _overpass_json(url, f"[out:json][timeout:25];relation(id:{ids});out geom;", fetcher, timeout)
                        if el.get("type") == "relation"}
        except DiscoveryError as exc:
            log(f"tracés des parcours balisés : {exc.detail}")
            notes.append("Les parcours balisés n'ont pas pu être chargés cette fois-ci : seuls les parcs et les "
                         "pistes sont affichés. Réessaie dans quelques minutes pour les voir.")
            detailed = {}
        for _, rel_id, tags in candidates:
            el = detailed.get(rel_id)
            if not el:
                continue
            lines = [[(g["lat"], g["lon"]) for g in m.get("geometry") or [] if g]
                     for m in el.get("members", []) if m.get("type") == "way"
                     and m.get("role", "") in ("", "main", "forward", "backward")]
            route = _marked_route("relation", rel_id, tags, lines, center)
            if route:
                results.append(route)

    for el in elements:
        tags = el.get("tags", {})
        if el.get("type") != "way":
            continue
        pts = [(g["lat"], g["lon"]) for g in el.get("geometry") or [] if g]
        if tags.get("leisure") == "park":
            found = _park("way", el["id"], tags.get("name"), pts, center)
        elif tags.get("leisure") == "track":
            found = _track("way", el["id"], tags.get("name"), pts, center)
        else:
            found = None
        if found:
            results.append(found)
    return results


# ----------------------------------------------------------------------------
# Service 2 : Postpass (Geofabrik, requêtes SQL sur une copie d'OpenStreetMap, réponse GeoJSON)
# ----------------------------------------------------------------------------
def _postpass_routes_sql(place: Place, radius_km: float) -> str:
    s, w, n, e = bbox(place, radius_km)
    env = f"ST_MakeEnvelope({w:.5f},{s:.5f},{e:.5f},{n:.5f},4326)"
    return ("SELECT osm_type, osm_id, tags->>'name' AS name, tags->>'ref' AS ref, tags->>'route' AS route, "
            "tags->>'network' AS network, tags->>'roundtrip' AS roundtrip, length_m, "
            "ST_Simplify(geom, 0.00003) AS geom FROM postpass_line "
            f"WHERE geom && {env} AND osm_type = 'R' "
            "AND tags->>'route' IN ('running','fitness_trail','foot','hiking') "
            "AND (tags ? 'name' OR tags ? 'ref') AND length_m BETWEEN 1000 AND 60000 "
            f"ORDER BY geom <-> ST_SetSRID(ST_MakePoint({place.lon:.5f},{place.lat:.5f}),4326) "
            f"LIMIT {MAX_RELATIONS}")


def _postpass_areas_sql(place: Place, radius_km: float) -> str:
    s, w, n, e = bbox(place, radius_km)
    env = f"ST_MakeEnvelope({w:.5f},{s:.5f},{e:.5f},{n:.5f},4326)"
    return ("(SELECT 'parc' AS kind, osm_type, osm_id, tags->>'name' AS name, ST_Simplify(geom, 0.00002) AS geom "
            f"FROM postpass_polygon WHERE geom && {env} AND tags->>'leisure' = 'park' AND tags ? 'name' "
            "AND area_m2 >= 80000 ORDER BY area_m2 DESC LIMIT 30) UNION ALL "
            "(SELECT 'piste' AS kind, osm_type, osm_id, tags->>'name' AS name, geom "
            f"FROM postpass_linepolygon WHERE geom && {env} AND tags->>'leisure' = 'track' "
            "AND tags->>'sport' ~ '(athletics|running)' LIMIT 30)")


def _geojson_lines(geom: dict | None) -> list[list[tuple[float, float]]]:
    """Tronçons (lignes) ou contours extérieurs (polygones) d'une géométrie GeoJSON, en (lat, lon)."""
    if not geom:
        return []
    kind, coords = geom.get("type"), geom.get("coordinates") or []
    as_pts = lambda seq: [(float(c[1]), float(c[0])) for c in seq if len(c) >= 2]  # noqa: E731
    if kind == "LineString":
        return [as_pts(coords)]
    if kind == "MultiLineString":
        return [as_pts(ln) for ln in coords]
    if kind == "Polygon":
        return [as_pts(coords[0])] if coords else []
    if kind == "MultiPolygon":
        return [as_pts(poly[0]) for poly in coords if poly]
    if kind == "GeometryCollection":
        return [ln for g in geom.get("geometries") or [] for ln in _geojson_lines(g)]
    return []


def _postpass_features(url: str, sql: str, fetcher, timeout: float) -> list[dict]:
    data = fetcher(url, data={"data": sql}, timeout=timeout)
    if not isinstance(data, dict) or "features" not in data:
        raise DiscoveryError(UNAVAILABLE, f"{_host(url)} : réponse inattendue")
    return [f for f in data.get("features") or [] if isinstance(f, dict)]


def _props(feature: dict) -> dict:
    props = dict(feature.get("properties") or {})
    nested = props.get("tags")
    if isinstance(nested, dict):
        props = {**nested, **{k: v for k, v in props.items() if v not in (None, "")}}
    return props


def _osm_type(value) -> str:
    return "relation" if str(value or "").upper().startswith("R") else "way"


def _via_postpass(url: str, place: Place, radius_km: float, fetcher, timeout: float, notes: list) -> list[FoundRoute]:
    center = (place.lat, place.lon)
    results: list[FoundRoute] = []
    errors = []
    for part, sql in (("routes", _postpass_routes_sql(place, radius_km)), ("areas", _postpass_areas_sql(place, radius_km))):
        try:
            features = _postpass_features(url, sql, fetcher, timeout)
        except DiscoveryError as exc:
            errors.append(exc)
            continue
        for f in features:
            p = _props(f)
            lines = _geojson_lines(f.get("geometry"))
            try:
                osm_id = int(abs(int(p.get("osm_id"))))
            except (TypeError, ValueError):
                continue
            if part == "routes":
                try:
                    length = float(p.get("length_m") or 0) / 1000
                except (TypeError, ValueError):
                    length = 0.0
                found = _marked_route(_osm_type(p.get("osm_type")), osm_id, p, lines, center, length)
            elif p.get("kind") == "parc" and lines:
                ring = max(lines, key=area_km2)
                found = _park(_osm_type(p.get("osm_type")), osm_id, p.get("name"), ring, center)
            elif p.get("kind") == "piste" and lines:
                found = _track(_osm_type(p.get("osm_type")), osm_id, p.get("name"), max(lines, key=len), center)
            else:
                found = None
            if found:
                results.append(found)
    if len(errors) == 2:
        raise DiscoveryError(UNAVAILABLE, " ; ".join(exc.detail for exc in errors))
    if errors:
        log(f"Postpass partiel : {errors[0].detail}")
        notes.append("Une partie des parcours n'a pas pu être chargée cette fois-ci. Réessaie dans quelques minutes "
                     "pour tout voir.")
    return results


# ----------------------------------------------------------------------------
# Recherche
# ----------------------------------------------------------------------------
def _attempts() -> list[tuple[str, str]]:
    """Ordre d'essai : Overpass principal, Postpass, puis les autres serveurs Overpass. Les services en
    échec récent passent en dernier."""
    plan = [("overpass", u) for u in OVERPASS_URLS[:1]] + [("postpass", u) for u in POSTPASS_URLS] + \
           [("overpass", u) for u in OVERPASS_URLS[1:]]
    order = _available([u for _, u in plan])
    kinds = dict((u, k) for k, u in plan)
    return [(kinds[u], u) for u in order]


def discover(place: Place, radius_km: float = 10, fetcher=fetch, notes: list | None = None) -> list[FoundRoute]:
    """Parcours existants autour de `place`, triés par type puis par proximité.

    Essaie les services un par un jusqu'à obtenir une réponse. `notes` reçoit les messages à afficher
    quand les résultats sont incomplets. Lève DiscoveryError si aucun service ne répond."""
    notes = notes if notes is not None else []
    deadline = time.monotonic() + TIME_BUDGET
    errors: list[str] = []
    for kind, url in _attempts():
        remaining = deadline - time.monotonic()
        if remaining < 5:
            errors.append("temps maximal de recherche atteint")
            break
        attempt_notes: list[str] = []
        try:
            runner = _via_overpass if kind == "overpass" else _via_postpass
            results = runner(url, place, radius_km, fetcher, min(REQUEST_TIMEOUT, remaining), attempt_notes)
        except DiscoveryError as exc:
            _failed(url, exc)
            errors.append(exc.detail or str(exc))
            continue
        except (KeyError, TypeError, ValueError, AttributeError, IndexError) as exc:   # réponse mal formée
            err = DiscoveryError(UNAVAILABLE, f"{_host(url)} : réponse inattendue ({type(exc).__name__})")
            _failed(url, err)
            errors.append(err.detail)
            continue
        _succeeded(url)
        notes.extend(attempt_notes)
        if errors:
            log(f"réponse obtenue via {_host(url)} après : {' ; '.join(errors)}")
        return _finish(results, radius_km)
    raise DiscoveryError(UNAVAILABLE, " ; ".join(errors))


def filter_by_length(routes: list[FoundRoute], band: str) -> list[FoundRoute]:
    lo, hi = DISTANCE_BANDS.get(band, (0, 1000))
    return [r for r in routes if r.kind == "piste" or lo <= r.length_km < hi] if band != "Toutes" else list(routes)
