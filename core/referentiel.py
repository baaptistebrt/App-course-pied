"""
Référentiel du coach : formules (ratios) globales et modèles de référence par distance.

* Les formules globales servent de point de départ à chaque NOUVEL élève : elles sont copiées
  dans son profil à la création. Les modifier ensuite ne change donc pas les plans existants.
* Les modèles de référence sont copiés dans le plan d'un nouvel élève (puis modifiables pour lui seul).
"""

from __future__ import annotations

import pandas as pd

from .calculs import clean_ratios
from .config import DEFAULT_RATIOS, DISTANCE_KEYS, RATIO_CODES, SESSION_COLUMNS, WEEK_COLUMNS
from .modeles import DEFAULT_TEMPLATES
from .plan import Plan
from .stockage import Store, read_workbook, write_workbook

RATIOS_FILE = "formules.xlsx"


def template_file(distance: str) -> str:
    return f"modeles/{distance}.xlsx"


# ----------------------------------------------------------------------------
# Plan <-> onglets Excel (format partagé par les modèles et les profils)
# ----------------------------------------------------------------------------
def plan_to_sheets(plan: Plan) -> dict[str, pd.DataFrame]:
    plan = plan.normalized()
    return {"semaines": plan.weeks[WEEK_COLUMNS], "seances": plan.sessions[SESSION_COLUMNS]}


def plan_from_sheets(sheets: dict[str, pd.DataFrame]) -> Plan:
    weeks = sheets.get("semaines", pd.DataFrame(columns=WEEK_COLUMNS)).copy()
    sessions = sheets.get("seances", pd.DataFrame(columns=SESSION_COLUMNS)).copy()
    for col in WEEK_COLUMNS:
        if col not in weeks.columns:
            weeks[col] = None
    for col in SESSION_COLUMNS:
        if col not in sessions.columns:
            sessions[col] = None
    return Plan(weeks[WEEK_COLUMNS], sessions[SESSION_COLUMNS]).normalized()


# ----------------------------------------------------------------------------
# Formules globales
# ----------------------------------------------------------------------------
def load_global_ratios(store: Store) -> dict[str, dict[str, float]]:
    """{distance: {code: %}} ; valeurs de l'Excel par défaut."""
    out = {d: dict(DEFAULT_RATIOS) for d in DISTANCE_KEYS}
    content = store.read(RATIOS_FILE)
    if content:
        try:
            df = read_workbook(content).get("formules", pd.DataFrame())
            for _, row in df.iterrows():
                if row.get("distance") in out and row.get("allure") in RATIO_CODES:
                    out[row["distance"]][row["allure"]] = row.get("pourcentage")
        except ValueError:
            pass
    return {d: clean_ratios(r) for d, r in out.items()}


def save_global_ratios(store: Store, distance: str, ratios: dict[str, float]) -> None:
    all_ratios = load_global_ratios(store)
    all_ratios[distance] = clean_ratios(ratios)
    rows = [{"distance": d, "allure": c, "pourcentage": v} for d, r in all_ratios.items() for c, v in r.items()]
    store.write(RATIOS_FILE, write_workbook({"formules": pd.DataFrame(rows)}))


# ----------------------------------------------------------------------------
# Modèles de référence
# ----------------------------------------------------------------------------
def default_template(distance: str) -> Plan:
    return Plan.from_week_list(DEFAULT_TEMPLATES[distance])


def load_template(store: Store, distance: str) -> Plan:
    """Modèle de la distance (créé à partir des valeurs par défaut s'il n'existe pas)."""
    content = store.read(template_file(distance))
    if content:
        try:
            return plan_from_sheets(read_workbook(content))
        except ValueError:
            pass
    plan = default_template(distance)
    save_template(store, distance, plan)
    return plan


def save_template(store: Store, distance: str, plan: Plan) -> None:
    store.write(template_file(distance), write_workbook(plan_to_sheets(plan)))


def reset_template(store: Store, distance: str) -> Plan:
    plan = default_template(distance)
    save_template(store, distance, plan)
    return plan


def ensure_referentiel(store: Store) -> None:
    """Crée les fichiers du référentiel manquants (premier lancement)."""
    if not store.exists(RATIOS_FILE):
        for d in DISTANCE_KEYS:
            save_global_ratios(store, d, DEFAULT_RATIOS)
    for d in DISTANCE_KEYS:
        if not store.exists(template_file(d)):
            save_template(store, d, default_template(d))
