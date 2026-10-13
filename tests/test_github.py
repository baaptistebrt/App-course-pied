"""
Test de la copie GitHub avec un faux serveur qui imite l'API GitHub (aucun accès réseau).
"""

import base64
import hashlib
import json
import sys
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import profils, referentiel  # noqa: E402
from core.stockage import GitHubMirror, Store  # noqa: E402

TOKEN = "jeton-de-test"


class FakeGitHub(BaseHTTPRequestHandler):
    files: dict = {}          # chemin -> octets
    requests_log: list = []

    def log_message(self, *args):  # silencieux
        pass

    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    @staticmethod
    def sha(content: bytes) -> str:
        return hashlib.sha1(content).hexdigest()

    def _auth_ok(self):
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            self._send(401, {"message": "Bad credentials"})
            return False
        return True

    def _body(self):
        return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")

    def do_GET(self):
        if not self._auth_ok():
            return
        url = urlparse(self.path)
        parts = url.path.strip("/").split("/")
        if parts[3:5] == ["git", "trees"]:
            if not self.files:
                return self._send(409, {"message": "Git Repository is empty."})
            tree = [{"path": p, "type": "blob", "sha": self.sha(c)} for p, c in self.files.items()]
            return self._send(200, {"tree": tree, "truncated": False})
        if parts[3:5] == ["git", "blobs"]:
            for c in self.files.values():
                if self.sha(c) == parts[5]:
                    return self._send(200, {"content": base64.b64encode(c).decode(), "encoding": "base64"})
            return self._send(404, {"message": "Not Found"})
        if parts[3] == "contents":
            path = "/".join(parts[4:])
            if path in self.files:
                return self._send(200, {"sha": self.sha(self.files[path])})
            return self._send(404, {"message": "Not Found"})
        self._send(404, {"message": "Not Found"})

    def do_PUT(self):
        if not self._auth_ok():
            return
        path = "/".join(urlparse(self.path).path.strip("/").split("/")[4:])
        body = self._body()
        FakeGitHub.requests_log.append(("PUT", path))
        if path in self.files:
            if "sha" not in body:
                return self._send(422, {"message": "Invalid request. \"sha\" wasn't supplied."})
            if body["sha"] != self.sha(self.files[path]):
                return self._send(409, {"message": "does not match"})
        content = base64.b64decode(body["content"])
        created = path not in self.files
        self.files[path] = content
        self._send(201 if created else 200, {"content": {"sha": self.sha(content)}})

    def do_DELETE(self):
        if not self._auth_ok():
            return
        path = "/".join(urlparse(self.path).path.strip("/").split("/")[4:])
        body = self._body()
        if path not in self.files:
            return self._send(404, {"message": "Not Found"})
        if body.get("sha") != self.sha(self.files[path]):
            return self._send(409, {"message": "does not match"})
        del self.files[path]
        self._send(200, {"commit": {}})


@pytest.fixture
def github():
    FakeGitHub.files = {}
    FakeGitHub.requests_log = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeGitHub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def mirror(api):
    return GitHubMirror(token=TOKEN, repo="coach/donnees", branch="main", api_url=api)


def test_sauvegarde_et_rechargement(github, tmp_path):
    a = Store(tmp_path / "pc_a", mirror(github))
    referentiel.ensure_referentiel(a)
    s = profils.create_student(a, "julie@x.fr", "Julie", "semi", "1:50:00", date(2026, 12, 6), 3)
    assert f"data/eleves/{s.id}.xlsx" in FakeGitHub.files
    assert a.mirror.last_error is None

    # Redémarrage sur un disque vide : tout revient depuis GitHub.
    b = Store(tmp_path / "pc_b", mirror(github))
    assert b.mirror.download_all(b.base_dir) == len(FakeGitHub.files)
    loaded = profils.get_student(b, s.id)
    assert loaded.prenom == "Julie" and loaded.code == s.code and loaded.date_course == date(2026, 12, 6)

    # Modification depuis b puis depuis a (empreinte périmée) : la 2e réessaie et réussit.
    profils.save_student(b, loaded.with_(objectif="01:45:00"))
    profils.save_student(a, s.with_(prenom="Julie B."))
    assert a.mirror.last_error is None
    c = Store(tmp_path / "pc_c", mirror(github))
    c.mirror.download_all(c.base_dir)
    assert profils.get_student(c, s.id).prenom == "Julie B."

    # Suppression propagée
    profils.delete_student(a, s.id)
    assert f"data/eleves/{s.id}.xlsx" not in FakeGitHub.files


def test_erreur_signalee_sans_bloquer(github, tmp_path):
    bad = GitHubMirror(token="mauvais", repo="coach/donnees", api_url=github)
    store = Store(tmp_path / "pc", bad)
    referentiel.ensure_referentiel(store)            # l'écriture locale fonctionne quand même
    assert store.exists("formules.xlsx")
    assert bad.last_error and "401" in bad.last_error
