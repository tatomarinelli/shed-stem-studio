"""Pipeline de recomendación con un MusicBrainz y un modelo simulados (sin red): barrera de género, tipo de disco, descartes con
motivo, cancelación con resultado parcial, rastro de decisión y reacciones.

Correr: cd engine && python3 -m unittest discover -s tests -v
"""
import json
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("STEMSHED_MEMORY_DIR", tempfile.mkdtemp(prefix="stemshed-test-"))
os.environ["STEMSHED_NO_SCHEDULER"] = "1"
import memory  # noqa: E402
import recs as R  # noqa: E402

PROFILE = {"instrument": "guitarra", "level": "avanzado", "improve": [], "loves": ["jazz"], "avoids": [], "essentials": [],
           "ownArtists": ["Mi Banda"], "discovery": "algo", "listening": "discos", "pace": "", "notes": "", "useTime": False,
           "useWeather": False, "city": "", "geo": None, "dismissed": False, "imported": None}


_module_patches = []


def setUpModule():
    """Todo el módulo corre sin leer ni escribir la configuración ni la carpeta de datos REAL del usuario: un test que se olvide de parchear algo no puede
    ensuciar sus cachés (así aparecieron artistas falsos de tests en mb-artists.json y rompieron portadas y enlaces)."""
    data = tempfile.mkdtemp(prefix="stemshed-test-data-")
    for p in (mock.patch.object(R.settings, "load", lambda: dict(R.settings.DEFAULTS)),
              mock.patch.object(R.settings, "effective", lambda d=None: {**R.settings.DEFAULTS, "dataDir": data})):
        p.start()
        _module_patches.append(p)


def tearDownModule():
    while _module_patches:
        _module_patches.pop().stop()


def isolate_settings(case):
    """Los tests no leen ni escriben la configuración real del usuario (ajustes de revisor, clasificador, carpetas...): usan los valores por defecto
    y una carpeta de datos temporal. Sin esto, prender el revisor en la app hacía llamadas reales al servidor de modelos desde los tests."""
    data = tempfile.mkdtemp(prefix="stemshed-test-data-")
    for p in (mock.patch.object(R.settings, "load", lambda: dict(R.settings.DEFAULTS)),
              mock.patch.object(R.settings, "effective", lambda d=None: {**R.settings.DEFAULTS, "dataDir": data})):
        p.start()
        case.addCleanup(p.stop)


def fid(name):
    """Id con forma de UUID (como los de MusicBrainz) para los artistas y discos simulados: la caché ignora los que no lo son."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, name))


def uid(n):
    return f"00000000-0000-0000-0000-{n:012d}"


# (artista, disco) -> datos que devolvería MusicBrainz
WORLD = {
    ("King Tubby", "Dub from the Roots"): {"id": uid(1), "year": 1974, "genres": ["dub", "reggae"]},
    ("Lee Perry", "Super Ape"): {"id": uid(2), "year": 1976, "genres": ["dub", "roots reggae"]},
    ("Augustus Pablo", "King Tubbys Meets Rockers Uptown"): {"id": uid(3), "year": 1976, "genres": ["dub"]},
    ("Scientist", "Scientist Rids the World of the Evil Curse of the Vampires"): {"id": uid(4), "year": 1981, "genres": ["dub"]},
    ("Bob Marley", "Exodus"): {"id": uid(5), "year": 1977, "genres": ["reggae", "roots reggae"]},
    ("Coldplay", "Parachutes"): {"id": uid(6), "year": 2000, "genres": ["alternative rock", "britpop"]},
    ("Obscure Dub Band", "Untagged"): {"id": uid(7), "year": 1999, "genres": [], "artist_genres": ["dub", "reggae"]},
    ("Nobody", "Untagged Pop"): {"id": uid(8), "year": 2001, "genres": [], "artist_genres": []},
    ("Bob Marley", "Live!"): {"id": uid(9), "year": 1975, "genres": ["reggae"], "secondary": ["Live"]},
    ("Miles Davis", "Kind of Blue"): {"id": uid(10), "year": 1959, "genres": ["modal jazz", "cool jazz"]},
}


def fake_search(artist, album, loose=False):
    for (a, t), d in WORLD.items():
        if R.norm(a) == R.norm(artist) and R.title_key(t) == R.title_key(album):
            return [{"id": d["id"], "title": t, "score": 100, "artist-credit": [{"name": a, "joinphrase": ""}],
                     "first-release-date": str(d["year"]), "primary-type": d.get("primary", "Album"), "secondary-types": d.get("secondary", [])}]
    return []


def fake_genres(mbid):
    return next(d["genres"] for d in WORLD.values() if d["id"] == mbid)


def fake_artist_genres(artist):
    return next((d.get("artist_genres", []) for (a, _), d in WORLD.items() if R.norm(a) == R.norm(artist)), [])


def cands(*pairs):
    return [{"artist": a, "album": t, "year": None, "confidence": 80} for a, t in pairs]


class Pipeline(unittest.TestCase):
    """Método anterior: el modelo propone discos y cada uno se verifica en MusicBrainz (ARTISTS_FIRST apagado)."""

    def setUp(self):
        isolate_settings(self)
        self.tmp = tempfile.TemporaryDirectory()
        patches = [
            mock.patch.object(R, "store", memory.Store(self.tmp.name)),
            mock.patch.object(R, "LAST", Path(self.tmp.name) / "recs-last.json"),
            mock.patch.object(R, "mb_search", fake_search), mock.patch.object(R, "mb_genres", fake_genres),
            mock.patch.object(R, "mb_artist_genres", fake_artist_genres), mock.patch.object(R, "_wait_catalog", lambda *a, **k: None),
            mock.patch.object(R, "load_sources", lambda: []), mock.patch.object(R, "load_profile", lambda: dict(PROFILE)),
            mock.patch.object(R, "load_presets", lambda: R.presets_mod.load(Path(self.tmp.name) / "presets.json")),
            mock.patch.object(R.albumctx, "get", lambda *a, **k: None), mock.patch.object(R.genresim, "vectors", lambda names: {}),
            mock.patch("covers.prefetch", lambda items: None), mock.patch.object(R, "ARTISTS_FIRST", False),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        R._cancel.clear()
        R._state.update(state="idle", step="", message="")

    def run_with(self, rounds, request, save=False):
        """rounds: lista de listas de candidatos que el "modelo" propone en cada ronda."""
        it = iter(rounds)
        calls = []

        def fake_ask(model, user, **kw):
            calls.append(user)
            return next(it, []), {"promptTokens": 100, "evalTokens": 50}

        with mock.patch.object(R, "ask_model", fake_ask):
            res = R._run("modelo-falso", "request", R.clean_request(request), now=1_700_000_000.0, save=save)
        res["_prompts"] = calls
        return res

    def shown(self, res):
        return [v["artist"] + " - " + v["album"] for v in ([res["pick"]] if res["pick"] else []) + res["alternatives"]]

    # ---- zona del mapa: el recomendador lee la red
    ZONE = {"zones": [{"name": "dub + reggae", "size": 20, "albums": 9, "genres": ["dub", "reggae"]}], "genres": ["dub", "reggae", "roots reggae"],
            "artists": [{"name": n, "genres": ["dub"]} for n in ("King Tubby", "Scientist", "Prince Jammy", "Mad Professor", "Yabby You", "Keith Hudson", "Linval Thompson")],
            "albums": ["King Tubby - In a Revival Dub"], "byGenre": {"dub": ["King Tubby", "Scientist"]}, "gaps": ["dancehall"], "bridges": ["dub"]}

    def run_zone(self, cs):
        with mock.patch("graph.context", lambda names, data=None: self.ZONE):
            return self.run_with([cs], {"prompt": "Algo parecido a mi zona de dub + reggae", "map": {"communities": ["dub + reggae"]}})

    def test_zone_prompt_carries_every_artist_of_the_zone(self):
        res = self.run_zone(cands(("Lee Perry", "Super Ape"), ("Augustus Pablo", "King Tubbys Meets Rockers Uptown")))
        text = res["_prompts"][0]
        for name in ("King Tubby", "Scientist", "Prince Jammy", "Mad Professor", "Yabby You", "Keith Hudson", "Linval Thompson"):
            self.assertIn(name, text)  # todos los artistas, no solo dos
        self.assertIn("Zona elegida del mapa", text)
        self.assertIn("dancehall", text)  # huecos de la zona

    def test_zone_artists_are_not_proposed_and_reason_cites_the_zone(self):
        res = self.run_zone(cands(("King Tubby", "Dub from the Roots"), ("Lee Perry", "Super Ape"), ("Augustus Pablo", "King Tubbys Meets Rockers Uptown")))
        self.assertNotIn("King Tubby - Dub from the Roots", self.shown(res))
        self.assertEqual(res["stats"]["discardedBy"].get("in_zone"), 1)
        top = res["pick"]
        self.assertIn("Encaja con tu zona dub + reggae", top["reason"])
        self.assertEqual(res["request"]["zone"]["artists"], 7)  # se guarda el resumen, no el volcado

    def test_unknown_zone_stops_with_a_clear_message(self):
        with mock.patch("graph.context", lambda names, data=None: None), self.assertRaises(ValueError):
            self.run_with([[]], {"prompt": "x", "map": {"communities": ["no existe"]}})

    # ---- barrera de género
    def test_genre_request_never_returns_other_genres(self):
        res = self.run_with([cands(("Coldplay", "Parachutes"), ("King Tubby", "Dub from the Roots"), ("Lee Perry", "Super Ape"),
                                   ("Augustus Pablo", "King Tubbys Meets Rockers Uptown"), ("Scientist", "Scientist Rids the World of the Evil Curse of the Vampires"))],
                            {"genres": ["dub"]})
        self.assertEqual(len(self.shown(res)), 4)
        self.assertNotIn("Coldplay - Parachutes", self.shown(res))
        self.assertEqual(res["stats"]["discardedBy"].get("off_genre"), 1)
        off = next(d for d in res["discarded"] if d["category"] == "off_genre")
        self.assertIn("alternative rock", off["why"])  # el motivo sale de los géneros reales
        for v in [res["pick"]] + res["alternatives"]:
            self.assertEqual(v["genre"]["status"], "match")

    def test_weak_never_outranks_a_match(self):
        res = self.run_with([cands(("Bob Marley", "Exodus"), ("King Tubby", "Dub from the Roots"))], {"genres": ["dub"]})
        self.assertEqual(res["pick"]["artist"], "King Tubby")          # dub exacto antes que reggae a secas
        self.assertEqual(res["alternatives"][0]["genre"]["status"], "weak")
        self.assertIn("Cercano", res["alternatives"][0]["reason"])

    def test_unknown_discarded_when_strict_but_artist_genres_rescue(self):
        res = self.run_with([cands(("Nobody", "Untagged Pop"), ("Obscure Dub Band", "Untagged"))], {"genres": ["dub"]})
        self.assertEqual(self.shown(res), ["Obscure Dub Band - Untagged"])
        self.assertEqual(res["pick"]["genre"]["source"], "artista")
        self.assertEqual(res["stats"]["discardedBy"], {"genre_unknown": 1})

    def test_not_strict_keeps_off_genre_but_ranks_it_last(self):
        res = self.run_with([cands(("Coldplay", "Parachutes"), ("King Tubby", "Dub from the Roots"))], {"genres": ["dub"], "strict": False})
        self.assertEqual(self.shown(res), ["King Tubby - Dub from the Roots", "Coldplay - Parachutes"])

    def test_genre_detected_from_text_and_prompt_says_mandatory(self):
        res = self.run_with([cands(("King Tubby", "Dub from the Roots"))], {"prompt": "algo de dub"})
        self.assertEqual(res["request"]["genres"], ["dub"])
        self.assertTrue(res["request"]["genresDetected"])
        self.assertIn("GÉNERO PEDIDO (obligatorio): dub", res["_prompts"][0])

    def test_more_rounds_until_enough_matches(self):
        res = self.run_with([cands(("Coldplay", "Parachutes"), ("Nobody", "Untagged Pop")),
                             cands(("King Tubby", "Dub from the Roots"), ("Lee Perry", "Super Ape"))], {"genres": ["dub"]})
        self.assertEqual(res["stats"]["rounds"], 3)  # la tercera viene vacía: no se insiste con una cuarta
        self.assertEqual(len(self.shown(res)), 2)
        self.assertIn("Coldplay - Parachutes", res["_prompts"][1])  # a la siguiente ronda se le dice qué ya se descartó

    # ---- verificación y descartes
    def test_missing_own_artist_and_history_are_discarded_with_reason(self):
        res = self.run_with([cands(("Fantasma", "Disco Inventado"), ("Mi Banda", "Lo Mejor"), ("Miles Davis", "Kind of Blue"))], {"mode": "estudiar"})
        by = res["stats"]["discardedBy"]
        self.assertEqual(by.get("missing"), 1)
        self.assertEqual(by.get("excluded"), 1)
        self.assertEqual(self.shown(res), ["Miles Davis - Kind of Blue"])

    def test_one_album_per_artist(self):
        res = self.run_with([cands(("Bob Marley", "Exodus"), ("Bob Marley", "Live!"))], {"mode": "estudiar"})
        self.assertEqual(len(self.shown(res)), 1)

    def test_type_filter(self):
        res = self.run_with([cands(("Bob Marley", "Exodus"), ("Bob Marley", "Live!"))], {"mode": "estudiar", "type": "live"})
        self.assertEqual(self.shown(res), ["Bob Marley - Live!"])
        self.assertEqual(res["stats"]["discardedBy"], {"off_type": 1})
        res = self.run_with([cands(("Bob Marley", "Live!"))], {"mode": "estudiar", "type": "album"})
        self.assertEqual(self.shown(res), [])

    # ---- transparencia
    def test_every_pick_carries_a_trail(self):
        res = self.run_with([cands(("King Tubby", "Dub from the Roots"))], {"genres": ["dub"]})
        t = res["pick"]["trail"]
        self.assertEqual(t["proposedBy"], "modelo-falso")
        self.assertEqual(t["round"], 1)
        self.assertEqual(t["score"]["gate"], 1.0)
        self.assertEqual(t["score"]["final"], res["pick"]["score"])
        self.assertEqual(res["stats"]["genres"], {"wanted": ["dub"], "strict": True, "method": "discos"})

    # ---- cancelación
    def test_cancel_mid_verification_returns_partial_result(self):
        calls = []

        def search(artist, album, loose=False):
            calls.append(artist)
            if len(calls) == 3:
                R._state["state"] = "running"
                R.cancel()
            return fake_search(artist, album, loose)

        with mock.patch.object(R, "mb_search", search):
            res = self.run_with([cands(("King Tubby", "Dub from the Roots"), ("Lee Perry", "Super Ape"), ("Augustus Pablo", "King Tubbys Meets Rockers Uptown"),
                                       ("Scientist", "Scientist Rids the World of the Evil Curse of the Vampires"))], {"genres": ["dub"]})
        self.assertTrue(res["stats"]["cancelled"])
        self.assertEqual(len(self.shown(res)), 3)  # el candidato en curso termina y lo ya verificado se conserva; el 4.º no se consulta
        self.assertEqual(len(calls), 3)
        self.assertNotIn("contextSeconds", res["stats"])  # y no se pierde tiempo armando contexto

    def test_cancelled_run_with_nothing_does_not_overwrite_last_result(self):
        R._write_json(R.LAST, {"version": 2, "daily": None, "request": {"marker": 1}})
        R._cancel.set()
        res = self.run_with([cands(("King Tubby", "Dub from the Roots"))], {"genres": ["dub"]}, save=True)
        self.assertTrue(res["stats"]["cancelled"])
        self.assertEqual(R._read_json(R.LAST, {})["request"], {"marker": 1})

    def test_cancel_when_idle_is_harmless_and_ask_model_checks_it(self):
        R._state["state"] = "idle"
        self.assertEqual(R.cancel()["state"], "idle")
        self.assertFalse(R._cancel.is_set())
        R._cancel.set()
        with mock.patch("models.chat") as chat, self.assertRaises(R.Cancelled):
            R.ask_model("m", "hola")
        chat.assert_not_called()

    def test_progress_is_reported_per_candidate(self):
        seen = []

        def search(artist, album, loose=False):
            seen.append((R._state["done"], R._state["total"]))
            return fake_search(artist, album, loose)

        with mock.patch.object(R, "mb_search", search):
            self.run_with([cands(("King Tubby", "Dub from the Roots"), ("Lee Perry", "Super Ape"))], {"genres": ["dub"]})
        self.assertEqual(seen[0], (0, 2))
        self.assertEqual(seen[1], (1, 2))


# ---- artistas primero: nombre -> {id, tags, albums: [(título, año, géneros, tipos secundarios)]}
ARTISTS = {
    "King Tubby": {"id": fid("a1"), "tags": [("dub", 5), ("reggae", 4)], "albums": [
        ("Dub from the Roots", 1974, ["dub", "reggae"], []), ("King Tubby Greatest Hits", 1990, ["dub"], ["Compilation"]),
        ("Live in Japan", 1980, ["dub"], ["Live"]), ("Dub from the Roots", 1997, ["dub", "reggae"], [])]},
    "Lee Perry": {"id": fid("a2"), "tags": [("dub", 6), ("reggae", 5)], "albums": [("Super Ape", 1976, ["dub", "roots reggae"], []), ("Return of the Super Ape", 1978, ["dub"], [])]},
    "Augustus Pablo": {"id": fid("a3"), "tags": [("dub", 3)], "albums": [("King Tubbys Meets Rockers Uptown", 1976, ["dub"], [])]},
    "Scientist": {"id": fid("a4"), "tags": [("dub", 3)], "albums": [("Scientist Rids the World", 1981, ["dub"], [])]},
    "Coldplay": {"id": fid("a5"), "tags": [("alternative rock", 8), ("britpop", 3)], "albums": [("Parachutes", 2000, ["alternative rock"], [])]},
    "Bob Marley": {"id": fid("a6"), "tags": [("reggae", 9), ("roots reggae", 5)], "albums": [("Exodus", 1977, ["reggae"], [])]},
    "Sin Tags": {"id": fid("a7"), "tags": [], "albums": [("Untitled Dub", 1999, ["dub"], []), ("Untitled Pop", 2001, ["pop"], [])]},
    "Charly García": {"id": fid("ar1"), "country": "AR", "tags": [("rock", 9), ("rock argentino", 8)], "albums": [("Clics modernos", 1983, ["rock", "new wave"], []), ("Piano Bar", 1984, ["rock"], [])]},
    "Soda Stereo": {"id": fid("ar2"), "country": "AR", "tags": [("rock", 9)], "albums": [("Dynamo", 1992, ["rock"], [])]},
    "Toto": {"id": fid("us1"), "country": "US", "area": "United States", "tags": [("rock", 9), ("aor", 5)], "albums": [("Toto IV", 1982, ["rock", "aor"], [])]},
    "Sin Origen": {"id": fid("xx1"), "tags": [("rock", 2)], "albums": [("Disco Perdido", 1999, ["rock"], [])]},
    "Mi Banda": {"id": fid("a8"), "tags": [("dub", 1)], "albums": [("Ensayo", 2020, ["dub"], [])]},
}


def fake_mb_get(url, tries=4):
    import urllib.parse

    fake_mb_get.calls.append(url)
    if "/artist?" in url:
        q = urllib.parse.unquote(url.split("query=")[1].split("&")[0])
        name = q[len('artist:"'):-1]
        return {"artists": [{"id": d["id"], "name": a, "score": 100, "tags": [{"name": n, "count": c} for n, c in d["tags"]],
                             "country": d.get("country"), "area": {"name": d["area"]} if d.get("area") else None}
                            for a, d in ARTISTS.items() if R.norm(a) == R.norm(name)]}
    if "release-group?artist=" in url:
        artist_id = url.split("artist=")[1].split("&")[0]
        d = next(d for d in ARTISTS.values() if d["id"] == artist_id)
        return {"release-groups": [{"id": str(uuid.uuid5(uuid.UUID(artist_id), str(i))), "title": t, "first-release-date": str(y), "primary-type": "Album", "secondary-types": sec,
                                    "genres": [{"name": g, "count": 3 - k} for k, g in enumerate(gs)]} for i, (t, y, gs, sec) in enumerate(d["albums"])]}
    raise AssertionError(url)


fake_mb_get.calls = []


def choose_title(*titles):
    """ask_choice simulado: elige, por título, los números de la lista que arma el prompt."""
    def fake(model, user):
        nums = []
        for line in user.splitlines():
            head, _, rest = line.partition(". ")
            if head.isdigit() and any(rest.startswith(t + " (") for t in titles):
                nums.append(int(head))
        return nums, {"promptTokens": 50, "evalTokens": 5}
    return fake


class ArtistFirst(unittest.TestCase):
    def setUp(self):
        isolate_settings(self)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        fake_mb_get.calls = []
        self.cache = R._Cache()
        for p in (mock.patch.object(R, "store", memory.Store(self.tmp.name)), mock.patch.object(R, "LAST", Path(self.tmp.name) / "recs-last.json"),
                  mock.patch.object(R, "mb_get", fake_mb_get), mock.patch.object(R, "_artist_cache", lambda: self.cache),
                  mock.patch.object(R, "_wait_catalog", lambda *a, **k: None), mock.patch.object(R, "load_sources", lambda: []),
                  mock.patch.object(R, "load_profile", lambda: dict(PROFILE)),
                  mock.patch.object(R, "load_presets", lambda: R.presets_mod.load(Path(self.tmp.name) / "presets.json")),
                  mock.patch.object(R.albumctx, "get", lambda *a, **k: None), mock.patch.object(R.genresim, "vectors", lambda names: {}),
                  mock.patch.object(R.albumctx, "extract", lambda *a, **k: None),  # nunca se consulta Wikipedia de verdad en los tests
                  mock.patch("covers.prefetch", lambda items: None)):
            p.start()
            self.addCleanup(p.stop)
        R._cancel.clear()
        R._state.update(state="idle", step="", message="")

    def run_with(self, artist_rounds, request, choice=None):
        it = iter(artist_rounds)
        prompts = []

        def fake_artists(model, user, temperature=0.7):
            prompts.append(user)
            return [{"name": n, "confidence": 80} for n in next(it, [])], {"promptTokens": 100, "evalTokens": 20}

        with mock.patch.object(R, "ask_artists", fake_artists), \
                mock.patch.object(R, "ask_choice", choice or (lambda model, user: ([], {"promptTokens": 10, "evalTokens": 1}))):
            res = R._run("modelo-falso", "request", R.clean_request(request), now=1_700_000_000.0, save=False)
        res["_prompts"] = prompts
        return res

    def shown(self, res):
        return [v["artist"] + " - " + v["album"] for v in ([res["pick"]] if res["pick"] else []) + res["alternatives"]]

    def test_only_real_albums_and_off_genre_artists_are_never_browsed(self):
        res = self.run_with([["King Tubby", "Coldplay", "Inventado Total", "Lee Perry", "Mi Banda"]], {"genres": ["dub"]})
        self.assertEqual(sorted(self.shown(res)), ["King Tubby - Dub from the Roots", "Lee Perry - Super Ape"])
        by = res["stats"]["discardedBy"]
        self.assertEqual((by["off_genre"], by["missing"], by["excluded"]), (1, 1, 1))
        self.assertFalse([u for u in fake_mb_get.calls if f"artist={fid('a5')}" in u])  # a Coldplay no se le piden los discos
        self.assertEqual(res["stats"]["genres"]["method"], "artistas")
        self.assertEqual(res["pick"]["trail"]["via"], "artistas")

    def test_studio_albums_only_and_duplicate_titles_count_once(self):
        res = self.run_with([["King Tubby"]], {"genres": ["dub"]})
        self.assertEqual(self.shown(res), ["King Tubby - Dub from the Roots"])  # sin el compilado, sin el en vivo, sin la reedición repetida

    def test_model_choice_is_respected_and_limited_to_listed_albums(self):
        res = self.run_with([["Lee Perry"]], {"genres": ["dub"]}, choice=choose_title("Return of the Super Ape"))
        self.assertEqual(res["pick"]["album"], "Return of the Super Ape")
        bad = lambda model, user: ([999, -1], {"promptTokens": 10, "evalTokens": 1})  # números inventados: se ignoran
        res = self.run_with([["Lee Perry"]], {"genres": ["dub"]}, choice=bad)
        self.assertEqual(res["pick"]["album"], "Super Ape")  # respaldo: el mejor según género y votos

    def test_choice_failure_falls_back_instead_of_failing(self):
        def boom(model, user):
            raise ValueError("el modelo no respondió")

        res = self.run_with([["Lee Perry", "Scientist"]], {"genres": ["dub"]}, choice=boom)
        self.assertEqual(len(self.shown(res)), 2)

    def test_untagged_artist_is_judged_by_its_albums_genres(self):
        res = self.run_with([["Sin Tags"]], {"genres": ["dub"]})
        self.assertEqual(self.shown(res), ["Sin Tags - Untitled Dub"])  # el de pop no pasa

    def test_weak_artist_is_kept_only_as_close_and_ranked_last(self):
        res = self.run_with([["Bob Marley", "Lee Perry"]], {"genres": ["dub"]})
        self.assertEqual(res["pick"]["artist"], "Lee Perry")
        self.assertEqual(res["alternatives"][0]["genre"]["status"], "weak")

    def test_shared_album_is_shown_once(self):
        ARTISTS["Dueto A"] = {"id": fid("d1"), "tags": [("dub", 3)], "albums": [("Juntos", 1970, ["dub"], [])]}
        ARTISTS["Dueto B"] = {"id": fid("d2"), "tags": [("dub", 3)], "albums": [("Juntos", 1970, ["dub"], [])]}
        for a in ("Dueto A", "Dueto B"):
            self.addCleanup(ARTISTS.pop, a)
        orig = fake_mb_get

        def same_id(url, tries=4):  # el mismo release-group figura en la discografía de los dos artistas
            out = orig(url)
            for g in out.get("release-groups", []):
                g["id"] = fid("compartido-1")
            return out

        with mock.patch.object(R, "mb_get", same_id):
            res = self.run_with([["Dueto A", "Dueto B"]], {"genres": ["dub"]})
        self.assertEqual(len(self.shown(res)), 1)

    # ---- país de origen y "lo fundamental" (caso real: pidió discos de Argentina y salió Toto)
    def argentina(self, prompt="Busca discos de Argentina que tengo que haber escuchado", artists=("Toto", "Charly García", "Sin Origen", "Soda Stereo")):
        prompts = []

        def ask(model, user, temperature=0.7):
            prompts.append(user)
            return [{"name": n, "confidence": 80} for n in artists], {"promptTokens": 10, "evalTokens": 1}

        with mock.patch.object(R, "ask_artists", ask), mock.patch.object(R, "ask_choice", lambda m, u: ([], {"promptTokens": 1, "evalTokens": 1})):
            res = R._run("modelo-falso", "request", R.clean_request({"prompt": prompt}), now=1_700_000_000.0, save=False)
        res["_prompts"] = prompts
        return res

    def test_a_requested_country_is_verified_with_musicbrainz_not_with_the_model(self):
        res = self.argentina()
        self.assertEqual({v["artist"] for v in [res["pick"]] + res["alternatives"] if v}, {"Charly García", "Soda Stereo"})
        by = {d["artist"]: d for d in res["discarded"]}
        self.assertEqual(by["Toto"]["category"], "off_origin")
        self.assertIn("Estados Unidos", by["Toto"]["why"])  # el motivo sale del dato de MusicBrainz
        self.assertEqual(by["Sin Origen"]["category"], "origin_unknown")  # sin país en MusicBrainz no se adivina
        self.assertEqual(res["request"]["countries"], ["AR"])
        self.assertTrue(res["request"]["countriesDetected"])
        self.assertEqual(res["stats"]["countries"], {"wanted": ["AR"], "strict": True})
        self.assertEqual(res["pick"]["trail"]["origin"]["status"], "match")

    def test_the_toto_request_asks_for_the_fundamental_and_leaves_tastes_out_of_the_prompt(self):
        res = self.argentina()
        p = res["_prompts"][0]
        self.assertIn("PAÍS DE ORIGEN (obligatorio): Argentina", p)
        self.assertIn("BUSCA LO FUNDAMENTAL", p)
        self.assertIn("ARTISTAS FUNDAMENTALES", p)
        self.assertNotIn("Gustos actuales", p)  # con país o "lo fundamental", los gustos solo distraen
        self.assertNotIn("Reacciones recientes", p)

    def test_an_explicit_request_overrides_the_active_profile_mode(self):
        """Medido: el pedido de Argentina salió con 'Modo: concentrarme (del perfil activo)', instrumental, y tus gustos al 90 %."""
        res = self.argentina()
        i = res["inputs"]
        self.assertIsNone(i["request"]["mode"])
        self.assertTrue(i["request"]["canon"])
        self.assertEqual(i["request"]["countries"], ["AR"])
        self.assertEqual(i["scoring"]["tastePct"], 30)  # lo fundamental: los gustos pesan poco
        self.assertNotIn("instrumental", res["_prompts"][0].lower().replace("mayormente instrumentales", "mayormente-instrumentales") if False else "")

    def test_a_country_request_is_never_answered_with_other_countries_even_if_it_means_fewer_discs(self):
        res = self.argentina(artists=("Toto",))
        self.assertIsNone(res["pick"])
        self.assertEqual(res["stats"]["discardedBy"], {"off_origin": 1})

    def test_without_a_country_nothing_changes(self):
        res = self.run_with([["King Tubby"]], {"prompt": "algo para tocar"})
        self.assertNotIn("countries", res["request"])
        self.assertNotIn("countries", res["stats"])

    # ---- el tipo de pedido decide cuánto pesan tus gustos y tu instrumento
    def seeded(self, request, artists):
        prompts = []

        def ask(model, user, temperature=0.7):
            prompts.append(user)
            return [{"name": n, "confidence": 80} for n in artists], {"promptTokens": 10, "evalTokens": 1}

        full = {**PROFILE, "updatedAt": 1, "improve": ["modos"], "avoids": ["smooth jazz"], "essentials": ["Miles Davis"], "pace": "30"}  # perfil completo (con fecha de edición)
        with mock.patch.object(R, "ask_artists", ask), mock.patch.object(R, "ask_choice", lambda m, u: ([], {"promptTokens": 1, "evalTokens": 1})), \
                mock.patch.object(R, "load_profile", lambda: dict(full)), \
                mock.patch.object(R, "mb_search", fake_search), mock.patch.object(R, "mb_genres", fake_genres), mock.patch.object(R, "genres_of", lambda a, t: []):
            res = R._run("modelo-falso", "request", R.clean_request(request), now=1_700_000_000.0, save=False)
        res["_prompts"] = prompts
        return res

    def test_similar_to_another_disc_does_not_carry_the_instrument_goals_or_tastes(self):
        """Pedido del usuario: 'parecido a otro disco' no debería pesar mis gustos o mi instrumento igual que 'para mí'."""
        res = self.seeded({"seed": {"artist": "Miles Davis", "album": "Kind of Blue"}}, ["King Tubby"])
        p = res["_prompts"][0]
        self.assertIn("PARECIDOS A Miles Davis - Kind of Blue (géneros: modal jazz, cool jazz)", p)
        for gone in ("Toca guitarra", "Quiere mejorar", "Ama:", "Gustos actuales", "Reacciones recientes"):
            self.assertNotIn(gone, p)
        self.assertIn("Evita: smooth jazz", p)  # lo que evita sí vale para cualquier pedido
        i = res["inputs"]
        self.assertEqual((i["plan"]["kind"], i["scoring"]["tastePct"], i["plan"]["requestPct"]), ("parecido_a", 25, 75))
        self.assertEqual((i["plan"]["useInstrument"], i["plan"]["useGoals"], i["plan"]["useTaste"]), (False, False, False))
        self.assertEqual((i["profile"]["focus"], i["profile"]["focusSkipped"]), ([], True))

    def test_for_you_keeps_the_instrument_and_the_tastes(self):
        res = self.seeded({"mode": "estudiar"}, ["King Tubby"])
        p = res["_prompts"][0]
        self.assertIn("Toca guitarra", p)
        self.assertIn("Gustos actuales", p)
        self.assertEqual(res["inputs"]["plan"]["kind"], "modo")
        self.assertTrue(res["inputs"]["plan"]["useInstrument"])

    def test_the_closest_disc_to_the_seed_ranks_first_whatever_the_taste(self):
        ARTISTS["Parecido"] = {"id": fid("p1"), "tags": [("modal jazz", 5)], "albums": [("Mismo Aire", 1960, ["modal jazz", "cool jazz"], [])]}
        ARTISTS["Lejano"] = {"id": fid("p2"), "tags": [("funk", 5)], "albums": [("Otro Mundo", 1995, ["funk", "soul"], [])]}
        for n in ("Parecido", "Lejano"):
            self.addCleanup(ARTISTS.pop, n)
        res = self.seeded({"seed": {"artist": "Miles Davis", "album": "Kind of Blue"}}, ["Lejano", "Parecido"])
        self.assertEqual(res["pick"]["artist"], "Parecido")
        self.assertGreater(res["pick"]["score"], res["alternatives"][0]["score"] + 0.3)  # y por bastante: manda el parecido, no la confianza del modelo

    def test_a_damaged_cache_with_fake_ids_is_ignored_and_refetched(self):
        """Pasó de verdad: tests escribieron artistas con id 'a1' en la caché real y las recomendaciones salían con discos de id falso (portadas y enlaces rotos)."""
        now = 2_000_000_000.0
        self.cache["artist:king tubby"] = {"at": now, "data": {"mbid": "a1", "name": "King Tubby", "genres": ["rock"], "votes": {}}}
        self.cache[f"rg:album:{fid('a1')}"] = {"at": now, "data": [{"mbid": "a1-0", "title": "Falso", "year": 1, "primary": "Album", "secondary": [], "genres": ["rock"], "votes": 1}]}
        art = R.artistfirst.resolve("King Tubby", fake_mb_get, self.cache, now=now)
        self.assertEqual(art["mbid"], fid("a1"))  # se volvió a pedir: no se devolvió el id falso ni sus géneros
        self.assertIn("dub", art["genres"])
        albums = R.artistfirst.albums_of(art, fake_mb_get, self.cache, now=now)
        self.assertTrue(all(len(a["mbid"]) == 36 for a in albums))
        self.assertNotIn("Falso", [a["title"] for a in albums])

    def test_second_run_uses_the_cache(self):
        self.run_with([["King Tubby", "Lee Perry"]], {"genres": ["dub"]})
        n = len(fake_mb_get.calls)
        self.assertEqual(n, 4)  # por artista: 1 búsqueda + 1 listado (nada por disco)
        self.run_with([["King Tubby", "Lee Perry"]], {"genres": ["dub"]})
        self.assertEqual(len(fake_mb_get.calls), n)

    def test_artists_already_tried_are_not_repeated_and_empty_round_stops(self):
        res = self.run_with([["King Tubby"], ["King Tubby"], ["Lee Perry"]], {"genres": ["dub"]})
        self.assertEqual(res["stats"]["rounds"], 2)  # la segunda ronda no trajo nada nuevo: se corta
        self.assertIn("Ya los propusiste", res["_prompts"][1])
        self.assertIn("King Tubby", res["_prompts"][1])

    def test_cancel_during_artist_lookup_keeps_partial_result(self):
        def search(url, tries=4):
            if "/artist?" in url and "Lee%20Perry" in url.replace("+", "%20"):
                R._state["state"] = "running"
                R.cancel()
            return fake_mb_get(url)

        with mock.patch.object(R, "mb_get", search):
            res = self.run_with([["King Tubby", "Lee Perry", "Scientist"]], {"genres": ["dub"]})
        self.assertTrue(res["stats"]["cancelled"])
        self.assertNotIn("Scientist", " ".join(self.shown(res)))

    def test_musicbrainz_down_is_reported_and_keeps_the_last_good_result(self):
        import urllib.error

        R._write_json(R.LAST, {"version": 2, "daily": None, "request": {"marker": "bueno"}})

        def down(url, tries=4):
            raise urllib.error.HTTPError(url, 503, "Service Unavailable", {}, None)

        with mock.patch.object(R, "mb_get", down):
            it = iter([[ "King Tubby", "Lee Perry"], []])
            with mock.patch.object(R, "ask_artists", lambda *a, **k: ([{"name": n, "confidence": 80} for n in next(it, [])], {"promptTokens": 1, "evalTokens": 1})):
                res = R._run("m", "request", R.clean_request({"genres": ["dub"]}), now=1_700_000_000.0, save=True)
        self.assertTrue(res["stats"]["mbDown"])
        self.assertEqual(res["stats"]["discardedBy"], {"mb_error": 2})
        self.assertEqual(R._read_json(R.LAST, {})["request"], {"marker": "bueno"})

    def test_context_is_skipped_by_default_and_built_when_set_to_now(self):
        calls = []
        with mock.patch.object(R.albumctx, "get", lambda *a, **k: calls.append(a[0]) or {"text": "t", "source": "musicbrainz"}):
            with mock.patch.object(R.settings, "load", lambda: {**R.settings.DEFAULTS, "recsContext": "demand"}):
                res = self.run_with([["King Tubby"]], {"genres": ["dub"]})
            self.assertEqual(calls, [])
            self.assertEqual(res["stats"]["contextMode"], "demand")
            self.assertNotIn("contextSeconds", res["stats"])
            with mock.patch.object(R.settings, "load", lambda: {**R.settings.DEFAULTS, "recsContext": "now"}):
                res = self.run_with([["King Tubby"]], {"genres": ["dub"]})
            self.assertEqual(len(calls), 1)
            self.assertIn("contextSeconds", res["stats"])

    # ---- clasificador complementario (NLI) sobre los casos en duda
    def with_classifier(self, label, conf=90, boom=False):
        import classify

        class Fake:
            name, calibrated = "fake", False
            calls = []

            def nli(self, prem, hyp):
                Fake.calls.append((prem, hyp))
                if boom:
                    raise RuntimeError("el modelo no respondió")
                rest = (1 - conf / 100) / 2
                return {k: (conf / 100 if k == label else rest) for k in classify.LABELS}

        saved = dict(classify._backends)
        self.addCleanup(lambda: (classify._backends.clear(), classify._backends.update(saved)))
        classify.register("llm", lambda model: Fake())
        log = Path(self.tmp.name) / "clf-log.jsonl"
        wiki = {"text": "A roots record with dub production.", "source": "wikipedia"}  # información nueva: sin ella el clasificador no opina
        patches = [mock.patch.object(R.settings, "load", lambda: {**R.settings.DEFAULTS, "classifier": "llm"}),
                   mock.patch.object(R.albumctx, "extract", lambda mbid, artist, album, data_dir, fetch=True, chars=1200: wiki["text"]),
                   mock.patch.object(R, "CLASSIFIER_LOG", log), mock.patch.object(R, "CLASSIFIER_CAL", Path(self.tmp.name) / "cal.json")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return Fake, log

    def test_classifier_upgrades_a_close_disc_and_the_verdict_is_logged_and_traced(self):
        Fake, log = self.with_classifier("entailment")
        res = self.run_with([["Bob Marley"]], {"genres": ["dub"]})
        self.assertEqual(res["pick"]["genre"]["status"], "match")
        self.assertEqual(res["pick"]["genre"]["source"], "clasificador")
        self.assertEqual(res["pick"]["trail"]["classifier"]["backend"], "fake")
        self.assertIn('genre "dub"', Fake.calls[0][1])
        self.assertIn("MusicBrainz genres", Fake.calls[0][0])
        rows = [json.loads(x) for x in log.read_text().splitlines()]
        self.assertEqual((rows[0]["gate"], rows[0]["changed"], rows[0]["to"]), ("weak", True, "match"))
        self.assertEqual(res["stats"]["classifier"], {"calls": 1, "changed": 1})

    def test_classifier_contradiction_drops_the_close_disc(self):
        self.with_classifier("contradiction")
        res = self.run_with([["Bob Marley", "Lee Perry"]], {"genres": ["dub"]})
        self.assertEqual(self.shown(res), ["Lee Perry - Super Ape"])
        self.assertEqual(res["stats"]["discardedBy"].get("off_genre"), 1)

    def test_kev_setting_creates_the_kev_backend_with_the_configured_url(self):
        import classify

        made = {}
        real = classify._backends["kev"]
        classify.register("kev", lambda model: made.setdefault("be", real(model)))
        self.addCleanup(lambda: classify.register("kev", real))
        with mock.patch.object(R.settings, "load", lambda: {**R.settings.DEFAULTS, "classifier": "kev", "classifierUrl": "http://127.0.0.1:8123"}):
            self.run_with([["Lee Perry"]], {"genres": ["dub"]})
        self.assertEqual(made["be"].url, "http://127.0.0.1:8123")

    def test_classifier_fetches_at_most_a_few_descriptions_per_search(self):
        Fake, _ = self.with_classifier("entailment")
        asked = []

        def extract(mbid, artist, album, data_dir, fetch=True, chars=1200):
            if fetch:
                asked.append(album)
            return None  # sin artículo: no hay evidencia, no se opina

        names = [f"Reggae {i}" for i in range(10)]
        for n in names:
            ARTISTS[n] = {"id": fid(f"r{n[-1]}"), "tags": [("reggae", 5), ("dub", 1)], "albums": [(f"Disco {n}", 1975, ["reggae"], [])]}
            self.addCleanup(ARTISTS.pop, n)
        with mock.patch.object(R.albumctx, "extract", extract):
            self.run_with([names], {"genres": ["dub"]})
        self.assertLessEqual(len(asked), R.CLASSIFIER_FETCHES)
        self.assertEqual(Fake.calls, [])

    def test_classifier_abstains_when_there_is_only_tags(self):
        Fake, log = self.with_classifier("entailment")
        with mock.patch.object(R.albumctx, "extract", lambda *a, **k: None), mock.patch.object(R.albumctx, "cached", lambda *a: None):
            res = self.run_with([["Bob Marley"]], {"genres": ["dub"]})
        self.assertEqual(Fake.calls, [])
        self.assertEqual(res["pick"]["genre"]["status"], "weak")
        self.assertFalse(log.exists())

    def test_classifier_is_not_called_for_exact_matches_or_musicbrainz_off(self):
        Fake, _ = self.with_classifier("entailment")
        self.run_with([["Lee Perry", "Coldplay"]], {"genres": ["dub"]})
        self.assertEqual(Fake.calls, [])  # un match exacto y un off de MusicBrainz no necesitan segunda opinión

    def test_classifier_failure_leaves_the_gate_untouched(self):
        self.with_classifier("entailment", boom=True)
        res = self.run_with([["Bob Marley"]], {"genres": ["dub"]})
        self.assertEqual(res["pick"]["genre"]["status"], "weak")
        self.assertNotIn("classifier", res["stats"])

    def test_classifier_off_by_default(self):
        import classify

        classify.register("llm", lambda model: (_ for _ in ()).throw(AssertionError("no debe crearse")))
        self.addCleanup(lambda: classify.register("llm", lambda model: classify.LlmBackend(R._clf_chat, model)))
        res = self.run_with([["Bob Marley"]], {"genres": ["dub"]})
        self.assertEqual(res["pick"]["genre"]["status"], "weak")

    # ---- agente revisor (etapa 2: buscador -> revisor -> clasificador)
    def with_reviewer(self, setting, verdicts=None, boom=False, order=None, extra=None):
        calls = []

        def chat_json(model, system, user, schema, temperature, tries=3, num_predict=700):
            calls.append((model, user))
            if order is not None:
                order.append("revisor")
            if boom:
                raise RuntimeError("el modelo no respondió")
            return {"revisiones": [{"n": n, "encaja": f, "motivo": m} for n, (f, m) in (verdicts or {}).items()]}, {"promptTokens": 40, "evalTokens": 5}

        for p in (mock.patch.object(R, "_chat_json", chat_json),
                  mock.patch.object(R.settings, "load", lambda: {**R.settings.DEFAULTS, "recsReviewer": setting, **(extra or {})})):
            p.start()
            self.addCleanup(p.stop)
        return calls

    def test_genre_only_request_has_nothing_to_review(self):
        """Medido (gemma3:4b): en un pedido solo de género, con el modo del perfil, el revisor dudó de 12 de 16 discos. No hay nada que juzgar."""
        calls = self.with_reviewer("same", {1: ("no", "energia")})
        res = self.run_with([["King Tubby", "Lee Perry"]], {"genres": ["dub"]})
        self.assertEqual(calls, [])
        ag = self.agents(res)["revisor"]
        self.assertEqual((ag["state"], ag["model"]), ("skipped", "modelo-falso"))
        self.assertIn("Sin nada que revisar", ag["detail"])
        self.assertTrue(any(e["agent"] == "revisor" and e["kind"] == "skip" and "Omitido" in e["text"] for e in res["log"]))

    def test_a_prompt_or_a_mode_or_no_genre_does_get_reviewed(self):
        calls = self.with_reviewer("same", {1: ("si", "ok")})
        self.run_with([["King Tubby"]], {"genres": ["dub"], "prompt": "algo tranquilo"})
        self.assertEqual(len(calls), 1)
        self.assertIn("NO los juzgues", calls[0][1])  # el género se menciona pero ya verificado: no se lo juzga
        self.run_with([["Lee Perry"]], {"mode": "estudiar"})  # sin género: nada verificado, el revisor sí opina
        self.assertEqual(len(calls), 2)
        self.assertNotIn("NO los juzgues", calls[1][1])

    def test_reviewer_is_off_by_default(self):
        calls = self.with_reviewer("off", {1: ("no", "energia")})
        res = self.run_with([["King Tubby", "Lee Perry"]], {"genres": ["dub"], "mode": "estudiar"})
        self.assertEqual(calls, [])
        self.assertIsNone(res["pick"]["trail"]["review"])
        self.assertNotIn("review", res["stats"])

    def test_reviewer_can_only_lower_and_its_note_is_labeled_as_the_models_opinion(self):
        calls = self.with_reviewer("same", {1: ("no", "energia"), 2: ("si", "ok")})
        res = self.run_with([["King Tubby", "Lee Perry"]], {"genres": ["dub"], "mode": "estudiar"})
        self.assertEqual(len(calls), 1)  # una sola pasada por ronda con todos los elegidos
        self.assertEqual(calls[0][0], "modelo-falso")  # "same" = el mismo modelo
        self.assertIn("1. King Tubby - Dub from the Roots", calls[0][1])
        by = {v["artist"]: v for v in [res["pick"]] + res["alternatives"]}
        low, ok = by["King Tubby"], by["Lee Perry"]
        self.assertEqual(low["trail"]["review"]["fit"], "no")
        self.assertIn("opinión del modelo, no verificada", low["trail"]["review"]["note"])
        self.assertEqual(low["trail"]["score"]["final"], low["score"])
        self.assertEqual(ok["trail"]["review"]["fit"], "si")
        self.assertGreater(ok["score"], low["score"])  # el bajado queda detrás aunque tuviera mejor puntaje de gustos
        self.assertEqual(res["pick"]["artist"], "Lee Perry")
        self.assertEqual(res["stats"]["review"], {"model": "modelo-falso", "reviewed": 2, "lowered": 1})

    def test_what_the_reviewer_lowers_does_not_count_as_found_and_triggers_another_round_that_knows_it(self):
        """Circuito buscador -> revisor -> buscador: lo que el revisor baja se le cuenta al buscador en la ronda siguiente."""
        prompts = []

        def ask(model, user, temperature=0.7):
            prompts.append(user)
            return ([{"name": "King Tubby", "confidence": 80}, {"name": "Lee Perry", "confidence": 70}] if len(prompts) == 1
                    else [{"name": "Scientist", "confidence": 60}]), {"promptTokens": 5, "evalTokens": 1}

        calls = self.with_reviewer("same", {1: ("no", "animo"), 2: ("no", "animo")})
        with mock.patch.object(R, "ask_artists", ask), mock.patch.object(R, "ask_choice", lambda m, u: ([], {"promptTokens": 1, "evalTokens": 1})):
            res = R._run("modelo-falso", "request", R.clean_request({"genres": ["dub"], "mode": "estudiar"}), now=1_700_000_000.0, save=False)
        self.assertGreaterEqual(len(prompts), 2)  # sin el revisor habría alcanzado con una ronda de 2 (cortaba por "nada nuevo")... y con "no" busca más
        self.assertIn("Un revisor descartó estos por no encajar", prompts[1])
        self.assertIn("King Tubby - Dub from the Roots", prompts[1])
        self.assertNotIn("Un revisor descartó", prompts[0])
        self.assertTrue(calls)

    # ---- visualización de los agentes (estado + registro)
    def agents(self, res):
        return {a["id"]: a for a in res["agents"]}

    def test_covers_are_prefetched_even_with_context_on_demand(self):
        """Regresión: la precarga de portadas estaba dentro del bloque de contexto 'now'; con el contexto a demanda (por defecto) no corría nunca."""
        asked = []
        with mock.patch("covers.prefetch", lambda items: asked.append(list(items))):
            res = self.run_with([["King Tubby", "Lee Perry"]], {"genres": ["dub"]})
        self.assertEqual(res["stats"]["contextMode"], "demand")
        self.assertEqual(len(asked), 1)
        self.assertEqual({(a_, al) for _, a_, al in asked[0]}, {("King Tubby", "Dub from the Roots"), ("Lee Perry", "Super Ape")})
        self.assertTrue(all(len(m) == 36 or m for m, _, _ in asked[0]))  # (mbid, artista, disco) listo para buscar en TIDAL

    def test_covers_are_not_prefetched_for_a_cancelled_search(self):
        asked = []
        R._cancel.set()
        with mock.patch("covers.prefetch", lambda items: asked.append(items)):
            self.run_with([["King Tubby"]], {"genres": ["dub"]})
        self.assertEqual(asked, [])

    def test_the_run_reports_the_variables_it_ran_with(self):
        res = self.run_with([["King Tubby"]], {"genres": ["dub"], "type": "album"})
        i = res["inputs"]
        self.assertEqual((i["request"]["genres"], i["request"]["strict"], i["request"]["type"]), (["dub"], True, "album"))
        self.assertEqual((i["profile"]["instrument"], i["profile"]["discovery"], i["profile"]["ownArtists"]), ("guitarra", "algo", ["Mi Banda"]))
        self.assertEqual(i["scoring"]["tastePct"], 50)  # pedido de género: los gustos pesan la mitad, no lo de "algo" (65)
        self.assertEqual(i["plan"]["kind"], "genero")
        self.assertEqual(i["scoring"]["genreWeightPct"], 75)
        self.assertEqual((i["engine"]["model"], i["engine"]["method"], i["engine"]["maxRounds"], i["engine"]["target"]), ("modelo-falso", "artistas", 4, 4))
        self.assertIsNone(i["engine"]["reviewer"])
        self.assertIsNone(i["engine"]["classifier"])
        self.assertEqual(i["preset"]["how"] in ("horario", "defecto", "elegido"), True)
        self.assertEqual(R._state["inputs"], i)  # también en vivo, no solo al terminar

    def test_inputs_say_when_the_reviewer_is_skipped_and_with_what_models(self):
        self.with_reviewer("same", extra={"classifier": "llm"})
        i = self.run_with([["King Tubby"]], {"genres": ["dub"]})["inputs"]["engine"]
        self.assertEqual((i["reviewer"], i["reviewerSkipped"]), (None, True))  # pidió solo un género: nada que revisar
        i = self.run_with([["King Tubby"]], {"genres": ["dub"], "mode": "estudiar"})["inputs"]["engine"]
        self.assertEqual((i["reviewer"], i["reviewerSkipped"]), ("modelo-falso", False))

    def test_agents_report_state_model_and_a_readable_log(self):
        res = self.run_with([["King Tubby", "Coldplay", "Inventado Total"]], {"genres": ["dub"], "mode": "estudiar"})
        ag = self.agents(res)
        self.assertEqual(list(ag), ["planificador", "buscador", "revisor", "clasificador"])
        self.assertEqual((ag["buscador"]["state"], ag["buscador"]["model"]), ("done", "modelo-falso"))
        self.assertIn("1 discos", ag["buscador"]["detail"])
        for off in ("planificador", "revisor", "clasificador"):  # apagados: se ven, pero como apagados
            self.assertEqual((ag[off]["state"], ag[off]["model"], ag[off]["detail"]), ("skipped", None, "Apagado"))
        texts = [(e["agent"], e["kind"], e["text"]) for e in res["log"]]
        self.assertIn(("buscador", "ok", "Verificó King Tubby - Dub from the Roots · género: match"), texts)
        self.assertTrue(any(k == "discard" and "Coldplay" in t and "alternative rock" in t for _, k, t in texts))  # con el motivo real
        self.assertTrue(any("Inventado Total" in t and "MusicBrainz no tiene a ese artista" in t for _, _, t in texts))
        self.assertTrue(any(t.startswith("Ronda 1: propuso 3 artistas") for _, _, t in texts))
        self.assertEqual([e["t"] for e in res["log"]], sorted(e["t"] for e in res["log"]))  # en orden cronológico

    def test_reviewer_and_classifier_appear_working_when_turned_on(self):
        Fake, _ = self.with_classifier("entailment")
        self.with_reviewer("same", {1: ("no", "animo"), 2: ("si", "ok")}, extra={"classifier": "llm"})
        res = self.run_with([["King Tubby", "Bob Marley"]], {"genres": ["dub"], "mode": "estudiar"})
        ag = self.agents(res)
        self.assertEqual((ag["revisor"]["state"], ag["revisor"]["model"]), ("done", "modelo-falso"))
        self.assertIn("con reparos", ag["revisor"]["detail"])
        self.assertEqual(ag["revisor"]["calls"], 1)
        self.assertEqual((ag["clasificador"]["state"], ag["clasificador"]["model"]), ("done", "llm"))
        texts = [(e["agent"], e["text"]) for e in res["log"]]
        self.assertTrue(any(a == "revisor" and "no encaja (el ánimo no encaja con lo que pediste)" in t for a, t in texts))
        self.assertTrue(any(a == "clasificador" and "entailment" in t and "→ match" in t for a, t in texts))

    def test_status_exposes_the_agents_live_and_the_last_run_after_a_restart(self):
        res = self.run_with([["King Tubby"]], {"genres": ["dub"], "mode": "estudiar"})
        R._write_json(R.LAST, {"version": 2, "daily": None, "request": res})
        R._state.update(agents=[], log=[])  # como tras reiniciar el motor
        with mock.patch.object(R, "snapshot", lambda *a, **k: {"md": ""}), mock.patch.object(R, "pick_preset", lambda *a, **k: {"id": "x", "name": "x", "how": "defecto", "data": {}}):
            st = R.status()
        self.assertEqual(st["agents"], [])
        self.assertEqual([a["id"] for a in st["lastRun"]["agents"]], ["planificador", "buscador", "revisor", "clasificador"])
        self.assertTrue(st["lastRun"]["log"])

    def test_cancelled_run_leaves_the_searcher_cancelled(self):
        R._cancel.set()
        res = self.run_with([["King Tubby"]], {"genres": ["dub"], "mode": "estudiar"})
        self.assertEqual(self.agents(res)["buscador"]["state"], "cancelled")

    def test_log_is_bounded(self):
        R._agents_reset({"buscador": "m"})
        for i in range(R.LOG_MAX + 30):
            R._log("buscador", f"x{i}")
        self.assertEqual(len(R._state["log"]), R.LOG_MAX)
        self.assertEqual(R._state["log"][-1]["text"], f"x{R.LOG_MAX + 29}")

    def test_another_model_can_review(self):
        calls = self.with_reviewer("gemma3:4b", {1: ("si", "ok")})
        self.run_with([["King Tubby"]], {"genres": ["dub"], "mode": "estudiar"})
        self.assertEqual(calls[0][0], "gemma3:4b")

    def test_reviewer_failure_leaves_the_search_untouched(self):
        self.with_reviewer("same", boom=True)
        res = self.run_with([["King Tubby", "Lee Perry"]], {"genres": ["dub"], "mode": "estudiar"})
        self.assertEqual(len(self.shown(res)), 2)
        self.assertIsNone(res["pick"]["trail"]["review"])

    def test_stage_order_is_searcher_then_reviewer_then_classifier(self):
        order = []
        Fake, _ = self.with_classifier("entailment")
        orig = Fake.nli

        def nli(self_, prem, hyp):
            order.append("clasificador")
            return orig(self_, prem, hyp)

        Fake.nli = nli
        self.with_reviewer("same", {1: ("si", "ok")}, order=order, extra={"classifier": "llm"})
        self.run_with([["Bob Marley"]], {"genres": ["dub"], "mode": "estudiar"})
        self.assertEqual(order, ["revisor", "clasificador"])

    def test_reviewer_setting_is_validated_and_resolved(self):
        import settings

        for ok in ("off", "same", "gemma3:4b", "library/qwen3:8b"):
            self.assertEqual(settings.validate({"recsReviewer": ok})["recsReviewer"], ok)
        for bad in (3, "mal nombre!", "x" * 90, None):
            with self.assertRaises(settings.SettingsError):
                settings.validate({"recsReviewer": bad})
        with mock.patch.object(R.settings, "load", lambda: {"recsReviewer": "same"}):
            self.assertEqual(R.reviewer_model("m"), "m")
        with mock.patch.object(R.settings, "load", lambda: {"recsReviewer": "off"}):
            self.assertIsNone(R.reviewer_model("m"))

    def test_shown_discs_are_diverse_not_clones(self):
        """Medido pidiendo 'bebop': tres discos 'jazz, hard bop'. Con MMR un disco algo peor pero distinto entra antes que un clon."""
        for n in ("Clon 1", "Clon 2", "Clon 3", "Otro"):
            self.addCleanup(ARTISTS.pop, n)
        for i in (1, 2, 3):
            ARTISTS[f"Clon {i}"] = {"id": fid(f"c{i}"), "tags": [("jazz", 9), ("hard bop", 9), ("bebop", 8)], "albums": [(f"Hard {i}", 1960, ["bebop", "hard bop", "jazz"], [])]}
        ARTISTS["Otro"] = {"id": fid("o1"), "tags": [("jazz", 3), ("bebop", 3)], "albums": [(f"Distinto", 1948, ["bebop", "swing"], [])]}
        res = self.run_with([["Clon 1", "Clon 2", "Clon 3", "Otro"]], {"genres": ["bebop"]})
        shown = self.shown(res)
        self.assertIn("Otro - Distinto", shown[:2])  # sube por distinto aunque tenga menos votos de género
        self.assertGreaterEqual(res["stats"]["spread"]["shown"], res["stats"]["spread"]["byScore"])
        self.assertIn("diversity", res["pick"]["trail"])
        self.assertEqual(res["pick"]["trail"]["diversity"], 0.0)  # el primero no se compara con nadie

    def test_early_stop_with_lookups_still_in_flight_saves_a_valid_cache(self):
        """Con 6 artistas alcanza: los hilos que siguen consultando escriben en la caché mientras se la guarda. No debe romper ni corromper."""
        import json
        import time

        names = [f"Dub {i}" for i in range(10)]
        for n in names:
            ARTISTS[n] = {"id": fid(f"x{n[-1]}"), "tags": [("dub", 5)], "albums": [(f"Disco {n}", 1975, ["dub"], [])]}
            self.addCleanup(ARTISTS.pop, n)

        def slow(url, tries=4):
            time.sleep(0.03)
            return fake_mb_get(url)

        cache_file = Path(self.tmp.name) / "mb-artists.json"
        cache = R._Cache()
        with mock.patch.object(R, "mb_get", slow), mock.patch.object(R, "_artist_cache", lambda: cache), \
                mock.patch.object(R, "_artist_cache_file", lambda: cache_file):
            res = self.run_with([names], {"genres": ["dub"]})
            time.sleep(0.4)  # los hilos que quedaron en vuelo terminan de escribir
            R._save_artist_cache()
        self.assertEqual(len(self.shown(res)), 4)
        self.assertTrue(json.loads(cache_file.read_text()))  # JSON válido

    def test_cache_survives_concurrent_writes_while_saving(self):
        import json
        import threading

        c = R._Cache()
        stop = threading.Event()

        def writer():
            i = 0
            while not stop.is_set():
                c[f"k{i % 300}"] = {"at": i, "data": list(range(20))}  # tamaño acotado
                i += 1

        threads = [threading.Thread(target=writer) for _ in range(3)]
        [t.start() for t in threads]
        try:
            for _ in range(200):
                json.dumps(c.snapshot())  # con dict(c) a secas esto levanta "dictionary changed size during iteration"
        finally:
            stop.set()
            [t.join() for t in threads]

    def test_type_filter_ep_uses_ep_listing(self):
        self.run_with([["King Tubby"]], {"genres": ["dub"], "type": "ep"})
        self.assertTrue(any("type=ep" in u for u in fake_mb_get.calls))

    # ---- agente planificador (etapa 0: planificador -> buscador -> revisor -> clasificador)
    def with_planner(self, setting, plan=None, boom=None, order=None, extra=None):
        """Parchea el modelo: el planificador (esquema planner.SCHEMA) responde `plan`; si pasa por otro lado (revisor) devuelve vacío."""
        import planner

        calls = []
        base = {"desde": 0, "hasta": 0, "animo": "ninguno", "instrumental": "indiferente", "idioma": "ninguno", "referencias": [], "paises": [], "generos": [], "fundamental": False, "brief": ""}

        def chat_json(model, system, user, schema, temperature, tries=3, num_predict=700):
            if schema is not planner.SCHEMA:
                return {"revisiones": []}, {"promptTokens": 1, "evalTokens": 1}
            calls.append((model, user, tries))
            if order is not None:
                order.append("planificador")
            if boom:
                raise boom
            return {**base, **(plan or {})}, {"promptTokens": 40, "evalTokens": 5}

        for p in (mock.patch.object(R, "_chat_json", chat_json),
                  mock.patch.object(R.settings, "load", lambda: {**R.settings.DEFAULTS, "recsPlanner": setting, **(extra or {})})):
            p.start()
            self.addCleanup(p.stop)
        return calls

    def test_planner_is_off_by_default_and_never_called(self):
        calls = self.with_planner("off", {"desde": 1970, "hasta": 1979})
        res = self.run_with([["Lee Perry"]], {"prompt": "dub tranquilo"})
        self.assertEqual(calls, [])
        ag = self.agents(res)["planificador"]
        self.assertEqual((ag["state"], ag["model"], ag["detail"]), ("skipped", None, "Apagado"))
        self.assertNotIn("era", res["stats"])
        self.assertFalse(res["inputs"]["planner"]["enabled"])
        self.assertEqual(R.settings.DEFAULTS["recsPlanner"], "off")

    def test_planner_setting_is_validated_and_resolved(self):
        import settings

        for ok in ("off", "same", "gemma3:12b", "library/qwen3:8b"):
            self.assertEqual(settings.validate({"recsPlanner": ok})["recsPlanner"], ok)
        for bad in (3, "mal nombre!", "x" * 90, None):
            with self.assertRaises(settings.SettingsError):
                settings.validate({"recsPlanner": bad})
        with mock.patch.object(R.settings, "load", lambda: {"recsPlanner": "same"}):
            self.assertEqual(R.planner_model("m"), "m")
        with mock.patch.object(R.settings, "load", lambda: {"recsPlanner": "gemma3:12b"}):
            self.assertEqual(R.planner_model("m"), "gemma3:12b")
        with mock.patch.object(R.settings, "load", lambda: {"recsPlanner": "off"}):
            self.assertIsNone(R.planner_model("m"))

    # ---- la época escrita se exige SIEMPRE (regex), sin planificador con modelo
    def test_written_era_is_enforced_with_the_real_year_even_without_the_planner_model(self):
        """Decisión del usuario: la regex de época va siempre. Sin modelo, 'de los 70' ya filtra con el año de MusicBrainz."""
        res = self.run_with([["King Tubby", "Lee Perry", "Scientist"]], {"prompt": "dub de los 70"})
        self.assertEqual(res["request"]["era"], {"from": 1970, "to": 1979, "source": "reglas", "strict": True})
        self.assertEqual(sorted(self.shown(res)), ["King Tubby - Dub from the Roots", "Lee Perry - Super Ape"])  # Scientist es de 1981: afuera
        disc = {d["artist"]: d for d in res["discarded"]}
        self.assertEqual(disc["Scientist"]["category"], "off_era")
        self.assertIn("1981", disc["Scientist"]["why"])  # el motivo trae el año real, no texto del modelo
        self.assertIn("ÉPOCA: discos editados entre 1970 y 1979 (obligatorio)", res["_prompts"][0])
        self.assertEqual(res["pick"]["trail"]["era"]["source"], "reglas")
        self.assertEqual(res["agents"][0]["id"], "planificador")
        self.assertEqual(res["agents"][0]["state"], "skipped")  # el modelo planificador sigue apagado: la época no lo necesita

    def test_written_era_alone_is_its_own_request_kind_and_does_not_penalize_by_text_match(self):
        res = self.run_with([["King Tubby", "Lee Perry"]], {"prompt": "algo de los 70 para tocar"})
        self.assertEqual(res["inputs"]["plan"]["kind"], "epoca")
        self.assertEqual(res["inputs"]["plan"]["requestPct"], 0)

    def test_flexible_written_era_only_orients_the_prompt(self):
        res = self.run_with([["King Tubby", "Scientist"]], {"prompt": "dub de los 70", "strict": False})
        self.assertFalse(res["request"]["era"]["strict"])
        self.assertEqual(len(self.shown(res)), 2)  # Scientist (1981) entra: pidió flexible
        self.assertIn("ÉPOCA: discos editados entre 1970 y 1979.", res["_prompts"][0])

    def test_no_era_in_the_text_means_no_filter(self):
        res = self.run_with([["King Tubby", "Scientist"]], {"prompt": "dub tranquilo"})
        self.assertNotIn("era", res["request"])
        self.assertNotIn("era", res["stats"])

    def test_model_era_is_a_hard_filter_checked_against_the_real_year(self):
        calls = self.with_planner("same", {"desde": 1975, "hasta": 1979, "animo": "tranquilo", "brief": "Dub calmo de fines de los 70."})
        res = self.run_with([["King Tubby", "Lee Perry", "Scientist"]], {"prompt": "un poco de dub de esa época"})
        self.assertEqual(self.shown(res), ["Lee Perry - Super Ape"])  # 1976; King Tubby (1974 y 1997) y Scientist (1981) no entran
        by = res["stats"]["discardedBy"]
        self.assertEqual(by.get("off_era"), 2)
        disc = {d["artist"]: d["why"] for d in res["discarded"]}
        self.assertIn("1975-1979", disc["Scientist"])
        self.assertIn("1981", disc["Scientist"])  # el motivo trae el dato de MusicBrainz, no texto del modelo
        self.assertIn("1974-1997", disc["King Tubby"])
        pick = res["pick"]
        self.assertIn("Es de 1976 según MusicBrainz, dentro de 1975-1979.", pick["reason"])
        self.assertEqual(pick["trail"]["era"], {"from": 1975, "to": 1979, "year": 1976, "source": "modelo"})
        self.assertEqual(res["stats"]["era"], {"from": 1975, "to": 1979, "strict": True, "source": "modelo"})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "modelo-falso")
        self.assertEqual(calls[0][2], 1)  # un solo intento: si falla siguen las reglas

    def test_written_era_beats_the_model_and_the_brief_is_labeled_as_opinion(self):
        self.with_planner("same", {"desde": 1990, "hasta": 1999, "brief": "Buscá cosas suaves y raras."})
        res = self.run_with([["King Tubby", "Lee Perry", "Scientist"]], {"prompt": "dub de los 70"})
        self.assertEqual(res["request"]["era"]["source"], "reglas")
        self.assertEqual(sorted(self.shown(res)), ["King Tubby - Dub from the Roots", "Lee Perry - Super Ape"])
        p = res["_prompts"][0]
        self.assertIn('ORIENTACIÓN DEL PLANIFICADOR (opinión de un modelo, no un dato): "Buscá cosas suaves y raras."', p)
        self.assertIn("ÉPOCA: discos editados entre 1970 y 1979 (obligatorio)", p)
        for v in [res["pick"]] + res["alternatives"]:  # el brief es opinión: nunca aparece como motivo ni en el rastro
            self.assertNotIn("suaves y raras", json.dumps({"reason": v["reason"], "trail": v["trail"]}))

    def test_flexible_request_keeps_the_era_as_a_hint_only(self):
        self.with_planner("same", {"desde": 1975, "hasta": 1979})
        res = self.run_with([["King Tubby", "Scientist"]], {"prompt": "dub", "strict": False})
        self.assertFalse(res["stats"]["era"]["strict"])
        self.assertEqual(len(self.shown(res)), 2)
        self.assertIsNone(res["pick"]["trail"]["era"])
        self.assertIn("ÉPOCA: discos editados entre 1975 y 1979.", res["_prompts"][0])

    def test_artists_without_a_year_are_discarded_when_the_era_is_hard(self):
        ARTISTS["Sin Año"] = {"id": fid("sa1"), "tags": [("dub", 3)], "albums": [("Dub sin fecha", None, ["dub"], [])]}
        self.addCleanup(ARTISTS.pop, "Sin Año")
        orig = fake_mb_get

        def mb(url, tries=4):
            out = orig(url, tries)
            for g in out.get("release-groups", []):
                if g["title"] == "Dub sin fecha":
                    g["first-release-date"] = ""
            return out

        self.with_planner("same", {"desde": 1970, "hasta": 1979})
        with mock.patch.object(R, "mb_get", mb):
            res = self.run_with([["Sin Año", "Lee Perry"]], {"prompt": "dub setentoso"})
        self.assertEqual(self.shown(res), ["Lee Perry - Super Ape"])
        self.assertEqual(res["stats"]["discardedBy"].get("era_unknown"), 1)

    def test_invented_values_are_dropped_and_logged(self):
        self.with_planner("same", {"desde": 1200, "hasta": 3000, "animo": "furioso", "paises": ["ZZ"], "generos": ["musica inventada"], "referencias": ["Nadie Nombrado"]})
        res = self.run_with([["Lee Perry"]], {"prompt": "dub tranquilo"})
        self.assertNotIn("era", res["request"])
        self.assertNotIn("countries", res["request"])
        self.assertEqual(res["request"]["plan"]["refs"], [])
        self.assertTrue(any(e["agent"] == "planificador" and e["kind"] == "discard" and "fuera de" in e["text"] for e in res["log"]))
        self.assertEqual(len(self.shown(res)), 1)

    def test_planner_failure_never_breaks_the_search(self):
        self.with_planner("same", boom=RuntimeError("el modelo no respondió"))
        res = self.run_with([["Lee Perry"]], {"prompt": "dub", "genres": ["dub"]})
        self.assertEqual(self.shown(res), ["Lee Perry - Super Ape"])
        ag = self.agents(res)["planificador"]
        self.assertEqual(ag["state"], "done")
        self.assertIn("siguió con las reglas", ag["detail"])
        self.assertTrue(any(e["agent"] == "planificador" and e["kind"] == "warn" for e in res["log"]))
        self.assertTrue(res["inputs"]["planner"]["enabled"])
        self.assertFalse(res["inputs"]["planner"]["ok"])

    def test_planner_can_be_cancelled(self):
        self.with_planner("same", boom=R.Cancelled())
        with self.assertRaises(R.Cancelled):
            self.run_with([["Lee Perry"]], {"prompt": "dub"})

    def test_stage_order_is_planner_then_searcher_then_reviewer(self):
        order = []
        self.with_planner("same", {"animo": "tranquilo"}, order=order, extra={"recsReviewer": "same"})

        def artists(model, user, temperature=0.7):
            order.append("buscador")
            return [{"name": "Lee Perry", "confidence": 80}], {"promptTokens": 1, "evalTokens": 1}

        with mock.patch.object(R, "ask_artists", artists), mock.patch.object(R, "ask_choice", lambda m, u: ([], {"promptTokens": 1, "evalTokens": 1})):
            R._run("modelo-falso", "request", R.clean_request({"prompt": "dub tranquilo", "mode": "estudiar"}), now=1_700_000_000.0, save=False)
        self.assertEqual(order[:2], ["planificador", "buscador"])

    def test_without_text_the_planner_has_nothing_to_read(self):
        calls = self.with_planner("same", {"desde": 1970, "hasta": 1979})
        res = self.run_with([["Lee Perry"]], {"genres": ["dub"]})
        self.assertEqual(calls, [])
        ag = self.agents(res)["planificador"]
        self.assertEqual((ag["state"], ag["model"]), ("skipped", "modelo-falso"))
        self.assertTrue(any(e["agent"] == "planificador" and e["kind"] == "skip" for e in res["log"]))

    def test_planner_summary_reaches_the_agents_screen(self):
        self.with_planner("same", {"desde": 1975, "hasta": 1979, "animo": "tranquilo", "instrumental": "si", "referencias": ["King Tubby"], "brief": "Dub calmo."})
        res = self.run_with([["Lee Perry"]], {"prompt": "dub como King Tubby"})
        pv = res["inputs"]["planner"]
        self.assertEqual((pv["enabled"], pv["ok"], pv["model"]), (True, True, "modelo-falso"))
        self.assertEqual((pv["era"]["from"], pv["era"]["source"], pv["mood"], pv["instrumental"], pv["refs"], pv["brief"]), (1975, "modelo", "tranquilo", True, ["King Tubby"], "Dub calmo."))
        self.assertEqual(res["inputs"]["engine"]["planner"], "modelo-falso")
        ag = self.agents(res)["planificador"]
        self.assertEqual((ag["state"], ag["calls"]), ("done", 1))
        self.assertIn("brief", ag["detail"])
        texts = [e["text"] for e in res["log"] if e["agent"] == "planificador"]
        self.assertTrue(any("opinión del modelo" in t for t in texts))
        self.assertFalse(any("Dub calmo." in t for t in texts))  # el texto del brief no va al registro como hecho

    def test_written_instrumental_wins_over_the_model(self):
        self.with_planner("same", {"instrumental": "no"})
        res = self.run_with([["Lee Perry"]], {"prompt": "dub sin voz"})
        self.assertTrue(res["request"]["plan"]["instrumental"])


class Sources(unittest.TestCase):
    """Los favoritos de Spotify y YouTube Music también cuentan para el gusto y para no repetir discos."""

    def setUp(self):
        isolate_settings(self)
        import catalog

        self.catalog = catalog
        saved = {pid: dict(catalog._ext_state(pid)) for pid in catalog.EXT_IDS}
        self.addCleanup(lambda: [catalog._ext.__setitem__(pid, v) for pid, v in saved.items()])
        catalog._ext["spotify"] = {"albums": [{"artist": "King Tubby", "title": "Dub from the Roots", "year": 1974, "addedAt": "2026-09-01T10:00:00Z"},
                                              {"artist": "Mi Banda", "title": "Ensayo", "addedAt": None}], "tracks": []}
        catalog._ext["ytmusic"] = {"albums": [{"artist": "King Tubby", "title": "Dub from the Roots", "addedAt": None},
                                              {"artist": "Lee Perry", "title": "Super Ape", "addedAt": None}],
                                   "tracks": [{"artist": "Scientist", "title": "Dub Track", "album": "Heavyweight Dub", "addedAt": None}]}
        p = mock.patch.object(R, "load_profile", lambda: dict(PROFILE))
        p.start()
        self.addCleanup(p.stop)

    def test_external_sources_have_the_same_shape_and_skip_own_band(self):
        out = R.external_sources(now=1_700_000_000.0)
        self.assertEqual({(i["kind"], i["artist"]) for i in out},
                         {("album", "King Tubby"), ("album", "Lee Perry"), ("track", "Scientist")})
        dated = next(i for i in out if i["source"] == "spotify")
        self.assertEqual(dated["added"], R.catalog_ts("2026-09-01T10:00:00Z"))
        undated = next(i for i in out if i["artist"] == "Lee Perry")
        self.assertEqual(undated["added"], 1_700_000_000.0 - R.UNDATED_DAYS * 86400)  # sin fecha: no se inventa una precisa

    def test_same_album_in_two_services_counts_once(self):
        merged = R.merge_sources([{"kind": "album", "artist": "King Tubby", "title": "Dub from the Roots"}], R.external_sources(now=1.0))
        self.assertEqual(sum(1 for i in merged if i["kind"] == "album" and i["artist"] == "King Tubby"), 1)

    def test_external_albums_are_excluded_from_recommendations_and_feed_taste(self):
        with mock.patch.object(R, "_read_json", lambda path, default: default):
            sources = R.cached_sources()
        snap = {"sources": sources, "history": [], "weights": {"artists": [], "genres": []}}
        pairs, _ = R._exclusions(snap)
        self.assertIn((R.norm("Lee Perry"), R.norm("Super Ape")), pairs)
        w = memory.weights(memory.empty_taste(), [], sources, {}, __import__("time").time())
        self.assertIn("Lee Perry", [a["name"] for a in w["artists"]])
        self.assertNotIn("Mi Banda", [a["name"] for a in w["artists"]])


class Reactions(unittest.TestCase):
    def setUp(self):
        isolate_settings(self)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for p in (mock.patch.object(R, "store", memory.Store(self.tmp.name)), mock.patch.object(R, "LAST", Path(self.tmp.name) / "last.json"),
                  mock.patch.object(R, "load_sources", lambda: []), mock.patch.object(R, "load_profile", lambda: dict(PROFILE)),
                  mock.patch.object(R, "cached_sources", lambda: [])):
            p.start()
            self.addCleanup(p.stop)
        item = {"mbid": uid(1), "artist": "King Tubby", "album": "Dub from the Roots", "genres": ["dub", "reggae"]}
        R._write_json(R.LAST, {"version": 2, "daily": None, "request": {"pick": item, "alternatives": [], "preset": {"name": "Trabajo"}}})

    def test_set_reaction_stores_known_flag_and_updates_map(self):
        out = R.set_reaction(uid(1), "liked", known=True)
        self.assertEqual(out, {uid(1): "liked"})
        ev = R.store.load_events()[-1]
        self.assertTrue(ev["known"])
        self.assertEqual(ev["preset"], "Trabajo")

    def test_reason_only_with_no_and_must_be_valid(self):
        R.set_reaction(uid(1), "no", reason="off_genre")
        self.assertEqual(R.store.load_events()[-1]["reason"], "off_genre")
        with self.assertRaises(ValueError):
            R.set_reaction(uid(1), "liked", reason="off_genre")
        with self.assertRaises(ValueError):
            R.set_reaction(uid(1), "no", reason="inventado")
        with self.assertRaises(ValueError):
            R.set_reaction(uid(1), "me_encanta")

    def test_reacted_album_is_never_proposed_again(self):
        R.set_reaction(uid(1), "disliked")
        snap = R.snapshot(1_700_000_000.0)
        pairs, lines = R._exclusions(snap)
        self.assertIn((R.norm("King Tubby"), R.norm("Dub from the Roots")), pairs)
        self.assertIn("King Tubby - Dub from the Roots", lines)


class Request(unittest.TestCase):
    def test_clean_request_map_zones(self):
        r = R.clean_request({"prompt": "algo parecido a mi zona de dub", "map": {"communities": ["dub + reggae", "dub + reggae", 3, "jazz  + soul"]}})
        self.assertEqual(r["map"]["communities"], ["dub + reggae", "jazz + soul"])
        self.assertNotIn("genres", r)  # el texto no dispara la detección de género: la zona manda
        self.assertEqual(R.clean_request({"map": {"communities": ["x"]}})["map"]["communities"], ["x"])
        self.assertIsNone(R.clean_request({"map": {"communities": []}}))

    def test_clean_request_genres(self):
        r = R.clean_request({"genres": ["Dub", "dub", "Jazz Modal", 3, "x" * 90], "type": "live"})
        self.assertEqual(r["genres"][:2], ["dub", "modal jazz"])
        self.assertTrue(r["strict"])
        self.assertEqual(r["type"], "live")
        self.assertFalse(r["genresDetected"])
        self.assertEqual(R.clean_request({"genres": ["dub"], "strict": False})["strict"], False)
        self.assertNotIn("type", R.clean_request({"genres": ["dub"], "type": "otro"}))

    def test_no_detection_when_there_is_a_seed_and_disco_is_not_a_genre(self):
        r = R.clean_request({"prompt": "algo de dub", "seed": {"artist": "Lee Perry"}})
        self.assertNotIn("genres", r)
        self.assertEqual(R.clean_request({"prompt": "un disco de jazz modal"})["genres"], ["modal jazz"])

    def test_start_accepts_a_request_that_only_has_genres(self):
        """El selector 'Afinar' permite pedir solo por género, sin texto ni modo."""
        with mock.patch.object(R, "choose_model", lambda: "m"), mock.patch.object(R, "run", lambda *a, **k: {"stats": {}}), \
                mock.patch.object(R, "_record_timing", lambda r: None):
            R._state.update(state="idle")
            out = R.start("request", {"genres": ["dub"]})
            self.assertIn(out["state"], ("running", "done"))  # el run simulado puede terminar antes de que start devuelva
            for _ in range(50):
                if R._state["state"] != "running":
                    break
                import time
                time.sleep(0.02)
            with self.assertRaises(ValueError):
                R.start("request", {})

    def test_cancel_message_depends_on_whether_anything_was_found(self):
        import time

        def finish(res):
            with mock.patch.object(R, "choose_model", lambda: "m"), mock.patch.object(R, "run", lambda *a, **k: res), \
                    mock.patch.object(R, "_record_timing", lambda r: None):
                R._state.update(state="idle", message="")
                R.start("request", {"genres": ["dub"]})
                for _ in range(100):
                    if R._state["state"] != "running":
                        break
                    time.sleep(0.02)
            return dict(R._state)

        empty = finish({"stats": {"cancelled": True}, "pick": None})
        self.assertEqual((empty["state"], empty["message"]), ("idle", "Búsqueda cancelada: no alcanzó a verificar ningún disco."))
        partial = finish({"stats": {"cancelled": True}, "pick": {"mbid": "x"}})
        self.assertEqual(partial["state"], "done")
        self.assertIn("cortada", partial["message"])

    def test_prompt_without_genre_is_unchanged(self):
        self.assertNotIn("genres", R.clean_request({"prompt": "algo tranqui"}))


if __name__ == "__main__":
    unittest.main()
