"""
Bouton « Répondre » du coach : un message court sous une séance ou un signalement de l'élève,
qu'il voit dans son planning (et par e-mail si le coach coche la case).
"""

from __future__ import annotations

import streamlit as st

from core import recap, reponses
from core.config import COMMENT_MAX
from core.emails import load_email_config
from ui import composants as ui


def _save(student, key: str, about: str, text_key: str, mail_key: str) -> None:
    store = ui.app_store()
    texte = (st.session_state.get(text_key) or "").strip()
    reponses.set_reply(store, student.id, key, texte)
    if not texte:
        ui.saved("Réponse effacée")
        return
    cfg = load_email_config()
    if st.session_state.get(mail_key) and cfg is not None and student.email:
        ok, msg = recap.send_now(recap.reply_email(student, about, texte, cfg, cfg.app_url), cfg)
        if ok:
            ui.saved(f"Réponse envoyée : {student.display_name} la voit dans son espace et l'a reçue par e-mail")
        else:
            ui.notify(f"Réponse enregistrée, mais l'e-mail n'est pas parti ({msg}).", "error")
        return
    ui.saved(f"Réponse enregistrée : {student.display_name} la verra dans son espace")


def reply_popover(student, key: str, about: str, widget_key: str, label: str = "Répondre") -> None:
    """Popover « Répondre » / « Modifier ma réponse ». `key` : séance ou « signal:<id> »."""
    current = reponses.load_coach(ui.app_store(), student.id).reply(key)
    cfg = load_email_config()
    tk, mk = f"{widget_key}_txt", f"{widget_key}_mail"
    with st.popover("Modifier ma réponse" if current else label, icon=":material/reply:", type="tertiary",
                    key=f"{widget_key}_pop"):
        st.caption(f"À propos de : {about}")
        with st.form(f"{widget_key}_form", border=False):
            st.text_area("Ta réponse à l'élève", value=current.texte if current else "", key=tk, max_chars=COMMENT_MAX,
                         height=110, placeholder="Bravo pour…, pense à…, on adapte la semaine prochaine…")
            st.checkbox("Le prévenir aussi par e-mail", key=mk, value=False,
                        disabled=cfg is None or not student.email,
                        help=None if cfg else "Envoi d'e-mails non configuré (onglet Réglages)")
            st.form_submit_button("Envoyer", type="primary", icon=":material/send:", on_click=_save,
                                  args=(student, key, about, tk, mk))
        if current:
            st.caption(f"Réponse du {current.le[8:10]}/{current.le[5:7]} à {current.le[11:16]}. "
                       "Vide le texte puis Envoyer pour l'effacer.")
