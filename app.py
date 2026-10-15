"""
Coach running — plans d'entraînement Marathon, Semi-marathon et 10 km.

Lancement :  streamlit run app.py

* Page d'accueil publique : un seul champ, le code d'accès (rien d'autre n'est visible sans code).
* Code du coach -> interface éditeur : profils élèves (code envoyé par e-mail), calcul des allures
  par objectif de temps ou par VMA, plans, formules, supervision des séances réalisées.
* Code d'un élève -> son espace : plan en lecture seule, cases « séance réalisée », temps de course,
  2, 3 ou 4 séances par semaine, export et impression.

Organisation du code :
    core/   logique métier, sans Streamlit
            calculs.py + moteur.py (calcul double), plan.py, modeles.py, referentiel.py,
            profils.py (élèves), suivi.py (séances réalisées), emails.py, stockage.py, exports.py, auth.py
    ui/     interface : design.py, composants.py, editeur.py, eleve.py, supervision.py
"""

from __future__ import annotations

import time

import streamlit as st

from core.auth import ROLE_EDITOR, ROLE_STUDENT, authenticate
from ui import composants as ui
from ui.design import inject_css, landing_css, landing_header, render
from ui.editeur import render_editor
from ui.eleve import render_student

st.set_page_config(page_title="Ton plan d'entraînement", page_icon="🏃", layout="wide")


def logout() -> None:
    for k in ("role", "student_id", "my_freq"):
        st.session_state.pop(k, None)


def render_landing() -> None:
    """Page d'accueil publique : visuel plein écran, logo, titre et champ du code d'accès."""
    landing_css(ui.app_store())
    _, center, _ = st.columns([1, 1.5, 1])
    with center:
        render(landing_header())
        with st.form("login", border=True):
            code = st.text_input("Code d'accès", type="password", placeholder="ex. K7PM-Q2XD")
            submitted = st.form_submit_button("Accéder à mon plan", type="primary", width="stretch",
                                              icon=":material/directions_run:")
        if submitted:
            result = authenticate(code, ui.app_store())
            if result:
                st.session_state["role"], st.session_state["student_id"] = result
                st.rerun()
            time.sleep(1)  # ralentit les essais en série
            st.error("Code inconnu. Vérifie le code reçu par e-mail (les tirets et majuscules ne comptent pas).")


def main() -> None:
    inject_css(ui.app_store())
    if st.query_params:              # pas d'accès direct au plan par un lien : on repart de l'accueil
        st.query_params.clear()
    role = st.session_state.get("role")
    if role == ROLE_EDITOR:
        render_editor(logout)
    elif role == ROLE_STUDENT:
        render_student(st.session_state["student_id"], logout)
    else:
        render_landing()


main()
