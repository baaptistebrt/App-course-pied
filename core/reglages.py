"""
Réglages du coach enregistrés avec les données (`data/reglages.xlsx`) et checklist du jour J
(`data/checklist.xlsx`), modifiables dans l'onglet Réglages.

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
FOR_OPTIONS = {"toutes": "Toutes les distances", "10k": "10 km", "semi": "Semi-marathon", "marathon": "Marathon"}

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
