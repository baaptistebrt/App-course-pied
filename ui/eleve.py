"""
Interface élève : son dossard, ses allures, son plan (lecture seule sur les allures et la structure),
une case « séance réalisée » par séance, le temps réalisé le jour de la course, le choix de
3 ou 4 séances par semaine, l'export et l'impression.

Tout ce que l'élève modifie est enregistré dans SON fichier de suivi (core/suivi.py), jamais
dans le plan lui-même.
"""

from __future__ import annotations

import re

import streamlit as st

from core import profils, suivi
from core.config import FREQUENCIES
from core.plan import is_race_day
from ui import composants as ui
from ui import supervision
from ui.design import pills, render, session_meta, session_title, student_hero, week_header


def _md(text: str) -> str:
    """Échappe les caractères Markdown du libellé d'une case à cocher."""
    return re.sub(r"([\\`*_{}\[\]<>#+|~])", r"\\\1", text)


def render_student(student_id: str, on_logout) -> None:
    store = ui.app_store()
    s = profils.get_student(store, student_id)
    if s is None:
        st.error("Ce profil n'existe plus. Demande un nouveau code à ton coach.")
        st.button("Retour à l'accueil", on_click=on_logout)
        return
    ui.show_notifications()
    stt = supervision.student_state(s)
    sp, pr, sv = stt.sp, stt.progress, stt.suivi

    with st.container(horizontal=True, horizontal_alignment="right"):
        st.button("Se déconnecter", icon=":material/logout:", on_click=on_logout, key="logout_student",
                  type="tertiary")
    render(student_hero(s.display_name, s.distance, sp.race_seconds, sp.race_is_estimate, s.date_course,
                        s.plan.n_weeks, sp.paces, ui.basis_text(sp, s), pr.race_time))

    # ---- actions de l'élève (enregistrées dans son fichier de suivi)
    def on_freq() -> None:
        value = st.session_state.get("my_freq")
        if value in FREQUENCIES:
            suivi.set_frequency(store, student_id, value)
            ui.saved(f"Plan affiché pour {value} séances par semaine")

    def on_check(session_id: str, key: str) -> None:
        done = bool(st.session_state.get(key))
        suivi.set_done(store, student_id, session_id, done)
        ui.saved("Séance réalisée, bravo !" if done else "Séance décochée")

    def on_race_time(key: str) -> None:
        try:
            suivi.set_race_time(store, student_id, st.session_state.get(key, ""))
        except ValueError as exc:
            ui.notify(str(exc), "error")
        else:
            ui.saved("Temps de course enregistré" if st.session_state.get(key) else "Temps de course effacé")

    done_ids = {k for k, v in stt.status.items() if v}
    with st.container(border=True, key="card-toolbar"):
        c_freq, c_exp = st.columns([1, 2], vertical_alignment="center")
        c_freq.segmented_control("Séances par semaine", FREQUENCIES, default=stt.frequency, key="my_freq",
                                 format_func=lambda n: f"{n} séances", on_change=on_freq, required=True,
                                 help="Change le nombre de séances affichées. Tes allures ne changent pas.")
        with c_exp:
            ui.exports_bar(s, stt.table, sp, stt.frequency, key="me", done=done_ids, race_time=pr.race_time)
        st.progress(pr.ratio, text=f"{pr.done} séance{'s' if pr.done > 1 else ''} réalisée{'s' if pr.done > 1 else ''} "
                                   f"sur {pr.total}")

    if stt.table.empty:
        render("<div class='empty'>Ton plan ne contient encore aucune séance : ton coach le prépare.</div>")
        return

    # ---- semaines : une case à cocher par séance, temps réalisé le jour J
    for position in sorted(stt.table["position"].unique()):
        sub = stt.table[stt.table["position"] == position]
        head, state = week_header(sub, position)
        wid = sub["week_id"].iloc[0]
        with st.container(key=f"card-wk{'cur' if state == 'current' else 'past' if state == 'past' else ''}-{wid}"):
            render(head)
            for _, r in sub.iterrows():
                sid = r["session_id"]
                if is_race_day(r["seance"]):
                    render(f"<div class='racebox'><div class='what'>🏁 {r['seance']} — {session_title(r)}</div>"
                           f"<div class='sesmeta' style='margin:4px 0 0;padding:0;border:0'>"
                           f"{session_meta(r, race=True)}{pills(r['allure'], sp.paces)}</div></div>")
                    k = f"race_{s.id}"
                    st.text_input("Temps réalisé (hh:mm:ss)", value=sv.temps_realise, key=k,
                                  placeholder="à remplir après la course, ex. 3:28:45",
                                  on_change=on_race_time, args=(k,))
                    continue
                k = f"chk_{sid}"
                st.checkbox(f"**{_md(str(r['seance']))}** — {_md(session_title(r))}", value=sid in sv.done,
                            key=k, on_change=on_check, args=(sid, k))
                render(f"<div class='sesmeta'>{session_meta(r)}{pills(r['allure'], sp.paces)}</div>")
