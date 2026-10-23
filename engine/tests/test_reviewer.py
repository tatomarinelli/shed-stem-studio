"""Agente revisor: pedido al modelo, lectura estricta de la respuesta y efecto acotado (solo baja). Sin red ni modelos."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import reviewer as RV  # noqa: E402

ITEMS = [{"n": 1, "artist": "Brian Eno", "album": "Music for Airports", "year": 1978, "genres": ["ambient"]},
         {"n": 2, "artist": "The Meters", "album": "Rejuvenation", "year": 1974, "genres": ["funk", "soul"]}]


class Prompt(unittest.TestCase):
    def test_prompt_has_request_mode_taste_and_numbered_real_discs(self):
        p = RV.build_prompt({"genres": ["ambient"], "prompt": "algo tranquilo"}, "concentrarme", ["Miles Davis", "Bill Evans"], ITEMS)
        self.assertIn("concentrarse", p)
        self.assertIn("Género: ambient", p)
        self.assertIn('"algo tranquilo"', p)
        self.assertIn("Suele escuchar: Miles Davis, Bill Evans", p)
        self.assertIn("1. Brian Eno - Music for Airports (1978) [ambient]", p)
        self.assertIn("2. The Meters - Rejuvenation (1974) [funk, soul]", p)

    def test_unknown_mode_and_empty_request_do_not_break(self):
        self.assertIn("probablemente no conozca", RV.build_prompt(None, None, [], ITEMS))
        self.assertIn("1.", RV.build_prompt({}, "inventado", [], ITEMS))


class Parse(unittest.TestCase):
    def test_keeps_only_valid_numbers_and_closed_values(self):
        data = {"revisiones": [{"n": 1, "encaja": "si", "motivo": "ok"}, {"n": 2, "encaja": "no", "motivo": "energia"}, {"n": 99, "encaja": "no", "motivo": "ok"},
                               {"n": 2, "encaja": "si", "motivo": "ok"}, {"n": 1, "encaja": "quizás", "motivo": "ok"}, {"n": 3, "encaja": "no", "motivo": "inventado"}]}
        out = RV.parse(data, {1, 2, 3})
        self.assertEqual(out, {1: {"fit": "si", "issue": "ok"}, 2: {"fit": "no", "issue": "energia"}})  # el primero de cada n; fuera de lista y de enum no entran

    def test_garbage_is_ignored(self):
        for bad in (None, [], {"revisiones": "x"}, {"revisiones": [1, "a", None]}):
            self.assertEqual(RV.parse(bad, {1}), {})

    def test_a_yes_never_carries_an_issue(self):
        self.assertEqual(RV.parse({"revisiones": [{"n": 1, "encaja": "si", "motivo": "energia"}]}, {1})[1]["issue"], "ok")


class GenreAlreadyVerified(unittest.TestCase):
    """Medido con gemma3:4b: con el género ya comprobado por MusicBrainz, dudó de 10 de 13 discos con 'no parece lo que pediste' (juzgaba el género
    de nuevo con lo que recuerda) y eso forzó rondas extra. Si se pidió un género, el revisor no lo juzga."""

    def test_prompt_tells_the_model_not_to_judge_the_genre(self):
        p = RV.build_prompt({"genres": ["modal jazz"]}, "estudiar", [], ITEMS, genre_verified=True)
        self.assertIn("ya están verificados con datos: NO los juzgues", p)
        self.assertNotIn("NO los juzgues", RV.build_prompt({"genres": ["modal jazz"]}, "estudiar", [], ITEMS))
        self.assertNotIn("NO los juzgues", RV.build_prompt({}, "estudiar", [], ITEMS, genre_verified=True))  # sin género pedido no hay nada que aclarar

    def test_not_asked_is_ignored_but_other_issues_still_count(self):
        data = {"revisiones": [{"n": 1, "encaja": "no", "motivo": "no_pedido"}, {"n": 2, "encaja": "no", "motivo": "energia"}]}
        self.assertEqual(RV.parse(data, {1, 2}, ignore=("no_pedido",)), {1: {"fit": "si", "issue": "ok"}, 2: {"fit": "no", "issue": "energia"}})
        self.assertEqual(RV.parse(data, {1, 2})[1]["fit"], "no")  # sin género verificado, se acepta

    def test_review_passes_the_flag_through(self):
        def chat(model, system, user, schema, temperature):
            self.assertIn("NO los juzgues", user)
            return {"revisiones": [{"n": 1, "encaja": "no", "motivo": "no_pedido"}]}, {"promptTokens": 1, "evalTokens": 1}

        out, _ = RV.review(chat, "m", {"genres": ["ambient"]}, "estudiar", [], ITEMS, genre_verified=True)
        self.assertEqual(out[1]["fit"], "si")


class Effect(unittest.TestCase):
    def test_review_can_only_lower_the_score(self):
        for fit in RV.FITS:
            self.assertLessEqual(RV.adjust(0.9, {"fit": fit, "issue": "ok"}), 0.9)
        self.assertEqual(RV.adjust(0.9, {"fit": "si", "issue": "ok"}), 0.9)
        self.assertEqual(RV.adjust(0.9, None), 0.9)
        self.assertLess(RV.adjust(0.9, {"fit": "no", "issue": "energia"}), RV.adjust(0.9, {"fit": "dudoso", "issue": "energia"}))

    def test_note_comes_from_a_fixed_table_and_says_it_is_an_opinion(self):
        self.assertIsNone(RV.note({"fit": "si", "issue": "ok"}))
        self.assertIsNone(RV.note(None))
        n = RV.note({"fit": "no", "issue": "energia"})
        self.assertIn("opinión del modelo, no verificada", n)
        self.assertIn("la energía no encaja", n)
        self.assertIn("dudó", RV.note({"fit": "dudoso", "issue": "animo"}))

    def test_review_calls_the_model_once_and_parses(self):
        calls = []

        def chat(model, system, user, schema, temperature):
            calls.append((model, schema is RV.SCHEMA, temperature))
            return {"revisiones": [{"n": 1, "encaja": "si", "motivo": "ok"}, {"n": 2, "encaja": "no", "motivo": "energia"}]}, {"promptTokens": 50, "evalTokens": 9}

        out, st = RV.review(chat, "m", {"prompt": "x"}, "concentrarme", [], ITEMS)
        self.assertEqual(calls, [("m", True, 0.1)])
        self.assertEqual(out[2]["fit"], "no")
        self.assertEqual(st["promptTokens"], 50)


if __name__ == "__main__":
    unittest.main()
