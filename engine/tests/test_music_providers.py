"""Las bibliotecas de Spotify y YouTube Music entran al catálogo de Música junto a los archivos y TIDAL."""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import catalog
import providers

LOCAL = {"tracks": [{"id": "L1", "album": "Kind of Blue", "artist": "Miles Davis", "title": "So What", "year": 1959,
                     "genre": "", "duration": 545, "rel": "a"}], "scanning": False, "scanned": 0, "total": 0}


def sp_album(i, title, artist, added):
    return {"id": i, "source": "spotify", "title": title, "artist": artist, "year": 2020, "addedAt": added}


class Merge(unittest.TestCase):
    def setUp(self):
        sp = {"albums": [sp_album("s1", "Kind of Blue", "Miles Davis", "2026-03-01T10:00:00Z"),
                         sp_album("s2", "Nuevo", "Alguien", "2026-05-01T10:00:00Z")],
              "tracks": [{"id": "st1", "source": "spotify", "title": "So What", "artist": "Miles Davis", "album": "Kind of Blue",
                          "duration": 545, "addedAt": "2026-03-01T10:00:00Z"}],
              "refreshing": False, "error": "", "fetchedAt": 1}
        tidal = [{"id": "t1", "title": "Viejo", "artist": "Otro", "year": 1, "savedAt": "2026-04-01T10:00:00+00:00"}]
        for p in (mock.patch.dict(catalog._ext, {"spotify": sp, "ytmusic": {"albums": [], "tracks": [], "refreshing": False, "error": "", "fetchedAt": None}}),
                  mock.patch.dict(catalog._tidal, {"albums": tidal, "tracks": []}),
                  mock.patch.object(catalog.library, "report", return_value=LOCAL)):
            p.start()
            self.addCleanup(p.stop)
        catalog._bump()

    def test_une_por_disco_y_lista_las_fuentes(self):
        kb = next(a for a in catalog.snapshot()["albums"] if a["title"] == "Kind of Blue")
        self.assertEqual(sorted(kb["sources"]), ["local", "spotify"])
        self.assertEqual(kb["extIds"], {"spotify": "s1"})
        self.assertEqual(kb["localIds"], ["L1"])

    def test_orden_de_guardado_mezcla_fuentes_por_fecha(self):
        titles = [a["title"] for a in catalog.query("albums")["items"]]
        self.assertEqual(titles, ["Nuevo", "Viejo", "Kind of Blue"])

    def test_filtra_por_fuente_y_cuenta(self):
        r = catalog.query("albums", source="spotify")
        self.assertEqual([a["title"] for a in r["items"]], ["Nuevo", "Kind of Blue"])
        self.assertEqual(r["facets"]["sources"]["spotify"], 2)
        self.assertEqual(r["facets"]["sources"]["ytmusic"], 0)
        self.assertEqual(r["status"]["providers"]["spotify"]["albums"], 2)

    def test_tema_guardado_se_une_al_local_por_artista_y_titulo(self):
        t = catalog.query("tracks")["items"][0]
        self.assertEqual(t["ids"], {"local": "L1"})
        self.assertEqual(t["refs"], {"spotify": "st1"})

    def test_sin_archivo_local_no_hay_portada_inventada(self):
        a = next(a for a in catalog.snapshot()["albums"] if a["title"] == "Nuevo")
        self.assertNotIn("artUrl", a)


class Refresh(unittest.TestCase):
    def provider(self, lib, connected=True):
        return mock.Mock(id="spotify", label="Spotify", configured=lambda: True, connected=lambda: connected, library=lambda: lib)

    def run_refresh(self, prov):
        done = threading.Event()
        with tempfile.TemporaryDirectory(prefix="José Pérez ") as d, mock.patch.object(catalog, "_dir", return_value=Path(d) / "catálogo"), \
                mock.patch.object(providers, "get", side_effect=lambda pid: prov if pid == "spotify" else mock.Mock(configured=lambda: False, connected=lambda: False)), \
                mock.patch.object(catalog, "enrich_genres", side_effect=done.set), \
                mock.patch.dict(catalog._ext, {}, clear=True):
            catalog.refresh_providers()
            if prov.connected():
                self.assertTrue(done.wait(5))
            st = dict(catalog._ext_state("spotify"))
            return st, (Path(d) / "catálogo" / "spotify.json").exists()

    def test_cuenta_conectada_se_guarda_en_disco(self):
        st, saved = self.run_refresh(self.provider({"albums": [sp_album("s1", "A", "B", None)], "tracks": []}))
        self.assertEqual(len(st["albums"]), 1)
        self.assertTrue(saved)

    def test_error_de_la_cuenta_queda_avisado_sin_romper(self):
        def boom():
            raise providers.ProviderError("reauth", "La sesión de Spotify venció.", 401)
        prov = self.provider(None)
        prov.library = boom
        done = threading.Event()
        with mock.patch.object(providers, "get", side_effect=lambda pid: prov if pid == "spotify" else mock.Mock(configured=lambda: False, connected=lambda: False)), \
                mock.patch.dict(catalog._ext, {}, clear=True):
            catalog.refresh_providers()
            for _ in range(100):
                if not catalog._ext_state("spotify")["refreshing"]:
                    break
                done.wait(0.05)
            self.assertIn("venció", catalog._ext_state("spotify")["error"])

    def test_desconectar_borra_la_copia_local(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(catalog, "_dir", return_value=Path(d)), \
                mock.patch.dict(catalog._ext, {"spotify": {"albums": [1], "tracks": [], "refreshing": False, "error": "", "fetchedAt": 1}}):
            (Path(d) / "spotify.json").write_text("{}")
            catalog.forget_provider("spotify")
            self.assertEqual(catalog._ext_state("spotify")["albums"], [])
            self.assertFalse((Path(d) / "spotify.json").exists())


if __name__ == "__main__":
    unittest.main()


class AlbumDetail(Merge):
    def test_disco_sin_tidal_se_pide_a_la_cuenta(self):
        catalog._album_cache.clear()
        fake = mock.Mock(album_tracks=lambda i: {"tracks": [{"id": "sv1", "title": "Uno", "artist": "Alguien", "duration": 100},
                                                            {"id": "sv2", "title": "Dos", "artist": "Alguien", "duration": 200}]})
        with mock.patch.object(providers, "get", return_value=fake):
            d = catalog.album_detail(catalog.album_key("Alguien", "Nuevo"))
        self.assertEqual([t["title"] for t in d["tracks"]], ["Uno", "Dos"])
        self.assertEqual(d["tracks"][0]["ids"], {})  # una referencia no es audio
        self.assertEqual(d["tracks"][0]["refs"], {"spotify": "sv1"})

    def test_si_la_cuenta_falla_muestra_lo_guardado(self):
        catalog._album_cache.clear()
        boom = mock.Mock(album_tracks=mock.Mock(side_effect=providers.ProviderError("no_session", "x")))
        with mock.patch.object(providers, "get", return_value=boom):
            d = catalog.album_detail(catalog.album_key("Miles Davis", "Kind of Blue"))
        self.assertEqual([t["title"] for t in d["tracks"]], ["So What"])
        self.assertEqual(d["tracks"][0]["ids"], {"local": "L1"})
        self.assertEqual(d["tracks"][0]["refs"], {"spotify": "st1"})


class Covers(unittest.TestCase):
    def test_solo_https_y_dominios_del_servicio(self):
        import extart
        self.assertTrue(extart.allowed("https://i.scdn.co/image/abc"))
        self.assertTrue(extart.allowed("https://yt3.googleusercontent.com/abc=w226-h226"))  # el que usa YouTube Music en la práctica
        self.assertTrue(extart.allowed("https://lh3.googleusercontent.com/abc"))
        for bad in ("http://i.scdn.co/x", "https://evil.example/x", "https://i.scdn.co.evil.example/x", "https://notgoogleusercontent.com/x", "https://googleusercontent.com.evil.example/x", "https://user@i.scdn.co/x", "file:///etc/passwd"):
            self.assertFalse(extart.allowed(bad), bad)
        self.assertIsNone(extart.url_for("https://evil.example/x"))
        self.assertTrue(extart.url_for("https://i.scdn.co/image/abc").startswith("/engine/extart?u="))

    def test_baja_una_vez_y_despues_sale_de_disco(self):
        import extart

        class R:
            headers = {"Content-Type": "image/jpeg"}
            def read(self, n=-1): return b"\xff\xd8jpg"
            def __enter__(self): return self
            def __exit__(self, *a): return False
        calls = []
        with tempfile.TemporaryDirectory() as d, mock.patch.object(extart, "_cache_dir", return_value=Path(d)), \
                mock.patch.object(extart, "_urlopen", side_effect=lambda *a, **k: (calls.append(1), R())[1]):
            self.assertEqual(extart.fetch("https://i.scdn.co/image/abc"), (b"\xff\xd8jpg", "image/jpeg"))
            self.assertEqual(extart.fetch("https://i.scdn.co/image/abc")[0], b"\xff\xd8jpg")
        self.assertEqual(len(calls), 1)

    def test_rechaza_lo_que_no_es_imagen(self):
        import extart

        class R:
            headers = {"Content-Type": "text/html"}
            def read(self, n=-1): return b"<html>"
            def __enter__(self): return self
            def __exit__(self, *a): return False
        with tempfile.TemporaryDirectory() as d, mock.patch.object(extart, "_cache_dir", return_value=Path(d)), \
                mock.patch.object(extart, "_urlopen", return_value=R()):
            self.assertIsNone(extart.fetch("https://i.scdn.co/image/abc"))


class Cache(unittest.TestCase):
    def test_portada_de_tidal_se_pide_una_sola_vez(self):
        import extart
        calls = []
        with tempfile.TemporaryDirectory() as d, mock.patch.object(extart, "_cache_dir", return_value=Path(d)):
            for _ in range(3):
                got = extart.cached_cover("tidal:1", lambda: (calls.append(1), b"\x89PNGdata")[1])
                self.assertEqual(got, b"\x89PNGdata")
        self.assertEqual(len(calls), 1)

    def test_biblioteca_de_tidal_sale_del_snapshot_sin_llamar_a_tidal(self):
        with mock.patch.dict(catalog._tidal, {"fetchedAt": 5, "albums": [{"id": "1"}], "tracks": [], "playlists": [{"id": "p"}]}):
            lib = catalog.tidal_library()
        self.assertEqual((len(lib["albums"]), len(lib["playlists"])), (1, 1))
        with mock.patch.dict(catalog._tidal, {"fetchedAt": None}):
            self.assertIsNone(catalog.tidal_library())

    def test_sesion_vencida_no_consulta_a_tidal_en_cada_sondeo(self):
        import tidal_source as ts
        calls = []

        class S:
            def check_login(self): return False

        fake = types_ns = type("M", (), {"Session": lambda: S()})
        with mock.patch.dict("sys.modules", {"tidalapi": fake}), mock.patch.object(ts, "_session", None), \
                mock.patch.object(ts, "_load_session", side_effect=lambda s: (calls.append(1), True)[1]), \
                mock.patch.object(ts.TIDAL_SESSION.__class__, "exists", return_value=True), \
                mock.patch.dict(ts._expired, {"at": 0.0, "error": None}):
            for _ in range(3):
                with self.assertRaises(ts.SourceError):
                    ts._get_session()
        self.assertEqual(len(calls), 1)


class TidalCovers(unittest.TestCase):
    def test_portada_sale_del_codigo_del_listado_sin_pedir_el_disco(self):
        import tidal_source as ts
        ts.remember_covers([{"id": 42, "cover": "3badd447-feb6-4a0e-8c29-b34fa339686d"}, {"id": 43}])
        seen = []

        class R:
            def read(self): return b"\x89PNG"
            def __enter__(self): return self
            def __exit__(self, *a): return False
        import urllib.request
        with mock.patch.object(ts, "_get_session", side_effect=AssertionError("no debe pedir el disco")), \
                mock.patch.object(urllib.request, "urlopen", side_effect=lambda req, timeout=0: (seen.append(req.full_url), R())[1]):
            self.assertEqual(ts.album_art("42"), b"\x89PNG")
        self.assertEqual(seen, ["https://resources.tidal.com/images/3badd447/feb6/4a0e/8c29/b34fa339686d/320x320.jpg"])

    def test_cover_url(self):
        import tidal_source as ts
        self.assertEqual(ts.cover_url("a-b-c", 80), "https://resources.tidal.com/images/a/b/c/80x80.jpg")

    def test_snapshot_viejo_se_completa_una_sola_vez_desde_el_listado(self):
        import threading
        import urllib.request
        import tidal_source as ts
        loads = []

        def fake_library():
            loads.append(1)
            ts.remember_covers([{"id": 7, "cover": "aaaa-bbbb"}])
            return {"albums": []}

        class R:
            def read(self): return b"img"
            def __enter__(self): return self
            def __exit__(self, *a): return False
        with mock.patch.dict(ts._covers, {}, clear=True), mock.patch.dict(ts._covers_filled, {"done": False}), \
                mock.patch.object(ts, "library", side_effect=fake_library), mock.patch.object(urllib.request, "urlopen", return_value=R()):
            out = []
            threads = [threading.Thread(target=lambda: out.append(ts.album_art("7"))) for _ in range(5)]
            [t.start() for t in threads]
            [t.join() for t in threads]
        self.assertEqual(out, [b"img"] * 5)  # los 5 pedidos en paralelo reciben la portada
        self.assertEqual(len(loads), 1)
