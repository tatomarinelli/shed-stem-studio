"""Biblioteca completa de YouTube Music (ytmusicapi, no oficial): instalación a pedido, login por encabezados y lectura.
La librería se reemplaza por una falsa: ninguna prueba instala nada ni toca la red."""
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["STEMSHED_NO_SCHEDULER"] = "1"
import providers  # noqa: E402
import ytmusic_source  # noqa: E402
import ytmusic_unofficial as yu  # noqa: E402
from providers import ProviderError  # noqa: E402

GOOD = {"cookie": "SAPISID=x", "authorization": "SAPISIDHASH 123_abc", "x-goog-authuser": "0"}


class FakeYT:
    calls = []
    fail = None

    def __init__(self, auth=None, **kw):
        self.auth = auth

    def _go(self, name, **kw):
        FakeYT.calls.append((name, kw))
        if FakeYT.fail:
            raise FakeYT.fail
        return {"get_library_albums": [{"browseId": "MPREb_1", "title": "Kind of Blue", "artists": [{"name": "Miles Davis"}], "year": "1959"},
                                       {"title": "sin id"}],
                "get_library_songs": [{"videoId": "v1", "title": "So What", "artists": [{"name": "Miles Davis"}], "album": {"name": "Kind of Blue"}, "duration_seconds": 545},
                                      {"videoId": "v2", "title": "Sin álbum", "artists": [], "album": None}],
                "get_library_playlists": [{"playlistId": "PL1", "title": "Jazz", "count": 12}]}[name]

    def get_library_albums(self, **kw): return self._go("get_library_albums", **kw)
    def get_library_songs(self, **kw): return self._go("get_library_songs", **kw)
    def get_library_playlists(self, **kw): return self._go("get_library_playlists", **kw)


def fake_setup(headers_raw=None, filepath=None):
    h = {k.strip().lower(): v.strip() for k, _, v in (l.partition(":") for l in headers_raw.splitlines()) if v}
    return json.dumps(h)


class Base(unittest.TestCase):
    def setUp(self):
        FakeYT.calls, FakeYT.fail = [], None
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        lib = types.SimpleNamespace(YTMusic=FakeYT)
        setup_mod = types.ModuleType("ytmusicapi.setup")
        setup_mod.setup = fake_setup
        for p in (mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp.name}), mock.patch.object(yu, "_lib", return_value=lib),
                  mock.patch.dict(sys.modules, {"ytmusicapi": lib, "ytmusicapi.setup": setup_mod}),
                  mock.patch.object(yu.osenv, "write_protected", side_effect=lambda path, data: (Path(path).write_bytes(data), "file-600")[1]),
                  mock.patch.object(yu.osenv, "read_protected", side_effect=lambda path: Path(path).read_bytes()),
                  mock.patch.object(yu.osenv, "delete_protected", side_effect=lambda path: Path(path).unlink(missing_ok=True))):
            p.start()
            self.addCleanup(p.stop)

    RAW = "Host: music.youtube.com\nCookie: SAPISID=x\nAuthorization: SAPISIDHASH 123_abc\nX-Goog-AuthUser: 0"


class Login(Base):
    def test_encabezados_validos_se_guardan_tras_leer_un_disco(self):
        yu.save_headers(self.RAW)
        self.assertTrue(yu.connected())
        self.assertEqual(FakeYT.calls, [("get_library_albums", {"limit": 1})])

    def test_sin_authorization_se_rechaza_y_no_guarda(self):
        with self.assertRaises(ProviderError) as c:
            yu.save_headers("Host: music.youtube.com\nCookie: SAPISID=x")
        self.assertEqual(c.exception.code, "bad_headers")
        self.assertFalse(yu.connected())

    def test_vacio_o_enorme(self):
        for raw in ("", " ", "x" * (yu.HEADERS_MAX + 1)):
            with self.assertRaises(ProviderError):
                yu.save_headers(raw)

    def test_sesion_ya_vencida_al_pegar_avisa_y_no_guarda(self):
        FakeYT.fail = RuntimeError("HTTP 401 Unauthorized")
        with self.assertRaises(ProviderError) as c:
            yu.save_headers(self.RAW)
        self.assertEqual(c.exception.code, "reauth")
        self.assertFalse(yu.connected())

    def test_sin_la_libreria_pide_instalarla(self):
        with mock.patch.object(yu, "_lib", return_value=None):
            with self.assertRaises(ProviderError) as c:
                yu.save_headers(self.RAW)
        self.assertEqual(c.exception.code, "not_installed")

    def test_borrar_la_sesion(self):
        yu.STORE.save(GOOD)
        yu.clear()
        self.assertFalse(yu.connected())


class Reading(Base):
    def setUp(self):
        super().setUp()
        yu.STORE.save(GOOD)

    def test_albumes_temas_y_playlists_normalizados(self):
        lib = yu.library()
        self.assertEqual([a["title"] for a in lib["albums"]], ["Kind of Blue"])  # el que no trae id se descarta
        self.assertEqual(lib["albums"][0]["year"], 1959)
        self.assertEqual(lib["albums"][0]["artist"], "Miles Davis")
        self.assertEqual({t["id"] for t in lib["tracks"]}, {"v1", "v2"})
        self.assertEqual(next(t for t in lib["tracks"] if t["id"] == "v1")["album"], "Kind of Blue")
        self.assertEqual(lib["playlists"][0]["name"], "Jazz")
        self.assertTrue(all(c[1].get("order") in (None, "recently_added") for c in FakeYT.calls))

    def test_pide_lo_mas_reciente_primero(self):
        yu.library()
        self.assertEqual({c[0]: c[1]["order"] for c in FakeYT.calls if "order" in c[1]}, {"get_library_albums": "recently_added", "get_library_songs": "recently_added"})

    def test_sesion_vencida_pide_pegar_de_nuevo(self):
        FakeYT.fail = RuntimeError("Server returned HTTP 403: Forbidden. Please sign in")
        with self.assertRaises(ProviderError) as c:
            yu.library()
        self.assertEqual(c.exception.code, "reauth")
        self.assertIn("Pegá", c.exception.message)

    def test_error_raro_sugiere_actualizar_la_libreria(self):
        FakeYT.fail = KeyError("contents")
        with self.assertRaises(ProviderError) as c:
            yu.library()
        self.assertIn("actualizar", c.exception.message)


class Provider(Base):
    def provider(self):
        return ytmusic_source.YouTubeMusicProvider()

    def test_solo_no_oficial_cuenta_como_conectada_y_con_albumes(self):
        p = self.provider()
        self.assertFalse(p.status()["connected"])
        yu.STORE.save(GOOD)
        st = p.status()
        self.assertTrue(st["configured"] and st["connected"])
        self.assertTrue(st["capabilities"]["albums"])
        self.assertEqual(st["unofficial"]["connected"], True)
        self.assertFalse(st["official"]["connected"])
        self.assertEqual([a["title"] for a in p.library()["albums"]], ["Kind of Blue"])

    def test_la_oficial_completa_sin_duplicar(self):
        yu.STORE.save(GOOD)
        p = self.provider()
        official = {"albums": [], "tracks": [{"id": "v1", "title": "dup"}, {"id": "v9", "title": "Me gusta"}], "playlists": [{"id": "PL1"}, {"id": "PL2"}]}
        with mock.patch.object(p, "_official", return_value=True), mock.patch.object(p, "_official_library", return_value=official):
            lib = p.library()
        self.assertEqual(sorted(t["id"] for t in lib["tracks"]), ["v1", "v2", "v9"])
        self.assertEqual(sorted(x["id"] for x in lib["playlists"]), ["PL1", "PL2"])

    def test_si_falla_la_no_oficial_sigue_con_la_oficial_y_avisa(self):
        yu.STORE.save(GOOD)
        FakeYT.fail = RuntimeError("401")
        p = self.provider()
        official = {"albums": [], "tracks": [{"id": "v9"}], "playlists": []}
        with mock.patch.object(p, "_official", return_value=True), mock.patch.object(p, "_official_library", return_value=official):
            lib = p.library()
        self.assertEqual([t["id"] for t in lib["tracks"]], ["v9"])
        self.assertIn("Pegá", lib["note"])

    def test_desconectar_borra_las_dos_sesiones(self):
        yu.STORE.save(GOOD)
        p = self.provider()
        p.logout()
        self.assertFalse(yu.connected())
        self.assertFalse(p.status()["connected"])


class Install(Base):
    def test_no_instala_si_ya_esta(self):
        with mock.patch.object(yu.subprocess, "run") as run:
            yu.install()
        run.assert_not_called()

    def test_instala_en_la_carpeta_propia_y_nunca_sola(self):
        state = {"n": 0}

        def fake_lib():
            return None if state["n"] == 0 else types.SimpleNamespace()

        done = mock.Mock(returncode=0, stdout="", stderr="")

        def run(cmd, **kw):
            state["n"] = 1
            self.assertEqual(cmd[1:3], ["-m", "pip"])
            self.assertIn("--target", cmd)
            self.assertEqual(Path(cmd[cmd.index("--target") + 1]), yu.pylibs())
            return done
        with mock.patch.object(yu, "_lib", side_effect=fake_lib), mock.patch.object(yu.subprocess, "run", side_effect=run), \
                mock.patch.object(yu.threading, "Thread", side_effect=lambda target, daemon: types.SimpleNamespace(start=target)):
            yu.install()
        self.assertEqual(yu.install_state()["state"], "done")


if __name__ == "__main__":
    unittest.main()
