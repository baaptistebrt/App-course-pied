"""
Espace élève.

En haut : le tour de piste (la préparation = un tour, le tracé jaune avance à chaque séance cochée),
le compte à rebours et les chiffres clés ; puis la demande de ressenti sur la dernière séance, et la
carte « Ta prochaine séance » avec son bouton « C'est fait ! » (ou la carte du jour J).
En dessous, les onglets : Mon Planning (semaine par semaine, séances par jour avec case à cocher,
ressenti et chrono du jour J, nombre de séances, export), Mes allures, Mon carnet, Mes courses,
Ma progression et Découverte de parcours.

`render_space` sert aussi au coach : onglet « Vue élève » de la fiche, en lecture seule.
Tout ce que l'élève modifie est enregistré dans SON fichier de suivi (core/suivi.py), jamais
dans le plan lui-même.
"""

from __future__ import annotations

import re
from datetime import date

import streamlit as st

from core import historique, profils, suivi
from core.config import COMMENT_MAX, DISTANCES, FEELINGS, FREQUENCIES
from core.exports import fr_date
from core.plan import is_race_day
from ui import composants as ui
from ui import planning, progression, supervision
from ui.parcours import render_student_routes
from ui.design import (bib, history_html, journal_html, lap_hero, next_session_html, paces_track, preview_note,
                       race_card_html, render, session_title)

FEEL_OPTIONS = list(FEELINGS)


def _md(text: str) -> str:
    """Échappe les caractères Markdown d'un libellé de case à cocher."""
    return re.sub(r"([\\`*_{}\[\]<>#+|~$])", r"\\\1", text)


def _feel(value: int) -> str:
    return " ".join(FEELINGS[value])


def _km(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".").replace(".", ",")


def _rel_day(d: date | None, today: date) -> str:
    if not isinstance(d, date):
        return ""
    delta = (d - today).days
    return {0: "aujourd'hui", 1: "demain", -1: "hier"}.get(delta, fr_date(d, weekday=True))


def _dist_name(distance: str) -> str:
    label = DISTANCES[distance].label
    return label if label[0].isdigit() else label.lower()


def render_student(student_id: str, on_logout) -> None:
    """Page de l'élève connecté avec son code."""
    store = ui.app_store()
    s = profils.get_student(store, student_id)
    if s is None:
        st.error("Ce profil n'existe plus. Demande un nouveau code à ton coach.")
        st.button("Retour à l'accueil", on_click=on_logout)
        return
    ui.show_notifications()
    st.html("<style>.block-container { max-width: 1000px; padding-top: 3rem; }"
            ".st-key-my_program [role='radiogroup'] { flex-wrap: wrap; overflow: visible; }</style>")
    programs = profils.programs_of(store, s)
    with st.container(horizontal=True, vertical_alignment="center", key="student-top"):
        if len(programs) > 1:
            by_id = {p.id: p for p in programs}
            finished = {p.id: historique.is_finished(p, suivi.load_suivi(store, p.id)) for p in programs}

            def switch() -> None:
                chosen = st.session_state.get("my_program")
                if chosen in by_id:            # uniquement les programmes de cet élève (même code)
                    st.session_state["student_id"] = chosen

            st.pills("Mes programmes", list(by_id), default=s.id, key="my_program", required=True,
                     on_change=switch, label_visibility="collapsed", width="stretch",
                     format_func=lambda i: by_id[i].race_name + (" ✓" if finished[i] else ""))
        else:
            st.space("stretch")
        st.button("Se déconnecter", icon=":material/logout:", on_click=on_logout, key="logout_student",
                  type="tertiary")
    render_space(s, readonly=False, prefix=f"me{s.id}")


def render_space(s, readonly: bool = False, prefix: str = "me") -> None:
    """Espace de l'élève `s`. readonly=True : aperçu du coach (rien n'est modifiable)."""
    store = ui.app_store()
    stt = supervision.student_state(s)
    sp, pr, sv, table = stt.sp, stt.progress, stt.suivi, stt.table
    today = date.today()

    def k(name: str) -> str:
        return f"{prefix}_{name}"

    # ------------------------------------------------------------------ actions de l'élève
    def week_done(position: int) -> bool:
        latest = suivi.load_suivi(store, s.id)
        week = table[table["position"] == position]
        return all(suivi.is_done(r, latest) for _, r in week.iterrows())

    def mark_done(session_id: str, position: int) -> None:
        suivi.set_done(store, s.id, session_id, True)
        if week_done(position):
            st.session_state[k("party")] = True
            ui.saved(f"Semaine {position + 1} bouclée, bravo !")
        else:
            ui.saved("Séance validée, bien joué !")

    def on_check(session_id: str, key: str, position: int) -> None:
        if st.session_state.get(key):
            mark_done(session_id, position)
        else:
            suivi.set_done(store, s.id, session_id, False)
            ui.saved("Séance décochée")

    def save_note(session_id: str, feel_key: str, text_key: str) -> None:
        suivi.set_note(store, s.id, session_id, st.session_state.get(feel_key), st.session_state.get(text_key, ""))
        ui.saved("Ressenti enregistré : ton coach le verra")

    def save_race(session_id: str, time_key: str, feel_key: str, text_key: str) -> None:
        typed = st.session_state.get(time_key, "")
        try:
            suivi.set_race_time(store, s.id, typed)
        except ValueError as exc:
            ui.notify(str(exc), "error")
            return
        suivi.set_note(store, s.id, session_id, st.session_state.get(feel_key), st.session_state.get(text_key, ""))
        if str(typed).strip():
            st.session_state[k("party")] = True
        ui.saved("Course enregistrée, bravo !")

    def later(session_id: str) -> None:
        st.session_state.setdefault(k("later"), set()).add(session_id)

    def on_freq(key: str) -> None:
        value = st.session_state.get(key)
        if value in FREQUENCIES:
            suivi.set_frequency(store, s.id, value)
            ui.saved(f"Plan affiché pour {value} séances par semaine")

    if not readonly and st.session_state.pop(k("party"), False):
        st.balloons()

    # ------------------------------------------------------------------ formulaires
    def note_form(session_id: str, form_key: str, submit: str = "Enregistrer", compact: bool = False) -> None:
        note = sv.note(session_id)
        fk, tk = f"{form_key}_feel", f"{form_key}_text"
        with st.form(form_key, border=False):
            st.pills("Comment tu l'as sentie ?", FEEL_OPTIONS, default=note.ressenti, format_func=_feel, key=fk,
                     disabled=readonly, label_visibility="collapsed" if compact else "visible")
            st.text_area("Un mot pour ton coach (facultatif)", value=note.commentaire, key=tk, max_chars=COMMENT_MAX,
                         height=72 if compact else 96, placeholder="Jambes, souffle, météo, douleurs…",
                         disabled=readonly)
            st.form_submit_button(submit, type="primary", icon=":material/check:", disabled=readonly,
                                  on_click=save_note, args=(session_id, fk, tk))

    def race_form(r, form_key: str) -> None:
        note = sv.note(r["session_id"])
        tk, fk, ck = f"{form_key}_time", f"{form_key}_feel", f"{form_key}_text"
        with st.form(form_key, border=False):
            st.text_input("Ton temps (hh:mm:ss)", value=sv.temps_realise, key=tk, placeholder="ex. 44:12 ou 3:28:45",
                          disabled=readonly)
            st.pills("Ton ressenti", FEEL_OPTIONS, default=note.ressenti, format_func=_feel, key=fk, disabled=readonly)
            st.text_area("Raconte ta course", value=note.commentaire, key=ck, max_chars=COMMENT_MAX, height=120,
                         placeholder="Ton départ, tes sensations, ce que tu retiens…", disabled=readonly)
            st.form_submit_button("Enregistrer ma course", type="primary", icon=":material/flag:", disabled=readonly,
                                  on_click=save_race, args=(r["session_id"], tk, fk, ck))

    # ------------------------------------------------------------------ bandeau : tour de piste
    dist_name = _dist_name(s.distance)
    dated = not table.empty and any(isinstance(d, date) for d in table["debut"])
    positions = sorted(table["position"].unique()) if not table.empty else []
    n_weeks = len(positions) or s.plan.n_weeks
    current = None
    if dated:
        for pos in positions:
            w = table[table["position"] == pos].iloc[0]
            if w["debut"] <= today <= w["fin"]:
                current = pos
    first_start = table["debut"].min() if dated else None
    days_left = (s.date_course - today).days if s.date_course else None
    pct = round(pr.ratio * 100)
    hello = f"Salut {s.prenom}," if s.prenom else "Salut,"
    race_pace = sp.paces[DISTANCES[s.distance].anchor].pace_str

    if pr.race_time:
        title, text = f"{DISTANCES[s.distance].label} bouclé en {pr.race_time}", \
            "Bravo ! Raconte ta course à ton coach dans la carte ci-dessous."
    elif days_left == 0:
        title, text = "C'est le jour J", f"Ton allure de course : {race_pace} au km. Profite de chaque kilomètre."
    elif days_left is not None and days_left < 0:
        title, text = "Alors, cette course ?", "Note ton chrono et ton ressenti dans la carte ci-dessous."
    elif dated and first_start and today < first_start:
        title = f"Départ le {fr_date(first_start, weekday=True)}"
        text = f"{n_weeks} semaines pour préparer ton {dist_name}. Ta première séance est juste en dessous."
    elif current is not None and current == positions[-1]:
        title, text = "Semaine de course", "Le plus dur est fait. Reste léger et fais-toi confiance."
    else:
        plural = "s" if pr.done > 1 else ""
        if current is not None:
            title = f"Semaine {current + 1} sur {n_weeks}"
            text = (f"{pr.done} séance{plural} sur {pr.total} : le point jaune avance à chaque séance cochée, "
                    "jusqu'à la ligne d'arrivée." if pr.done else
                    "Coche ta première séance : le point jaune avancera à chaque séance, jusqu'à la ligne d'arrivée.")
        elif pr.done:
            title = f"{pr.done} séance{plural} faite{plural} sur {pr.total}"
            text = "Le point jaune avance à chaque séance cochée, jusqu'à la ligne d'arrivée."
        else:
            title = "C'est parti !"
            text = (f"{n_weeks} semaines pour préparer ton {dist_name}. Le point jaune avancera à chaque séance "
                    "cochée, jusqu'à la ligne d'arrivée.")
    # Centre du tour de piste : la progression (le compte à rebours est sur le dossard)
    if pr.race_time:
        big, small = "Arrivée", "tour bouclé"
    elif days_left == 0:
        big, small = "Jour J", "dernière ligne droite"
    else:
        big, small = f"{pct} %", "du plan réalisé"
    stats = [("km courus", _km(pr.km_done), False), ("séances faites", f"{pr.done}/{pr.total}", False)]
    if current is not None:
        week = table[table["position"] == current]
        n_week_done = sum(1 for _, r in week.iterrows() if suivi.is_done(r, sv))
        stats.append(("cette semaine", f"{n_week_done}/{len(week)}", True))
    p = 1.0 if pr.race_time else pr.ratio
    p_from = st.session_state.get(k("lap"), 0.0)
    st.session_state[k("lap")] = p
    if readonly:
        render(preview_note(s.display_name))
    bib_html = bib(s.display_name, s.distance, sp.race_seconds, sp.race_is_estimate, s.date_course, n_weeks,
                   pr.race_time, s.course)
    render(lap_hero(bib_html=bib_html, hello=hello, title=title, text=text, big=big, small=small, stats=stats, p=p,
                    n_weeks=n_weeks, p_from=p_from, label=f"Tour de piste : {pct} % des séances faites"))

    if table.empty:
        render("<div class='empty'>Ton plan ne contient encore aucune séance : ton coach le prépare.</div>")
        return

    # ------------------------------------------------------------------ ressenti de la dernière séance
    pending = suivi.pending_feedback(table, sv, today)
    if pending is not None and pending["session_id"] not in st.session_state.get(k("later"), set()):
        sid = pending["session_id"]
        try:
            rel = _rel_day(date.fromisoformat(sv.done[sid]), today)
        except ValueError:
            rel = ""
        when = {"aujourd'hui": "d'aujourd'hui", "hier": "d'hier"}.get(rel, f"du {rel}" if rel else "")
        with st.container(key=f"{prefix}-card-feel"):
            render(f"<div class='ask'>Ta séance {when} : comment tu l'as sentie ?"
                   f"<small>{session_title(pending)}</small></div>")
            note_form(sid, k(f"pf_{sid}"), "Enregistrer mon ressenti", compact=True)
            st.button("Plus tard", type="tertiary", key=k(f"later_{sid}"), on_click=later, args=(sid,),
                      disabled=readonly)

    # ------------------------------------------------------------------ prochaine séance / jour J
    race_rows = table[[is_race_day(x) for x in table["seance"]]]
    race_row = race_rows.iloc[0] if len(race_rows) else None
    nxt = suivi.next_session(table, sv, today)
    race_now = race_row is not None and (
        bool(sv.temps_realise) or nxt is None or nxt["session_id"] == race_row["session_id"]
        or (s.date_course is not None and today >= s.date_course))
    if race_now:
        with st.container(key=f"{prefix}-card-race"):
            rd = race_row["date"] if isinstance(race_row["date"], date) else None
            when = f"Jour J, {fr_date(rd, True, True)}" if rd else "Jour J"
            render(race_card_html(race_row, sp.paces, when, pr.race_time))
            race_form(race_row, k("race_top"))
    elif nxt is not None:
        sub = table[table["position"] == nxt["position"]]
        idx = list(sub["session_id"]).index(nxt["session_id"]) + 1
        rel = _rel_day(nxt["date"], today)
        when = f"Ta prochaine séance : {rel}" if rel else \
            f"Ta prochaine séance : semaine {int(nxt['position']) + 1}, séance {idx} sur {len(sub)}"
        with st.container(key=f"{prefix}-card-next"):
            render(next_session_html(nxt, sp.paces, when))
            st.button("C'est fait !", type="primary", icon=":material/check:", key=k(f"done_{nxt['session_id']}"),
                      on_click=mark_done, args=(nxt["session_id"], int(nxt["position"])), disabled=readonly,
                      width="stretch")
    else:
        with st.container(key=f"{prefix}-card-next"):
            render("<div class='allset'>Toutes tes séances sont faites. Bravo !</div>")

    # ------------------------------------------------------------------ boutons d'une séance (Mon Planning)
    def check_box(r) -> None:
        sid = r["session_id"]
        ck = k(f"chk_{sid}")
        callback = {} if readonly else {"on_change": on_check, "args": (sid, ck, int(r["position"]))}
        st.checkbox(f"**{_md(session_title(r))}**", value=sid in sv.done, key=ck, width="stretch", wrap=True,
                    disabled=readonly, **callback)

    def feel_button(r) -> None:
        sid = r["session_id"]
        note = sv.note(sid)
        label = f"{note.emoji} Ressenti" if note.emoji else ("💬 Ressenti" if note.commentaire else "Ressenti")
        with st.popover(label, type="tertiary", key=k(f"pop_{sid}"), wrap=False,
                        icon=None if (note.emoji or note.commentaire) else ":material/add_comment:"):
            note_form(sid, k(f"nf_{sid}"))

    def race_button(r) -> None:
        sid = r["session_id"]
        with st.popover("Mon chrono", icon=":material/flag:", key=k(f"pop_{sid}"), wrap=False):
            race_form(r, k(f"race_{sid}"))

    # ------------------------------------------------------------------ onglets
    t_planning, t_paces, t_log, t_races, t_prog, t_routes = st.tabs(
        ["Mon Planning", "Mes allures", "Mon carnet", "Mes courses", "Ma progression", "Découverte de parcours"],
        key=k("tabs"))

    with t_planning:
        done_ids = {sid for sid, ok in stt.status.items() if ok}
        with st.container(horizontal=True, vertical_alignment="bottom", key=f"{prefix}-plan-tools"):
            freq_key = k(f"freq{stt.frequency}")      # clé liée à la valeur : suit un changement fait par le coach
            st.segmented_control("Séances par semaine", FREQUENCIES, default=stt.frequency, key=freq_key,
                                 format_func=lambda n: f"{n} séances", on_change=on_freq, args=(freq_key,),
                                 required=True,
                                 disabled=readonly,
                                 help="Change le nombre de séances de toutes tes semaines. Tes allures ne changent "
                                      "pas. Pour une seule semaine, utilise « Modifier ma semaine » en bas.")
            st.space("stretch")
            with st.popover("Imprimer ou exporter", icon=":material/print:", key=k("exports")):
                ui.exports_bar(s, table, sp, stt.frequency, key=prefix, done=done_ids, race_time=pr.race_time,
                               notes=sv.notes, vertical=True)
        planning.render_planning(s, stt, readonly, prefix,
                                 planning.Controls(check=check_box, feel=feel_button, race=race_button))

    with t_paces:
        render(paces_track(sp.paces, ui.basis_text(sp, s)))
        st.caption("À droite de chaque allure : le temps qu'elle donne sur sa distance de référence. "
                   "Les pastilles de couleur des séances renvoient à ces allures.")

    with t_log, st.container(key=f"{prefix}-card-log"):
        render(journal_html(suivi.journal(table, sv), pr.race_time))

    records = historique.race_history(store, profils.programs_of(store, s))
    with t_races, st.container(key=f"{prefix}-card-log-races"):
        render(history_html(records))

    with t_prog:
        progression.render_program(stt, f"{prefix}_prog")
        st.markdown("##### Tes courses")
        progression.render_races(records, f"{prefix}_races")

    with t_routes:
        render_student_routes(prefix)
