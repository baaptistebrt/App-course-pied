"""
Référentiel du coach : formules (ratios) globales et modèles de référence par distance.

* Les formules globales (ratios « objectif de temps » et plages de % de VMA) servent de point de
  départ à chaque NOUVEL élève : elles sont copiées
  dans son profil à la création. Les modifier ensuite ne change donc pas les plans existants.
* Les modèles de référence sont copiés dans le plan d'un nouvel élève (puis modifiables pour lui seul).
"""

from __future__ import annotations

import pandas as pd

from .calculs import clean_ratios, clean_vma_pct
from .config import (DEFAULT_RATIOS, DEFAULT_VMA_PCT, DISTANCE_KEYS, PACE_CODES, RATIO_CODES, SESSION_COLUMNS,
                     WEEK_COLUMNS)
from .modeles import DEFAULT_TEMPLATES
from .plan import Plan
from .stockage import Store, read_workbook, write_workbook

RATIOS_FILE = "formules.xlsx"
# Version des modèles par défaut. Un modèle enregistré avec une version plus ancienne est remplacé
# au démarrage (l'ancien est gardé en « modeles/<distance>_v<n>.xlsx »). 10 km v3 = fichier Excel de Maud.
TEMPLATE_VERSIONS: dict[str, int] = {"marathon": 2, "semi": 2, "10k": 3}


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
    # Fichiers d'une version précédente (sans identifiant de séance) : identifiant déterministe,
    # pour que le suivi « séance réalisée » reste stable tant que le plan n'est pas réenregistré.
    missing = sessions["session_id"].isna() | (sessions["session_id"].astype(str).str.strip().isin(["", "nan", "None"]))
    if missing.any():
        sessions.loc[missing, "session_id"] = [f"{w}-{o}" for w, o in zip(sessions.loc[missing, "week_id"],
                                                                          sessions.loc[missing, "ordre"])]
    return Plan(weeks[WEEK_COLUMNS], sessions[SESSION_COLUMNS]).normalized()


# ----------------------------------------------------------------------------
# Formules globales
# ----------------------------------------------------------------------------
def _read_formules(store: Store) -> dict[str, pd.DataFrame]:
    content = store.read(RATIOS_FILE)
    if not content:
        return {}
    try:
        return read_workbook(content)
    except ValueError:
        return {}


def load_global_ratios(store: Store) -> dict[str, dict[str, float]]:
    """{distance: {code: %}} ; valeurs de l'Excel par défaut."""
    out = {d: dict(DEFAULT_RATIOS) for d in DISTANCE_KEYS}
    for _, row in _read_formules(store).get("formules", pd.DataFrame()).iterrows():
        if row.get("distance") in out and row.get("allure") in RATIO_CODES:
            out[row["distance"]][row["allure"]] = row.get("pourcentage")
    return {d: clean_ratios(r) for d, r in out.items()}


def load_global_vma_pct(store: Store) -> dict[str, dict[str, tuple[float, float]]]:
    """{distance: {code: (% min, % max)}} ; valeurs du plan 10 km de référence par défaut."""
    out = {d: dict(DEFAULT_VMA_PCT) for d in DISTANCE_KEYS}
    for _, row in _read_formules(store).get("vma", pd.DataFrame()).iterrows():
        if row.get("distance") in out and row.get("allure") in PACE_CODES:
            out[row["distance"]][row["allure"]] = (row.get("pct_min"), row.get("pct_max"))
    return {d: clean_vma_pct(r) for d, r in out.items()}


def _write_formules(store: Store, ratios: dict, vma: dict) -> None:
    rows_r = [{"distance": d, "allure": c, "pourcentage": v} for d, r in ratios.items() for c, v in r.items()]
    rows_v = [{"distance": d, "allure": c, "pct_min": lo, "pct_max": hi}
              for d, r in vma.items() for c, (lo, hi) in r.items()]
    store.write(RATIOS_FILE, write_workbook({"formules": pd.DataFrame(rows_r), "vma": pd.DataFrame(rows_v)}))


def save_global_ratios(store: Store, distance: str, ratios: dict[str, float]) -> None:
    all_ratios = load_global_ratios(store)
    all_ratios[distance] = clean_ratios(ratios)
    _write_formules(store, all_ratios, load_global_vma_pct(store))


def save_global_vma_pct(store: Store, distance: str, pct: dict) -> None:
    all_vma = load_global_vma_pct(store)
    all_vma[distance] = clean_vma_pct(pct)
    _write_formules(store, load_global_ratios(store), all_vma)


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
    meta = pd.DataFrame([("version", TEMPLATE_VERSIONS[distance])], columns=["cle", "valeur"])
    store.write(template_file(distance), write_workbook({**plan_to_sheets(plan), "meta": meta}))


def stored_template_version(store: Store, distance: str) -> int:
    content = store.read(template_file(distance))
    if not content:
        return 0
    try:
        meta = read_workbook(content).get("meta")
    except ValueError:
        return 0
    if meta is None or meta.empty:
        return 2                                  # fichiers de la version précédente, sans onglet « meta »
    values = dict(zip(meta["cle"], meta["valeur"]))
    try:
        return int(values.get("version", 2))
    except (TypeError, ValueError):
        return 2


def reset_template(store: Store, distance: str) -> Plan:
    plan = default_template(distance)
    save_template(store, distance, plan)
    return plan


def ensure_referentiel(store: Store) -> None:
    """Crée les fichiers du référentiel manquants (premier lancement)."""
    if not store.exists(RATIOS_FILE) or "vma" not in _read_formules(store):
        _write_formules(store, load_global_ratios(store), load_global_vma_pct(store))
    for d in DISTANCE_KEYS:
        if not store.exists(template_file(d)):
            save_template(store, d, default_template(d))
            continue
        old_version = stored_template_version(store, d)
        if old_version < TEMPLATE_VERSIONS[d]:
            store.write(f"modeles/{d}_v{old_version}.xlsx", store.read(template_file(d)))   # copie de l'ancien
            save_template(store, d, default_template(d))
