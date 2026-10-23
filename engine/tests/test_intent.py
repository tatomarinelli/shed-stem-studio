"""Lo que se pide en texto libre, convertido en restricciones verificables: país de origen y "lo fundamental". Puro, sin red."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import intent as I  # noqa: E402


class Countries(unittest.TestCase):
    def test_the_case_that_failed_in_real_use(self):
        t = "Busca discos de Argentina que tengo que haber escuchado"
        self.assertEqual(I.countries(t), ["AR"])
        self.assertTrue(I.canon(t))

    def test_country_names_and_demonyms_in_order_of_appearance(self):
        self.assertEqual(I.countries("rock uruguayo"), ["UY"])
        self.assertEqual(I.countries("jazz de Estados Unidos y Francia"), ["US", "FR"])
        self.assertEqual(I.countries("discos argentinos y brasileños"), ["AR", "BR"])
        self.assertEqual(I.countries("música francesa"), ["FR"])

    def test_no_false_positives(self):
        for t in ("música americana", "usa guitarras", "algo tranquilo", "canciones en francés", "cantadas en español", "una argentinaXYZ", ""):
            self.assertEqual(I.countries(t), [], t)  # "americana" es un género; "usa" un verbo; "en francés" un idioma

    def test_language_demonym_is_origin_only_without_en(self):
        self.assertEqual(I.countries("música española"), ["ES"])
        self.assertEqual(I.countries("grabado en España"), ["ES"])  # el nombre del país sí cuenta

    def test_accents_and_case_do_not_matter(self):
        self.assertEqual(I.countries("MÉXICO"), ["MX"])
        self.assertEqual(I.countries("discos mexicanos"), ["MX"])


class Canon(unittest.TestCase):
    def test_phrases(self):
        for t in ("los imprescindibles del jazz", "tengo que conocer el rock nacional", "clásicos de bossa", "discos fundamentales", "lo mejor de Spinetta"):
            self.assertTrue(I.canon(t), t)
        for t in ("algo tranquilo para trabajar", "algo nuevo", ""):
            self.assertFalse(I.canon(t), t)


class Origin(unittest.TestCase):
    def test_match_by_country_or_by_area(self):
        self.assertEqual(I.judge_origin(["AR"], {"country": "AR"})["status"], "match")
        self.assertEqual(I.judge_origin(["AR"], {"country": None, "area": "Argentina"})["status"], "match")
        self.assertEqual(I.judge_origin(["AR"], {"beginArea": "Argentina"})["status"], "match")

    def test_other_country_is_off_with_a_reason_from_the_data(self):
        r = I.judge_origin(["AR"], {"country": "US", "area": "United States"})
        self.assertEqual(r["status"], "off")
        self.assertIn("Estados Unidos", r["why"])
        self.assertIn("Argentina", r["why"])

    def test_no_data_is_unknown_not_a_guess(self):
        r = I.judge_origin(["AR"], {})
        self.assertEqual(r["status"], "unknown")
        self.assertIn("no se puede comprobar", r["why"])

    def test_no_wanted_country_always_matches(self):
        self.assertEqual(I.judge_origin([], {"country": "US"})["status"], "match")

    def test_any_of_several_countries(self):
        self.assertEqual(I.judge_origin(["AR", "UY"], {"country": "UY"})["status"], "match")


if __name__ == "__main__":
    unittest.main()
