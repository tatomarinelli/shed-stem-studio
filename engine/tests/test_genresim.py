"""Similitud de géneros con vectores sintéticos (sin modelo)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import genresim as G  # noqa: E402
import recs as R  # noqa: E402


class Sim(unittest.TestCase):
    def test_soft_mapping(self):
        self.assertEqual(G.soft(0.5), 0.0)
        self.assertEqual(G.soft(0.99), 1.0)
        self.assertAlmostEqual(G.soft((G.LOW + G.HIGH) / 2), 0.5)

    def test_embeddings_generalize_tokens_stay(self):
        vecs = {"soul jazz": [1.0, 0.1], "hard bop": [1.0, 0.12], "reggae": [0.0, 1.0]}
        tok = lambda a, b: R._match(R.norm(a), R.norm(b))
        self.assertEqual(tok("soul jazz", "hard bop"), 0.0)
        self.assertGreater(G.similarity("soul jazz", "hard bop", vecs, tok), 0.9)
        self.assertEqual(G.similarity("soul jazz", "reggae", vecs, tok), 0.0)
        self.assertEqual(G.similarity("jazz", "modal jazz", {}, tok), 0.5)  # sin vectores: palabras

    def test_assess_uses_vectors(self):
        snap = {"weights": {"genres": [{"name": "hard bop", "w": 1.0, "from": ["favoritos"]}], "artists": []},
                "history": [], "taste": {"known": {}}, "sources": [], "profile": {}}
        fit0, _, _ = R.assess(["soul jazz"], "X", snap, None, {})
        fit1, reason, _ = R.assess(["soul jazz"], "X", snap, None, {}, {"soul jazz": [1.0, 0.1], "hard bop": [1.0, 0.12]})
        self.assertEqual(fit0, 0.0)
        self.assertGreater(fit1, 0.5)
        self.assertIn("soul jazz", reason.lower())


if __name__ == "__main__":
    unittest.main()
