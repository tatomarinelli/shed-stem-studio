"""Memoria segmentada: facetas derivadas con datos, observaciones con evidencia y grafo. Sin red, en carpetas temporales."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("STEMSHED_MEMORY_DIR", tempfile.mkdtemp(prefix="stemshed-test-"))
os.environ["STEMSHED_NO_SCHEDULER"] = "1"
import facets as F  # noqa: E402
import memory  # noqa: E402
import recs as R  # noqa: E402

_module_patches = []


def setUpModule():
    """Sin tocar la configuración ni los datos reales del usuario (ver test_recs.py)."""
    import tempfile as _t
    from unittest import mock as _m

    data = _t.mkdtemp(prefix="stemshed-test-data-")
    for p in (_m.patch.object(R.settings, "load", lambda: dict(R.settings.DEFAULTS)),
              _m.patch.object(R.settings, "effective", lambda d=None: {**R.settings.DEFAULTS, "dataDir": data})):
        p.start()
        _module_patches.append(p)


def tearDownModule():
    while _module_patches:
        _module_patches.pop().stop()
from perms import assert_private  # noqa: E402

DAY = 86400.0
T0 = 1_700_000_000.0
PROFILE = {"instrument": "guitarra", "level": "avanzado", "improve": ["modos"], "loves": ["jazz"], "avoids": ["smooth jazz"], "essentials": [],
           "ownArtists": ["Mi Banda"], "discovery": "algo", "listening": "discos", "pace": "", "notes": "", "useTime": False,
           "useWeather": False, "city": "", "geo": None, "dismissed": False, "imported": None}


def uid(n):
    return f"00000000-0000-0000-0000-{n:012d}"


def reaction(n, action, artist, album, genres, known=False, day=0):
    return memory.make_event(T0 + day * DAY, "reaction", uid(n), artist, album, action, genres, known=known)


def snap_from(events, now=T0 + 10 * DAY, prof=None):
    taste, keep = memory.compact(memory.empty_taste(), events, now)
    hist = memory.history(taste, keep)
    w = memory.weights(taste, keep, [], {"genres": [], "artists": []}, now)
    return {"taste": taste, "events": keep, "profile": prof or dict(PROFILE), "sources": [], "weights": w, "history": hist}


class Observations(unittest.TestCase):
    def test_genre_positive_needs_enough_evidence(self):
        evs = [reaction(i, "loved", f"A{i}", f"D{i}", ["dub"]) for i in range(2)]
        self.assertEqual((lambda s: F.observations(s["history"], s["taste"], events=s["events"]))(snap_from(evs)), [])
        evs.append(reaction(3, "liked", "A3", "D3", ["dub", "reggae"]))
        s = snap_from(evs)
        obs = F.observations(s["history"], s["taste"], events=s["events"])
        self.assertEqual([o["kind"] for o in obs], ["genre-pos"])
        self.assertEqual(sorted(obs[0]["evidence"]), sorted(uid(i) for i in (0, 1, 3)))  # cada observación cita sus discos
        self.assertIn("3 de 3", obs[0]["text"])

    def test_negative_observation_is_shown_but_changes_no_weights(self):
        evs = [reaction(i, "disliked", f"A{i}", f"D{i}", ["smooth jazz"]) for i in range(3)]
        s = snap_from(evs)
        obs = F.observations(s["history"], s["taste"], events=s["events"])
        self.assertEqual(obs[0]["kind"], "genre-neg")
        self.assertEqual(obs[0]["status"], "proposed")
        self.assertTrue(all(g["name"] != "smooth jazz" or g["w"] >= 0 for g in s["weights"]["genres"]))  # por ítem, nunca por género
        self.assertEqual(F.derive(s, T0 + 10 * DAY)["avoid"]["confirmedStyles"], [])  # sin confirmar no filtra nada

    def test_confirmed_negative_becomes_an_avoid_style(self):
        evs = [reaction(i, "no", f"A{i}", f"D{i}", ["smooth jazz"]) for i in range(3)]
        s = snap_from(evs)
        oid = F.observations(s["history"], s["taste"], events=s["events"])[0]["id"]
        f = F.derive(s, T0 + 10 * DAY, states={oid: "confirmed"})
        self.assertEqual(f["avoid"]["confirmedStyles"], ["smooth jazz"])
        f = F.derive(s, T0 + 10 * DAY, states={oid: "rejected"})
        self.assertEqual(f["avoid"]["confirmedStyles"], [])
        self.assertEqual(f["observations"]["items"][0]["status"], "rejected")

    def test_artist_loved_twice_and_known_rate(self):
        evs = [reaction(1, "loved", "Bob Marley", "Exodus", ["reggae"]), reaction(2, "loved", "Bob Marley", "Kaya", ["reggae"], day=1)]
        evs += [reaction(10 + i, "liked", f"X{i}", f"Y{i}", ["jazz"], known=True, day=2 + i) for i in range(6)]
        s = snap_from(evs)
        kinds = {o["kind"] for o in F.observations(s["history"], s["taste"], events=s["events"])}
        self.assertTrue({"artist-pos", "known-high"} <= kinds)

    def test_ids_are_stable(self):
        evs = [reaction(i, "loved", f"A{i}", f"D{i}", ["dub"]) for i in range(3)]
        s = snap_from(evs)
        a = F.observations(s["history"], s["taste"], events=s["events"])[0]["id"]
        self.assertEqual(a, F.observations(s["history"], s["taste"], events=s["events"])[0]["id"])


class Facets(unittest.TestCase):
    def test_all_facets_present_and_own_band_never_in_taste_or_graph(self):
        evs = [reaction(1, "loved", "Mi Banda", "Ensayo", ["dub"]), reaction(2, "loved", "King Tubby", "Dub from the Roots", ["dub", "reggae"])]
        s = snap_from(evs)
        s["weights"]["artists"].append({"name": "Mi Banda", "w": 9.0, "from": ["reacciones"]})
        f = F.derive(s, T0 + 10 * DAY)
        self.assertEqual(set(f), set(F.FACETS))
        self.assertNotIn("Mi Banda", [a["name"] for a in f["taste"]["artists"]])
        self.assertFalse([n for n in f["graph"]["nodes"] if "mi banda" in n["id"] or n["label"] == "Ensayo"])
        self.assertEqual(f["identity"]["ownArtists"], ["Mi Banda"])  # sí figura en la identidad: es lo que él declaró

    def test_graph_links_albums_artists_genres_and_hierarchy(self):
        evs = [reaction(1, "loved", "King Tubby", "Dub from the Roots", ["dub", "reggae"])]
        s = snap_from(evs)
        g = F.derive(s, T0 + 10 * DAY)["graph"]
        ids = {n["id"] for n in g["nodes"]}
        self.assertIn("d:" + uid(1), ids)
        self.assertIn("a:king tubby", ids)
        self.assertIn("g:dub", ids)
        types = {(e["type"]) for e in g["edges"]}
        self.assertTrue({"by", "has-genre", "subgenre-of"} <= types)
        for e in g["edges"]:  # ninguna arista apunta a un nodo que no existe
            self.assertIn(e["from"], ids)
            self.assertIn(e["to"], ids)

    def test_markdown_is_generated_from_data_only(self):
        evs = [reaction(i, "loved", f"A{i}", f"D{i}", ["dub"]) for i in range(3)]
        f = F.derive(snap_from(evs), T0 + 10 * DAY)
        md = F.render_md("observations", f["observations"])
        self.assertIn("Te gustan los discos de dub", md)
        self.assertIn("3 discos de evidencia", md)
        self.assertIn("guitarra", F.render_md("identity", f["identity"]))

    def test_write_all_files_private_and_states_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            st = memory.Store(d)
            f = F.derive(snap_from([reaction(1, "loved", "A", "B", ["jazz"])]), T0 + 10 * DAY)
            F.write_all(d, f, st._write)
            for name in F.FACETS:
                self.assertTrue(Path(d, "memory", f"{name}.json").exists())
                assert_private(self, os.path.join(d, "memory", f"{name}.json"))
            self.assertEqual(json.loads(Path(d, "memory", "taste.json").read_text())["artists"][0]["name"], "A")
            F.set_state(d, st._write, "genre-pos:abc12345", "confirmed")
            self.assertEqual(F.load_states(d), {"genre-pos:abc12345": "confirmed"})
            with self.assertRaises(ValueError):
                F.set_state(d, st._write, "x", "inventado")
            Path(d, "memory", "observation-states.json").write_text("{roto")
            self.assertEqual(F.load_states(d), {})  # un archivo roto no tira la memoria


class Integration(unittest.TestCase):
    def setUp(self):
        data = tempfile.mkdtemp(prefix="stemshed-test-data-")  # sin leer la configuración real del usuario
        for p in (mock.patch.object(R.settings, "load", lambda: dict(R.settings.DEFAULTS)),
                  mock.patch.object(R.settings, "effective", lambda d=None: {**R.settings.DEFAULTS, "dataDir": data})):
            p.start()
            self.addCleanup(p.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for p in (mock.patch.object(R, "store", memory.Store(self.tmp.name)), mock.patch.object(R, "LAST", Path(self.tmp.name) / "last.json"),
                  mock.patch.object(R, "load_profile", lambda: dict(PROFILE)), mock.patch.object(R, "cached_sources", lambda: []),
                  mock.patch.object(R, "load_presets", lambda: R.presets_mod.load(Path(self.tmp.name) / "presets.json"))):
            p.start()
            self.addCleanup(p.stop)

    def test_snapshot_writes_facets_and_confirmed_avoid_reaches_prompt_and_filter(self):
        for i in range(3):
            R.store.append(reaction(i, "no", f"A{i}", f"D{i}", ["country"], day=0))
        snap = R.snapshot(T0 + 10 * DAY)
        self.assertTrue(Path(self.tmp.name, "memory", "observations.md").exists())
        self.assertTrue(Path(self.tmp.name, "memory", "graph.json").exists())
        oid = snap["facets"]["observations"]["items"][0]["id"]
        self.assertNotIn("country", R.build_prompt(snap, None, "", [], 4, [], {}))  # una observación sin confirmar no llega al modelo
        R.set_observation(oid, "confirmed")
        snap = R.snapshot(T0 + 10 * DAY)
        self.assertIn("Evitar estilos: smooth jazz, country", R.build_prompt(snap, None, "", [], 4, [], {}))
        with self.assertRaises(ValueError):
            R.set_observation("../../etc", "confirmed")

if __name__ == "__main__":
    unittest.main()
