"""
Supervision (coach, lecture seule) : séances réalisées et temps de course de chaque élève.

Le coach voit ce que l'élève a coché ou saisi, sans pouvoir le modifier : ces données sont dans
le fichier de suivi de l'élève (core/suivi.py), que l'interface coach ne réécrit jamais.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from core import profils, suivi
from core.calculs import format_race_time, fr_number
from core.config import DISTANCES, METHODS
from core.moteur import StudentPaces, student_paces
from core.plan import full_plan_table
from core.profils import Student
from ui import composants as ui
from ui.design import render, week_cards


@dataclass
class StudentState:
    student: Student
    sp: StudentPaces
    frequency: int
    table: pd.DataFrame
    suivi: suivi.Suivi
    progress: suivi.Progress

    @property
    def status(self) -> dict[str, bool]:
        return {r["session_id"]: suivi.is_done(r, self.suivi) for _, r in self.table.iterrows()} if not self.table.empty else {}


def student_state(s: Student) -> StudentState:
    """Plan tel que l'élève le voit (sa fréquence) + son suivi."""
    store = ui.app_store()
    sp = student_paces(s)
    sv = suivi.load_suivi(store, s.id)
    freq = suivi.effective_frequency(s, sv)
    table = full_plan_table(s.plan, sp.paces, sp.race_seconds, s.date_course, freq, hide_empty=True)
    objective = sp.race_seconds if s.objectif else None
    return StudentState(s, sp, freq, table, sv, suivi.progress(table, sv, objective))


def _fmt_day(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}" if len(iso) >= 10 else ""


def render_student_suivi(s: Student) -> None:
    """Détail du suivi d'un élève (onglet « Suivi » de sa fiche)."""
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
    st.caption(f"Plan affiché pour {stt.frequency} séances par semaine. Les cases sont cochées par l'élève "
               "dans son espace ; tu les vois ici en lecture seule.")
    render(week_cards(stt.table, stt.sp.paces, status=stt.status, race_time=pr.race_time))


def render_overview() -> None:
    """Onglet « Supervision » : tous les élèves, toutes distances."""
    store = ui.app_store()
    students = profils.list_students(store)
    if not students:
        st.html("<div class='empty'>Aucun élève pour l'instant : crée un profil dans l'onglet de sa distance.</div>")
        return
    states = [student_state(s) for s in students]
    rows = []
    for stt in states:
        s, pr = stt.student, stt.progress
        ref = (format_race_time(stt.sp.race_seconds) if s.objectif else "") + \
              (f"{' / ' if s.objectif else ''}VMA {fr_number(s.vma)}" if s.vma is not None else "")
        rows.append({"id": s.id, "Élève": s.display_name, "Distance": DISTANCES[s.distance].label,
                     "Méthode": METHODS[stt.sp.method], "Objectif / VMA": ref,
                     "Course": s.date_course.strftime("%d/%m/%Y") if s.date_course else "",
                     "Progression": round(pr.ratio * 100), "Réalisées": f"{pr.done}/{pr.total}",
                     "Dernière séance": _fmt_day(pr.last_date), "Temps réalisé": pr.race_time, "Écart": pr.race_gap})
    df = pd.DataFrame(rows)
    st.markdown("#### Suivi de tous les élèves")
    st.dataframe(df.drop(columns=["id"]), hide_index=True, width="stretch", column_config={
        "Progression": st.column_config.ProgressColumn("Progression", min_value=0, max_value=100, format="%d %%"),
    })
    by_id = {stt.student.id: stt.student for stt in states}
    choice = st.selectbox("Voir le détail d'un élève", [None, *by_id], key="sup_detail",
                          format_func=lambda i: "Choisir un élève…" if i is None else
                          f"{by_id[i].display_name} — {DISTANCES[by_id[i].distance].label}")
    if choice:
        render_student_suivi(by_id[choice])
