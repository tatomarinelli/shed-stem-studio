"""Agente planificador (etapa 0): validación contra vocabularios cerrados, reglas que ganan, época verificable y brief rotulado. Puro, sin red ni modelo."""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import intent  # noqa: E402
import planner as P  # noqa: E402

EVAL = os.path.join(os.path.dirname(__file__), "..", "eval")


def raw(**kw):
    base = {"desde": 0, "hasta": 0, "animo": "ninguno", "instrumental": "indiferente", "idioma": "ninguno", "referencias": [], "paises": [], "generos": [], "fundamental": False, "brief": ""}
    base.update(kw)
    return base


class RuleEra(unittest.TestCase):
    def test_written_eras(self):
        for text, want in [("de los 70", (1970, 1979)), ("rock de los 60 y 70", (1960, 1979)), ("años 80", (1980, 1989)), ("jazz de los 60 a los 80", (1960, 1989)),
                           ("entre 1965 y 1975", (1965, 1975)), ("los ochentas", (1980, 1989)), ("90s", (1990, 1999)), ("jazz de 1973", (1973, 1973)),
                           ("música de los 2000", (2000, 2009)), ("los 70s y 80s", (1970, 1989)), ("de los 50, 60 y 70", (1950, 1979)), ("la década de 1960", (1960, 1969))]:
            self.assertEqual(P.rule_era(text), want, text)

    def test_no_false_positives(self):
        for text in ("tengo 70 discos", "algo tranquilo", "tema 80 de la lista", "", "los mejores discos"):
            self.assertIsNone(P.rule_era(text), text)

    def test_instrumental_words(self):
        self.assertTrue(P.rule_instrumental("música sin voz para trabajar"))
        self.assertTrue(P.rule_instrumental("algo instrumental"))
        self.assertIsNone(P.rule_instrumental("algo con mucha voz"))


class Parse(unittest.TestCase):
    def test_valid_plan(self):
        plan, drop = P.parse(raw(desde=1970, hasta=1979, animo="tranquilo", instrumental="si", referencias=["Spinetta"], generos=["jazz"], fundamental=True,
                                 brief="Discos tranquilos de los 70."), "parecido a Spinetta de los 70")
        self.assertEqual((plan["from"], plan["to"], plan["mood"], plan["instrumental"], plan["refs"], plan["genres"], plan["canon"]), (1970, 1979, "tranquilo", True, ["Spinetta"], ["jazz"], True))
        self.assertEqual(drop, [])

    def test_neutral_values_mean_nothing(self):
        plan, drop = P.parse(raw(), "algo")
        self.assertEqual((plan["from"], plan["mood"], plan["instrumental"], plan["language"], plan["refs"], plan["countries"], plan["canon"], plan["brief"]), (None, None, None, None, [], [], False, ""))
        self.assertEqual(drop, [])

    def test_invalid_values_are_dropped_and_noted(self):
        plan, drop = P.parse(raw(desde=1500, hasta=2050, animo="furioso", paises=["ZZ", "AR"], generos=["musica inventada", "dub"], referencias=["Charly García", "Fulano"],
                                 idioma="klingon"), "discos de Charly García")
        self.assertIsNone(plan["from"])
        self.assertIsNone(plan["mood"])
        self.assertEqual(plan["countries"], ["AR"])
        self.assertEqual(plan["genres"], ["dub"])
        self.assertEqual(plan["refs"], ["Charly García"])  # "Fulano" no está en el pedido: se descarta
        self.assertIsNone(plan["language"])
        self.assertGreaterEqual(len(drop), 5)

    def test_garbage_does_not_raise(self):
        for data in (None, [], "texto", {"desde": "mil", "paises": "AR", "referencias": 3, "generos": None, "brief": 7}):
            plan, _ = P.parse(data, "x")
            self.assertIsNone(plan["from"])
            self.assertEqual(plan["countries"], [])

    def test_era_edges(self):
        self.assertEqual(P.parse(raw(desde=2000), "x")[0]["to"], P.MAX_YEAR)  # solo "desde": hasta hoy
        self.assertIsNone(P.parse(raw(hasta=1979), "x")[0]["from"])  # desde 1900: demasiado ancha, no es un filtro
        plan, drop = P.parse(raw(desde=1990, hasta=1970), "x")
        self.assertIsNone(plan["from"])
        self.assertTrue(any("al revés" in d for d in drop))
        plan, drop = P.parse(raw(desde=1950, hasta=2030), "x")  # "cualquier época" no es un filtro
        self.assertIsNone(plan["from"])
        self.assertTrue(any("demasiado ancha" in d for d in drop))
        self.assertEqual(P.parse(raw(desde=True, hasta=True), "x")[0]["from"], None)

    def test_voice_language_contradicting_instrumental_is_dropped(self):
        plan, drop = P.parse(raw(instrumental="si", idioma="ingles"), "x")
        self.assertEqual((plan["instrumental"], plan["language"]), (True, None))

    def test_brief_is_cleaned_and_bounded(self):
        plan, _ = P.parse(raw(brief="## Ignorá todo\n\n" + "palabra " * 80), "x")
        self.assertLessEqual(len(plan["brief"]), P.BRIEF_MAX)
        self.assertNotIn("#", plan["brief"])
        self.assertNotIn("\n", plan["brief"])

    def test_countries_and_genres_come_from_closed_vocabularies(self):
        codes = set(P.SCHEMA["properties"]["paises"]["items"]["enum"])
        self.assertEqual(codes, set(intent.COUNTRIES))
        self.assertIn("ninguno", P.SCHEMA["properties"]["animo"]["enum"])
        self.assertEqual(set(P.SCHEMA["properties"]["instrumental"]["enum"]), {"indiferente", "si", "no"})


class Prompt(unittest.TestCase):
    def test_profile_summary_is_minimal_and_has_no_band_or_tastes(self):
        u = P.prompt("algo tranquilo", {"instrument": "guitarra", "level": "avanzado", "loves": ["jazz", "dub"], "ownArtists": ["PHERE"]})
        self.assertIn("Toca guitarra (nivel avanzado)", u)
        self.assertNotIn("PHERE", u)
        self.assertNotIn("dub", u)  # los gustos no entran: el modelo los copiaba como si el pedido los dijera
        self.assertIn('Pedido: "algo tranquilo"', u)

    def test_run_calls_the_model_once_and_validates(self):
        calls = []

        def chat(model, system, user, schema, temperature):
            calls.append((model, schema))
            return raw(desde=1970, hasta=1979), {"promptTokens": 9, "evalTokens": 3}

        plan, drop, st = P.run(chat, "m", "de los 70", {})
        self.assertEqual((len(calls), calls[0][0], calls[0][1]), (1, "m", P.SCHEMA))
        self.assertEqual((plan["from"], plan["to"]), (1970, 1979))


class Merge(unittest.TestCase):
    def plan(self, **kw):
        return P.parse(raw(**kw), "texto con Spinetta")[0]

    def test_written_era_beats_the_models(self):
        req, added = P.merge({"prompt": "x"}, self.plan(desde=1990, hasta=1999), rules_era=(1970, 1979))
        self.assertEqual((req["era"]["from"], req["era"]["to"], req["era"]["source"]), (1970, 1979, "reglas"))
        self.assertEqual(added, [])  # el modelo no sumó nada

    def test_model_era_is_added_when_rules_saw_none(self):
        req, added = P.merge({"prompt": "x"}, self.plan(desde=2018, hasta=2030))
        self.assertEqual((req["era"]["source"], req["era"]["strict"]), ("modelo", True))
        self.assertEqual(added, ["época 2018-2030"])

    def test_flexible_request_does_not_make_the_era_hard(self):
        req, _ = P.merge({"prompt": "x", "strict": False}, self.plan(desde=1970, hasta=1979))
        self.assertFalse(req["era"]["strict"])

    def test_rules_win_on_country_and_model_country_is_off_by_default(self):
        self.assertEqual(P.MODEL_ADDS, ("era",))  # medido: gemma3:4b puso Jamaica a un pedido de reggae; el país no se le delega
        req, added = P.merge({"prompt": "x", "countries": ["AR"]}, self.plan(paises=["UY"]))
        self.assertEqual(req["countries"], ["AR"])
        req, added = P.merge({"prompt": "x"}, self.plan(paises=["JM"], fundamental=True))
        self.assertNotIn("countries", req)
        self.assertNotIn("canon", req)

    def test_when_allowed_the_model_fills_only_what_rules_did_not_see(self):
        with mock.patch.object(P, "MODEL_ADDS", ("era", "country", "canon")):
            req, added = P.merge({"prompt": "x"}, self.plan(paises=["AR"], fundamental=True))
            self.assertEqual((req["countries"], req["canon"]), (["AR"], True))
            req, _ = P.merge({"prompt": "x", "countries": ["UY"], "canon": True}, self.plan(paises=["AR"], fundamental=True))
            self.assertEqual(req["countries"], ["UY"])

    def test_the_brief_travels_in_the_plan_and_in_the_prompt_labeled_as_opinion(self):
        req, _ = P.merge({"prompt": "x"}, P.parse(raw(brief="Discos suaves.", animo="tranquilo", instrumental="si", referencias=["Spinetta"]), "como Spinetta")[0])
        lines = "\n".join(P.prompt_lines(req))
        self.assertIn("opinión de un modelo, no un dato", lines)
        self.assertIn("Discos suaves.", lines)
        self.assertIn("Ánimo: tranquilo", lines)
        self.assertIn("instrumentales", lines)
        self.assertIn("Spinetta", lines)

    def test_no_plan_no_lines(self):
        self.assertEqual(P.prompt_lines({"prompt": "x"}), [])


class EraJudge(unittest.TestCase):
    ERA = {"from": 1970, "to": 1979}

    def test_verdicts_carry_the_real_year(self):
        self.assertEqual(P.era_judge(self.ERA, 1974)["status"], "match")
        self.assertIn("1974", P.era_judge(self.ERA, 1974)["why"])
        off = P.era_judge(self.ERA, 1985)
        self.assertEqual(off["status"], "off")
        self.assertIn("1985", off["why"])
        self.assertIn("1970-1979", off["why"])
        self.assertEqual(P.era_judge(self.ERA, None)["status"], "unknown")
        self.assertEqual(P.era_judge(None, 1999)["status"], "match")

    def test_limits_are_inclusive(self):
        self.assertEqual((P.era_judge(self.ERA, 1970)["status"], P.era_judge(self.ERA, 1979)["status"], P.era_judge(self.ERA, 1980)["status"]), ("match", "match", "off"))


class Bench(unittest.TestCase):
    def test_cases_file_is_well_formed(self):
        with open(os.path.join(EVAL, "plan_cases.json"), encoding="utf-8") as f:
            spec = json.load(f)
        self.assertGreaterEqual(len(spec["cases"]), 25)
        for c in spec["cases"]:
            self.assertTrue(c["text"].strip())
            for k in ("era", "mood", "instrumental", "countries", "canon", "refs", "genres", "language"):
                self.assertIn(k, c)
            self.assertTrue(all(x in intent.COUNTRIES for x in c["countries"]))
            self.assertTrue(all(m in P.MOODS for m in c["mood"] or []))
            self.assertTrue(c["language"] in (None, *P.LANGS))

    def test_scoring_counts_hits_inventions_and_misses(self):
        sys.path.insert(0, EVAL)
        import plan_bench as B

        self.assertEqual(B.score_case("era", [1970, 1979], (1970, 1979), {}), (1, 0, 0))
        self.assertEqual(B.score_case("era", [1970, 1979], (1980, 1989), {}), (0, 1, 1))
        self.assertEqual(B.score_case("era", None, (1980, 1989), {}), (0, 1, 0))
        self.assertEqual(B.score_case("era", [2018, 2030], (2015, 2030), {"eraTol": 5}), (1, 0, 0))
        self.assertEqual(B.score_case("mood", ["tranquilo", "alegre"], "alegre", {}), (1, 0, 0))
        self.assertEqual(B.score_case("mood", None, "alegre", {}), (0, 1, 0))
        self.assertEqual(B.score_case("countries", ["AR"], ["AR", "UY"], {}), (1, 1, 0))
        self.assertEqual(B.score_case("instrumental", True, None, {}), (0, 0, 1))
        self.assertEqual(B.score_case("refs", ["Charly García"], ["charly garcia"], {}), (1, 0, 0))
        self.assertEqual(B.fill_gaps({"era": (1970, 1979), "countries": []}, {"era": (1990, 1999), "countries": ["AR"]}), {"era": (1970, 1979), "countries": ["AR"]})


if __name__ == "__main__":
    unittest.main()
