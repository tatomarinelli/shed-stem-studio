"""Mapa de conocimiento: invariantes del grafo con datos sintéticos. Sin red ni datos reales."""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import graph as G  # noqa: E402
import memory  # noqa: E402

NOW = 1_700_000_000.0
DAY = 86400.0


def alb(artist, title, genres, days=10, sources=("tidal",)):
    return {"key": f"{memory.norm(artist)}|{memory.norm(title)}", "title": title, "artist": artist, "year": 1970, "genres": list(genres),
            "sources": list(sources), "savedAt": NOW - days * DAY}


ALBUMS = [
    alb("Miles Davis", "Kind of Blue", ["modal jazz", "jazz"], 5),
    alb("John Coltrane", "Giant Steps", ["hard bop", "jazz"], 20),
    alb("Grant Green", "Idle Moments", ["hard bop", "soul jazz"], 400),
    alb("King Tubby", "Dub From the Roots", ["dub", "reggae"], 30),
    alb("Lee Perry", "Super Ape", ["dub", "reggae"], 60, ("ytmusic",)),
    alb("Mi Banda", "Primer Disco", ["organic house"], 1),
    alb("Sin Género", "Anónimo", [], 3),
]
WEIGHTS = {"artists": [{"name": "Miles Davis", "w": 3.0}, {"name": "King Tubby", "w": 1.0}],
           "genres": [{"name": "jazz", "w": 4.0}, {"name": "reggae", "w": 2.0}]}


def build(**kw):
    args = dict(albums=ALBUMS, weights=WEIGHTS, reactions=[], recommended=[], own={"mi banda"}, now=NOW)
    args.update(kw)
    return G.build(**args)


def by_id(g):
    return {n["id"]: n for n in g["nodes"]}


class Nodes(unittest.TestCase):
    def test_own_band_never_appears(self):
        g = build(recommended=[{"artist": "Mi Banda", "album": "Otro", "genres": ["jazz"]}])
        text = repr(g)
        self.assertNotIn("Mi Banda", text)
        self.assertNotIn("organic house", text)

    def test_counts_and_ids(self):
        g = build()
        n = by_id(g)
        self.assertEqual(g["stats"]["album"], 6)
        self.assertIn(G.album_id("Miles Davis", "Kind of Blue"), n)
        self.assertIn("a:miles davis", n)
        self.assertIn("g:modal jazz", n)

    def test_idempotent(self):
        self.assertEqual(build(), build())

    def test_albums_without_genre_still_show(self):
        n = by_id(build())
        self.assertIn(G.album_id("Sin Género", "Anónimo"), n)


class Weights(unittest.TestCase):
    def test_recent_favorite_weighs_more_than_old(self):
        n = by_id(build())
        self.assertGreater(n[G.album_id("Miles Davis", "Kind of Blue")]["w"], n[G.album_id("Grant Green", "Idle Moments")]["w"])

    def test_reaction_is_per_item_and_genre_does_not_drop(self):
        base = by_id(build())
        r = [{"artist": "Grant Green", "album": "Idle Moments", "action": "no", "at": "x"}]
        g = by_id(build(reactions=r))
        self.assertEqual(g["g:hard bop"]["w"], base["g:hard bop"]["w"])
        self.assertEqual(g[G.album_id("Grant Green", "Idle Moments")]["reaction"], "no")
        loved = by_id(build(reactions=[{"artist": "Grant Green", "album": "Idle Moments", "action": "loved", "at": "x"}]))
        self.assertGreater(loved[G.album_id("Grant Green", "Idle Moments")]["w"], base[G.album_id("Grant Green", "Idle Moments")]["w"])

    def test_undated_favorite_uses_default_age(self):
        a = dict(alb("X", "Y", ["jazz"]), savedAt=None)
        n = by_id(build(albums=[a], own=set()))
        self.assertIsNone(n[G.album_id("X", "Y")]["saved"])
        self.assertAlmostEqual(n[G.album_id("X", "Y")]["w"], memory.decay(1.0, NOW - 90 * DAY, NOW, 180.0), places=3)

    def test_params_are_adjustable(self):
        a = by_id(build(params={"albumBase": 2.0}))
        b = by_id(build())
        self.assertAlmostEqual(a[G.album_id("Miles Davis", "Kind of Blue")]["w"], 2 * b[G.album_id("Miles Davis", "Kind of Blue")]["w"], places=2)


class Edges(unittest.TestCase):
    def test_dub_is_subgenre_of_reggae(self):
        g = build()
        self.assertTrue(any(e["type"] == "subgenre-of" and e["from"] == "g:dub" and e["to"] == "g:reggae" for e in g["edges"]))

    def test_similar_connects_shared_genres_not_unrelated(self):
        g = build()
        pairs = {frozenset((e["from"], e["to"])) for e in g["edges"] if e["type"] == "similar"}
        kt, lp = G.album_id("King Tubby", "Dub From the Roots"), G.album_id("Lee Perry", "Super Ape")
        miles = G.album_id("Miles Davis", "Kind of Blue")
        self.assertIn(frozenset((kt, lp)), pairs)
        self.assertNotIn(frozenset((kt, miles)), pairs)

    def test_every_edge_has_evidence_and_why_with_known_names(self):
        g = build(recommended=[{"artist": "Wes Montgomery", "album": "Smokin", "genres": ["hard bop", "jazz"]}])
        labels = {n["label"] for n in g["nodes"]} | {n.get("artist") for n in g["nodes"]}
        for e in g["edges"]:
            self.assertTrue(e["evidence"], e)
            for name in re.findall(r'"([^"]+)"', e["why"]):
                self.assertIn(name, labels | {n["label"] for n in g["nodes"]} | set(G.genregate.PARENTS), (name, e["why"]))

    def test_edges_point_to_existing_nodes(self):
        g = build(recommended=[{"artist": "Wes Montgomery", "album": "Smokin", "genres": ["hard bop"]}])
        ids = set(by_id(g))
        for e in g["edges"]:
            self.assertIn(e["from"], ids)
            self.assertIn(e["to"], ids)


class Recommended(unittest.TestCase):
    REC = {"artist": "Wes Montgomery", "album": "Smokin", "genres": ["hard bop", "jazz"], "reason": "Hard bop, como Giant Steps.", "score": 0.9}

    def test_rec_is_outside_the_network(self):
        g = build(recommended=[self.REC])
        n = by_id(g)
        rec = [x for x in g["nodes"] if x["type"] == "rec"][0]
        self.assertEqual(rec["radius"], G.PARAMS["rRec"])
        self.assertGreater(rec["radius"], max(x["radius"] for x in g["nodes"] if x["type"] != "rec"))
        self.assertTrue(any(e["type"] == "similar-to" and e["from"] == rec["id"] for e in g["edges"]))
        self.assertEqual(rec["reason"], self.REC["reason"])
        self.assertNotIn(rec["id"], {e["to"] for e in g["edges"] if e["type"] == "by"})
        self.assertIn(rec["id"], n)

    def test_already_owned_is_not_a_recommendation(self):
        g = build(recommended=[{"artist": "Miles Davis", "album": "Kind of Blue", "genres": ["jazz"]}])
        self.assertEqual(g["stats"]["rec"], 0)


class Layout(unittest.TestCase):
    def test_heavier_is_closer_to_center(self):
        n = by_id(build())
        self.assertLess(n["a:miles davis"]["radius"], n["a:grant green"]["radius"])
        self.assertLess(n["g:jazz"]["radius"], n["g:reggae"]["radius"])

    def test_same_family_shares_sector(self):
        n = by_id(build())
        self.assertEqual(n[G.album_id("King Tubby", "Dub From the Roots")]["group"], n[G.album_id("Lee Perry", "Super Ape")]["group"])
        self.assertEqual(n[G.album_id("Grant Green", "Idle Moments")]["group"], "jazz")

    def test_empty_input(self):
        g = G.build([], {"artists": [], "genres": []}, now=NOW)
        self.assertEqual(g["nodes"], [])


def world(artists, genres, n=2):
    return [alb(a, f"{a} {i}", genres, 10 + i) for a in artists for i in range(n)]


TWO_WORLDS = world(["Miles", "Coltrane", "Monk", "Evans"], ["jazz", "hard bop"]) + world(["Tubby", "Perry", "Scratch", "Mad Professor"], ["reggae", "dub"]) + \
    [alb("Puente", "Jazz 1", ["jazz", "hard bop"]), alb("Puente", "Jazz 2", ["jazz"]), alb("Puente", "Dub 1", ["dub", "reggae"]), alb("Puente", "Dub 2", ["reggae"])]
W2 = {"artists": [], "genres": [{"name": "jazz", "w": 5.0}, {"name": "reggae", "w": 5.0}]}


class Flower(unittest.TestCase):
    def test_albums_of_one_artist_circle_their_artist(self):
        g = build(albums=TWO_WORLDS, weights=W2, own=())
        n = by_id(g)
        import math
        for artist in ("Miles", "Tubby", "Puente"):
            a = n["a:" + memory.norm(artist)]
            kids = [x for x in g["nodes"] if x["type"] == "album" and x.get("artist") == artist]
            self.assertEqual(len(kids), 4 if artist == "Puente" else 2)
            dist = [math.hypot(k["x"] - a["x"], k["y"] - a["y"]) for k in kids]
            self.assertLess(max(dist), G.PARAMS["petalMax"] + 1e-3)
            self.assertAlmostEqual(min(dist), max(dist), places=2)  # parejos: todos a la misma distancia

    def test_flowers_do_not_overlap(self):
        import math
        g = build(albums=TWO_WORLDS, weights=W2, own=())
        ar = [x for x in g["nodes"] if x["type"] == "artist"]
        for i, a in enumerate(ar):
            for b in ar[i + 1:]:
                self.assertGreater(math.hypot(a["x"] - b["x"], a["y"] - b["y"]), 0.03)

    def test_similar_edges_tell_same_band_from_other_bands(self):
        g = build(albums=TWO_WORLDS, weights=W2, own=())
        sc = {e["scope"] for e in g["edges"] if e["type"] == "similar"}
        self.assertEqual(sc, {"same-artist", "other-artist"})


class ArtistRelations(unittest.TestCase):
    def test_artist_links_to_its_genres_and_to_similar_artists(self):
        g = build(albums=TWO_WORLDS, weights=W2, own=())
        e = g["edges"]
        gen = [x for x in e if x["type"] == "has-genre" and x["from"] == "a:miles"]
        self.assertEqual({x["to"] for x in gen}, {"g:jazz", "g:hard bop"})
        self.assertTrue(all(x["why"].startswith('"') and "Miles" in x["why"] for x in gen))
        rel = {x["to"] if x["from"] == "a:miles" else x["from"] for x in e if x["type"] == "related" and "a:miles" in (x["from"], x["to"])}
        self.assertTrue(rel & {"a:coltrane", "a:monk", "a:evans"})
        self.assertFalse(rel & {"a:tubby", "a:perry"})  # otro mundo: no se relacionan

    def test_related_is_symmetric_without_duplicates(self):
        g = build(albums=TWO_WORLDS, weights=W2, own=())
        pairs = [tuple(sorted((x["from"], x["to"]))) for x in g["edges"] if x["type"] == "related"]
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_gaps_count_albums_not_artists(self):
        gaps = {x["genre"]: x for x in G.build(ALBUMS, WEIGHTS, [], [], (), NOW)["gaps"]}
        self.assertIn("lo tenés en 2 discos", gaps["dancehall"]["why"])  # King Tubby y Lee Perry: 2 discos de reggae, no 4 nodos


class Inherited(unittest.TestCase):
    def test_album_without_genres_inherits_artist_genres(self):
        albums = [alb("Ghost", "Sin Tags", [], 5), alb("Otro", "Jazz Uno", ["hard bop", "jazz"], 5)]
        g = G.build(albums, W2, [], [], (), NOW, artist_genres={"ghost": ["jazz", "hard bop"]})
        n = by_id(g)
        d = n[G.album_id("Ghost", "Sin Tags")]
        self.assertEqual(d["genresFrom"], "artist")
        e = [x for x in g["edges"] if x["type"] == "has-genre" and x["from"] == d["id"]]
        self.assertEqual({x["to"] for x in e}, {"g:jazz", "g:hard bop"})
        self.assertTrue(all("no tiene géneros propios" in x["why"] for x in e))
        self.assertTrue(any(x["type"] == "similar" and d["id"] in (x["from"], x["to"]) for x in g["edges"]))  # ya se relaciona con otros

    def test_no_fallback_stays_marked(self):
        g = G.build([alb("Ghost", "Sin Tags", [], 5)], W2, [], [], (), NOW)
        self.assertEqual(g["nodes"][0]["genresFrom"] if g["nodes"][0]["type"] == "album" else by_id(g)[G.album_id("Ghost", "Sin Tags")]["genresFrom"], "none")

    def test_inherited_genres_do_not_hide_a_gap(self):
        g = G.build([alb("Ghost", "Sin Tags", [], 5)], W2, [], [], (), NOW, artist_genres={"ghost": ["dancehall", "reggae"]})
        self.assertNotIn("dancehall", {x["genre"] for x in g["gaps"]})  # no hay discos con género propio


class Context(unittest.TestCase):
    def test_context_lists_every_artist_of_the_zone(self):
        g = build(albums=TWO_WORLDS, weights=W2, own=(), params={"commMin": 3})
        jazz = next(c["name"] for c in g["communities"] if "jazz" in c["name"])
        z = G.context([jazz], g)
        names = {a["name"] for a in z["artists"]}
        self.assertTrue({"Miles", "Coltrane", "Monk", "Evans"} <= names)  # todos, no solo dos
        self.assertFalse(names & {"Tubby", "Perry"})
        self.assertIn("jazz", z["genres"])
        self.assertTrue(all(a["genres"] for a in z["artists"] if a["name"] in {"Miles", "Monk"}))
        self.assertTrue(z["albums"] and all(" - " in x for x in z["albums"]))

    def test_unknown_zone_is_none(self):
        self.assertIsNone(G.context(["no existe"], build()))

    def test_own_band_never_in_context(self):
        g = build()
        for c in g["communities"]:
            z = G.context([c["name"]], g)
            self.assertNotIn("Mi Banda", repr(z))


class Insights(unittest.TestCase):
    def setUp(self):
        self.g = build(albums=TWO_WORLDS, weights=W2, own=(), params={"commMin": 3})

    def test_two_worlds_two_communities(self):
        n = by_id(self.g)
        self.assertEqual(n["a:miles"]["community"], n["a:coltrane"]["community"])
        self.assertEqual(n["a:tubby"]["community"], n["a:perry"]["community"])
        self.assertNotEqual(n["a:miles"]["community"], n["a:tubby"]["community"])
        self.assertTrue(any("jazz" in c["name"] for c in self.g["communities"]))

    def test_communities_are_deterministic(self):
        self.assertEqual(self.g["communities"], build(albums=TWO_WORLDS, weights=W2, own=(), params={"commMin": 3})["communities"])

    def test_bridge_is_found_and_verifiable(self):
        ids = {b["id"] for b in self.g["bridges"]}
        self.assertIn("a:puente", ids)
        names = {c["name"] for c in self.g["communities"]}
        for b in self.g["bridges"]:
            self.assertEqual(len(b["communities"]), 2)
            for c in b["communities"]:
                self.assertIn(self.g["communities"][c]["name"], b["why"])
            self.assertTrue(b["why"].startswith('"' + b["label"] + '"'))
        self.assertTrue(names)

    def test_gap_is_a_neighbor_genre_without_albums(self):
        gaps = {x["genre"]: x for x in G.build(ALBUMS, WEIGHTS, [], [], (), NOW)["gaps"]}
        self.assertIn("dancehall", gaps)  # hijo de reggae, que sí tenés
        self.assertNotIn("dub", gaps)     # dub ya tiene discos
        self.assertIn('"reggae"', gaps["dancehall"]["why"])

    def test_refused_genre_is_not_a_gap(self):
        albums = ALBUMS + [alb("X", "Y", ["dancehall"], 5)]
        gaps = G.build(albums, WEIGHTS, [{"artist": "X", "album": "Y", "action": "no", "at": NOW}], [], (), NOW)["gaps"]
        self.assertNotIn("dancehall", {x["genre"] for x in gaps})


if __name__ == "__main__":
    unittest.main()
