"""
Tests de la v8 : option 2 séances par semaine, recherche de parcours robuste (IGN + Nominatim,
Overpass + Postpass, serveurs de secours, résultats partiels), choix de l'élève visibles par le coach.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fake_osm  # noqa: E402
from core import decouverte, historique, profils, referentiel, suivi  # noqa: E402
from core.config import FREQUENCIES  # noqa: E402
from core.plan import is_race_day  # noqa: E402
from core.stockage import Store  # noqa: E402

TODAY = date.today()


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "data")
    referentiel.ensure_referentiel(s)
    return s


# ----------------------------------------------------------------------------- 2 séances
def test_deux_seances(store):
    assert FREQUENCIES == [2, 3, 4]
    s = profils.create_student(store, "deux@x.fr", "Deux", "marathon", "3:30:00", TODAY + timedelta(days=90), 2)
    assert s.frequence_defaut == 2
    assert profils.get_student(store, s.id).frequence_defaut == 2           # relu depuis le fichier
    st2 = historique.program_state(store, s)
    assert st2.frequency == 2
    for pos in st2.table["position"].unique():
        week = st2.table[st2.table["position"] == pos]
        assert 1 <= len(week) <= 2
    # la séance du jour de course est toujours gardée
    assert any(is_race_day(x) for x in st2.table["seance"])
    # l'élève choisit 3 puis 4 : son choix est enregistré, le coach le voit
    suivi.set_frequency(store, s.id, 3)
    st3 = historique.program_state(store, s)
    assert st3.frequency == 3 and len(st3.table) > len(st2.table)
    suivi.set_frequency(store, s.id, 4)
    assert len(historique.program_state(store, s).table) > len(st3.table)
    suivi.set_frequency(store, s.id, 2)
    assert suivi.load_suivi(store, s.id).frequence == 2
    assert len(historique.program_state(store, s).table) == len(st2.table)


def test_deux_seances_premiere_et_derniere(store):
    s = profils.create_student(store, "d2@x.fr", "D2", "semi", "1:45:00", TODAY + timedelta(days=70), 4)
    full = historique.program_state(store, s).table
    suivi.set_frequency(store, s.id, 2)
    two = historique.program_state(store, s).table
    for pos in two["position"].unique():
        a = full[full["position"] == pos]
        b = two[two["position"] == pos]
        if len(a) >= 2 and not any(is_race_day(x) for x in a["seance"]):
            assert list(b["session_id"]) == [a["session_id"].iloc[0], a["session_id"].iloc[-1]]


# ----------------------------------------------------------------------------- découverte
@pytest.fixture
def osm(monkeypatch):
    server = fake_osm.start()
    base = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setattr(decouverte, "OVERPASS_URLS", [f"{base}/api/interpreter"])
    monkeypatch.setattr(decouverte, "POSTPASS_URLS", [f"{base}/postpass/interpreter"])
    monkeypatch.setattr(decouverte, "NOMINATIM_URL", f"{base}/search")
    monkeypatch.setattr(decouverte, "IGN_URL", f"{base}/geocodage/search")
    monkeypatch.setattr(decouverte, "_DOWN", {})
    fake_osm.FakeOSM.calls = []
    for flag in ("fail_overpass", "fail_details", "fail_postpass", "fail_ign", "fail_nominatim"):
        setattr(fake_osm.FakeOSM, flag, False)
    yield base
    server.shutdown()


def _summary(found):
    return [(r.kind, r.name, round(r.length_km, 1)) for r in found]


def test_geocodage_ign_puis_nominatim(osm):
    place = decouverte.geocode("Lyon")
    assert place.name == "Lyon" and "Rhône" in place.label
    assert fake_osm.FakeOSM.calls[-1] == ("GET", "lyon")             # un seul appel : l'IGN a suffi
    # ville hors de France : l'IGN ne trouve rien, Nominatim prend le relais
    assert decouverte.geocode("Genève").name == "Genève"
    # IGN en panne : Nominatim répond
    fake_osm.FakeOSM.fail_ign = True
    assert decouverte.geocode("Bordeaux").name == "Bordeaux"
    # les deux en panne : message clair
    fake_osm.FakeOSM.fail_nominatim = True
    with pytest.raises(decouverte.DiscoveryError) as err:
        decouverte.geocode("Bordeaux")
    assert "situer la ville" in str(err.value) and "500" in err.value.detail and "403" in err.value.detail
    # commune approchante de l'IGN gardée en dernier recours
    fake_osm.FakeOSM.fail_ign = fake_osm.FakeOSM.fail_nominatim = False
    assert decouverte.geocode("Villz test").name == "Villetest-sur-Mer"
    assert decouverte.geocode("Nullepart") is None


def test_postpass_donne_les_memes_parcours(osm, monkeypatch):
    place = decouverte.geocode("ville test")
    via_overpass = decouverte.discover(place, 10)
    monkeypatch.setattr(decouverte, "OVERPASS_URLS", [])
    via_postpass = decouverte.discover(place, 10)
    assert _summary(via_postpass) == _summary(via_overpass)
    assert [r.loop for r in via_postpass] == [r.loop for r in via_overpass]
    assert via_postpass[0].url == "https://www.openstreetmap.org/relation/101"


def test_secours_et_mise_de_cote(osm):
    place = decouverte.geocode("ville test")
    reference = _summary(decouverte.discover(place, 10))
    # Overpass répond 504 : Postpass prend le relais
    fake_osm.FakeOSM.fail_overpass = True
    fake_osm.FakeOSM.calls = []
    assert _summary(decouverte.discover(place, 10)) == reference
    assert [c[1] for c in fake_osm.FakeOSM.calls][:1] == ["/api/interpreter"]
    # Overpass vient d'échouer : il est mis de côté, Postpass est essayé en premier
    fake_osm.FakeOSM.calls = []
    decouverte.discover(place, 10)
    assert fake_osm.FakeOSM.calls[0][1].startswith("/postpass")
    # erreur d'exécution Overpass (réponse 200 avec « remark ») : traitée comme une panne
    decouverte._DOWN.clear()
    fake_osm.FakeOSM.fail_overpass = "remark"
    assert _summary(decouverte.discover(place, 10)) == reference
    # tout est en panne : message lisible + détail technique
    fake_osm.FakeOSM.fail_overpass = True
    fake_osm.FakeOSM.fail_postpass = True
    with pytest.raises(decouverte.DiscoveryError) as err:
        decouverte.discover(place, 10)
    assert "Réessaie" in str(err.value) and "504" in err.value.detail and "503" in err.value.detail


def test_resultats_partiels(osm):
    place = decouverte.geocode("ville test")
    fake_osm.FakeOSM.fail_details = True
    notes = []
    found = decouverte.discover(place, 10, notes=notes)
    assert {r.kind for r in found} == {"parc", "piste"} and notes


def test_rayon(osm):
    place = decouverte.geocode("ville test")
    near = decouverte.discover(place, 1)
    assert all(r.center_km <= 1.5 for r in near)
    assert len(near) < len(decouverte.discover(place, 10))


def test_geojson():
    poly = {"type": "MultiPolygon", "coordinates": [[[[4.0, 45.0], [4.1, 45.0], [4.1, 45.1], [4.0, 45.0]]]]}
    assert decouverte._geojson_lines(poly) == [[(45.0, 4.0), (45.0, 4.1), (45.1, 4.1), (45.0, 4.0)]]
    assert decouverte._geojson_lines({"type": "LineString", "coordinates": [[1, 2], [3, 4]]}) == [[(2, 1), (4, 3)]]
    assert decouverte._geojson_lines(None) == []
    assert decouverte._props({"properties": {"tags": {"name": "A", "route": "hiking"}, "osm_id": 3}}) == \
        {"name": "A", "route": "hiking", "osm_id": 3, "tags": {"name": "A", "route": "hiking"}}
