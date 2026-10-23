"""Estimación de tiempos: referencia sin historial, mediana con historial, y cómo cambia con el contexto y el género. Sin red."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import timing as T  # noqa: E402


def run(total=30.0, model=4.0, verify=26.0, context=0.0, genre=False, method="artistas"):
    return {"method": method, "genre": genre, "rounds": 1, "proposed": 10, "model": model, "musicbrainz": verify, "context": context,
            "total": total, "contextMode": "now" if context else "demand"}


class Timing(unittest.TestCase):
    def test_reference_values_are_labeled_as_estimates(self):
        e = T.estimate([], genre=True)
        self.assertEqual(e["total"], round(T.DEFAULT["model"] + T.DEFAULT["musicbrainz"]))
        self.assertIn("estimado", e["basis"])

    def test_measured_median_replaces_reference(self):
        runs = [run(verify=24, model=4), run(verify=30, model=6), run(verify=60, model=5)]  # la mediana ignora el atípico
        e = T.estimate(runs, genre=False)
        self.assertEqual(e["parts"]["model"], 5.0)
        self.assertEqual(e["parts"]["musicbrainz"], 24.0)  # mediana de (24-4), (30-6) y (60-5): no se suma dos veces lo del modelo
        self.assertIn("3 búsquedas", e["basis"])

    def test_context_mode_adds_its_cost_only_when_on(self):
        runs = [run(context=15.0), run(context=9.0)]
        self.assertEqual(T.estimate(runs, context="demand")["parts"]["context"], 0.0)
        self.assertEqual(T.estimate(runs, context="now")["parts"]["context"], 12.0)
        self.assertGreater(T.estimate(runs, context="now")["total"], T.estimate(runs, context="demand")["total"])

    def test_genre_and_free_requests_are_estimated_separately(self):
        runs = [run(verify=24, genre=True), run(verify=26, genre=True), run(verify=10, genre=False), run(verify=12, genre=False)]
        self.assertGreater(T.estimate(runs, genre=True)["total"], T.estimate(runs, genre=False)["total"])

    def test_entry_skips_cancelled_and_history_is_bounded(self):
        self.assertIsNone(T.entry({"stats": {"cancelled": True, "seconds": 5}}))
        runs = []
        for i in range(T.KEEP + 5):
            runs = T.add(runs, run(total=i))
        self.assertEqual(len(runs), T.KEEP)
        self.assertEqual(runs[-1]["total"], T.KEEP + 4)
        self.assertEqual(T.add(runs, None), runs)


if __name__ == "__main__":
    unittest.main()
