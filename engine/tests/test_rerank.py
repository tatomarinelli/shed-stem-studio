"""Re-ranking con diversidad (MMR): puro, sin red."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import rerank as RR  # noqa: E402


def v(name, score, genres, year=1960):
    return {"artist": name, "score": score, "genres": genres, "year": year}


HB = ["jazz", "hard bop"]


class Similarity(unittest.TestCase):
    def test_same_genres_and_decade_are_identical_unrelated_are_zero(self):
        self.assertEqual(RR.similarity(v("a", 1, HB), v("b", 1, HB)), 1.0)
        self.assertEqual(RR.similarity(v("a", 1, HB, 1960), v("b", 1, ["funk", "soul"], 1990)), 0.0)

    def test_the_requested_genre_is_ignored_because_everyone_shares_it(self):
        a, b = v("a", 1, ["bebop", "jazz"]), v("b", 1, ["bebop", "hard bop"])
        self.assertLess(RR.similarity(a, b, ignore={"bebop"}), RR.similarity(a, b))

    def test_missing_years_and_genres_do_not_break_it(self):
        self.assertEqual(RR.similarity({"genres": [], "year": None}, {"genres": None}), 0.0)


class Diversify(unittest.TestCase):
    def test_first_is_always_the_best_score(self):
        out, _ = RR.diversify([v("a", 0.6, HB), v("b", 0.9, HB), v("c", 0.8, ["funk"])], k=3)
        self.assertEqual(out[0]["artist"], "b")

    def test_a_clone_loses_to_a_slightly_worse_but_different_disc(self):
        items = [v("a", 0.95, HB), v("clone", 0.93, HB), v("distinto", 0.85, ["modal jazz", "post-bop"], 1970)]
        out, rest = RR.diversify(items, k=2, lam=0.7)
        self.assertEqual([x["artist"] for x in out], ["a", "distinto"])
        self.assertEqual([x["artist"] for x in rest], ["clone"])
        self.assertEqual(out[1]["diversity"], 0.0)

    def test_lam_one_is_plain_score_order(self):
        items = [v("a", 0.95, HB), v("clone", 0.93, HB), v("distinto", 0.85, ["funk"], 1970)]
        out, _ = RR.diversify(items, k=3, lam=1.0)
        self.assertEqual([x["artist"] for x in out], ["a", "clone", "distinto"])

    def test_tiers_are_never_mixed_until_the_better_one_runs_out(self):
        """Un 'cercano' no se cuela por ser distinto mientras queden discos del género exacto."""
        items = [v("a", 0.95, HB), v("clone", 0.90, HB), v("cercano", 0.60, ["funk"], 1990)]
        out, _ = RR.diversify(items, k=3, lam=0.5, tier=lambda x: 1 if x["artist"] == "cercano" else 0)
        self.assertEqual([x["artist"] for x in out], ["a", "clone", "cercano"])

    def test_fewer_items_than_k_and_empty(self):
        self.assertEqual(RR.diversify([], k=4), ([], []))
        self.assertEqual(len(RR.diversify([v("a", 1, HB)], k=4)[0]), 1)

    def test_does_not_mutate_the_input(self):
        items = [v("a", 0.9, HB), v("b", 0.8, HB)]
        RR.diversify(items, k=2)
        self.assertNotIn("diversity", items[0])


class Spread(unittest.TestCase):
    def test_spread_goes_up_with_variety(self):
        same = [v("a", 1, HB), v("b", 1, HB), v("c", 1, HB)]
        varied = [v("a", 1, HB), v("b", 1, ["funk"], 1990), v("c", 1, ["dub"], 1975)]
        self.assertEqual(RR.spread(same), 0.0)
        self.assertGreater(RR.spread(varied), 0.9)
        self.assertIsNone(RR.spread([v("a", 1, HB)]))


if __name__ == "__main__":
    unittest.main()
