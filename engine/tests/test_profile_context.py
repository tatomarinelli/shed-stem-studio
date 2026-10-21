"""Perfil (cuestionario), contexto (hora/día/clima) y motivo determinístico. Sin red."""
import os
import sys
import tempfile
import unittest
from unittest import mock
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("STEMSHED_MEMORY_DIR", tempfile.mkdtemp(prefix="stemshed-test-"))
os.environ["STEMSHED_NO_SCHEDULER"] = "1"
import context as C  # noqa: E402
import profile as P  # noqa: E402
import recs as R  # noqa: E402


class Profile(unittest.TestCase):
    def test_validate_whitelists_and_caps(self):
        v = P.validate({"instrument": "  guitarra   eléctrica ", "level": "avanzado", "improve": ["teoria", "hackear"],
                        "loves": "jazz, Jazz, bossa nova", "geo": {"latitude": 1}, "evil": 1, "notes": "x" * 999})
        self.assertEqual(v["instrument"], "guitarra eléctrica")
        self.assertEqual(v["improve"], ["teoria"])
        self.assertEqual(v["loves"], ["jazz", "bossa nova"])
        self.assertNotIn("geo", v)
        self.assertNotIn("evil", v)
        self.assertEqual(len(v["notes"]), 300)
        with self.assertRaises(P.ProfileError):
            P.validate({"discovery": "muchísimo"})

    def test_save_geocodes_only_when_weather_on(self):
        calls = []

        def geo(city):
            calls.append(city)
            return {"name": city, "latitude": -34.6, "longitude": -58.4, "timezone": "America/Argentina/Buenos_Aires"}

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "profile.json")
            P.save(path, {"city": "Rosario"}, geocode=geo)
            self.assertEqual(calls, [])  # sin opt-in no sale nada
            data = P.save(path, {"useWeather": True}, geocode=geo)
            self.assertEqual(calls, ["Rosario"])
            self.assertEqual(data["geo"]["query"], "Rosario")
            P.save(path, {"instrument": "guitarra"}, geocode=geo)
            self.assertEqual(calls, ["Rosario"])  # misma ciudad: no se vuelve a buscar
            self.assertEqual(oct(os.stat(path).st_mode & 0o777), "0o600")

    def test_empty_profile_falls_back(self):
        self.assertEqual(P.describe(P.load("/nonexistent/profile.json")), P.LEGACY)


class Context(unittest.TestCase):
    def test_opt_in(self):
        self.assertIsNone(C.build({"useTime": False, "useWeather": False}, 0))

    def test_time_and_weather(self):
        tz = "America/Argentina/Buenos_Aires"
        ts = datetime(2026, 10, 20, 22, 30, tzinfo=ZoneInfo(tz)).timestamp()  # martes a la noche
        prof = {"useTime": True, "useWeather": True, "geo": {"name": "Rosario", "latitude": -34.6, "timezone": tz}}
        ctx = C.build(prof, ts, {"temp": 15.6, "code": 1})
        self.assertEqual(C.describe(ctx), "martes a la noche · Rosario, primavera · 16 °C, mayormente despejado")
        self.assertEqual(C.season(datetime(2026, 1, 10).date(), south=False), "invierno")


class Reason(unittest.TestCase):
    def snap(self):
        return {"weights": {"genres": [{"name": "jazz", "w": 2.0, "from": ["perfil"]}, {"name": "reggae", "w": 1.0, "from": ["favoritos"]}],
                            "artists": [{"name": "Miles Davis", "w": 1.0, "from": ["favoritos"]}]},
                "history": [], "taste": {"known": {}}, "sources": [], "profile": P.load("/nonexistent")}

    def test_reason_from_overlap(self):
        fit, reason, ov = R.assess(["modal jazz", "hard bop"], "Miles Davis", self.snap(), None, {})
        self.assertGreater(fit, 0)
        self.assertIn("modal jazz", reason.lower())
        self.assertIn("Miles Davis está en tus favoritos", reason)

    def test_reason_outside_zone_is_honest(self):
        fit, reason, _ = R.assess(["krautrock"], "Can", self.snap(), None, {})
        self.assertEqual(fit, 0)
        self.assertEqual(reason, "Un paso fuera de tu zona: krautrock.")
        _, reason, _ = R.assess([], "Can", self.snap(), {"seed": {"artist": "Neu!"}}, {})
        self.assertIn("MusicBrainz no tiene géneros", reason)
        self.assertIn("Neu!", reason)

    def test_due(self):
        day = datetime(2026, 10, 20, 23, 0).timestamp()
        self.assertTrue(R.is_due(None, 24, day))
        self.assertTrue(R.is_due(day, 24, day + 2 * 3600))   # cambió la fecha
        self.assertFalse(R.is_due(day, 6, day + 2 * 3600))
        self.assertTrue(R.is_due(day, 6, day + 6 * 3600))

    def test_chat_model_choice(self):
        tags = [{"name": "nomic-embed-text:latest", "capabilities": ["embedding"], "modified_at": "2026-10-21T05:00:00"},
                {"name": "b:12b", "capabilities": ["completion"], "modified_at": "2026-10-21T02:00:00"},
                {"name": "a:latest", "capabilities": ["completion", "tools"], "modified_at": "2026-10-21T00:49:00"}]
        self.assertEqual(R.pick_chat_model(tags, ""), "a:latest")              # el instalado primero, sin importar el orden
        self.assertEqual(R.pick_chat_model(list(reversed(tags)), ""), "a:latest")
        self.assertEqual(R.pick_chat_model(tags, "b:12b"), "b:12b")
        self.assertEqual(R.pick_chat_model(tags, "nomic-embed-text:latest"), "a:latest")  # nunca uno de embeddings
        self.assertIsNone(R.pick_chat_model(tags[:1], ""))

    def test_clean_request(self):
        r = R.clean_request({"prompt": "  algo  tranqui ", "mode": "x", "seed": {"artist": "Miles Davis", "album": "Kind of Blue", "evil": 1}})
        self.assertEqual(r, {"prompt": "algo tranqui", "mode": None, "seed": {"artist": "Miles Davis", "album": "Kind of Blue"}})
        self.assertIsNone(R.clean_request({}))

class OwnArtists(unittest.TestCase):
    def test_validate_dedups_and_limits(self):
        out = P.validate({"ownArtists": ["Mi banda", "mi banda", " Otra  banda "]})
        self.assertEqual(out["ownArtists"], ["Mi banda", "Otra banda"])

    def test_recs_excludes_own_artist(self):
        import recs

        with mock.patch.object(recs, "load_profile", return_value={"ownArtists": ["Mi Banda"]}):
            self.assertEqual(recs.own_artists(), {recs.norm("Mi Banda")})
            ok, why, cat = recs.verify({"artist": "mi banda", "album": "x", "year": None, "confidence": 90}, set())
            self.assertFalse(ok)
            self.assertEqual(cat, "excluded")

class NoTidal(unittest.TestCase):
    def test_load_sources_without_tidal_is_empty_not_an_error(self):
        import recs
        import tidal_source

        err = tidal_source.SourceError("no_session", "Todavía no conectaste TIDAL.")
        with mock.patch.object(recs, "read_sources", side_effect=err), mock.patch.object(recs, "cached_sources", return_value=[]):
            self.assertEqual(recs.load_sources(), [])
        with mock.patch.object(recs, "read_sources", side_effect=err), mock.patch.object(recs, "cached_sources", return_value=[{"kind": "artist", "artist": "X"}]):
            self.assertEqual(len(recs.load_sources()), 1)


if __name__ == "__main__":
    unittest.main()
