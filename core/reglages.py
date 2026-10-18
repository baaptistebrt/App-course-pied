"""
Réglages du coach enregistrés avec les données (`data/reglages.xlsx`), checklist du jour J
(`data/checklist.xlsx`) et conseils nutrition du jour de course par distance (`data/nutrition.xlsx`),
modifiables dans l'onglet Réglages et dans l'onglet de chaque distance.

Réglages : e-mail du coach (alertes et récap), récap du dimanche pour les élèves et pour le coach,
e-mail au coach quand un élève signale une douleur ou une absence.

Checklist : une ligne par conseil (pour, moment, texte). « pour » = toutes les distances ou une seule.
Une checklist par défaut est proposée tant que le coach n'a pas enregistré la sienne.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace

import pandas as pd

from .stockage import Store, read_workbook, write_workbook

SETTINGS_FILE = "reglages.xlsx"
CHECKLIST_FILE = "checklist.xlsx"


@dataclass(frozen=True)
class Settings:
    coach_email: str = ""            # vide : adresse d'envoi des e-mails
    recap_eleves: bool = True        # récap du dimanche aux élèves
    recap_coach: bool = True         # bilan du dimanche au coach
    alertes_email: bool = True       # e-mail au coach quand un élève signale une douleur ou une absence

    def with_(self, **changes) -> "Settings":
        return replace(self, **changes)


def _text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _flag(value, default: bool) -> bool:
    text = _text(value).lower()
    if not text:
        return default
    return text not in ("0", "0.0", "non", "false", "faux")


def load_settings(store: Store) -> Settings:
    if not store.exists(SETTINGS_FILE):
        return Settings()
    try:
        df = read_workbook(store.read(SETTINGS_FILE)).get("reglages", pd.DataFrame({"cle": [], "valeur": []}))
    except ValueError:
        return Settings()
    values = {_text(k): v for k, v in zip(df.get("cle", []), df.get("valeur", []))}
    base = Settings()
    return Settings(coach_email=_text(values.get("coach_email")),
                    recap_eleves=_flag(values.get("recap_eleves"), base.recap_eleves),
                    recap_coach=_flag(values.get("recap_coach"), base.recap_coach),
                    alertes_email=_flag(values.get("alertes_email"), base.alertes_email))


def save_settings(store: Store, settings: Settings) -> None:
    df = pd.DataFrame([("coach_email", settings.coach_email), ("recap_eleves", int(settings.recap_eleves)),
                       ("recap_coach", int(settings.recap_coach)), ("alertes_email", int(settings.alertes_email))],
                      columns=["cle", "valeur"])
    store.write(SETTINGS_FILE, write_workbook({"reglages": df}))


# ----------------------------------------------------------------------------
# Checklist du jour J
# ----------------------------------------------------------------------------
MOMENTS = ["La veille", "Le matin", "Échauffement", "Manger et boire", "Pendant la course"]
FOR_OPTIONS = {"toutes": "Toutes les distances", "10k": "10 km", "semi": "Semi-marathon", "marathon": "Marathon",
               "trail50": "Trail 50 km", "triL": "Triathlon L"}

DEFAULT_CHECKLIST = [
    ("toutes", "La veille", "Prépare ta tenue, tes chaussures, ton dossard et tes épingles"),
    ("toutes", "La veille", "Vérifie l'heure et le lieu du départ, et comment tu t'y rends"),
    ("toutes", "La veille", "Repas habituel, avec des féculents : rien de nouveau"),
    ("toutes", "La veille", "Couche-toi tôt ; si tu dors mal, pas de panique : c'est surtout l'avant-veille qui compte"),
    ("toutes", "Le matin", "Petit-déjeuner 2 à 3 h avant le départ, déjà testé à l'entraînement"),
    ("toutes", "Le matin", "Arrive au moins 45 min avant le départ"),
    ("toutes", "Le matin", "Passe aux toilettes avant de rejoindre le sas"),
    ("10k", "Échauffement", "15 à 20 min de footing lent, puis 3 accélérations progressives"),
    ("semi", "Échauffement", "10 à 15 min de footing lent, puis 2 ou 3 accélérations"),
    ("marathon", "Échauffement", "5 à 10 min de footing très tranquille suffisent : garde ton énergie"),
    ("toutes", "Manger et boire", "Bois régulièrement la veille et le matin, sans excès"),
    ("10k", "Manger et boire", "Pas besoin de ravitailler : une gorgée d'eau s'il fait chaud"),
    ("semi", "Manger et boire", "Prends de l'eau aux ravitaillements ; un gel vers le 12e km si tu l'as testé"),
    ("marathon", "Manger et boire", "Gels testés à l'entraînement, toutes les 30 à 45 min, avec de l'eau"),
    ("toutes", "Pendant la course", "Pars à ton allure, pas plus vite : les premiers km doivent sembler faciles"),
    # v10 : trail et triathlon (ajoutés à la liste par défaut ; une checklist déjà enregistrée n'est pas modifiée)
    ("trail50", "La veille", "Prépare et vérifie le matériel obligatoire (réserve d'eau, couverture de survie, "
                             "frontale, coupe-vent…)"),
    ("trail50", "Pendant la course", "Marche dans les fortes montées dès le début : garde de l'énergie pour la fin"),
    ("triL", "La veille", "Dépose ton vélo au parc et repère les entrées et sorties des transitions"),
    ("triL", "Le matin", "Prépare ta zone de transition : casque, chaussures, dossard, lunettes, gels"),
    ("triL", "Pendant la course", "Vélo : reste à ton allure Half Iron Man, même si on te double"),
]


@dataclass(frozen=True)
class ChecklistItem:
    pour: str           # clé de FOR_OPTIONS
    moment: str
    texte: str

    @property
    def key(self) -> str:
        """Identifiant stable (sert à garder la case cochée par l'élève)."""
        return hashlib.sha1(f"{self.moment}|{self.texte}".encode()).hexdigest()[:8]


def default_checklist() -> list[ChecklistItem]:
    return [ChecklistItem(*row) for row in DEFAULT_CHECKLIST]


def load_checklist(store: Store) -> list[ChecklistItem]:
    if not store.exists(CHECKLIST_FILE):
        return default_checklist()
    try:
        df = read_workbook(store.read(CHECKLIST_FILE)).get("checklist", pd.DataFrame())
    except ValueError:
        return default_checklist()
    items = []
    for _, r in df.iterrows():
        texte, moment = _text(r.get("texte")), _text(r.get("moment"))
        pour = _text(r.get("pour")) or "toutes"
        if texte:
            items.append(ChecklistItem(pour if pour in FOR_OPTIONS else "toutes", moment or MOMENTS[0], texte))
    return items


def save_checklist(store: Store, items: list[ChecklistItem]) -> None:
    df = pd.DataFrame([{"pour": i.pour, "moment": i.moment, "texte": i.texte} for i in items],
                      columns=["pour", "moment", "texte"])
    store.write(CHECKLIST_FILE, write_workbook({"checklist": df}))


def checklist_for(items: list[ChecklistItem], distance: str) -> list[tuple[str, list[ChecklistItem]]]:
    """Conseils d'une distance, groupés par moment (dans l'ordre des moments)."""
    mine = [i for i in items if i.pour in ("toutes", distance)]
    order = MOMENTS + sorted({i.moment for i in mine} - set(MOMENTS))
    return [(m, [i for i in mine if i.moment == m]) for m in order if any(i.moment == m for i in mine)]


# ----------------------------------------------------------------------------
# Nutrition le jour de la course (un texte par distance, modifiable dans l'onglet de la distance)
# ----------------------------------------------------------------------------
NUTRITION_FILE = "nutrition.xlsx"

DEFAULT_NUTRITION: dict[str, str] = {
    "marathon": (
        "La veille : un repas habituel riche en féculents (pâtes, riz, pommes de terre), sans excès de graisses ni "
        "de fibres. Bois régulièrement.\n"
        "Le matin : petit-déjeuner 3 h avant le départ, déjà testé à l'entraînement (pain ou céréales, miel, banane, "
        "boisson chaude).\n"
        "Pendant la course : bois un peu à chaque ravitaillement ; prends un gel (ou l'équivalent) toutes les 30 à "
        "45 min à partir de la 45e minute, toujours avec de l'eau.\n"
        "Après : bois et mange dans l'heure (fruit, barre, boisson de récupération).\n"
        "Rien de nouveau le jour J : tout doit avoir été testé sur tes sorties longues."),
    "semi": (
        "La veille : un repas habituel avec des féculents, sans excès.\n"
        "Le matin : petit-déjeuner 2 à 3 h avant le départ, déjà testé à l'entraînement.\n"
        "Pendant la course : quelques gorgées d'eau aux ravitaillements ; un gel vers le 12e km si tu l'as testé.\n"
        "Après : bois et mange un fruit ou une barre.\n"
        "Rien de nouveau le jour J."),
    "10k": (
        "La veille : un repas habituel, pas besoin de faire le plein de féculents.\n"
        "Le matin : petit-déjeuner léger 2 à 3 h avant le départ.\n"
        "Pendant la course : pas de ravitaillement nécessaire ; une gorgée d'eau s'il fait chaud.\n"
        "Après : bois et mange un fruit ou une barre."),
    "trail50": (
        "La veille : repas riche en féculents ; bois régulièrement.\n"
        "Le matin : petit-déjeuner 3 h avant le départ, déjà testé sur tes sorties longues.\n"
        "Pendant la course : environ 60 g de glucides par heure dès la première heure (gels, barres, pâtes de "
        "fruits, compotes) et 500 à 750 ml de boisson par heure selon la chaleur. Pense au salé aux "
        "ravitaillements (soupe, bouillon, fromage) sur la deuxième moitié.\n"
        "Emporte toujours l'eau et le matériel demandés par l'organisation.\n"
        "Rien de nouveau le jour J : tout doit avoir été testé sur tes SL."),
    "triL": (
        "La veille : repas riche en féculents ; bois régulièrement.\n"
        "Le matin : petit-déjeuner 3 h avant le départ, déjà testé à l'entraînement.\n"
        "Natation : rien à prendre ; un gel 15 min avant le départ si tu en as l'habitude.\n"
        "Vélo : c'est là qu'on mange et qu'on boit : 60 à 90 g de glucides par heure (barres, gels, boisson "
        "énergétique) et 500 à 750 ml par heure, par petites prises régulières.\n"
        "Course à pied : un gel toutes les 30 à 45 min avec de l'eau, et bois à chaque ravitaillement.\n"
        "Rien de nouveau le jour J : tout doit avoir été testé sur tes enchaînements."),
}


def load_nutrition(store: Store) -> dict[str, str]:
    """{distance: conseils} ; texte proposé par défaut tant que le coach n'a pas écrit le sien."""
    out = dict(DEFAULT_NUTRITION)
    if store.exists(NUTRITION_FILE):
        try:
            df = read_workbook(store.read(NUTRITION_FILE)).get("nutrition", pd.DataFrame())
        except ValueError:
            df = pd.DataFrame()
        for _, r in df.iterrows():
            key = _text(r.get("distance"))
            if key:
                out[key] = _text(r.get("texte"))
    return out


def save_nutrition(store: Store, distance: str, text: str) -> None:
    current = load_nutrition(store)
    current[distance] = str(text or "").strip()
    df = pd.DataFrame([{"distance": k, "texte": v} for k, v in current.items()], columns=["distance", "texte"])
    store.write(NUTRITION_FILE, write_workbook({"nutrition": df}))


def nutrition_for(store: Store, student) -> str:
    """Conseils nutrition de l'élève : son texte perso, sinon celui de sa distance."""
    own = str(getattr(student, "nutrition", "") or "").strip()
    return own or load_nutrition(store).get(student.distance, "")
