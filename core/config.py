"""
Constantes métier : distances, types d'allure, ratios par défaut, schéma des données.

Logique reprise du fichier Excel « Than_than_plan_Marathon_18_10_26.xlsx » :

    vitesse A1 (km/h) = 42,2 / objectif (min) × 60          (cellule H4)
    Endurance = A1 × 85 %      A2 = A1 × 105 %      A3 = A2 × 105 %
    A4 = A3 × 105 %            Sprint = A4 × 120 %             (colonne M)
    allure (min/km) = 60 / vitesse                               (colonne N)

Chaque distance a sa propre ancre : l'objectif fixe l'allure de course de cette
distance (marathon -> A1, semi -> A2, 10 km -> A3). Les autres allures se déduisent
avec les mêmes ratios, dans les deux sens de la chaîne.
"""

from __future__ import annotations

from dataclasses import dataclass


# ----------------------------------------------------------------------------
# Distances
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Distance:
    key: str                 # identifiant stocké ("marathon", "semi", "10k")
    label: str               # libellé affiché
    km: float                # distance utilisée pour calculer l'allure de course
    anchor: str              # allure fixée par l'objectif
    default_objective: str   # objectif proposé à la création d'un élève
    min_seconds: int         # bornes de saisie de l'objectif
    max_seconds: int


DISTANCES: dict[str, Distance] = {
    # 42,2 km comme la cellule C4 de l'Excel (et non 42,195), pour rester fidèle aux calculs.
    "marathon": Distance("marathon", "Marathon", 42.2, "A1", "03:30:00", 1 * 3600 + 50 * 60, 8 * 3600),
    "semi": Distance("semi", "Semi-marathon", 21.1, "A2", "01:45:00", 50 * 60, 4 * 3600),
    "10k": Distance("10k", "10 km", 10.0, "A3", "00:50:00", 25 * 60, 2 * 3600),
}
DISTANCE_KEYS: list[str] = list(DISTANCES)


# ----------------------------------------------------------------------------
# Types d'allure et ratios
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class PaceDefinition:
    code: str               # identifiant stocké dans les séances
    label: str              # libellé court
    description: str        # correspondance en langage courant
    base: str | None        # allure de référence du ratio (None pour A1, sommet de la chaîne)
    default_pct: float      # ratio par défaut, en % de la vitesse de `base`
    ref_km: float | None    # distance pour le temps d'équivalence (colonne Q de l'Excel)
    ref_label: str | None


# Ordre = ordre de calcul ET ordre d'intensité (zone 1 à 6).
PACE_DEFINITIONS: list[PaceDefinition] = [
    PaceDefinition("Endurance", "Endurance", "Footing, sortie longue", "A1", 85.0, None, None),
    PaceDefinition("A1", "A1 · marathon", "Allure marathon", None, 100.0, 42.2, "Marathon"),
    PaceDefinition("A2", "A2 · semi", "Allure semi-marathon", "A1", 105.0, 21.1, "Semi"),
    PaceDefinition("A3", "A3 · 10 km", "Allure 10 km", "A2", 105.0, 10.0, "10 km"),
    PaceDefinition("A4", "A4 · 5 km", "Allure 5 km", "A3", 105.0, 5.0, "5 km"),
    PaceDefinition("Sprint", "Sprint", "Fractionné court (30\"/30\")", "A4", 120.0, None, None),
]
PACE_BY_CODE: dict[str, PaceDefinition] = {p.code: p for p in PACE_DEFINITIONS}
PACE_CODES: list[str] = [p.code for p in PACE_DEFINITIONS]
PACE_LABELS: dict[str, str] = {p.code: p.label for p in PACE_DEFINITIONS}
# Allures dont le ratio est réglable (A1 est le sommet de la chaîne).
RATIO_CODES: list[str] = [p.code for p in PACE_DEFINITIONS if p.base is not None]
DEFAULT_RATIOS: dict[str, float] = {p.code: p.default_pct for p in PACE_DEFINITIONS if p.base is not None}

# Couleur d'intensité de chaque allure (du plus facile au plus intense).
ZONE_COLORS: dict[str, tuple[str, str]] = {   # (fond, texte)
    "Endurance": ("#2F9E6E", "#FFFFFF"),
    "A1": ("#2A6FDB", "#FFFFFF"),
    "A2": ("#6E56CF", "#FFFFFF"),
    "A3": ("#F2B01E", "#1A1A1A"),
    "A4": ("#E2611B", "#FFFFFF"),
    "Sprint": ("#CF2E3F", "#FFFFFF"),
}

# ----------------------------------------------------------------------------
# Fréquence d'entraînement
# ----------------------------------------------------------------------------
FREQUENCIES: list[int] = [3, 4]
# Valeurs de la colonne « frequence » d'une séance.
FREQ_ALWAYS = "3-4"     # séance faite dans les deux cas
FREQ_ONLY_4 = "4"       # séance faite seulement à 4 séances par semaine
FREQ_LABELS: dict[str, str] = {FREQ_ALWAYS: "Toujours", FREQ_ONLY_4: "Si 4 séances"}

# Séance de course : sa durée est l'objectif (cellule E11 = D4 de l'Excel).
RACE_DAY_LABEL = "JOUR J"

# ----------------------------------------------------------------------------
# Schéma des séances
# ----------------------------------------------------------------------------
SESSION_COLUMNS: list[str] = [
    "week_id",     # identifiant de la semaine
    "ordre",       # ordre dans la semaine
    "seance",      # s1, s2… ou JOUR J
    "km_env",      # kilométrage approximatif (texte : « 12 », « 25 à 30 »)
    "duree_env",   # durée approximative (h:mm)
    "contenu",     # contenu / partie spécifique
    "km_spe",      # km à l'allure choisie (nombre) -> temps spécifique
    "allure",      # code du type d'allure
    "frequence",   # « 3-4 » (toujours) ou « 4 » (seulement à 4 séances/semaine)
    "remarque",    # note libre
]
SESSION_INPUT_COLUMNS: list[str] = [c for c in SESSION_COLUMNS if c not in ("week_id", "ordre")]
SESSION_TEXT_COLUMNS: list[str] = ["seance", "km_env", "duree_env", "contenu", "remarque"]
WEEK_COLUMNS: list[str] = ["week_id", "position", "phase"]

DISPLAY_NAMES: dict[str, str] = {
    "semaine": "Semaine", "debut": "Du", "fin": "Au", "phase": "Phase",
    "seance": "Séance", "km_env": "Km (env.)", "duree_env": "Durée (env.)",
    "contenu": "Contenu", "km_spe": "Km spé.", "allure": "Allure",
    "frequence": "Fréquence", "allure_txt": "Allure /km", "allure_dec": "Allure (min,cent./km)",
    "vitesse": "km/h", "temps_spe": "Temps spé.", "temps_spe_min": "Temps spé. (min)",
    "remarque": "Remarque",
}

# Semaine ajoutée à la main : squelette de 3 séances, comme la semaine S0 de l'Excel.
SKELETON_WEEK: list[dict] = [
    {"seance": "s1", "allure": "A2"},
    {"seance": "s2", "allure": "A1"},
    {"seance": "s3", "allure": "A2"},
]
