"""Plan por tipo de pedido: cuánto pesan los gustos, el instrumento y los objetivos de estudio según qué se pide. Puro, sin red."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import genregate  # noqa: E402
import planner as P  # noqa: E402
import profile as PR  # noqa: E402


class Kind(unittest.TestCase):
    def test_priority_seed_canon_country_genre_mode_text_forvos(self):
        self.assertEqual(P.kind_of({"seed": {"artist": "X"}, "canon": True, "countries": ["AR"], "genres": ["dub"], "mode": "estudiar", "prompt": "x"}), "parecido_a")
        self.assertEqual(P.kind_of({"canon": True, "countries": ["AR"], "genres": ["dub"]}), "clasicos")
        self.assertEqual(P.kind_of({"countries": ["AR"], "genres": ["dub"]}), "origen")
        self.assertEqual(P.kind_of({"genres": ["dub"], "mode": "estudiar"}), "genero")
        self.assertEqual(P.kind_of({"mode": "estudiar", "prompt": "x"}), "modo")
        self.assertEqual(P.kind_of({"prompt": "algo tranquilo"}), "texto")
        self.assertEqual(P.kind_of({}), "para_vos")
        self.assertEqual(P.kind_of(None), "para_vos")


class Weights(unittest.TestCase):
    def test_similar_to_another_disc_barely_weighs_taste_instrument_or_goals(self):
        p = P.plan({"seed": {"artist": "Miles Davis"}})
        self.assertEqual((p["kind"], p["taste"], p["requestWeight"]), ("parecido_a", 0.25, 0.75))
        self.assertEqual((p["useInstrument"], p["useGoals"], p["useTaste"]), (False, False, False))
        self.assertIn("Tu instrumento no se usa en este pedido", p["why"])

    def test_for_you_uses_everything_and_taste_follows_the_discovery_setting(self):
        p = P.plan({})
        self.assertEqual((p["kind"], p["taste"], p["requestWeight"]), ("para_vos", None, 0.0))
        self.assertEqual((p["useInstrument"], p["useGoals"], p["useTaste"]), (True, True, True))
        self.assertEqual(p["why"], [])

    def test_daily_disc_in_another_mode_skips_study_goals_but_keeps_the_instrument(self):
        p = P.plan(None, mode_from_preset="concentrarme")
        self.assertEqual((p["useInstrument"], p["useGoals"]), (True, False))
        self.assertTrue(P.plan(None, mode_from_preset="estudiar")["useGoals"])

    def test_studying_uses_instrument_and_goals_whatever_the_kind(self):
        p = P.plan({"genres": ["dub"], "mode": "estudiar"})
        self.assertEqual((p["kind"], p["useInstrument"], p["useGoals"]), ("genero", True, True))

    def test_country_and_classics_leave_taste_out_with_low_weight(self):
        self.assertEqual((P.plan({"countries": ["AR"]})["taste"], P.plan({"countries": ["AR"]})["useTaste"]), (0.5, False))
        c = P.plan({"canon": True, "countries": ["AR"]})
        self.assertEqual((c["kind"], c["taste"], c["useTaste"]), ("clasicos", 0.3, False))

    def test_surprise_me_lowers_taste(self):
        self.assertEqual(P.plan({"mode": "sorprenderme"})["taste"], 0.25)


class Similarity(unittest.TestCase):
    def sim(self, genres, year):
        return P.seed_similarity(genres, year, ["modal jazz", "cool jazz"], 1959, genregate.relation)

    def test_same_genres_and_decade_beats_related_beats_unrelated(self):
        same, related, far = self.sim(["modal jazz", "cool jazz"], 1955), self.sim(["jazz", "hard bop"], 1955), self.sim(["funk", "soul"], 1995)  # 1955: misma década que 1959
        self.assertEqual(same, 1.0)
        self.assertGreater(same, related)
        self.assertGreater(related, far)
        self.assertLess(far, 0.2)

    def test_decade_matters_but_less_than_genre(self):
        self.assertGreater(self.sim(["modal jazz", "cool jazz"], 1995), self.sim(["funk"], 1959))
        self.assertGreater(self.sim(["modal jazz", "cool jazz"], 1959), self.sim(["modal jazz", "cool jazz"], 1995))
        self.assertEqual(self.sim(["modal jazz", "cool jazz"], 1960), 0.9)  # 1959 y 1960 son décadas vecinas: media cercanía

    def test_unknown_year_is_neutral_and_no_seed_genres_is_zero(self):
        self.assertEqual(P.decade_closeness(None, 1959), 0.5)
        self.assertEqual(P.seed_similarity(["jazz"], 1960, [], 1959, genregate.relation), 0.0)


class DescribeSkips(unittest.TestCase):
    PROF = {"instrument": "guitarra", "level": "avanzado", "improve": ["modos"], "loves": ["jazz"], "avoids": ["smooth jazz"], "essentials": ["Miles Davis"],
            "listening": "discos", "discovery": "algo", "pace": "30", "notes": "", "updatedAt": 1}

    def test_skip_removes_only_the_requested_parts(self):
        full = PR.describe(self.PROF)
        self.assertIn("Toca guitarra", full)
        self.assertIn("Quiere mejorar", full)
        cut = PR.describe(self.PROF, {"instrument", "pace", "improve", "loves", "essentials"})
        for gone in ("Toca guitarra", "Quiere mejorar", "Ama:", "Imprescindibles", "Estudia unos"):
            self.assertNotIn(gone, cut)
        for kept in ("Evita: smooth jazz", "Escucha discos enteros", "Quiere conocer algo"):
            self.assertIn(kept, cut)  # lo que evita y cómo escucha siguen valiendo para cualquier pedido


if __name__ == "__main__":
    unittest.main()
