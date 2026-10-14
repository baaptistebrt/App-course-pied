"""
Supervision (coach, lecture seule) : séances réalisées, ressentis, temps de course et historique
des courses terminées de chaque élève.

Le coach voit ce que l'élève a coché ou saisi, sans pouvoir le modifier : ces données sont dans
le fichier de suivi de l'élève (core/suivi.py), que l'interface coach ne réécrit jamais.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from core import historique, profils, suivi
from core.calculs import format_race_time, fr_number
from core.config import DISTANCES, METHODS
from core.profils import Student
from ui import composants as ui
from ui.design import journal_html, recent_notes_html, render, week_cards


def student_state(s: Student) -> historique.ProgramState:
    """Plan tel que l'élève le voit (sa fréquence) + son suivi."""
    return historique.program_state(ui.app_store(), s)


def _fmt_day(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}" if len(iso) >= 10 else ""


def history_table(records: list, with_student: bool = True, key: str = "hist") -> None:
    """Tableau de l'historique + téléchargement Excel."""
    st.dataframe(historique.history_frame(records, with_student), hide_index=True, width="stretch")
    st.download_button("Télécharger l'historique (Excel)", historique.history_excel(records),
                       file_name=f"historique_courses_{date.today():%Y%m%d}.xlsx", icon=":material/download:",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       key=f"dl_{key}", on_click="ignore")


def render_student_suivi(s: Student) -> None:
    """Détail du suivi d'un programme (onglet « Suivi » de sa fiche) et historique de l'élève."""
    stt = student_state(s)
    pr = stt.progress
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Séances réalisées", f"{pr.done} / {pr.total}", border=True)
    c2.metric("Progression", f"{round(pr.ratio * 100)} %", border=True)
    c3.metric("Dernière séance cochée", _fmt_day(pr.last_date) or "—", border=True)
    c4.metric("Temps de course", pr.race_time or "—", pr.race_gap or None, delta_color="inverse",
              delta_arrow="off" if not pr.race_gap else "auto", border=True,
              help="Écart avec l'objectif (négatif = plus rapide)" if s.objectif else None)
    st.progress(pr.ratio)
    st.caption(f"Plan affiché pour {stt.frequency} séances par semaine. Les cases, ressentis et commentaires "
               "sont écrits par l'élève dans son espace ; tu les vois ici en lecture seule.")
    c_log, c_weeks = st.columns([2, 3], gap="large")
    with c_log:
        st.markdown(f"#### Carnet de {s.display_name}")
        with st.container(border=True, key=f"card-log-{s.id}"):
            render(journal_html(suivi.journal(stt.table, stt.suivi), pr.race_time))
    with c_weeks:
        st.markdown("#### Semaine par semaine")
        render(week_cards(stt.table, stt.sp.paces, status=stt.status, race_time=pr.race_time,
                          notes=stt.suivi.notes))
    store = ui.app_store()
    records = historique.race_history(store, profils.programs_of(store, s))
    st.markdown(f"#### Courses terminées de {s.display_name}")
    if records:
        history_table(records, with_student=False, key=f"hist_{s.id}")
    else:
        st.caption("Aucune course terminée pour l'instant : elle apparaîtra ici dès que l'élève aura saisi son "
                   "temps, ou après la date de la course.")


def render_overview() -> None:
    """Onglet « Supervision » : tous les élèves, toutes distances, et l'historique des courses."""
    store = ui.app_store()
    students = profils.list_students(store)
    if not students:
        st.html("<div class='empty'>Aucun élève pour l'instant : crée un profil dans l'onglet de sa distance.</div>")
        return
    states = [student_state(s) for s in students]
    running = [stt for stt in states if not stt.finished()]
    rows = []
    for stt in running:
        s, pr = stt.student, stt.progress
        ref = (format_race_time(stt.sp.race_seconds) if s.objectif else "") + \
              (f"{' / ' if s.objectif else ''}VMA {fr_number(s.vma)}" if s.vma is not None else "")
        rows.append({"Élève": s.display_name, "Course": s.race_name, "Distance": DISTANCES[s.distance].label,
                     "Date": s.date_course.strftime("%d/%m/%Y") if s.date_course else "",
                     "Méthode": METHODS[stt.sp.method], "Objectif / VMA": ref,
                     "Progression": round(pr.ratio * 100), "Réalisées": f"{pr.done}/{pr.total}",
                     "Dernière séance": _fmt_day(pr.last_date)})
    st.markdown("#### Programmes en cours")
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", column_config={
            "Progression": st.column_config.ProgressColumn("Progression", min_value=0, max_value=100,
                                                           format="%d %%"),
        })
    else:
        st.caption("Aucun programme en cours.")

    records = sorted((historique.race_record(stt) for stt in states if stt.finished()),
                     key=lambda r: (r.race_date or date.min, r.name), reverse=True)
    st.markdown("#### Historique des courses terminées")
    if records:
        st.caption("Une ligne par course : chrono, écart à l'objectif, part du plan réalisée, ressenti et récit de "
                   "l'élève. Le fichier Excel donne aussi les temps en secondes, pour tes calculs.")
        history_table(records, key="hist_all")
    else:
        st.caption("Les courses apparaissent ici dès que l'élève a saisi son temps, ou après la date de la course.")

    recent = []
    for stt in states:
        shown = {r["session_id"]: r for _, r in stt.table.iterrows()} if not stt.table.empty else {}
        recent += [(n.le, stt.student.display_name, shown[sid], n) for sid, n in stt.suivi.notes.items() if sid in shown]
    if recent:
        st.markdown("#### Derniers ressentis")
        with st.container(key="card-log-recent"):
            render(recent_notes_html(sorted(recent, key=lambda x: x[0], reverse=True)[:10]))

    by_id = {stt.student.id: stt.student for stt in states}
    choice = st.selectbox("Voir le détail d'un programme", [None, *by_id], key="sup_detail",
                          format_func=lambda i: "Choisir un élève…" if i is None else
                          f"{by_id[i].display_name} — {by_id[i].race_name}")
    if choice:
        render_student_suivi(by_id[choice])
