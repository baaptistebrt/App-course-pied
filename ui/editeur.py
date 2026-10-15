"""
Interface éditeur (coach).

Onglets : Marathon / Semi-marathon / 10 km (élèves, formules, modèle de référence de la distance),
Supervision (suivi de tous les élèves) et Réglages (e-mails, visuels, sauvegarde).
"""

from __future__ import annotations

import time
from datetime import date

import pandas as pd
import streamlit as st

from core import historique, profils, referentiel, suivi
from core.auth import load_editor_code
from core.calculs import (compute_paces, compute_paces_vma, format_race_time, fr_number, normalize_objective,
                          parse_objective, parse_vma)
from core.config import DEFAULT_VMA_PCT, DISTANCE_KEYS, DISTANCES, FREQUENCIES, METHODS, VMA_DEFAULT
from core.emails import load_email_config, send_access_email, send_test_email
from core.exports import fr_date
from core.moteur import comparison, student_paces
from core.plan import weeks_until
from core.profils import Student
from ui import composants as ui
from ui import eleve, supervision
from ui.parcours import render_editor_routes
from ui.design import MEDIA_FILES, editor_track, media_uri, paces_track, prepare_photo, render

FREQ_FMT = {3: "3 séances", 4: "4 séances"}
DIST_ICONS = {"marathon": ":material/directions_run:", "semi": ":material/sprint:", "10k": ":material/timer:"}


def app_url() -> str:
    """Adresse de l'application, pour l'e-mail envoyé à l'élève."""
    cfg = load_email_config()
    if cfg and cfg.app_url:
        return cfg.app_url
    return str(getattr(st.context, "url", "") or "").split("?")[0].rstrip("/")


# =========================================================================== barre latérale
def sidebar(on_logout) -> None:
    store = ui.app_store()
    with st.sidebar:
        st.html(f"<div style='display:flex;gap:10px;align-items:center'>{_logo()}"
                "<b style='font-family:var(--cond);font-size:1.35rem'>Coach running</b></div>")
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
        st.caption("E-mails : " + ("envoi automatique activé" if load_email_config() else
                                   "non configurés (voir Réglages)"))
        if load_editor_code().is_demo:
            st.warning("Code coach de démonstration actif : définis le tien dans les Secrets (voir README).",
                       icon="🔐")
        st.button("Se déconnecter", icon=":material/logout:", on_click=on_logout, key="logout_editor")


def _logo() -> str:
    from ui.design import logo_svg

    return logo_svg(34)


# =========================================================================== page principale
def render_editor(on_logout) -> None:
    store = ui.app_store()
    sidebar(on_logout)
    ui.show_notifications()
    counts = {d: len(profils.list_students(store, d)) for d in DISTANCE_KEYS}
    render(editor_track(counts))
    labels = [f"{DIST_ICONS[d]} {DISTANCES[d].label}" for d in DISTANCE_KEYS]
    tabs = st.tabs([*labels, ":material/monitoring: Supervision", ":material/map: Parcours",
                    ":material/settings: Réglages"], key="main_tabs")
    for tab, d in zip(tabs, DISTANCE_KEYS):
        with tab:
            view = st.segmented_control("Vue", ["Élèves", "Formules", "Modèle de référence"], default="Élèves",
                                        required=True, key=f"view_{d}", label_visibility="collapsed")
            if view == "Formules":
                render_global_formulas(d)
            elif view == "Modèle de référence":
                render_template(d)
            else:
                render_students(d)
    with tabs[len(DISTANCE_KEYS)]:
        supervision.render_overview()
    with tabs[len(DISTANCE_KEYS) + 1]:
        render_editor_routes()
    with tabs[len(DISTANCE_KEYS) + 2]:
        render_settings()


# =========================================================================== élèves
def _send_code(student_id: str) -> None:
    """Envoie (ou renvoie) le code d'accès à l'élève et note la date d'envoi."""
    store = ui.app_store()
    s = profils.get_student(store, student_id)
    ok, message = send_access_email(s, load_email_config(), app_url())
    if ok:
        profils.save_student(store, s.with_(email_envoye_le=time.strftime("%Y-%m-%d %H:%M")))
        ui.saved(message)
    else:
        ui.notify(message, "warning")


def _create_student(distance: str) -> None:
    """Callback du formulaire « Nouvel élève »."""
    store = ui.app_store()
    g = lambda k: st.session_state.get(f"new_{k}_{distance}")  # noqa: E731
    known = {s.person for s in profils.list_students(store)
             if s.email.lower() == (g("email") or "").strip().lower()}
    try:
        student = profils.create_student(
            store, g("email") or "", g("prenom") or "", distance, g("objectif") or None, g("date"),
            g("freq") or 4, reserved_codes={load_editor_code().value}, vma=g("vma") or None, methode=g("methode"),
            course=g("course") or "")
    except ValueError as exc:
        ui.notify(str(exc), "error")
        return
    st.session_state[f"sel_{distance}"] = student.id
    for k in ("email", "prenom", "date", "vma", "course"):
        st.session_state.pop(f"new_{k}_{distance}", None)
    if student.person in known:
        ui.saved(f"Nouveau programme « {student.race_name} » pour {student.display_name}, "
                 f"avec son code habituel : {student.code}")
    else:
        ui.saved(f"{student.display_name} ajouté(e). Code d'accès : {student.code}")
    if g("send") and load_email_config():
        _send_code(student.id)


def new_student_form(distance: str) -> None:
    dist = DISTANCES[distance]
    email_ready = load_email_config() is not None
    with st.form(f"new_student_{distance}", border=False, clear_on_submit=False):
        st.text_input("E-mail de l'élève", key=f"new_email_{distance}", placeholder="prenom.nom@exemple.fr",
                      help="E-mail d'un élève existant : crée un nouveau programme pour lui, avec le même code")
        c0a, c0b = st.columns(2)
        c0a.text_input("Prénom (facultatif)", key=f"new_prenom_{distance}")
        c0b.text_input("Nom de la course (facultatif)", key=f"new_course_{distance}",
                       placeholder=f"ex. {dist.label} de Lyon 2027")
        st.radio("Calcul des allures", list(METHODS), index=list(METHODS).index(dist.default_method),
                 format_func=METHODS.get, horizontal=True, key=f"new_methode_{distance}",
                 help="Tu peux renseigner les deux pour comparer, puis changer de méthode dans la fiche de l'élève")
        c1, c2 = st.columns(2)
        c1.text_input(f"Objectif {dist.label.lower()} (hh:mm:ss)", value=dist.default_objective,
                      key=f"new_objectif_{distance}", help="Facultatif avec la méthode VMA")
        c2.text_input("VMA (km/h)", key=f"new_vma_{distance}", placeholder=f"ex. {fr_number(VMA_DEFAULT)}",
                      help="Facultatif avec la méthode objectif de temps")
        c3, c4 = st.columns(2)
        c3.date_input("Date de course (facultatif)", value=None, format="DD/MM/YYYY", key=f"new_date_{distance}",
                      min_value=date.today())
        c4.radio("Séances par semaine", FREQUENCIES, index=1 if distance != "10k" else 0, horizontal=True,
                 format_func=FREQ_FMT.get, key=f"new_freq_{distance}")
        st.checkbox("Envoyer le code d'accès par e-mail à l'élève", value=email_ready, disabled=not email_ready,
                    key=f"new_send_{distance}",
                    help=None if email_ready else "Configure l'envoi d'e-mails dans l'onglet Réglages")
        st.caption(f"Le plan part du modèle de référence {dist.label.lower()} et des formules globales actuelles. "
                   "Un code d'accès personnel est créé automatiquement ; un élève déjà inscrit garde le sien et "
                   "retrouve tous ses programmes dans son espace.")
        st.form_submit_button("Créer le programme", type="primary", on_click=_create_student, args=(distance,))


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

    done = {s.id: historique.is_finished(s, suivi.load_suivi(store, s.id)) for s in students}
    students = sorted(students, key=lambda s: (done[s.id], s.display_name.lower(), s.date_course or date.max))
    ids = [s.id for s in students]
    by_id = {s.id: s for s in students}
    key = f"sel_{distance}"
    if st.session_state.get(key) not in ids:
        st.session_state[key] = ids[0]
    c_sel, c_new = st.columns([3, 1], vertical_alignment="bottom")
    c_sel.selectbox("Élève et programme", ids, key=key, format_func=lambda i: (
        f"{by_id[i].display_name} — {by_id[i].race_name}"
        + (f", {by_id[i].date_course:%d/%m/%Y}" if by_id[i].date_course else "")
        + (" (terminée)" if done[i] else "")))
    with c_new.popover("Nouvel élève", icon=":material/person_add:", width="stretch"):
        new_student_form(distance)

    student_panel(by_id[st.session_state[key]])

    with st.expander(f"Tous les programmes {label} ({len(students)})"):
        st.dataframe(pd.DataFrame([{
            "Élève": s.display_name, "Nom de la course": s.course, "Statut": "Terminée" if done[s.id] else "En cours",
            "E-mail": s.email, "Code": s.code, "Méthode": METHODS[s.methode],
            "Objectif": format_race_time(parse_objective(s.objectif, s.distance)) if s.objectif else "",
            "VMA": fr_number(s.vma) if s.vma is not None else "",
            "Date de course": s.date_course.strftime("%d/%m/%Y") if s.date_course else "",
            "Semaines": s.plan.n_weeks, "Code envoyé le": s.email_envoye_le, "Créé le": s.cree_le,
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
    sp = student_paces(s)

    def on_objective(k: str) -> None:
        raw = (st.session_state.get(k) or "").strip()
        try:
            value = normalize_objective(raw, s.distance) if raw else ""
        except ValueError as exc:
            ui.notify(str(exc), "error")
        else:
            if not value and s.methode == "temps":
                ui.notify("Cet élève est calculé sur son objectif : choisis d'abord la méthode VMA pour l'effacer.",
                          "error")
            elif not value and s.vma is None:
                ui.notify("Il faut au moins un objectif ou une VMA.", "error")
            else:
                _save_student(s.id, "Objectif enregistré", objectif=value)
        ui.bump(key)

    def on_vma(k: str) -> None:
        raw = (st.session_state.get(k) or "").strip()
        try:
            value = parse_vma(raw) if raw else None
        except ValueError as exc:
            ui.notify(str(exc), "error")
        else:
            if value is None and s.methode == "vma":
                ui.notify("Cet élève est calculé sur sa VMA : choisis d'abord la méthode objectif pour l'effacer.",
                          "error")
            else:
                _save_student(s.id, "VMA enregistrée", vma=value)
        ui.bump(key)

    def on_method(k: str) -> None:
        value = st.session_state.get(k)
        if value == "vma" and s.vma is None:
            ui.notify("Renseigne d'abord une VMA pour cet élève.", "error")
        elif value == "temps" and not s.objectif:
            ui.notify("Renseigne d'abord un objectif de temps pour cet élève.", "error")
        elif value in METHODS:
            _save_student(s.id, f"Méthode retenue : {METHODS[value].lower()}", methode=value)
        ui.bump(key)

    def on_date(k: str) -> None:
        _save_student(s.id, "Date de course enregistrée", date_course=st.session_state.get(k))
        ui.bump(key)

    def on_freq(k: str) -> None:
        value = st.session_state.get(k)
        if value in FREQUENCIES:
            _save_student(s.id, "Fréquence par défaut enregistrée", frequence_defaut=value)
        ui.bump(key)

    def on_course(k: str) -> None:
        value = (st.session_state.get(k) or "").strip()
        _save_student(s.id, "Nom de la course enregistré" if value else "Nom de la course effacé", course=value)
        ui.bump(key)

    def save_identity(prenom_key: str, email_key: str) -> None:
        current = profils.get_student(store, s.id)
        try:
            updated = profils.update_identity(store, current, st.session_state.get(email_key, ""),
                                              st.session_state.get(prenom_key, ""))
        except ValueError as exc:
            ui.notify(str(exc), "error")
            return
        if updated.email.lower() != current.email.lower():
            ui.saved(f"E-mail modifié : {updated.email}. Envoie-lui son code avec le bouton « Envoyer le code "
                     "par e-mail »." if load_email_config() else f"E-mail modifié : {updated.email}.")
        else:
            ui.saved("Élève modifié")
        ui.bump(key)

    def regenerate() -> None:
        updated = profils.regenerate_code(store, profils.get_student(store, s.id),
                                          reserved_codes={load_editor_code().value})
        ui.saved(f"Nouveau code : {updated.code} (pour tous ses programmes). L'ancien ne fonctionne plus.")
        if load_email_config():
            _send_code(updated.id)
        ui.bump(key)

    def delete() -> None:
        profils.delete_student(store, s.id)
        st.session_state.pop(f"sel_{s.distance}", None)
        ui.saved(f"Programme « {s.race_name} » de {s.display_name} supprimé")

    # ---- identité, code, e-mail
    with st.container(border=True, key=f"card-student-{s.id}"):
        c_who, c_code, c_act = st.columns([2.2, 2.2, 1], vertical_alignment="top")
        others = [o for o in profils.programs_of(store, s) if o.id != s.id]
        with c_who:
            st.markdown(f"### {s.display_name}")
            st.markdown(f"**{s.race_name}**" + (f" ({DISTANCES[s.distance].label})" if s.course else ""))
            st.caption(f"{s.email}, programme créé le {s.cree_le[:10]}")
            if others:
                st.caption("Autres programmes : " + ", ".join(
                    o.race_name + (f" du {o.date_course:%d/%m/%Y}" if o.date_course else "") for o in others))
            with st.popover("Modifier le prénom ou l'e-mail", icon=":material/edit:", key=f"idpop_{s.id}_{ver}"):
                pk, ek = f"idp_{s.id}_{ver}", f"ide_{s.id}_{ver}"
                with st.form(f"ident_{s.id}_{ver}", border=False):
                    st.text_input("Prénom", value=s.prenom, key=pk)
                    st.text_input("E-mail", value=s.email, key=ek)
                    st.form_submit_button("Enregistrer", type="primary", icon=":material/check:",
                                          on_click=save_identity, args=(pk, ek))
                st.caption("S'applique à tous les programmes de l'élève. Son code d'accès ne change pas.")
        with c_code:
            st.caption("Code d'accès")
            st.code(s.code, language=None)
            if s.email_envoye_le:
                st.caption(f"✉️ Envoyé par e-mail le {s.email_envoye_le[8:10]}/{s.email_envoye_le[5:7]} "
                           f"à {s.email_envoye_le[11:16]}")
            elif load_email_config():
                st.caption("✉️ Pas encore envoyé par e-mail")
            else:
                st.caption(f"✉️ À transmettre à l'élève avec le lien : {app_url() or 'adresse de l app'}")
            if load_email_config():
                st.button("Renvoyer le code par e-mail" if s.email_envoye_le else "Envoyer le code par e-mail",
                          icon=":material/mail:", key=f"mail_{s.id}_{ver}", on_click=_send_code, args=(s.id,))
        with c_act.popover("Actions", icon=":material/more_horiz:", width="stretch"):
            st.button("Générer un nouveau code", icon=":material/key:", on_click=regenerate,
                      key=f"regen_{s.id}_{ver}", width="stretch", help="L'ancien code ne fonctionnera plus")
            ok = st.checkbox("Confirmer la suppression", key=f"delok_{s.id}_{ver}")
            st.button("Supprimer ce programme" if others else "Supprimer l'élève", icon=":material/delete:",
                      type="primary", disabled=not ok, on_click=delete, key=f"del_{s.id}_{ver}", width="stretch",
                      help="Ses autres programmes sont gardés" if others else None)

        c_name, c_date, c_freq, c_info = st.columns([1.3, 1, 1.1, 1.7], vertical_alignment="bottom")
        k_name = f"course_{s.id}_{ver}"
        c_name.text_input("Nom de la course (facultatif)", value=s.course, key=k_name, on_change=on_course,
                          args=(k_name,), placeholder=f"ex. {DISTANCES[s.distance].label} de Lyon 2027")
        k_date = f"date_{s.id}_{ver}"
        c_date.date_input("Date de course (facultatif)", value=s.date_course, format="DD/MM/YYYY", key=k_date,
                          on_change=on_date, args=(k_date,))
        k_freq = f"freq_{s.id}_{ver}"
        c_freq.segmented_control("Séances par semaine (défaut)", FREQUENCIES, default=s.frequence_defaut,
                                 format_func=FREQ_FMT.get, key=k_freq, on_change=on_freq, args=(k_freq,),
                                 help="L'élève peut ensuite choisir 3 ou 4 séances dans son espace")
        with c_info:
            info_weeks(s)

    # ---- moteur double : objectif / VMA, comparaison, méthode retenue
    with st.container(border=True, key=f"card-method-{s.id}"):
        st.markdown("**Calcul des allures**")
        c_obj, c_vma, c_met = st.columns([1, 1, 1.4], vertical_alignment="bottom")
        k_obj = f"obj_{s.id}_{ver}"
        c_obj.text_input(f"Objectif {DISTANCES[s.distance].label.lower()}", value=s.objectif, key=k_obj,
                         on_change=on_objective, args=(k_obj,), placeholder="hh:mm:ss")
        k_vma = f"vma_{s.id}_{ver}"
        c_vma.text_input("VMA (km/h)", value=fr_number(s.vma) if s.vma is not None else "", key=k_vma,
                         on_change=on_vma, args=(k_vma,), placeholder=f"ex. {fr_number(VMA_DEFAULT)}")
        k_met = f"met_{s.id}_{ver}"
        c_met.segmented_control("Méthode retenue pour le plan", list(METHODS), default=s.methode,
                                format_func=METHODS.get, key=k_met, on_change=on_method, args=(k_met,),
                                required=True)
        rows = comparison(s)
        if rows:
            st.caption("Comparaison des deux méthodes (écart = VMA − objectif, en secondes par km ; "
                       "positif : la VMA donne une allure plus lente).")
            st.dataframe(pd.DataFrame([{
                "Allure": r["label"] + (" (course)" if r["is_anchor"] else ""), "Objectif de temps": r["temps"],
                "VMA": r["vma"], "Écart (s/km)": f"{r['ecart_s']:+d}",
            } for r in rows]), hide_index=True, width="stretch")
        else:
            st.caption("Renseigne aussi " + ("une VMA" if s.objectif else "un objectif") +
                       " pour comparer les deux méthodes.")

    basis = ("Allures sur la VMA" if sp.method == "vma" else "Allures sur l'objectif de temps") + \
            ("" if s.objectif else f" — temps de course estimé : {format_race_time(sp.race_seconds)}")
    render(paces_track(sp.paces, basis))

    t_plan, t_form, t_suivi, t_preview = st.tabs(["Plan de l'élève", "Formules de l'élève", "Suivi",
                                                  "Vue élève"], key=f"stabs_{s.id}")
    with t_plan:
        ui.plan_editor(
            s.plan, sp.paces, sp.race_seconds, s.date_course, key=f"plan_{s.id}",
            load=lambda: profils.get_student(store, s.id).plan,
            save=lambda plan, msg: _save_student(s.id, msg, plan=plan))
    with t_form:
        st.caption("Formules propres à cet élève : copiées des formules globales à sa création, modifiables ici "
                   "sans toucher aux autres élèves.")
        st.markdown("**Objectif de temps** : ratios entre allures")
        sample = parse_objective(s.objectif or DISTANCES[s.distance].default_objective, s.distance)
        ui.ratios_editor(s.ratios, s.distance, sample, key=f"ratios_{s.id}",
                         on_save=lambda r: _save_student(s.id, "Ratios de l'élève enregistrés", ratios=r))
        st.markdown("**VMA** : plages de % de VMA")
        ui.vma_pct_editor(s.vma_pct, s.distance, s.vma or VMA_DEFAULT, key=f"vmapct_{s.id}",
                          on_save=lambda p: _save_student(s.id, "% VMA de l'élève enregistrés", vma_pct=p))
        g_ratios = referentiel.load_global_ratios(store)[s.distance]
        g_vma = referentiel.load_global_vma_pct(store)[s.distance]
        if g_ratios != s.ratios or g_vma != s.vma_pct:
            def reapply() -> None:
                _save_student(s.id, "Formules globales appliquées", ratios=dict(g_ratios), vma_pct=dict(g_vma))
                ui.bump(f"ratios_{s.id}")
                ui.bump(f"vmapct_{s.id}")
            st.button("Reprendre les formules globales actuelles", icon=":material/sync:", key=f"rg_{s.id}_{ver}",
                      on_click=reapply)
    with t_suivi:
        supervision.render_student_suivi(s)
    with t_preview:
        eleve.render_space(s, readonly=True, prefix=f"pv{s.id}")


def info_weeks(s: Student) -> None:
    """Semaines restantes avant la course, à titre indicatif, avec ajustement en un clic."""
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
            cur = profils.get_student(ui.app_store(), s.id)
            _save_student(s.id, f"Plan ajusté à {left} semaines", plan=cur.plan.resize(left))
            ui.bump(f"plan_{s.id}")
        st.button(f"Adapter le plan à {left} semaines", key=f"fit_{s.id}_{s.plan.n_weeks}_{left}",
                  on_click=adjust, help="Ajoute ou retire des semaines au début ; la fin du plan ne bouge pas")


# =========================================================================== formules globales
def render_global_formulas(distance: str) -> None:
    store = ui.app_store()
    dist = DISTANCES[distance]
    st.markdown(f"#### Formules globales {dist.label.lower()}")
    st.caption("Elles s'appliquent aux élèves créés **à partir de maintenant** : les plans existants gardent leurs "
               "propres formules (modifiables dans la fiche de chaque élève).")
    t_time, t_vma = st.tabs(["Objectif de temps", "VMA"], key=f"gf_{distance}")
    with t_time:
        st.caption(f"L'objectif fixe l'allure **{dist.anchor}** ({dist.label.lower()} sur "
                   f"{fr_number(dist.km)} km) ; les autres allures en découlent avec ces ratios.")
        c_obj, _ = st.columns([1, 3])
        sample = c_obj.text_input("Objectif d'exemple", value=dist.default_objective, key=f"sample_{distance}")
        try:
            seconds = parse_objective(sample, distance)
        except ValueError as exc:
            st.error(str(exc))
        else:
            ratios = referentiel.load_global_ratios(store)[distance]

            def save(r: dict) -> None:
                referentiel.save_global_ratios(store, distance, r)
                ui.saved("Ratios globaux enregistrés (nouveaux élèves)")

            ui.ratios_editor(ratios, distance, seconds, key=f"gratios_{distance}", on_save=save)
            render(paces_track(compute_paces(seconds, distance, ratios)))
            if ratios != referentiel.DEFAULT_RATIOS:
                st.button("Revenir aux valeurs de l'Excel", icon=":material/restart_alt:", key=f"gr_reset_{distance}",
                          on_click=lambda: (save(dict(referentiel.DEFAULT_RATIOS)), ui.bump(f"gratios_{distance}")))
    with t_vma:
        st.caption("Chaque allure est une plage de % de VMA ; l'allure de référence est le bas de la plage, "
                   "comme dans le plan 10 km de référence.")
        c_v, _ = st.columns([1, 3])
        raw = c_v.text_input("VMA d'exemple (km/h)", value=fr_number(16.0), key=f"vsample_{distance}")
        try:
            vma = parse_vma(raw)
        except ValueError as exc:
            st.error(str(exc))
        else:
            pct = referentiel.load_global_vma_pct(store)[distance]

            def save_v(p: dict) -> None:
                referentiel.save_global_vma_pct(store, distance, p)
                ui.saved("% VMA globaux enregistrés (nouveaux élèves)")

            ui.vma_pct_editor(pct, distance, vma, key=f"gvma_{distance}", on_save=save_v)
            render(paces_track(compute_paces_vma(vma, distance, pct)))
            if pct != DEFAULT_VMA_PCT:
                st.button("Revenir aux valeurs de l'Excel", icon=":material/restart_alt:", key=f"gv_reset_{distance}",
                          on_click=lambda: (save_v(dict(DEFAULT_VMA_PCT)), ui.bump(f"gvma_{distance}")))


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
        st.write("Remplace ce modèle par la version d'origine (celle des fichiers Excel de référence).")
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


# =========================================================================== réglages
def render_settings() -> None:
    store = ui.app_store()
    c_mail, c_img = st.columns(2, gap="large")
    with c_mail:
        st.markdown("#### E-mails aux élèves")
        cfg = load_email_config()
        if cfg:
            st.success(f"Envoi automatique activé depuis **{cfg.user}** ({cfg.host}).", icon="✉️")
            st.caption(f"Lien mis dans les e-mails : {cfg.app_url or app_url() or '—'}")
            with st.form("mail_test", border=True):
                to = st.text_input("Envoyer un e-mail de test à", placeholder="ton.adresse@exemple.fr")
                if st.form_submit_button("Envoyer le test", icon=":material/send:") and to:
                    ok, msg = send_test_email(cfg, to.strip())
                    (st.success if ok else st.error)(msg)
        else:
            st.info("L'envoi automatique n'est pas configuré : les codes s'affichent dans la fiche de chaque élève "
                    "et tu les transmets toi-même. Pour l'activer, ajoute une section `[email]` dans les Secrets "
                    "(adresse Gmail + mot de passe d'application) : voir le README.", icon="✉️")
        st.markdown("#### Sauvegarde")
        if store.mirror:
            st.caption(f"Copie GitHub : `{store.mirror.repo}`"
                       + (f" — erreur : {store.mirror.last_error}" if store.mirror.last_error else " — OK"))
        else:
            st.caption("Fichiers du serveur uniquement (pas de copie GitHub configurée).")
        code = load_editor_code()
        st.caption("Code coach : " + {"secrets": "défini dans les Secrets", "env": "variable d'environnement",
                                      "demo": "code de démonstration (à changer)"}[code.source])

    with c_img:
        st.markdown("#### Visuels")
        st.caption("Par défaut, une illustration de piste d'athlétisme. Tu peux la remplacer par tes photos "
                   "(JPG ou PNG ; elles sont redimensionnées automatiquement).")
        for kind, label in (("accueil", "Photo de la page d'accueil"), ("banniere", "Photo des bandeaux")):
            with st.container(border=True, key=f"card-media-{kind}"):
                st.markdown(f"**{label}**")
                current = media_uri(store, kind)
                if current:
                    st.html(f"<img src='{current}' alt='' style='width:100%;max-height:150px;object-fit:cover;"
                            f"border-radius:8px'>")
                ver = ui.version(f"media_{kind}")
                up = st.file_uploader(label, type=["jpg", "jpeg", "png", "webp"], key=f"up_{kind}_{ver}",
                                      label_visibility="collapsed")
                c1, c2 = st.columns(2)
                if up is not None and c1.button("Utiliser cette photo", type="primary", key=f"use_{kind}_{ver}"):
                    try:
                        store.write(MEDIA_FILES[kind], prepare_photo(up.getvalue()))
                    except Exception as exc:  # image illisible
                        st.error(f"Image illisible : {exc}")
                    else:
                        ui.saved("Photo enregistrée")
                        ui.bump(f"media_{kind}")
                        st.rerun()
                if current and c2.button("Revenir à l'illustration", key=f"rm_{kind}_{ver}"):
                    store.delete(MEDIA_FILES[kind])
                    ui.saved("Illustration par défaut rétablie")
                    ui.bump(f"media_{kind}")
                    st.rerun()
