"""La sección Música trae TODO de TIDAL (paginado, del más recién guardado al más viejo) y ordena como se pide."""
import datetime
import importlib.util
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

import catalog
import tidal_source as ts

HAS_TIDALAPI = importlib.util.find_spec("tidalapi") is not None
DAY = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)


def make_albums(n):
    """n álbumes; el 0 es el más viejo y el n-1 el último guardado. Nombres que alfabéticamente van al revés."""
    return [NS(id=i, name=f"Disco {n - i:04d}", artist=NS(name=f"Artista {i % 7}"), year=2000, num_tracks=9,
               user_date_added=DAY + datetime.timedelta(days=i)) for i in range(n)]


class Favs:
    """Simula favoritos de TIDAL: tope de página del servidor (`cap`), order/orderDirection por fecha."""
    def __init__(self, albums, cap=50, ignore_offset=False):
        self.data, self.cap, self.ignore_offset, self.calls = albums, cap, ignore_offset, []

    def albums(self, limit=50, offset=0, order=None, order_direction=None):
        self.calls.append((limit, offset, order and order.value, order_direction and order_direction.value))
        rows = sorted(self.data, key=lambda a: a.user_date_added, reverse=(order_direction and order_direction.value) == "DESC")
        start = 0 if self.ignore_offset else offset
        return rows[start:start + min(limit, self.cap)]

    def tracks(self, **kw):
        return []

    def artists(self, **kw):
        return []


def fake_session(favs):
    return NS(user=NS(id=1, favorites=favs), request=NS(map_request=lambda *a, **k: []))


@unittest.skipUnless(HAS_TIDALAPI, "falta tidalapi")
class LibraryPagination(unittest.TestCase):
    def setUp(self):
        ts.clear_cache()

    def library(self, favs):
        with mock.patch.object(ts, "_get_session", return_value=fake_session(favs)), \
                mock.patch.object(ts, "_own_playlists", return_value=[]):
            return ts.library()

    def test_trae_mas_de_cien_y_en_orden_de_guardado(self):
        favs = Favs(make_albums(230))
        lib = self.library(favs)
        self.assertEqual(len(lib["albums"]), 230)
        self.assertEqual(lib["albums"][0]["id"], "229")      # el último guardado va primero
        self.assertEqual(lib["albums"][-1]["id"], "0")
        self.assertTrue(lib["albums"][0]["savedAt"] > lib["albums"][1]["savedAt"])
        self.assertTrue(all(c[2] == "DATE" and c[3] == "DESC" for c in favs.calls))

    def test_el_album_nuevo_aparece_tras_actualizar(self):
        albums = make_albums(100)
        favs = Favs(albums)
        self.assertEqual(len(self.library(favs)["albums"]), 100)
        albums.append(NS(id=999, name="Aaa recién guardado", artist=NS(name="Z"), year=2026, num_tracks=8,
                         user_date_added=DAY + datetime.timedelta(days=500)))
        ts.clear_cache()
        lib = self.library(favs)
        self.assertEqual((len(lib["albums"]), lib["albums"][0]["id"]), (101, "999"))

    def test_servidor_que_ignora_el_offset_no_cuelga(self):
        lib = self.library(Favs(make_albums(80), ignore_offset=True))
        self.assertEqual(len(lib["albums"]), 50)  # una sola página repetida: corta, no se repite

    def test_servidor_con_pagina_chica(self):
        self.assertEqual(len(self.library(Favs(make_albums(77), cap=20))["albums"]), 77)

    def test_paged_y_vacio(self):
        data = list(range(130))
        self.assertEqual(ts.paged(lambda n, o: data[o:o + min(n, 40)], key=lambda x: x), data)
        self.assertEqual(ts.paged(lambda n, o: [], key=lambda x: x), [])


class CatalogOrder(unittest.TestCase):
    def setUp(self):
        tidal = [{"id": str(i), "title": t, "artist": a, "year": 2000, "tracks": 5, "savedAt": f"2026-01-0{9 - i}"}
                 for i, (a, t) in enumerate([("Zeta", "Bravo"), ("Alfa", "Zulu"), ("Mika", "Alba")])]  # en orden de guardado
        local = {"tracks": [{"id": "L1", "album": "Local solo", "artist": "Beta", "title": "t", "year": 1999,
                             "genre": "", "duration": 1, "rel": "a"}], "scanning": False, "scanned": 0, "total": 0}
        for p in (mock.patch.dict(catalog._tidal, {"albums": tidal, "tracks": []}),
                  mock.patch.object(catalog.library, "report", return_value=local)):
            p.start()
            self.addCleanup(p.stop)
        catalog._bump()

    def titles(self, sort=None):
        kw = {"sort": sort} if sort else {}
        return [i["title"] for i in catalog.query("albums", **kw)["items"]]

    def test_por_defecto_es_orden_de_guardado(self):
        self.assertEqual(self.titles(), ["Bravo", "Zulu", "Alba", "Local solo"])

    def test_alfabetico_y_por_artista(self):
        self.assertEqual(self.titles("alpha"), ["Alba", "Bravo", "Local solo", "Zulu"])
        self.assertEqual(self.titles("artist"), ["Zulu", "Local solo", "Alba", "Bravo"])
        self.assertEqual(self.titles("raro"), self.titles("saved"))

    def test_paginado_conserva_el_orden(self):
        page = [i["title"] for i in catalog.query("albums", limit=2, offset=2)["items"]]
        self.assertEqual(page, ["Alba", "Local solo"])


class RefreshSurvivesBrokenPlaylist(unittest.TestCase):
    def test_una_playlist_rota_no_tira_la_actualizacion(self):
        lib = {"tracks": [], "albums": [{"id": "1", "title": "A", "artist": "B", "year": 1, "tracks": 1, "savedAt": None}],
               "artists": [], "playlists": [{"id": "p1", "name": "Rota"}, {"id": "p2", "name": "Ok"}]}

        def pl(pid):
            if pid == "p1":
                raise RuntimeError("404")
            return {"tracks": [{"id": "t", "title": "x", "artist": "y", "album": "z", "duration": 1}]}
        done = threading.Event()
        with tempfile.TemporaryDirectory(prefix="José Pérez ") as d, mock.patch.object(catalog, "_dir", return_value=Path(d) / "catálogo"), \
                mock.patch.object(ts, "library", return_value=lib), mock.patch.object(ts, "playlist_tracks", side_effect=pl), \
                mock.patch.object(ts, "clear_cache"), mock.patch.object(catalog, "enrich_genres", side_effect=done.set), \
                mock.patch.dict(catalog._tidal, {"albums": [], "tracks": [], "refreshing": False, "error": ""}):
            catalog.refresh_tidal()
            self.assertTrue(done.wait(5))
            self.assertEqual(len(catalog._tidal["albums"]), 1)
            self.assertEqual(catalog._tidal["tracks"][0]["collections"], ["Ok"])
            self.assertIn("1 playlist", catalog._tidal["error"])


if __name__ == "__main__":
    unittest.main()
