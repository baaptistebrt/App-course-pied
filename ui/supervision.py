"""
Supervision (coach, lecture seule) : séances réalisées, ressentis, temps de course et historique
des courses terminées de chaque élève.

Le coach voit ce que l'élève a coché ou saisi, sans pouvoir le modifier : ces données sont dans
le fichier de suivi de l'élève (core/suivi.py), que l'interface coach ne réécrit jamais.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from core import historique, profils, suivi
from core.calculs import format_race_time, fr_number
from core.config import DISTANCES
from core.profils import Student
from ui import composants as ui
from ui import planning, progression
from ui.design import journal_html, recent_notes_html, render


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


def frequency_text(s: Student, stt: historique.ProgramState, short: bool = False) -> str:
    """Séances par semaine affichées à l'élève, ex. « 2 (élève), 1 sem. modifiée » ou « 4 »."""
    chosen = stt.suivi.frequence or s.frequence_eleve
    out = str(stt.frequency)
    if chosen and chosen != s.frequence_defaut:
        out += " (élève)" if short else " (choix de l'élève)"
    n = len(stt.suivi.semaines)
    if n:
        out += f", {n} sem. modifiée{'s' if n > 1 else ''}"
    return out


def choices_html(s: Student, stt: historique.ProgramState) -> str:
    """Ce que l'élève a réglé lui-même dans son espace : séances par semaine, semaines modifiées."""
    sv = stt.suivi
    chosen = sv.frequence or s.frequence_eleve
    items = []
    if chosen and chosen != s.frequence_defaut:
        items.append(f"<b>{chosen} séances par semaine</b>, choisi par l'élève (ton réglage : {s.frequence_defaut}). "
                     "C'est ce qu'il voit dans son planning.")
    else:
        items.append(f"<b>{stt.frequency} séances par semaine</b>"
                     + (", confirmé par l'élève." if chosen else ", ton réglage (l'élève ne l'a pas changé)."))
    weeks = s.plan.weeks.set_index("week_id") if not s.plan.weeks.empty else None
    modified = []
    for week_id, n in sv.semaines.items():
        if weeks is None or week_id not in weeks.index:
            continue
        pos = int(weeks.loc[week_id, "position"])
        start = s.plan.week_start(pos, s.date_course)
        when = f" ({start:%d/%m}–{start + timedelta(days=6):%d/%m})" if start else ""
        natural = planning.natural_count(planning._plan_week_sessions(s, week_id), stt.frequency)
        modified.append((pos, f"Semaine {pos + 1}{when} : <b>{n} séances</b> au lieu de {natural}"))
    if modified:
        items.append("Semaines modifiées par l'élève : " + " ; ".join(t for _, t in sorted(modified)) + ".")
    else:
        items.append("Aucune semaine modifiée par l'élève.")
    if sv.maj_le:
        items.append(f"Dernière action de l'élève : le {sv.maj_le[8:10]}/{sv.maj_le[5:7]} à {sv.maj_le[11:16]}.")
    lis = "".join(f"<li>{x}</li>" for x in items)
    return f"<div class='choices'><div class='ch-t'>Réglages de l'élève</div><ul>{lis}</ul></div>"


CHOICES_CSS = """<style>
.choices { background: #fff; border-radius: 12px; border-left: 6px solid var(--chrono); padding: 12px 18px 8px; }
.choices .ch-t { font-family: var(--cond); font-weight: 700; font-size: 1.2rem; color: var(--night); }
.choices ul { margin: 4px 0 0; padding-left: 18px; }
.choices li { margin: 2px 0 4px; color: var(--night); }
</style>"""


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
    st.html(CHOICES_CSS + choices_html(s, stt))
    st.caption("Les cases, ressentis, commentaires et réglages sont faits par l'élève dans son espace ; tu les vois "
               "ici en lecture seule. L'onglet « Vue élève » montre exactement son écran.")
    t_week, t_log, t_charts, t_races = st.tabs(["Semaine par semaine", f"Carnet de {s.display_name}", "Graphiques",
                                                "Courses terminées"], key=f"sv_tabs_{s.id}")
    with t_week:
        planning.render_coach_week(s, stt, f"sv{s.id}")
    with t_log, st.container(key=f"card-log-{s.id}"):
        render(journal_html(suivi.journal(stt.table, stt.suivi), pr.race_time))
    with t_charts:
        progression.render_program(stt, f"sv_{s.id}")
    store = ui.app_store()
    records = historique.race_history(store, profils.programs_of(store, s))
    with t_races:
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
                     "Méthode": "VMA" if stt.sp.method == "vma" else "Objectif", "Objectif / VMA": ref,
                     "Séances/sem.": frequency_text(s, stt, short=True),
                     "Progression": round(pr.ratio * 100), "Réalisées": f"{pr.done}/{pr.total}",
                     "Dernière séance": _fmt_day(pr.last_date)})
    st.markdown("#### Programmes en cours")
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", column_config={
            "Progression": st.column_config.ProgressColumn("Progression", min_value=0, max_value=100,
                                                           format="%d %%"),
            "Élève": st.column_config.TextColumn(width="small"),
            "Méthode": st.column_config.TextColumn(width="small", help="Méthode de calcul des allures retenue"),
            "Date": st.column_config.TextColumn(width="small"),
            "Réalisées": st.column_config.TextColumn(width="small"),
            "Dernière séance": st.column_config.TextColumn("Dernière", width="small",
                                                           help="Dernière séance cochée"),
            "Séances/sem.": st.column_config.TextColumn(help="Séances par semaine vues par l'élève ; « (élève) » : "
                                                             "il a changé ton réglage ; semaines qu'il a modifiées"),
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

    render_progress_analysis(states)

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


def render_progress_analysis(states: list) -> None:
    """Analyse de progression (Plotly) : assiduité de tous les programmes en cours, puis vue consolidée
    d'un élève (tous ses programmes : séances, volume, ressentis, courses)."""
    st.markdown("#### Analyse de progression")
    running = [stt for stt in states if not stt.finished()]
    fig = progression.completion_overview(running)
    if fig is not None:
        with st.container(key="card-chart-overview"):
            st.plotly_chart(fig, config=progression.CONFIG, theme=None, key="ch_overview")
    people: dict[str, list] = {}
    for stt in states:
        people.setdefault(stt.student.person, []).append(stt.student)
    names = {k: v[0].display_name for k, v in people.items()}
    person = st.selectbox("Progression d'un élève", [None, *sorted(people, key=lambda k: names[k].lower())],
                          key="sup_person", format_func=lambda k: "Choisir un élève…" if k is None else
                          f"{names[k]} ({len(people[k])} programme{'s' if len(people[k]) > 1 else ''})")
    if person:
        progs = sorted(people[person], key=lambda p: (p.date_course or date.max, p.cree_le))
        progression.render_person(ui.app_store(), progs, f"sup_{person}")
