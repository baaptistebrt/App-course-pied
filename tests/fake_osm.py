"""
Faux services OpenStreetMap (Nominatim + Overpass) pour les tests, sans accès réseau.

Données SIMULÉES autour d'un centre fictif : une boucle de course de ~5 km, un parcours sportif
de ~2 km, un sentier de ~12 km, un GR national (doit être écarté), une relation sans nom (écartée),
un grand parc (~1,6 km de tour), un petit parc (écarté) et une piste de 400 m.

Lancement autonome (pour essayer l'interface) :  python tests/fake_osm.py 8099
"""

from __future__ import annotations

import json
import math
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

CENTER = (45.7578, 4.8320)


def _offset(lat, lon, dn_km, de_km):
    return lat + dn_km / 111.2, lon + de_km / (111.2 * math.cos(math.radians(lat)))


def circle(center_km=(0.0, 0.0), radius_km=0.8, n=60):
    c = _offset(*CENTER, *center_km)
    pts = [_offset(*c, radius_km * math.sin(2 * math.pi * i / n), radius_km * math.cos(2 * math.pi * i / n))
           for i in range(n)]
    return [*pts, pts[0]]


def line(start_km, end_km, n=40):
    return [_offset(*CENTER, start_km[0] + (end_km[0] - start_km[0]) * i / n,
                    start_km[1] + (end_km[1] - start_km[1]) * i / n) for i in range(n + 1)]


def square(center_km, side_km):
    h = side_km / 2
    corners = [(-h, -h), (-h, h), (h, h), (h, -h), (-h, -h)]
    return [_offset(*CENTER, center_km[0] + a, center_km[1] + b) for a, b in corners]


def _geom(points):
    return [{"lat": a, "lon": b} for a, b in points]


def _bounds(points):
    return {"minlat": min(p[0] for p in points), "minlon": min(p[1] for p in points),
            "maxlat": max(p[0] for p in points), "maxlon": max(p[1] for p in points)}


RELATIONS = {
    101: ({"type": "route", "route": "running", "name": "Boucle des Berges", "roundtrip": "yes"},
          [circle((1.0, 0.5), 0.8)]),
    102: ({"type": "route", "route": "fitness_trail", "name": "Parcours sportif du Bois"},
          [line((2.0, -1.0), (2.0, 1.0))]),
    103: ({"type": "route", "route": "hiking", "name": "Sentier des Coteaux", "ref": "PR 4"},
          [line((-3.0, -3.0), (3.0, 3.0)), line((3.0, 3.0), (3.0, 6.0))]),
    104: ({"type": "route", "route": "hiking", "name": "GR national", "network": "nwn"},
          [line((-200.0, 0.0), (200.0, 0.0))]),
    105: ({"type": "route", "route": "foot"}, [line((0.0, 0.0), (0.0, 2.0))]),
}
WAYS = [
    {"type": "way", "id": 201, "tags": {"leisure": "park", "name": "Parc des Sports"}, "pts": square((-1.0, -1.0), 0.4)},
    {"type": "way", "id": 202, "tags": {"leisure": "park", "name": "Square Fleuri"}, "pts": square((0.2, 0.2), 0.05)},
    {"type": "way", "id": 203, "tags": {"leisure": "track", "sport": "athletics", "name": "Piste du stade municipal"},
     "pts": circle((-0.5, 1.5), 0.0637)},
]


def overview():
    out = [{"type": "relation", "id": rid, "tags": tags, "bounds": _bounds([p for ln in lines for p in ln])}
           for rid, (tags, lines) in RELATIONS.items()]
    out += [{"type": "way", "id": w["id"], "tags": w["tags"], "bounds": _bounds(w["pts"]), "geometry": _geom(w["pts"])}
            for w in WAYS]
    return out


def details(ids):
    out = []
    for rid in ids:
        if rid in RELATIONS:
            tags, lines = RELATIONS[rid]
            out.append({"type": "relation", "id": rid, "tags": tags, "bounds": _bounds([p for ln in lines for p in ln]),
                        "members": [{"type": "way", "ref": rid * 10 + i, "role": "", "geometry": _geom(ln)}
                                    for i, ln in enumerate(lines)]})
    return out


class FakeOSM(BaseHTTPRequestHandler):
    calls: list = []
    fail_overpass = False

    def log_message(self, *args):
        pass

    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        q = parse_qs(url.query).get("q", [""])[0].strip().lower()
        FakeOSM.calls.append(("GET", q))
        if url.path.endswith("/search"):
            if q in ("ville test", "lyon", "bordeaux"):
                return self._send(200, [{"lat": str(CENTER[0]), "lon": str(CENTER[1]), "name": q.title(),
                                         "display_name": f"{q.title()}, France"}])
            return self._send(200, [])
        self._send(404, {})

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        query = parse_qs(body).get("data", [""])[0]
        FakeOSM.calls.append(("POST", query[:40]))
        if FakeOSM.fail_overpass:
            return self._send(504, {})
        if "relation(id:" in query:
            ids = [int(x) for x in query.split("relation(id:")[1].split(")")[0].split(",")]
            return self._send(200, {"elements": details(ids)})
        return self._send(200, {"elements": overview()})


def start(port: int = 0):
    server = ThreadingHTTPServer(("127.0.0.1", port), FakeOSM)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8099), FakeOSM)
    srv.serve_forever()
