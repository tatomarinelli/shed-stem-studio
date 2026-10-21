"""Contexto del álbum: aceptación de páginas y validación del resumen (sin red)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import albumctx as A  # noqa: E402

SRC = ("Idle Moments is an album by American jazz guitarist Grant Green recorded in 1963 and released on the Blue Note label "
       "in 1965. It features performances by tenor saxophonist Joe Henderson and vibraphonist Bobby Hutcherson.")


class Page(unittest.TestCase):
    def test_accepts_album_page(self):
        self.assertTrue(A.is_album_page({"title": "Idle Moments", "extract": SRC}, "Grant Green", "Idle Moments", "en"))
        self.assertTrue(A.is_album_page({"title": "Idle Moments (album)", "extract": SRC}, "Grant Green", "Idle Moments", "en"))

    def test_rejects(self):
        self.assertFalse(A.is_album_page({"title": "Idle Moments", "extract": SRC, "pageprops": {"disambiguation": ""}}, "Grant Green", "Idle Moments", "en"))
        self.assertFalse(A.is_album_page({"title": "Idle Moments", "extract": SRC}, "Wes Montgomery", "Idle Moments", "en"))  # otro artista
        self.assertFalse(A.is_album_page({"title": "Grant Green", "extract": SRC}, "Grant Green", "Idle Moments", "en"))     # página del artista
        self.assertFalse(A.is_album_page({"title": "Idle Moments", "extract": "Idle Moments is a 1963 film directed by Grant Green, set in a quiet town."},
                                         "Grant Green", "Idle Moments", "en"))  # no es un disco


class Validate(unittest.TestCase):
    def test_supported_summary_passes(self):
        ok = "Grabado en 1963 y editado por Blue Note en 1965. Toca con Joe Henderson y Bobby Hutcherson."
        self.assertEqual(A.unsupported(ok, SRC), [])

    def test_invented_facts_fail(self):
        self.assertIn("1964", A.unsupported("Grabado en 1964 por Blue Note.", SRC))
        self.assertIn("Coltrane", A.unsupported("Grabado en 1963 con John Coltrane.", SRC))
        self.assertIn("diez", A.unsupported("Se grabó en diez horas.", SRC))
        self.assertEqual(A.unsupported("Tiene dos invitados: Joe Henderson y Bobby Hutcherson.", SRC + " two guests"), [])

    def test_fallback_when_model_invents(self):
        text, summarized = A.summarize(lambda s, u: '{"resumen": "Un disco de 1959 con Miles Davis, clave del cool jazz."}', SRC)
        self.assertFalse(summarized)
        self.assertTrue(text.startswith("Idle Moments is an album"))
        text, summarized = A.summarize(lambda s, u: '{"resumen": "Grabado en 1963 y editado por Blue Note en 1965, con Joe Henderson."}', SRC)
        self.assertTrue(summarized)


if __name__ == "__main__":
    unittest.main()
