"""Barrera de género: decide con géneros de MusicBrainz si un disco es del género pedido. Sin red."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import genregate as G  # noqa: E402


class Relation(unittest.TestCase):
    def test_exact_and_aliases(self):
        self.assertEqual(G.relation("dub", "dub")[0], 1.0)
        self.assertEqual(G.relation("Jazz Modal", "modal jazz")[0], 1.0)  # español -> MusicBrainz
        self.assertEqual(G.relation("rap", "hip hop")[0], 1.0)

    def test_variant_subgenre_and_family(self):
        self.assertEqual(G.relation("dub", "dub techno"), (0.9, "variante"))
        self.assertEqual(G.relation("reggae", "dub"), (0.9, "subgénero"))   # pedí reggae y es dub: sirve
        self.assertEqual(G.relation("dub", "reggae"), (0.5, "familia"))     # pedí dub y es reggae a secas: cercano
        self.assertEqual(G.relation("roots reggae", "reggae"), (0.5, "familia"))

    def test_unrelated_is_below_weak_even_with_noisy_embeddings(self):
        v, _ = G.relation("dub", "death metal", soft=1.0)
        self.assertLess(v, G.WEAK)  # los embeddings solos nunca alcanzan para "cercano"


class Judge(unittest.TestCase):
    def test_match_weak_off(self):
        self.assertEqual(G.judge(["dub"], ["dub", "reggae"])["status"], "match")
        self.assertEqual(G.judge(["dub"], ["reggae", "roots reggae"])["status"], "weak")
        r = G.judge(["dub"], ["indie rock", "alternative rock"])
        self.assertEqual(r["status"], "off")
        self.assertIn("indie rock", r["why"])  # el motivo sale de los géneros reales

    def test_requested_genre_far_down_the_list_is_only_close(self):
        """Medido: un disco de post-rock con 'ambient' en 5.º lugar no es un disco de ambient."""
        r = G.judge(["ambient"], ["post-rock", "rock", "instrumental", "experimental", "ambient"])
        self.assertEqual(r["status"], "weak")
        self.assertIn("secundario", r["matched"]["via"])
        self.assertEqual(G.judge(["ambient"], ["post-rock", "ambient"])["status"], "match")  # entre los 3 primeros sí

    def test_no_request_always_passes(self):
        self.assertEqual(G.judge([], ["death metal"])["status"], "match")

    def test_unknown_when_no_genres_anywhere(self):
        self.assertEqual(G.judge(["dub"], [], [])["status"], "unknown")

    def test_artist_genres_fill_in_when_disc_has_none(self):
        r = G.judge(["dub"], [], ["dub", "reggae"])
        self.assertEqual((r["status"], r["source"]), ("match", "artista"))

    def test_disc_off_but_artist_matches_is_only_weak(self):
        r = G.judge(["dub"], ["pop"], ["dub"])
        self.assertEqual(r["status"], "weak")
        self.assertLessEqual(r["score"], 0.6)

    def test_any_requested_genre_is_enough(self):
        self.assertEqual(G.judge(["bossa nova", "samba"], ["samba"])["status"], "match")


class Detect(unittest.TestCase):
    def test_finds_genres_in_free_text(self):
        self.assertEqual(G.detect("algo de dub para la tarde"), ["dub"])
        self.assertEqual(G.detect("un disco de jazz modal o bossa"), ["modal jazz", "bossa nova"])
        self.assertEqual(G.detect("quiero algo tranquilo"), [])

    def test_does_not_split_longer_names(self):
        self.assertEqual(G.detect("post rock instrumental"), ["post-rock"])


if __name__ == "__main__":
    unittest.main()
