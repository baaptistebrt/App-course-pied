"""
Authentification par code d'accès.

* Éditeur (coach) : un code unique, lu dans `.streamlit/secrets.toml` ([access] editor_code),
  sinon dans la variable d'environnement PLAN_EDITOR_CODE, sinon code de démonstration.
* Élève : code individuel généré à la création de son profil (voir profils.py).
"""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass

from .profils import find_by_code
from .stockage import Store

ROLE_EDITOR = "editeur"
ROLE_STUDENT = "eleve"
DEMO_EDITOR_CODE = "coach-2026"


@dataclass(frozen=True)
class EditorCode:
    value: str
    source: str   # "secrets", "env" ou "demo"

    @property
    def is_demo(self) -> bool:
        return self.source == "demo"


def load_editor_code() -> EditorCode:
    try:
        import streamlit as st

        value = st.secrets.get("access", {}).get("editor_code")
        if value:
            return EditorCode(str(value), "secrets")
    except Exception:  # pas de secrets.toml
        pass
    if os.environ.get("PLAN_EDITOR_CODE"):
        return EditorCode(os.environ["PLAN_EDITOR_CODE"], "env")
    return EditorCode(DEMO_EDITOR_CODE, "demo")


def authenticate(code: str, store: Store, editor: EditorCode | None = None) -> tuple[str, str | None] | None:
    """(rôle, id élève) pour un code valide, sinon None. Comparaison à temps constant pour l'éditeur."""
    code = (code or "").strip()
    if not code:
        return None
    editor = editor or load_editor_code()
    if hmac.compare_digest(code.encode(), editor.value.encode()):
        return ROLE_EDITOR, None
    student = find_by_code(store, code)
    if student:
        return ROLE_STUDENT, student.id
    return None
