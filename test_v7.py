"""
Tests de la découverte automatique de parcours (OpenStreetMap), avec de faux services locaux.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fake_osm  # noqa: E402
from core import decouverte  # noqa: E402


@pytest.fixture
def osm(monkeypatch):
    server = fake_osm.start()
    base = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setattr(decouverte, "OVERPASS_URLS", [f"{base}/api/interpreter"])
    monkeypatch.setattr(decouverte, "POSTPASS_URLS", [])
    monkeypatch.setattr(decouverte, "NOMINATIM_URL", f"{base}/search")
    monkeypatch.setattr(decouverte, "IGN_URL", f"{base}/geocodage/search")
    monkeypatch.setattr(decouverte, "_DOWN", {})
    fake_osm.FakeOSM.calls = []
    for flag in ("fail_overpass", "fail_postpass", "fail_ign", "fail_nominatim"):
        setattr(fake_osm.FakeOSM, flag, False)
    yield base
    server.shutdown()


def test_geocode(osm):
    place = decouverte.geocode("Ville test")
    assert place.name == "Ville Test" and abs(place.lat - fake_osm.CENTER[0]) < 1e-6
    assert decouverte.geocode("Nullepart") is None
    assert decouverte.geocode("  ") is None


def test_discover(osm):
    place = decouverte.geocode("ville test")
    found = decouverte.discover(place, 10)
    by_name = {r.name: r for r in found}
    assert [r.kind for r in found] == ["course", "sportif", "sentier", "parc", "piste"]       # ordre d'affichage
    assert "GR national" not in by_name and "Square Fleuri" not in by_name                 # écartés
    loop = by_name["Boucle des Berges"]
    assert loop.loop and loop.length_km == pytest.approx(2 * 3.1416 * 0.8, rel=0.02)
    assert loop.url == "https://www.openstreetmap.org/relation/101" and loop.lines
    assert by_name["Parcours sportif du Bois"].length_km == pytest.approx(2.0, rel=0.02)
    assert not by_name["Parcours sportif du Bois"].loop
    trail = by_name["Sentier des Coteaux (PR 4)"]
    assert trail.length_km == pytest.approx(8.485 + 3.0, rel=0.02)
    park = by_name["Parc des Sports"]
    assert park.kind == "parc" and park.length_km == pytest.approx(1.6, rel=0.03) and park.loop
    track = by_name["Piste du stade municipal"]
    assert track.length_str == "400 m" and track.kind == "piste"
    assert decouverte.filter_by_length(found, "Moins de 5 km") == [by_name["Parcours sportif du Bois"], park, track]
    assert decouverte.filter_by_length(found, "10 à 21 km") == [trail, track]


def test_service_indisponible(osm, monkeypatch):
    fake_osm.FakeOSM.fail_overpass = True
    place = decouverte.geocode("ville test")
    with pytest.raises(decouverte.DiscoveryError):
        decouverte.discover(place, 10)
    # serveur de secours : le premier échoue, le second répond
    monkeypatch.setattr(decouverte, "OVERPASS_URLS", ["http://127.0.0.1:9/indisponible",
                                                      f"{osm}/api/interpreter"])
    fake_osm.FakeOSM.fail_overpass = False
    assert decouverte.discover(place, 10)


def test_geometrie():
    assert decouverte.haversine_km((45.0, 4.0), (46.0, 4.0)) == pytest.approx(111.2, rel=0.01)
    sq = fake_osm.square((0, 0), 1.0)
    assert decouverte.area_km2(sq) == pytest.approx(1.0, rel=0.02)
