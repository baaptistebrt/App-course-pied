"""
Supervision (coach, lecture seule) : séances réalisées, ressentis, temps de course et historique
des courses terminées de chaque élève.

Le coach voit ce que l'élève a coché ou saisi, sans pouvoir le modifier : ces données sont dans
le fichier de suivi de l'élève (core/suivi.py), que l'interface coach ne réécrit jamais.
"""

from __future__ import annotations

import html
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from core import alertes, historique, profils, reponses, suivi
from core.calculs import format_race_time, fr_number
from core.config import DISTANCES
from core.plan import is_race_day
from core.profils import Student
from ui import composants as ui
from ui import planning, progression
from ui.coach_reply import reply_popover
from ui.design import journal_html, render, reply_html, session_title

e = html.escape


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
    if not sv.recap:
        items.append("Il a désactivé le récap du dimanche par e-mail.")
    lis = "".join(f"<li>{x}</li>" for x in items)
    return f"<div class='choices'><div class='ch-t'>Réglages de l'élève</div><ul>{lis}</ul></div>"


CHOICES_CSS = """<style>
.choices { background: #fff; border-radius: 12px; border-left: 6px solid var(--chrono); padding: 12px 18px 8px; }
.choices .ch-t { font-family: var(--cond); font-weight: 700; font-size: 1.2rem; color: var(--night); }
.choices ul { margin: 4px 0 0; padding-left: 18px; }
.choices li { margin: 2px 0 4px; color: var(--night); }
</style>"""


ALERTS_CSS = """<style>
[class*="st-key-"][class*="card-alert"] { background: #fff; border-radius: 12px; padding: 10px 16px 6px;
    border-left: 6px solid #3D5A80; }
[class*="st-key-"][class*="card-alert-rouge"] { border-left-color: #CF2E3F; }
[class*="st-key-"][class*="card-alert-orange"] { border-left-color: #E2611B; }
.al-t { font-weight: 700; color: var(--night); }
.al-w { color: var(--muted); font-size: .88rem; }
.al-d { color: var(--night); font-size: .93rem; margin-top: 2px; }
[class*="st-key-"][class*="card-note"] { background: #fff; border-radius: 12px; padding: 10px 16px 4px; }
</style>"""


@st.dialog("Suivi de l'élève", width="large")
def suivi_dialog(student_id: str) -> None:
    s = profils.get_student(ui.app_store(), student_id)
    if s is None:
        st.error("Ce programme n'existe plus.")
        return
    st.markdown(f"### {s.display_name} — {s.race_name}")
    render_student_suivi(s, where="dlg")


def render_alerts(items: list, where: str, show_name: bool = True) -> None:
    """Cartes « À surveiller » : (état du programme, alerte). Boutons Répondre, Voir le suivi, C'est vu."""
    store = ui.app_store()
    st.html(ALERTS_CSS)
    for n, (stt, a) in enumerate(items):
        s = stt.student

        def seen(sid: str = s.id, key: str = a.key) -> None:
            reponses.dismiss_alert(store, sid, key)
            ui.saved("Alerte marquée comme vue")

        with st.container(key=f"{where}-card-alert-{a.level}-{n}"):
            who = f"<b>{e(s.display_name)}</b> · {e(s.race_name)} · " if show_name else ""
            day = f"{a.when[8:10]}/{a.when[5:7]}" if len(a.when) >= 10 else ""
            render(f"<div class='al-t'>{a.icon} {e(a.title)}</div>"
                   f"<div class='al-w'>{who}{e(day)}</div>"
                   + (f"<div class='al-d'>{e(a.detail)}</div>" if a.detail else ""))
            current = reponses.load_coach(store, s.id).reply(a.reply_key) if a.reply_key else None
            if current is not None:
                render(reply_html(current, "Ta réponse"))
            with st.container(horizontal=True, gap="small"):
                if a.reply_key:
                    about = a.title if a.reply_key.startswith("signal:") else _about(stt, a.reply_key)
                    reply_popover(s, a.reply_key, about, f"{where}_al_{n}")
                if show_name and st.button("Voir le suivi", icon=":material/visibility:", type="tertiary",
                                                key=f"{where}_alv_{n}"):
                    suivi_dialog(s.id)
                st.button("C'est vu", icon=":material/done:", type="tertiary", key=f"{where}_als_{n}", on_click=seen,
                          help="L'alerte disparaît ; elle reviendra seulement s'il y a un nouveau signal")


def _about(stt, session_id: str) -> str:
    rows = stt.table[stt.table["session_id"] == session_id] if not stt.table.empty else stt.table
    if not len(rows):
        return "une séance"
    r = rows.iloc[0]
    return "ta course" if is_race_day(r["seance"]) else session_title(r)


def render_reports(s: Student, stt, where: str) -> None:
    """Signalements de l'élève (douleurs, absences, maladies), avec « Répondre »."""
    store = ui.app_store()
    coach = reponses.load_coach(store, s.id)
    reports = [r for r in stt.suivi.reports if not r.closed or r.closed[:10] >= (date.today() - timedelta(days=30)).isoformat()]
    if not reports:
        return
    st.markdown("##### Signalements de l'élève")
    st.html(ALERTS_CSS)
    for rep in reversed(reports):
        level = "rouge" if rep.kind == "douleur" and not rep.closed else ("orange" if not rep.closed else "info")
        with st.container(key=f"{where}-card-alert-{level}-rp-{rep.id}"):
            state = (f"clos le {rep.closed[8:10]}/{rep.closed[5:7]}" if rep.closed else
                     "à venir" if rep.upcoming() else "en cours")
            render(f"<div class='al-t'>{e(rep.label)} {e(rep.period)}</div><div class='al-w'>{e(state)}, signalé le "
                   f"{e(rep.created[8:10])}/{e(rep.created[5:7])}</div>"
                   + (f"<div class='al-d'>« {e(rep.comment)} »</div>" if rep.comment else "")
                   + reply_html(coach.reply(reponses.signal_key(rep.id)), "Ta réponse"))
            reply_popover(s, reponses.signal_key(rep.id), rep.label.lower(), f"{where}_rp_{rep.id}")


def render_student_suivi(s: Student, where: str = "fiche") -> None:
    """Détail du suivi d'un programme (onglet « Suivi » de sa fiche, Supervision) et historique de l'élève.
    `where` distingue les endroits où ce bloc est affiché (clés des widgets)."""
    stt = student_state(s)
    pr = stt.progress
    store = ui.app_store()
    coach = reponses.load_coach(store, s.id)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Séances réalisées", f"{pr.done} / {pr.total}", border=True)
    c2.metric("Progression", f"{round(pr.ratio * 100)} %", border=True)
    c3.metric("Dernière séance cochée", _fmt_day(pr.last_date) or "—", border=True)
    c4.metric("Temps de course", pr.race_time or "—", pr.race_gap or None, delta_color="inverse",
              delta_arrow="off" if not pr.race_gap else "auto", border=True,
              help="Écart avec l'objectif (négatif = plus rapide)" if s.objectif else None)
    st.progress(pr.ratio)
    st.html(CHOICES_CSS + choices_html(s, stt))
    alerts = [(stt, a) for a in alertes.program_alerts(stt, coach) if not a.key.startswith("signal:")]
    if alerts:
        st.markdown("##### À surveiller")
        render_alerts(alerts, f"{where}{s.id}", show_name=False)
    render_reports(s, stt, f"{where}{s.id}")
    st.caption("Les cases, ressentis, commentaires et réglages sont faits par l'élève dans son espace ; tu les vois "
               "ici. Réponds-lui sous une séance avec « Répondre » : il verra ta réponse dans son planning. L'onglet "
               "« Vue élève » montre exactement son écran.")
    t_week, t_log, t_charts, t_races = st.tabs(["Semaine par semaine", f"Carnet de {s.display_name}", "Graphiques",
                                                "Courses terminées"], key=f"{where}_sv_tabs_{s.id}")
    with t_week:
        planning.render_coach_week(s, stt, f"{where}sv{s.id}", coach)
    with t_log, st.container(key=f"{where}-card-log-{s.id}"):
        render(journal_html(suivi.journal(stt.table, stt.suivi), pr.race_time, coach.replies))
    with t_charts:
        progression.render_program(stt, f"{where}_sv_{s.id}")
    records = historique.race_history(store, profils.programs_of(store, s))
    with t_races:
        if records:
            history_table(records, with_student=False, key=f"{where}_hist_{s.id}")
        else:
            st.caption("Aucune course terminée pour l'instant : elle apparaîtra ici dès que l'élève aura saisi son "
                       "temps, ou après la date de la course.")


def render_watchlist(states: list) -> None:
    """« À surveiller » : tous les programmes en cours."""
    store = ui.app_store()
    items = []
    for stt in states:
        if stt.finished():
            continue
        items += [(stt, a) for a in alertes.program_alerts(stt, reponses.load_coach(store, stt.student.id))]
    items.sort(key=lambda x: (alertes.LEVELS[x[1].level], -int((x[1].when or "0000-00-00").replace("-", ""))))
    st.markdown("#### À surveiller")
    if not items:
        st.success("Rien à signaler : pas de douleur, de séance ratée en série ni d'élève inactif.", icon="👍")
        return
    st.caption("Les signaux à regarder, calculés à partir de ce que tes élèves ont coché et écrit. « C'est vu » "
               "retire une alerte (elle revient seulement s'il y a un nouveau signal).")
    shown = items[:8]
    render_alerts(shown, "sup")
    if len(items) > len(shown):
        with st.expander(f"Voir les {len(items) - len(shown)} autres"):
            render_alerts(items[len(shown):], "supx")


def render_recent_notes(states: list) -> None:
    """Derniers ressentis de tous les élèves, avec « Répondre »."""
    store = ui.app_store()
    recent = []
    for stt in states:
        shown = {r["session_id"]: r for _, r in stt.table.iterrows()} if not stt.table.empty else {}
        recent += [(n.le, stt, shown[sid], n) for sid, n in stt.suivi.notes.items() if sid in shown]
    if not recent:
        return
    st.markdown("#### Derniers ressentis")
    st.html(ALERTS_CSS)
    for n, (le, stt, r, note) in enumerate(sorted(recent, key=lambda x: x[0], reverse=True)[:10]):
        s = stt.student
        sid = r["session_id"]
        reply = reponses.load_coach(store, s.id).reply(sid)
        with st.container(key=f"sup-card-note-{n}"):
            quote = f"<div class='al-d' style='white-space:pre-wrap'>« {e(note.commentaire)} »</div>" if note.commentaire else ""
            render(f"<div class='al-t'>{e(s.display_name)} · {e(note.label) or '💬'}</div>"
                   f"<div class='al-w'>{e(le[8:10])}/{e(le[5:7])} · {e(session_title(r))}, semaine "
                   f"{int(r['position']) + 1} · {e(s.race_name)}</div>{quote}{reply_html(reply, 'Ta réponse')}")
            reply_popover(s, sid, _about(stt, sid), f"sup_note_{n}")


def render_overview() -> None:
    """Onglet « Supervision » : à surveiller, programmes en cours, historique, analyse, ressentis."""
    store = ui.app_store()
    students = profils.list_students(store)
    if not students:
        st.html("<div class='empty'>Aucun élève pour l'instant : crée un profil dans l'onglet de sa distance.</div>")
        return
    states = [student_state(s) for s in students]
    render_watchlist(states)
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
    render_recent_notes(states)

    by_id = {stt.student.id: stt.student for stt in states}
    choice = st.selectbox("Voir le détail d'un programme", [None, *by_id], key="sup_detail",
                          format_func=lambda i: "Choisir un élève…" if i is None else
                          f"{by_id[i].display_name} — {by_id[i].race_name}")
    if choice:
        render_student_suivi(by_id[choice], where="sup")


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
