"""Pruebas de la memoria: decaimiento, compactación, reacciones por ítem y resumen. Sin red y en carpetas temporales.

Correr: cd engine && python3 -m unittest discover -s tests -v
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import memory as M  # noqa: E402
from perms import assert_private  # noqa: E402

DAY = 86400.0
T0 = 1_700_000_000.0  # fecha fija: nada depende del reloj


def ev(day, action, mbid, artist="Bob Marley", album="Exodus", genres=("reggae",)):
    return M.make_event(T0 + day * DAY, "reaction", mbid, artist, album, action, list(genres))


def gw(w, name):
    return next((x["w"] for x in w["genres"] if x["name"] == name), 0.0)


def aw(w, name):
    return next((x["w"] for x in w["artists"] if x["name"] == name), 0.0)


class Decay(unittest.TestCase):
    def test_half_life(self):
        self.assertAlmostEqual(M.decay(1.0, T0, T0 + 180 * DAY, 180), 0.5)
        self.assertAlmostEqual(M.decay(1.0, T0, T0 + 360 * DAY, 180), 0.25)
        self.assertEqual(M.decay(1.0, T0, T0 - DAY, 180), 1.0)  # hacia atrás no crece

    def test_reggae_fades_until_cut(self):
        """Un año de reggae a full y después nada: pierde peso hasta recortarse."""
        sources = [{"kind": "album", "artist": f"Artista {i}", "title": f"Disco {i}", "added": T0 + i * DAY} for i in range(10)]
        genres = lambda a, t: ["reggae"]
        hl = M.HALF_LIFE_DAYS
        t = M.empty_taste(hl)
        w_then = M.weights(t, [], sources, {}, T0 + 10 * DAY, genres)
        w_1y = M.weights(t, [], sources, {}, T0 + 375 * DAY, genres)
        w_4y = M.weights(t, [], sources, {}, T0 + 4 * 365 * DAY, genres)
        self.assertGreater(gw(w_then, "reggae"), 4.0)
        self.assertLess(gw(w_1y, "reggae"), gw(w_then, "reggae") * 0.3)
        self.assertEqual(gw(w_4y, "reggae"), 0.0)  # 10 discos: se recorta en ~3,5 años (por debajo de PRUNE)
        one = [sources[0]]
        self.assertEqual(gw(M.weights(t, [], one, {}, T0 + 2.2 * 365 * DAY, genres), "reggae"), 0.0)  # 1 disco: ~2 años

    def test_recent_beats_old(self):
        sources = [{"kind": "artist", "artist": "Viejo", "added": T0}, {"kind": "artist", "artist": "Nuevo", "added": T0 + 400 * DAY}]
        w = M.weights(M.empty_taste(), [], sources, {}, T0 + 410 * DAY)
        self.assertEqual(w["artists"][0]["name"], "Nuevo")

    def test_decades_from_album_years(self):
        sources = [{"kind": "album", "artist": "A", "title": "B", "added": T0, "year": 1963},
                   {"kind": "album", "artist": "C", "title": "D", "added": T0, "year": 1965},
                   {"kind": "album", "artist": "E", "title": "F", "added": T0, "year": 1999}]
        w = M.weights(M.empty_taste(), [], sources, {}, T0)
        self.assertEqual([(d["name"], d["w"]) for d in w["decades"]], [("1960s", 1.0), ("1990s", 0.5)])

    def test_declared_does_not_decay(self):
        w = M.weights(M.empty_taste(), [], [], {"genres": ["jazz"], "artists": []}, T0 + 5000 * DAY)
        self.assertEqual(gw(w, "jazz"), M.DECLARED_W)


class Reactions(unittest.TestCase):
    def test_no_is_per_item(self):
        """"No me va" excluye ESE disco pero no resta al artista ni al género."""
        w = M.weights(M.empty_taste(), [ev(0, "no", "a")], [], {}, T0 + DAY)
        self.assertEqual(gw(w, "reggae"), 0.0)
        self.assertEqual(aw(w, "Bob Marley"), 0.0)
        self.assertEqual(M.reactions_map(M.empty_taste(), [ev(0, "no", "a")]), {"a": "no"})

    def test_latest_reaction_wins_and_clear_undoes(self):
        evs = [ev(0, "loved", "a"), ev(1, "no", "a")]
        self.assertEqual(gw(M.weights(M.empty_taste(), evs, [], {}, T0 + 2 * DAY), "reggae"), 0.0)
        evs = [ev(0, "loved", "a"), ev(0.01, "clear", "a")]
        t = M.empty_taste()
        self.assertEqual(M.reactions_map(t, evs), {})
        self.assertEqual(M.history(t, evs), [])

    def test_loved_adds_evidence(self):
        w = M.weights(M.empty_taste(), [ev(0, "loved", "a")], [], {}, T0)
        self.assertAlmostEqual(aw(w, "Bob Marley"), 3.0)
        self.assertAlmostEqual(gw(w, "reggae"), 1.0)


class NewReactions(unittest.TestCase):
    def test_liked_is_between_heard_and_loved(self):
        w = M.weights(M.empty_taste(), [ev(0, "liked", "a")], [], {}, T0)
        self.assertAlmostEqual(aw(w, "Bob Marley"), 1.5)
        self.assertAlmostEqual(gw(w, "reggae"), 0.5)

    def test_disliked_only_touches_that_artist_never_the_genre(self):
        evs = [ev(0, "loved", "a", artist="X", genres=("reggae",)), ev(0, "disliked", "b", artist="Y", genres=("reggae",))]
        w = M.weights(M.empty_taste(), evs, [], {}, T0)
        self.assertAlmostEqual(gw(w, "reggae"), 1.0)  # el género no baja por el "no" a un disco
        self.assertEqual(aw(w, "Y"), 0.0)             # y el artista ni aparece (peso negativo recortado)
        self.assertEqual(M.reactions_map(M.empty_taste(), evs)["b"], "disliked")

    def test_legacy_heard_still_counts(self):
        w = M.weights(M.empty_taste(), [ev(0, "heard", "a")], [], {}, T0)
        self.assertAlmostEqual(aw(w, "Bob Marley"), 0.5)
        self.assertEqual(M.LABELS["heard"], "Lo conocía")

    def test_change_of_mind_after_compaction_with_new_actions(self):
        taste, keep = M.compact(M.empty_taste(), [ev(0, "disliked", "a")], T0 + 100 * DAY)
        self.assertEqual(keep, [])
        w = M.weights(taste, [ev(101, "liked", "a")], [], {}, T0 + 101 * DAY, cut=0)
        self.assertAlmostEqual(aw(w, "Bob Marley"), 1.5, places=6)

    def test_known_flag_travels_to_history_and_survives_compaction(self):
        e = M.make_event(T0, "reaction", "a", "X", "Y", "liked", ["jazz"], known=True)
        self.assertTrue(e["known"])
        self.assertNotIn("known", M.make_event(T0, "reaction", "b", "X", "Z", "liked"))
        self.assertTrue(M.history(M.empty_taste(), [e])[0]["known"])
        taste, _ = M.compact(M.empty_taste(), [e], T0 + 100 * DAY)
        self.assertTrue(M.history(taste, [])[0]["known"])

    def test_reason_only_valid_values(self):
        self.assertEqual(M.make_event(T0, "reaction", "a", "X", "Y", "no", reason="off_genre")["reason"], "off_genre")
        self.assertNotIn("reason", M.make_event(T0, "reaction", "a", "X", "Y", "no", reason="otra cosa"))


class Compaction(unittest.TestCase):
    def events(self):
        out = []
        for i in range(40):  # 40 reacciones a lo largo de 400 días
            out.append(ev(i * 10, "loved" if i % 3 else "heard", f"m{i}", artist=f"A{i % 4}", genres=("jazz", f"g{i % 5}")))
        return out

    def test_compact_then_read_equals_no_compaction(self):
        evs = self.events()
        t1, t2 = T0 + 420 * DAY, T0 + 600 * DAY
        plain = M.weights(M.empty_taste(), evs, [], {}, t2, cut=0)
        taste, keep = M.compact(M.empty_taste(), evs, t1)
        self.assertLess(len(keep), len(evs))
        compacted = M.weights(taste, keep, [], {}, t2, cut=0)
        # Igual salvo lo que la poda recortó (pesos < PRUNE en t1, que en t2 son todavía menores).
        for field in ("artists", "genres"):
            a = {x["name"]: x["w"] for x in plain[field]}
            b = {x["name"]: x["w"] for x in compacted[field]}
            for name, w in a.items():
                self.assertAlmostEqual(b.get(name, 0.0), w, delta=M.PRUNE, msg=name)
        self.assertEqual(M.reactions_map(M.empty_taste(), evs), M.reactions_map(taste, keep))

    def test_compaction_is_idempotent_and_bounded(self):
        evs = self.events()
        now = T0 + 420 * DAY
        taste, keep = M.compact(M.empty_taste(), evs, now)
        taste2, keep2 = M.compact(taste, keep, now)
        self.assertEqual(keep, keep2)
        self.assertEqual(taste["artists"], taste2["artists"])
        many = [ev(i * 0.001, "heard", f"x{i}") for i in range(M.RAW_MAX + 50)]
        _, rest = M.compact(M.empty_taste(), many, T0 + DAY)
        self.assertLessEqual(len(rest), M.RAW_MAX)

    def test_change_of_mind_after_compaction(self):
        evs = [ev(0, "loved", "a")]
        taste, keep = M.compact(M.empty_taste(), evs, T0 + 100 * DAY)
        self.assertEqual(keep, [])
        later = [ev(101, "no", "a")]
        w = M.weights(taste, later, [], {}, T0 + 101 * DAY, cut=0)
        self.assertAlmostEqual(gw(w, "reggae"), 0.0, places=6)
        self.assertEqual(M.reactions_map(taste, later), {"a": "no"})

    def test_old_shown_events_dropped(self):
        shown = [M.make_event(T0, "shown", "s", "X", "Y")]
        _, keep = M.compact(M.empty_taste(), shown, T0 + 100 * DAY)
        self.assertEqual(keep, [])

    def test_store_roundtrip_and_permissions(self):
        with tempfile.TemporaryDirectory() as d:
            st = M.Store(d)
            for e in self.events():
                st.append(e)
            with open(os.path.join(d, "events.jsonl"), "a") as f:
                f.write('{"roto": \n')  # una línea cortada no rompe la lectura
            self.assertEqual(len(st.load_events()), 40)
            taste, keep = st.compact(T0 + 420 * DAY)
            self.assertEqual(len(st.load_events()), len(keep))
            self.assertEqual(json.loads(Path(d, "taste.json").read_text())["artists"], taste["artists"])
            assert_private(self, os.path.join(d, "taste.json"))
            assert_private(self, os.path.join(d, "events.jsonl"))


class Summary(unittest.TestCase):
    def test_summary_only_uses_data(self):
        sources = [{"kind": "album", "artist": "Bob Marley", "title": "Exodus", "added": T0},
                   {"kind": "album", "artist": "Miles Davis", "title": "Kind of Blue", "added": T0 + 300 * DAY}]
        g = {"Exodus": ["reggae"], "Kind of Blue": ["modal jazz"]}
        genres = lambda a, t: g[t]
        now = T0 + 320 * DAY
        w_now = M.weights(M.empty_taste(), [], sources, {}, now, genres)
        w_before = M.weights(M.empty_taste(), [], sources, {}, now - 180 * DAY, genres)
        md = M.summary(w_now, w_before, [], "Toca guitarra.", now)
        self.assertIn("modal jazz", md)
        self.assertIn("Bajando", md)
        self.assertIn("reggae", md.split("## Bajando")[1])
        self.assertLess(len(md), 1500)


if __name__ == "__main__":
    unittest.main()
