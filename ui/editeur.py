"""
Interface éditeur (coach) : trois onglets Marathon / Semi-marathon / 10 km, chacun avec
ses élèves, ses formules globales et son modèle de référence.
"""

from __future__ import annotations

import time
from datetime import date

import pandas as pd
import streamlit as st

from core import profils, referentiel
from core.auth import load_editor_code
from core.calculs import compute_paces, format_race_time, normalize_objective, parse_objective
from core.config import DISTANCE_KEYS, DISTANCES, FREQUENCIES
from core.exports import fr_date
from core.plan import full_plan_table, weeks_until
from core.profils import Student
from ui import composants as ui
from ui.design import editor_track, paces_track, render, week_cards

FREQ_FMT = {3: "3 séances", 4: "4 séances"}


# =========================================================================== barre latérale
def sidebar(on_logout) -> None:
    store = ui.app_store()
    with st.sidebar:
        st.markdown("### 🏃 Coach running")
        st.caption("Connecté en tant que coach")
        if store.mirror:
            m = store.mirror
            if m.last_error:
                st.warning(f"Copie GitHub en échec : {m.last_error}", icon="☁️")
            else:
                st.caption(f"Sauvegarde : fichiers du serveur + copie GitHub ({m.repo})"
                           + (f", dernière à {m.last_success:%H:%M}" if m.last_success else ""))
        else:
            st.caption("Sauvegarde : fichiers du dossier `data/` du serveur.")
        if load_editor_code().is_demo:
            st.warning("Code coach de démonstration actif : définis le tien dans les Secrets (voir README).",
                       icon="🔐")
        st.button("Se déconnecter", icon=":material/logout:", on_click=on_logout, key="logout_editor")


# =========================================================================== page principale
def render_editor(on_logout) -> None:
    store = ui.app_store()
    sidebar(on_logout)
    ui.show_notifications()
    counts = {d: len(profils.list_students(store, d)) for d in DISTANCE_KEYS}
    render(editor_track(counts))
    tabs = st.tabs([DISTANCES[d].label for d in DISTANCE_KEYS], key="distance_tabs")
    for tab, d in zip(tabs, DISTANCE_KEYS):
        with tab:
            view = st.segmented_control("Vue", ["Élèves", "Formules", "Modèle de référence"], default="Élèves",
                                        required=True, key=f"view_{d}", label_visibility="collapsed")
            if view == "Formules":
                render_global_ratios(d)
            elif view == "Modèle de référence":
                render_template(d)
            else:
                render_students(d)


# =========================================================================== élèves
def _create_student(distance: str) -> None:
    """Callback du formulaire « Nouvel élève »."""
    store = ui.app_store()
    g = lambda k: st.session_state.get(f"new_{k}_{distance}")  # noqa: E731
    try:
        student = profils.create_student(
            store, g("email") or "", g("prenom") or "", distance, g("objectif") or None, g("date"),
            g("freq") or 4, reserved_codes={load_editor_code().value})
    except ValueError as exc:
        ui.notify(str(exc), "error")
        return
    st.session_state[f"sel_{distance}"] = student.id
    for k in ("email", "prenom", "date"):
        st.session_state.pop(f"new_{k}_{distance}", None)
    ui.saved(f"{student.display_name} ajouté(e). Code d'accès : {student.code}")


def new_student_form(distance: str) -> None:
    dist = DISTANCES[distance]
    with st.form(f"new_student_{distance}", border=False, clear_on_submit=False):
        st.text_input("E-mail de l'élève", key=f"new_email_{distance}", placeholder="prenom.nom@exemple.fr")
        st.text_input("Prénom (facultatif)", key=f"new_prenom_{distance}")
        c1, c2 = st.columns(2)
        c1.text_input(f"Objectif {dist.label.lower()} (hh:mm:ss)", value=dist.default_objective,
                      key=f"new_objectif_{distance}")
        c2.date_input("Date de course (facultatif)", value=None, format="DD/MM/YYYY", key=f"new_date_{distance}",
                      min_value=date.today())
        st.radio("Séances par semaine", FREQUENCIES, index=1, horizontal=True, format_func=FREQ_FMT.get,
                 key=f"new_freq_{distance}")
        st.caption(f"Le plan part du modèle de référence {dist.label.lower()} et des formules globales actuelles. "
                   "Un code d'accès personnel est créé automatiquement.")
        st.form_submit_button("Créer l'élève", type="primary", on_click=_create_student, args=(distance,))


def render_students(distance: str) -> None:
    store = ui.app_store()
    students = profils.list_students(store, distance)
    label = DISTANCES[distance].label.lower()
    if not students:
        st.html(f"<div class='empty'>Aucun élève en {label} pour l'instant. Ajoute ton premier élève avec son "
                "e-mail : son code d'accès est créé automatiquement.</div>")
        with st.container(border=True, key=f"card-new-{distance}"):
            new_student_form(distance)
        return

    ids = [s.id for s in students]
    by_id = {s.id: s for s in students}
    key = f"sel_{distance}"
    if st.session_state.get(key) not in ids:
        st.session_state[key] = ids[0]
    c_sel, c_new = st.columns([3, 1], vertical_alignment="bottom")
    c_sel.selectbox("Élève", ids, key=key, format_func=lambda i: f"{by_id[i].display_name} — {by_id[i].email}")
    with c_new.popover("Nouvel élève", icon=":material/person_add:", width="stretch"):
        new_student_form(distance)

    student_panel(by_id[st.session_state[key]])

    with st.expander(f"Tous les élèves en {label} ({len(students)})"):
        st.dataframe(pd.DataFrame([{
            "Élève": s.display_name, "E-mail": s.email, "Code": s.code,
            "Objectif": format_race_time(parse_objective(s.objectif, s.distance)),
            "Course": s.date_course.strftime("%d/%m/%Y") if s.date_course else "",
            "Séances/sem.": s.frequence, "Semaines": s.plan.n_weeks, "Créé le": s.cree_le,
        } for s in students]), hide_index=True, width="stretch")


def _save_student(student_id: str, message: str, **changes) -> None:
    store = ui.app_store()
    current = profils.get_student(store, student_id)
    if current is None:
        ui.notify("Cet élève n'existe plus.", "error")
        return
    profils.save_student(store, current.with_(**changes))
    ui.saved(message)


def student_panel(s: Student) -> None:
    store = ui.app_store()
    key = f"stu_{s.id}"
    ver = ui.version(key)
    seconds = parse_objective(s.objectif, s.distance)
    paces = compute_paces(seconds, s.distance, s.ratios)

    def on_objective(k: str) -> None:
        try:
            value = normalize_objective(st.session_state[k], s.distance)
        except ValueError as exc:
            ui.notify(str(exc), "error")
        else:
            _save_student(s.id, "Objectif enregistré", objectif=value)
        ui.bump(key)

    def on_date(k: str) -> None:
        _save_student(s.id, "Date de course enregistrée", date_course=st.session_state.get(k))
        ui.bump(key)

    def on_freq(k: str) -> None:
        value = st.session_state.get(k)
        if value in FREQUENCIES:
            _save_student(s.id, "Fréquence enregistrée", frequence_defaut=value)
        ui.bump(key)

    def regenerate() -> None:
        updated = profils.regenerate_code(store, profils.get_student(store, s.id),
                                          reserved_codes={load_editor_code().value})
        ui.saved(f"Nouveau code : {updated.code}. L'ancien ne fonctionne plus.")
        ui.bump(key)

    def delete() -> None:
        profils.delete_student(store, s.id)
        st.session_state.pop(f"sel_{s.distance}", None)
        ui.saved(f"{s.display_name} supprimé(e)")

    with st.container(border=True, key=f"card-student-{s.id}"):
        c_who, c_code, c_act = st.columns([2.2, 2.2, 1], vertical_alignment="top")
        c_who.markdown(f"### {s.display_name}")
        c_who.caption(f"{s.email} — {DISTANCES[s.distance].label}, créé le {s.cree_le[:10]}")
        with c_code:
            st.caption("Code d'accès à transmettre")
            st.code(s.code, language=None)
            base = str(getattr(st.context, "url", "") or "").split("?")[0].rstrip("/")
            if base:
                st.caption("Lien direct (connexion sans saisir le code)")
                st.code(f"{base}/?code={s.code}", language=None)
        with c_act.popover("Actions", icon=":material/more_horiz:", width="stretch"):
            st.button("Générer un nouveau code", icon=":material/key:", on_click=regenerate,
                      key=f"regen_{s.id}_{ver}", width="stretch",
                      help="L'ancien code ne fonctionnera plus")
            ok = st.checkbox("Confirmer la suppression", key=f"delok_{s.id}_{ver}")
            st.button("Supprimer l'élève", icon=":material/delete:", type="primary", disabled=not ok,
                      on_click=delete, key=f"del_{s.id}_{ver}", width="stretch")

        c_obj, c_date, c_freq, c_info = st.columns([1, 1, 1.1, 1.6], vertical_alignment="bottom")
        k_obj = f"obj_{s.id}_{ver}"
        c_obj.text_input(f"Objectif {DISTANCES[s.distance].label.lower()}", value=s.objectif, key=k_obj,
                         on_change=on_objective, args=(k_obj,), help="hh:mm:ss")
        k_date = f"date_{s.id}_{ver}"
        c_date.date_input("Date de course (facultatif)", value=s.date_course, format="DD/MM/YYYY", key=k_date,
                          on_change=on_date, args=(k_date,))
        k_freq = f"freq_{s.id}_{ver}"
        c_freq.segmented_control("Séances par semaine", FREQUENCIES, default=s.frequence_defaut,
                                 format_func=FREQ_FMT.get, key=k_freq, on_change=on_freq, args=(k_freq,))
        with c_info:
            info_weeks(s)

    render(paces_track(paces))

    t_plan, t_ratios, t_preview = st.tabs(["Plan de l'élève", "Formules de l'élève", "Aperçu et export"])
    with t_plan:
        ui.plan_editor(
            s.plan, paces, seconds, s.date_course, key=f"plan_{s.id}",
            load=lambda: profils.get_student(store, s.id).plan,
            save=lambda plan, msg: _save_student(s.id, msg, plan=plan))
    with t_ratios:
        st.caption("Formules propres à cet élève : copiées des formules globales à sa création, modifiables ici "
                   "sans toucher aux autres élèves.")
        ui.ratios_editor(s.ratios, s.distance, seconds, key=f"ratios_{s.id}",
                         on_save=lambda r: _save_student(s.id, "Formules de l'élève enregistrées", ratios=r))
        globals_ = referentiel.load_global_ratios(store)[s.distance]
        if globals_ != s.ratios:
            st.button("Reprendre les formules globales actuelles", icon=":material/sync:", key=f"rg_{s.id}_{ver}",
                      on_click=lambda: (_save_student(s.id, "Formules globales appliquées", ratios=dict(globals_)),
                                        ui.bump(f"ratios_{s.id}")))
    with t_preview:
        st.caption(f"Ce que voit l'élève avec {s.frequence} séances par semaine.")
        table = full_plan_table(s.plan, paces, seconds, s.date_course, s.frequence, hide_empty=True)
        ui.exports_bar(s, table, paces, seconds, key=f"exp_{s.id}")
        render(week_cards(table))


def info_weeks(s: Student) -> None:
    """Semaines restantes avant la course, à titre indicatif, avec ajustement en un clic."""
    if s.frequence_eleve and s.frequence_eleve != s.frequence_defaut:
        st.caption(f"L'élève a choisi {s.frequence_eleve} séances par semaine.")
    if not s.date_course:
        st.caption(f"Plan de {s.plan.n_weeks} semaines, sans date de course.")
        return
    left = weeks_until(s.date_course)
    if left < 1:
        st.caption(f"La course du {fr_date(s.date_course, True)} est passée.")
        return
    st.markdown(f"**{left} semaine{'s' if left > 1 else ''}** avant la course (semaine en cours comprise) ; "
                f"le plan en compte {s.plan.n_weeks}.")
    if left != s.plan.n_weeks:
        def adjust() -> None:
            store = ui.app_store()
            cur = profils.get_student(store, s.id)
            _save_student(s.id, f"Plan ajusté à {left} semaines", plan=cur.plan.resize(left))
            ui.bump(f"plan_{s.id}")
        st.button(f"Adapter le plan à {left} semaines", key=f"fit_{s.id}_{s.plan.n_weeks}_{left}",
                  on_click=adjust, help="Ajoute ou retire des semaines au début ; la fin du plan ne bouge pas")


# =========================================================================== formules globales
def render_global_ratios(distance: str) -> None:
    store = ui.app_store()
    dist = DISTANCES[distance]
    st.markdown(f"#### Formules globales {dist.label.lower()}")
    st.caption(f"L'objectif fixe l'allure **{dist.anchor}** ({dist.label.lower()} sur {str(dist.km).replace('.', ',')} km) ; "
               "les autres allures en découlent avec ces ratios. Ils s'appliquent aux élèves créés **à partir de "
               "maintenant** : les plans existants gardent leurs propres formules.")
    c_obj, _ = st.columns([1, 3])
    sample = c_obj.text_input("Objectif d'exemple", value=dist.default_objective, key=f"sample_{distance}")
    try:
        seconds = parse_objective(sample, distance)
    except ValueError as exc:
        st.error(str(exc))
        return
    ratios = referentiel.load_global_ratios(store)[distance]

    def save(r: dict) -> None:
        referentiel.save_global_ratios(store, distance, r)
        ui.saved("Formules globales enregistrées (nouveaux élèves)")

    ui.ratios_editor(ratios, distance, seconds, key=f"gratios_{distance}", on_save=save)
    render(paces_track(compute_paces(seconds, distance, ratios)))
    if ratios != referentiel.DEFAULT_RATIOS:
        st.button("Revenir aux valeurs de l'Excel", icon=":material/restart_alt:", key=f"gr_reset_{distance}",
                  on_click=lambda: (save(dict(referentiel.DEFAULT_RATIOS)), ui.bump(f"gratios_{distance}")))


# =========================================================================== modèle de référence
def render_template(distance: str) -> None:
    store = ui.app_store()
    dist = DISTANCES[distance]
    st.markdown(f"#### Modèle de référence {dist.label.lower()}")
    st.caption("Point de départ du plan de chaque nouvel élève. Le modifier ne change pas les plans existants.")
    c_obj, c_reset = st.columns([1, 3], vertical_alignment="bottom")
    sample = c_obj.text_input("Objectif d'exemple", value=dist.default_objective, key=f"tsample_{distance}")
    try:
        seconds = parse_objective(sample, distance)
    except ValueError as exc:
        st.error(str(exc))
        return
    with c_reset.popover("Réinitialiser le modèle", icon=":material/restart_alt:"):
        st.write("Remplace ce modèle par la version d'origine (6 semaines + semaine de course).")
        ok = st.checkbox("Je confirme", key=f"tr_ok_{distance}")
        if st.button("Réinitialiser", type="primary", disabled=not ok, key=f"tr_btn_{distance}"):
            referentiel.reset_template(store, distance)
            ui.saved("Modèle réinitialisé")
            ui.bump(f"tpl_{distance}")
            time.sleep(0.2)
            st.rerun()
    ratios = referentiel.load_global_ratios(store)[distance]
    ui.plan_editor(referentiel.load_template(store, distance), compute_paces(seconds, distance, ratios), seconds,
                   None, key=f"tpl_{distance}", load=lambda: referentiel.load_template(store, distance),
                   save=lambda plan, msg: (referentiel.save_template(store, distance, plan), ui.saved(msg)))
