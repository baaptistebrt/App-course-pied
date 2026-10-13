"""
Coach running — plans d'entraînement Marathon, Semi-marathon et 10 km.

Lancement :  streamlit run app.py

* Le coach (code éditeur) crée un profil par élève, avec un code d'accès généré automatiquement,
  et ajuste objectif, date de course, fréquence, plan et formules.
* L'élève (code personnel) consulte son plan, choisit 3 ou 4 séances par semaine, exporte et imprime.

Organisation du code :
    core/   logique métier (calculs, plans, profils, stockage, exports) — sans Streamlit
    ui/     interface : design.py (identité visuelle), composants.py, editeur.py, eleve.py
"""

from __future__ import annotations

import time

import streamlit as st

from core.auth import ROLE_EDITOR, ROLE_STUDENT, authenticate
from ui import composants as ui
from ui.design import inject_css, login_track, render
from ui.editeur import render_editor
from ui.eleve import render_student

st.set_page_config(page_title="Coach running", page_icon="🏃", layout="wide")


def logout() -> None:
    for k in ("role", "student_id", "my_freq"):
        st.session_state.pop(k, None)


def login(code: str) -> bool:
    result = authenticate(code, ui.app_store())
    if not result:
        return False
    st.session_state["role"], st.session_state["student_id"] = result
    return True


def render_login() -> None:
    _, center, _ = st.columns([1, 2.2, 1])
    with center:
        render(login_track())
        with st.form("login", border=True):
            code = st.text_input("Code d'accès", type="password", placeholder="ex. K7PM-Q2XD")
            submitted = st.form_submit_button("Voir mon plan", type="primary", width="stretch")
        if submitted:
            if login(code):
                st.rerun()
            time.sleep(1)  # ralentit les essais en série
            st.error("Code inconnu. Vérifie-le auprès de ton coach (les tirets et majuscules ne comptent pas).")


def main() -> None:
    inject_css()
    # Lien direct envoyé par le coach : https://…/?code=XXXX-XXXX (codes élèves uniquement).
    if "role" not in st.session_state and "code" in st.query_params:
        result = authenticate(st.query_params.get("code", ""), ui.app_store())
        if result and result[0] == ROLE_STUDENT:
            st.session_state["role"], st.session_state["student_id"] = result
        st.query_params.clear()

    role = st.session_state.get("role")
    if role == ROLE_EDITOR:
        render_editor(logout)
    elif role == ROLE_STUDENT:
        render_student(st.session_state["student_id"], logout)
    else:
        render_login()


main()
