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
        self.assertEqual(t["ids"], {"local": "L1", "spotify": "st1"})

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
