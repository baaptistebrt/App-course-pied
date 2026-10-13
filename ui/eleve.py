"""
Interface élève : son dossard, ses allures, son plan (lecture seule), le choix de sa fréquence
d'entraînement (3 ou 4 séances par semaine), l'export et l'impression.
"""

from __future__ import annotations

import streamlit as st

from core import profils
from core.calculs import compute_paces, parse_objective
from core.config import FREQUENCIES
from core.plan import full_plan_table
from ui import composants as ui
from ui.design import render, student_hero, week_cards


def render_student(student_id: str, on_logout) -> None:
    store = ui.app_store()
    s = profils.get_student(store, student_id)
    if s is None:
        st.error("Ce profil n'existe plus. Demande un nouveau code à ton coach.")
        st.button("Retour à l'accueil", on_click=on_logout)
        return
    ui.show_notifications()
    seconds = parse_objective(s.objectif, s.distance)
    paces = compute_paces(seconds, s.distance, s.ratios)

    with st.container(horizontal=True, horizontal_alignment="right"):
        st.button("Se déconnecter", icon=":material/logout:", on_click=on_logout, key="logout_student",
                  type="tertiary")
    render(student_hero(s.display_name, s.distance, seconds, s.date_course, s.plan.n_weeks, paces))

    def on_freq() -> None:
        value = st.session_state.get("my_freq")
        if value in FREQUENCIES:
            current = profils.get_student(store, student_id)
            profils.save_student(store, current.with_(frequence_eleve=value))
            ui.saved(f"Plan affiché pour {value} séances par semaine")

    table = full_plan_table(s.plan, paces, seconds, s.date_course, s.frequence, hide_empty=True)
    with st.container(border=True, key="card-toolbar"):
        c_freq, c_exp = st.columns([1, 2], vertical_alignment="center")
        c_freq.segmented_control("Séances par semaine", FREQUENCIES, default=s.frequence, key="my_freq",
                                 format_func=lambda n: f"{n} séances", on_change=on_freq, required=True,
                                 help="Change le nombre de séances affichées. Tes allures ne changent pas.")
        with c_exp:
            ui.exports_bar(s, table, paces, seconds, key="me")
    render(week_cards(table))
