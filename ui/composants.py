"""
Composants partagés entre l'interface éditeur et l'interface élève :
notifications, éditeur de plan (semaines / séances), éditeur de formules, exports et impression.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Callable

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from core import referentiel
from core.calculs import Pace, compute_paces, compute_paces_vma, format_minutes, format_pct_range, ratio_formula
from core.config import (DAY_LABELS, DAYS, FREQ_ALWAYS, FREQ_LABELS, PACE_BY_CODE, PACE_CODES, PACE_LABELS,
                         RATIO_CODES, SESSION_INPUT_COLUMNS, ZONE_COLORS)
from core.exports import export_csv, export_excel, fr_date, print_button_html, print_document, print_page
from core.plan import Plan, computed_columns, pace_codes, sessions_equal
from core.stockage import Store, get_store


# =========================================================================== stockage
@st.cache_resource(show_spinner="Chargement des données…")
def app_store() -> Store:
    """Stockage partagé par toutes les sessions (rechargé depuis GitHub au démarrage si configuré)."""
    store = get_store()
    referentiel.ensure_referentiel(store)
    return store


# =========================================================================== notifications
def notify(message: str, kind: str = "success") -> None:
    st.session_state.setdefault("_notes", []).append((kind, message))


def saved(message: str) -> None:
    """À appeler après un enregistrement : confirme, et signale un échec de copie GitHub."""
    store = app_store()
    if store.mirror and store.mirror.last_error:
        notify(f"Enregistré sur le serveur, mais la copie GitHub a échoué : {store.mirror.last_error}", "warning")
    else:
        notify(message)


def show_notifications() -> None:
    for kind, message in st.session_state.pop("_notes", []):
        if kind == "error":
            st.error(message, icon="⚠️")
        elif kind == "warning":
            st.warning(message, icon="☁️")
        else:
            st.toast(message, icon="✅")


def version(key: str) -> int:
    return st.session_state.setdefault(f"_v_{key}", 0)


def bump(key: str) -> None:
    """Change la clé des widgets concernés pour qu'ils se recréent avec les données enregistrées."""
    st.session_state[f"_v_{key}"] = version(key) + 1


# =========================================================================== éditeur de plan
COMPUTED = ["allure_txt", "temps_auto"]
EDITOR_ORDER = ["seance", "jour", "km_env", "duree_env", "contenu", "allure", "intensite", "km_spe", "temps_spe",
                "frequence", *COMPUTED, "remarque"]


def column_config() -> dict:
    cc = st.column_config
    return {
        "seance": cc.TextColumn("Séance", width=72, help="s1, s2… ou « JOUR J » (durée = objectif)"),
        "jour": cc.SelectboxColumn("Jour", width=92, options=DAYS, format_func=lambda d: DAY_LABELS.get(d, d),
                                   help="Facultatif : donne la date réelle de la séance"),
        "km_env": cc.TextColumn("Km", width=62, help="Nombre ou fourchette : 12, 25 à 30"),
        "duree_env": cc.TextColumn("Durée", width=66, help="h:mm, ex. 1:10"),
        "contenu": cc.TextColumn("Contenu", width=230, help='Ex. : 2x2000 A1 r=1000, 8x30"/30"'),
        "allure": cc.MultiselectColumn("Allure(s)", width=170, options=PACE_CODES,
                                       format_func=lambda c: PACE_LABELS.get(c, c),
                                       color=[ZONE_COLORS[c][0] for c in PACE_CODES],
                                       help="Une ou plusieurs allures ; elles se calculent selon la méthode de l'élève"),
        "intensite": cc.TextColumn("Intensité", width=150,
                                   help="Texte libre affiché tel quel à l'élève dans « Mon Planning », "
                                        "ex. « Facile, en aisance respiratoire »"),
        "km_spe": cc.NumberColumn("Km spé.", width=66, min_value=0.0, max_value=60.0, step=0.1, format="%.1f",
                                  help="Km à la 1re allure : le temps spécifique est alors calculé"),
        "temps_spe": cc.TextColumn("Temps spé.", width=78,
                                   help="Saisi à la main (ex. 27'30). Laisse vide pour le calcul automatique"),
        "frequence": cc.SelectboxColumn("Fréquence", width=105, options=list(FREQ_LABELS), required=True,
                                        default=FREQ_ALWAYS, format_func=lambda f: FREQ_LABELS.get(f, f),
                                        help="« Si 4 séances » : séance retirée quand l'élève s'entraîne 3 fois"),
        "allure_txt": cc.TextColumn("/km", width=110, disabled=True),
        "temps_auto": cc.TextColumn("Calculé", width=66, disabled=True,
                                    help="Km spé. × allure (utilisé si « Temps spé. » est vide)"),
        "remarque": cc.TextColumn("Remarque", width=190),
    }


def editor_frame(sessions: pd.DataFrame, paces: dict[str, Pace], seconds: int) -> pd.DataFrame:
    comp = computed_columns(sessions, paces, seconds)
    view = sessions.copy()
    view["allure_txt"] = comp["allure_txt"]
    view["temps_auto"] = [format_minutes(m) for m in comp["temps_spe_min"]]
    for col in ("session_id", "seance", "jour", "km_env", "duree_env", "contenu", "temps_spe", "remarque",
                "intensite", "allure_txt", "temps_auto", "frequence"):
        view[col] = view[col].astype(object)
    view["jour"] = [d or None for d in view["jour"]]
    view["allure"] = pd.Series([pace_codes(v) for v in view["allure"]], dtype=object)
    view["km_spe"] = view["km_spe"].astype("float64")
    return view[["session_id", *EDITOR_ORDER]]


def plan_editor(plan: Plan, paces: dict[str, Pace], seconds: int, race_date: date | None, key: str,
                load: Callable[[], Plan], save: Callable[[Plan, str], None]) -> None:
    """Édition complète d'un plan. `load` relit le plan enregistré, `save(plan, message)` l'enregistre."""
    ver = version(key)

    def apply(op: Callable[[Plan], Plan], message: str) -> None:
        try:
            save(op(load()), message)
        except ValueError as exc:
            notify(str(exc), "error")
        bump(key)

    with st.container(border=True, key=f"card-struct-{key}"):
        c_n, c_apply, c_add = st.columns([1, 1.3, 2.6], vertical_alignment="bottom")
        target = int(c_n.number_input("Durée du plan (semaines)", 1, 52, plan.n_weeks, key=f"n_{key}_{ver}"))
        diff = target - plan.n_weeks
        with c_apply.popover("Appliquer la durée", disabled=diff == 0, icon=":material/date_range:"):
            st.write(f"{diff} semaine(s) seront ajoutées **au début** (3 séances à compléter)." if diff > 0 else
                     f"Les **{-diff} premières semaines** et leurs séances seront supprimées.")
            st.caption("La fin du plan (affûtage et semaine de course) ne bouge pas.")
            st.button("Confirmer", type="primary", key=f"rs_{key}_{ver}",
                      on_click=apply, args=(lambda p: p.resize(target), f"Plan ajusté à {target} semaines"))
        with c_add, st.container(horizontal=True):
            st.button("Semaine au début", icon=":material/add:", key=f"af_{key}_{ver}",
                      on_click=apply, args=(lambda p: p.insert_week(0), "Semaine ajoutée au début"))
            st.button("Semaine à la fin", icon=":material/add:", key=f"al_{key}_{ver}",
                      on_click=apply, args=(lambda p: p.insert_week(p.n_weeks), "Semaine ajoutée à la fin"))
        st.caption("Double-clique sur une case pour la modifier ; « + » sous un tableau ajoute une séance, "
                   "la case à cocher d'une ligne puis la corbeille la supprime. Tout est enregistré automatiquement.")

    for _, week in plan.weeks.sort_values("position").iterrows():
        wid, pos = week["week_id"], int(week["position"])
        start = plan.week_start(pos, race_date)
        with st.container(border=True, key=f"card-week-{key}-{wid}"):
            c_t, c_p, c_a = st.columns([1.5, 3, 0.9], vertical_alignment="center")
            dates = f" — du {fr_date(start)} au {fr_date(start + timedelta(days=6))}" if start else ""
            c_t.markdown(f"**{Plan.week_label(pos)}**{dates}")
            phase_key = f"ph_{key}_{wid}_{ver}"
            c_p.text_input("Phase", value=week["phase"], key=phase_key, label_visibility="collapsed",
                           placeholder="Phase ou objectif de la semaine (facultatif)",
                           on_change=lambda w=wid, k=phase_key: apply(lambda p: p.set_phase(w, st.session_state[k]),
                                                                       "Phase enregistrée"))
            with c_a.popover("Actions", icon=":material/more_horiz:", width="stretch"):
                st.button("Insérer une semaine avant", icon=":material/add:", key=f"ins_{key}_{wid}_{ver}",
                          width="stretch", on_click=apply,
                          args=(lambda p, i=pos: p.insert_week(i), "Semaine insérée"))
                st.button("Dupliquer (copie avant)", icon=":material/content_copy:", key=f"dup_{key}_{wid}_{ver}",
                          width="stretch", on_click=apply,
                          args=(lambda p, w=wid: p.duplicate_week(w), "Semaine dupliquée"))
                ok = st.checkbox("Confirmer la suppression", key=f"cf_{key}_{wid}_{ver}")
                st.button("Supprimer la semaine", icon=":material/delete:", type="primary", width="stretch",
                          key=f"del_{key}_{wid}_{ver}", disabled=not ok or plan.n_weeks <= 1, on_click=apply,
                          args=(lambda p, w=wid: p.delete_week(w), "Semaine supprimée"))
            view = editor_frame(plan.sessions_of(wid), paces, seconds)
            edited = st.data_editor(view, key=f"ed_{key}_{wid}_{ver}_{seconds}", num_rows="dynamic",
                                    hide_index=True, width="stretch", column_config=column_config(),
                                    column_order=EDITOR_ORDER, disabled=COMPUTED, placeholder="")
            if not sessions_equal(edited[SESSION_INPUT_COLUMNS], view[SESSION_INPUT_COLUMNS]):
                save(load().replace_week_sessions(wid, edited[SESSION_INPUT_COLUMNS]),
                     f"{Plan.week_label(pos)} enregistrée")
                bump(key)
                st.rerun()


# =========================================================================== formules
def ratios_editor(ratios: dict[str, float], distance: str, objective_seconds: int, key: str,
                  on_save: Callable[[dict[str, float]], None]) -> None:
    """Tableau des ratios (en %), avec l'allure obtenue pour l'objectif indiqué."""
    ver = version(key)
    paces = compute_paces(objective_seconds, distance, ratios)
    df = pd.DataFrame([{
        "code": c, "Allure": PACE_LABELS[c], "Calculée à partir de": PACE_BY_CODE[c].base,
        "Pourcentage": float(ratios[c]), "Résultat": f"{paces[c].pace_str} /km",
        "Formule": ratio_formula(c, ratios),
    } for c in RATIO_CODES])
    edited = st.data_editor(
        df, key=f"rat_{key}_{ver}_{objective_seconds}", hide_index=True, width="stretch",
        disabled=["Allure", "Calculée à partir de", "Résultat", "Formule"], column_order=[
            "Allure", "Calculée à partir de", "Pourcentage", "Formule", "Résultat"],
        column_config={"Pourcentage": st.column_config.NumberColumn(
            "Ratio (% de la vitesse)", min_value=50.0, max_value=200.0, step=0.5, format="%.1f %%", required=True,
            help="Ex. 105 % : 5 % plus rapide que l'allure de référence")})
    new = {r["code"]: float(r["Pourcentage"]) for _, r in edited.iterrows()}
    if any(abs(new[c] - float(ratios[c])) > 1e-9 for c in RATIO_CODES):
        on_save(new)
        bump(key)
        st.rerun()


def vma_pct_editor(pct: dict, distance: str, vma: float, key: str, on_save: Callable[[dict], None]) -> None:
    """Plages de % de VMA par allure, avec l'allure obtenue pour la VMA indiquée."""
    ver = version(key)
    paces = compute_paces_vma(vma, distance, pct)
    df = pd.DataFrame([{"code": c, "Allure": PACE_LABELS[c], "% min": float(pct[c][0]), "% max": float(pct[c][1]),
                        "Plage": format_pct_range(*pct[c]), "Résultat": f"{paces[c].pace_str} /km"}
                       for c in PACE_CODES])
    num = lambda label: st.column_config.NumberColumn(label, min_value=30.0, max_value=140.0, step=0.5,  # noqa: E731
                                                      format="%.1f %%", required=True)
    edited = st.data_editor(
        df, key=f"vma_{key}_{ver}_{vma}", hide_index=True, width="stretch",
        disabled=["Allure", "Plage", "Résultat"], column_order=["Allure", "% min", "% max", "Plage", "Résultat"],
        column_config={"% min": num("% VMA min"), "% max": num("% VMA max")})
    new = {r["code"]: (float(r["% min"]), float(r["% max"])) for _, r in edited.iterrows()}
    if any(tuple(map(float, pct[c])) != new[c] for c in PACE_CODES):
        on_save(new)
        bump(key)
        st.rerun()


# =========================================================================== exports
def exports_bar(student, table: pd.DataFrame, sp, frequency: int, key: str, done: set[str] | None = None,
                race_time: str = "", notes: dict | None = None, vertical: bool = False) -> None:
    """Boutons d'export Excel / CSV et d'impression du plan affiché (en colonne : vertical=True)."""
    stem = re.sub(r"[^\w-]+", "_", f"plan_{student.race_name}_{student.display_name}").strip("_")
    doc = print_document(student, table, sp, frequency, done, race_time, notes)
    with st.container(horizontal=not vertical, vertical_alignment="center",
                      horizontal_alignment="left" if vertical else "right", gap="small"):
        components.html(print_button_html(doc), height=44, width=220 if vertical else 185)
        st.download_button("Excel", export_excel(student, table, sp, frequency, done, race_time, notes),
                           file_name=f"{stem}.xlsx", icon=":material/download:", key=f"xl_{key}", on_click="ignore",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.download_button("CSV", export_csv(table, done, notes), file_name=f"{stem}.csv", mime="text/csv",
                           icon=":material/download:", key=f"csv_{key}", on_click="ignore")
        st.download_button("Page imprimable", print_page(doc, f"Plan de {student.display_name}"),
                           file_name=f"{stem}.html", mime="text/html", icon=":material/description:",
                           key=f"html_{key}", on_click="ignore",
                           help="Page à ouvrir dans le navigateur puis à imprimer, si le bouton Imprimer est bloqué")


def basis_text(sp, student) -> str:
    """Phrase qui rappelle sur quoi reposent les allures."""
    if sp.method == "vma":
        return f"Allures calculées sur ta VMA de {str(student.vma).replace('.', ',').rstrip('0').rstrip(',')} km/h"
    return "Allures calculées sur ton objectif de temps"
