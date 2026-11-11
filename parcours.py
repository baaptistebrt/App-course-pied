"""
Découverte de parcours : base de parcours de course à pied, alimentée à la main par le coach
(ville, nom du parcours, distance, lien vers une carte). Aucune API externe.

Fichier `data/parcours.xlsx`, un onglet « parcours » :
    id, ville, nom, distance_km, lien, ajoute_le
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from .stockage import Store, read_workbook, write_workbook

ROUTES_FILE = "parcours.xlsx"
COLUMNS = ["id", "ville", "nom", "distance_km", "lien", "ajoute_le"]
URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)


@dataclass(frozen=True)
class Route:
    id: str
    ville: str
    nom: str
    distance_km: float | None
    lien: str
    ajoute_le: str = ""

    @property
    def distance_str(self) -> str:
        if self.distance_km is None:
            return ""
        return f"{self.distance_km:.1f}".rstrip("0").rstrip(".").replace(".", ",") + " km"


def normalize(text: str) -> str:
    """Pour comparer des villes : minuscules, sans accents, tirets et espaces unifiés (« Saint-Étienne » = « saint etienne »)."""
    raw = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[\s\-'’]+", " ", raw).strip()


def _distance(value) -> float | None:
    try:
        v = float(str(value).replace(",", ".").replace("km", "").strip())
    except (TypeError, ValueError):
        return None
    return round(v, 2) if 0 < v <= 500 else None


def _text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def clean_link(value) -> str:
    """Lien http(s) ou "" ; « www.… » est complété en https://."""
    link = _text(value)
    if link and not link.lower().startswith(("http://", "https://")) and "." in link:
        link = "https://" + link
    return link if URL_RE.match(link) else ""


def load_routes(store: Store) -> list[Route]:
    content = store.read(ROUTES_FILE)
    if not content:
        return []
    try:
        df = read_workbook(content).get("parcours", pd.DataFrame(columns=COLUMNS))
    except ValueError:
        return []
    routes = []
    for _, r in df.iterrows():
        ville, nom = _text(r.get("ville")), _text(r.get("nom"))
        if ville and nom:
            routes.append(Route(_text(r.get("id")) or uuid.uuid4().hex[:8], ville, nom, _distance(r.get("distance_km")),
                                clean_link(r.get("lien")), _text(r.get("ajoute_le"))))
    return sorted(routes, key=lambda x: (normalize(x.ville), x.distance_km or 0, x.nom.lower()))


def save_routes(store: Store, routes: list[Route]) -> None:
    df = pd.DataFrame([{"id": r.id, "ville": r.ville, "nom": r.nom, "distance_km": r.distance_km, "lien": r.lien,
                        "ajoute_le": r.ajoute_le} for r in routes], columns=COLUMNS)
    store.write(ROUTES_FILE, write_workbook({"parcours": df}))


def make_route(ville: str, nom: str, distance, lien: str = "", route_id: str | None = None,
               ajoute_le: str | None = None) -> Route:
    """Parcours validé. Lève ValueError si la ville, le nom ou la distance manquent, ou si le lien est invalide."""
    ville, nom = _text(ville), _text(nom)
    if not ville:
        raise ValueError("Indique la ville du parcours.")
    if not nom:
        raise ValueError("Indique le nom du parcours.")
    dist = _distance(distance)
    if dist is None:
        raise ValueError("Indique une distance en km (ex. 8,5).")
    link = clean_link(lien)
    if _text(lien) and not link:
        raise ValueError("Le lien doit être une adresse web (https://…).")
    return Route(route_id or uuid.uuid4().hex[:8], ville, nom, dist, link,
                 ajoute_le or datetime.now().strftime("%Y-%m-%d"))


def add_route(store: Store, ville: str, nom: str, distance, lien: str = "") -> Route:
    route = make_route(ville, nom, distance, lien)
    routes = load_routes(store)
    if any(normalize(r.ville) == normalize(route.ville) and normalize(r.nom) == normalize(route.nom) for r in routes):
        raise ValueError(f"« {route.nom} » existe déjà pour {route.ville}.")
    save_routes(store, [*routes, route])
    return route


def cities(routes: list[Route]) -> list[str]:
    """Villes disponibles (une seule écriture par ville)."""
    seen: dict[str, str] = {}
    for r in routes:
        seen.setdefault(normalize(r.ville), r.ville)
    return sorted(seen.values(), key=normalize)


def search(routes: list[Route], city: str) -> list[Route]:
    """Parcours d'une ville : correspondance exacte d'abord, sinon début ou partie du nom de la ville."""
    wanted = normalize(city)
    if not wanted:
        return []
    exact = [r for r in routes if normalize(r.ville) == wanted]
    if exact:
        return exact
    return [r for r in routes if normalize(r.ville).startswith(wanted) or wanted in normalize(r.ville)]
