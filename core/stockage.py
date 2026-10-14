"""
Stockage des données : fichiers Excel locaux + copie optionnelle sur GitHub.

Organisation du dossier `data/` :
    data/formules.xlsx            ratios globaux par distance
    data/modeles/<distance>.xlsx  modèle de référence de chaque distance
    data/eleves/<id>.xlsx         un fichier par élève (profil, formules, plan) — écrit par le coach
    data/suivi/<id>.xlsx          suivi de l'élève (séances réalisées, temps) — écrit par l'élève
    data/medias/                  images de la page d'accueil et des bannières (facultatif)

Écriture atomique (fichier temporaire puis remplacement) : un fichier n'est jamais à moitié écrit.

Copie GitHub (facultative) : sur un hébergement dont le disque n'est pas permanent
(Streamlit Community Cloud), chaque enregistrement est aussi envoyé dans un dépôt GitHub
privé, et ce dépôt est rechargé au démarrage. Activée si les secrets contiennent :
    [github]
    token = "github_pat_..."
    repo = "utilisateur/coach-running-data"
    branch = "main"          # facultatif
"""

from __future__ import annotations

import base64
import io
import os
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

APP_DIR = Path(__file__).resolve().parent.parent
# Fichiers copiés depuis GitHub au démarrage : classeurs et images (page d'accueil, bannière).
DATA_SUFFIXES = (".xlsx", ".jpg", ".jpeg", ".png", ".webp")
DEFAULT_DATA_DIR = Path(os.environ.get("PLAN_DATA_DIR", APP_DIR / "data"))


# ----------------------------------------------------------------------------
# Classeurs Excel <-> DataFrames
# ----------------------------------------------------------------------------
def write_workbook(sheets: dict[str, pd.DataFrame]) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)
            ws = writer.sheets[name]
            for col_cells in ws.columns:
                length = max((len(str(c.value)) for c in col_cells if c.value is not None), default=8)
                ws.column_dimensions[col_cells[0].column_letter].width = min(max(10, length + 2), 45)
    return buffer.getvalue()


def read_workbook(content: bytes) -> dict[str, pd.DataFrame]:
    try:
        return pd.read_excel(io.BytesIO(content), sheet_name=None, dtype=object, engine="openpyxl")
    except Exception as exc:  # fichier corrompu ou d'un autre format
        raise ValueError(f"Fichier illisible : {exc}") from exc


# ----------------------------------------------------------------------------
# Copie GitHub
# ----------------------------------------------------------------------------
@dataclass
class GitHubMirror:
    token: str
    repo: str                      # « utilisateur/depot »
    branch: str = "main"
    folder: str = "data"           # dossier du dépôt qui contient les données
    api_url: str = "https://api.github.com"
    timeout: float = 15.0
    last_error: str | None = None
    last_success: datetime | None = None
    _shas: dict = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _session(self):
        import requests  # dépendance de Streamlit, toujours disponible

        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {self.token}",
                          "Accept": "application/vnd.github+json",
                          "X-GitHub-Api-Version": "2022-11-28"})
        return s

    def _remote(self, rel: str) -> str:
        return f"{self.folder}/{rel}" if self.folder else rel

    def _fail(self, message: str) -> bool:
        self.last_error = f"{datetime.now():%H:%M:%S} — {message}"
        return False

    def download_all(self, local_dir: Path) -> int:
        """Copie tous les fichiers du dépôt dans le dossier local. Renvoie le nombre de fichiers."""
        with self._lock:
            try:
                s = self._session()
                r = s.get(f"{self.api_url}/repos/{self.repo}/git/trees/{self.branch}",
                          params={"recursive": "1"}, timeout=self.timeout)
                if r.status_code in (404, 409):      # dépôt vide ou branche absente : rien à charger
                    self.last_success = datetime.now()
                    return 0
                r.raise_for_status()
                prefix = f"{self.folder}/" if self.folder else ""
                count = 0
                for item in r.json().get("tree", []):
                    if item.get("type") != "blob" or not item["path"].startswith(prefix):
                        continue
                    rel = item["path"][len(prefix):]
                    if not rel.lower().endswith(DATA_SUFFIXES):
                        continue
                    blob = s.get(f"{self.api_url}/repos/{self.repo}/git/blobs/{item['sha']}", timeout=self.timeout)
                    blob.raise_for_status()
                    target = local_dir / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    _atomic_write(target, base64.b64decode(blob.json()["content"]))
                    self._shas[rel] = item["sha"]
                    count += 1
                self.last_success, self.last_error = datetime.now(), None
                return count
            except Exception as exc:
                self._fail(f"chargement depuis GitHub impossible ({exc})")
                return -1

    def _current_sha(self, s, rel: str) -> str | None:
        r = s.get(f"{self.api_url}/repos/{self.repo}/contents/{self._remote(rel)}",
                  params={"ref": self.branch}, timeout=self.timeout)
        return r.json().get("sha") if r.status_code == 200 else None

    def push(self, rel: str, content: bytes) -> bool:
        """Envoie (crée ou remplace) un fichier dans le dépôt."""
        with self._lock:
            try:
                s = self._session()
                url = f"{self.api_url}/repos/{self.repo}/contents/{self._remote(rel)}"
                body = {"message": f"Mise à jour {rel}", "content": base64.b64encode(content).decode(),
                        "branch": self.branch}
                for attempt in range(3):
                    sha = self._shas.get(rel)
                    payload = {**body, **({"sha": sha} if sha else {})}
                    r = s.put(url, json=payload, timeout=self.timeout)
                    if r.status_code in (200, 201):
                        self._shas[rel] = r.json()["content"]["sha"]
                        self.last_success, self.last_error = datetime.now(), None
                        return True
                    if r.status_code in (409, 422) and attempt < 2:
                        # Empreinte inconnue ou périmée : on relit celle du dépôt et on réessaie.
                        self._shas[rel] = self._current_sha(s, rel)
                        if r.status_code == 422 and "branch" in r.text.lower():
                            body.pop("branch", None)      # dépôt vide : GitHub crée la branche par défaut
                        continue
                    return self._fail(f"envoi de {rel} refusé ({r.status_code} : {r.text[:120]})")
                return self._fail(f"envoi de {rel} impossible")
            except Exception as exc:
                return self._fail(f"envoi de {rel} impossible ({exc})")

    def delete(self, rel: str) -> bool:
        with self._lock:
            try:
                s = self._session()
                sha = self._shas.get(rel) or self._current_sha(s, rel)
                if not sha:
                    return True
                r = s.delete(f"{self.api_url}/repos/{self.repo}/contents/{self._remote(rel)}",
                             json={"message": f"Suppression {rel}", "sha": sha, "branch": self.branch},
                             timeout=self.timeout)
                if r.status_code in (200, 404):
                    self._shas.pop(rel, None)
                    self.last_success, self.last_error = datetime.now(), None
                    return True
                return self._fail(f"suppression de {rel} refusée ({r.status_code})")
            except Exception as exc:
                return self._fail(f"suppression de {rel} impossible ({exc})")


# ----------------------------------------------------------------------------
# Stockage local (+ copie)
# ----------------------------------------------------------------------------
def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(content)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


class Store:
    """Accès aux fichiers de données par chemin relatif (« eleves/abc123.xlsx »)."""

    def __init__(self, base_dir: Path, mirror: GitHubMirror | None = None):
        self.base_dir = Path(base_dir)
        self.mirror = mirror
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def path(self, rel: str) -> Path:
        return self.base_dir / rel

    def exists(self, rel: str) -> bool:
        return self.path(rel).exists()

    def read(self, rel: str) -> bytes | None:
        p = self.path(rel)
        return p.read_bytes() if p.exists() else None

    def version(self, rel: str) -> tuple[int, int]:
        """Signature (date de modification, taille) servant de clé de cache."""
        st_ = self.path(rel).stat()
        return st_.st_mtime_ns, st_.st_size

    def write(self, rel: str, content: bytes) -> None:
        _atomic_write(self.path(rel), content)
        if self.mirror:
            self.mirror.push(rel, content)

    def delete(self, rel: str) -> None:
        p = self.path(rel)
        if p.exists():
            p.unlink()
        if self.mirror:
            self.mirror.delete(rel)

    def list(self, folder: str, suffix: str | tuple = ".xlsx") -> list[str]:
        d = self.path(folder)
        if not d.exists():
            return []
        return sorted(f"{folder}/{p.name}" for p in d.iterdir() if p.is_file() and p.name.endswith(suffix))


# ----------------------------------------------------------------------------
# Instance unique pour l'application
# ----------------------------------------------------------------------------
_STORE: Store | None = None
_STORE_LOCK = threading.Lock()


def _read_secret_section(name: str) -> dict:
    try:
        import streamlit as st

        return dict(st.secrets.get(name, {}))
    except Exception:  # pas de secrets.toml
        return {}


def mirror_from_config() -> GitHubMirror | None:
    conf = _read_secret_section("github")
    token = conf.get("token") or os.environ.get("PLAN_GITHUB_TOKEN")
    repo = conf.get("repo") or os.environ.get("PLAN_GITHUB_REPO")
    if not (token and repo):
        return None
    return GitHubMirror(token=str(token), repo=str(repo),
                        branch=str(conf.get("branch") or os.environ.get("PLAN_GITHUB_BRANCH") or "main"),
                        folder=str(conf.get("folder", "data")),
                        api_url=str(os.environ.get("PLAN_GITHUB_API", "https://api.github.com")))


def get_store() -> Store:
    """Stockage de l'application. Au premier appel, recharge les données depuis GitHub si configuré."""
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            mirror = mirror_from_config()
            store = Store(DEFAULT_DATA_DIR, mirror)
            if mirror:
                mirror.download_all(store.base_dir)
            _STORE = store
        return _STORE
