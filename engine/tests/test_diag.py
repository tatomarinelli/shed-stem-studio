"""Diagnóstico de portadas: el navegador avisa cuando una falla o tarda y queda una línea local y acotada. Sin tocar los datos reales."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import diag  # noqa: E402
import settings  # noqa: E402


class Diag(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.object(settings, "effective", lambda d=None: {**settings.DEFAULTS, "dataDir": self.tmp.name})
        p.start()
        self.addCleanup(p.stop)
        self.file = Path(self.tmp.name, "diag", "covers.log")

    def test_valid_report_is_stored_with_known_fields_only(self):
        ok = diag.cover({"src": "/engine/cover/abc", "kind": "slow", "tries": 2, "ms": 6000, "online": True, "connections": 5, "secreto": "no debe guardarse"})
        self.assertTrue(ok)
        row = json.loads(self.file.read_text().splitlines()[0])
        self.assertEqual((row["src"], row["kind"], row["connections"], row["online"]), ("/engine/cover/abc", "slow", 5, True))
        self.assertNotIn("secreto", row)

    def test_only_engine_urls_and_dict_bodies_are_accepted(self):
        for bad in (None, [], "x", {"src": "https://evil.example/x"}, {"kind": "slow"}):
            self.assertFalse(diag.cover(bad))
        self.assertFalse(self.file.exists())

    def test_fields_are_cleaned_and_bounded_and_the_log_is_capped(self):
        diag.cover({"src": "/engine/cover/" + "x" * 1000, "kind": "a\nb"})
        row = json.loads(self.file.read_text().splitlines()[0])
        self.assertLessEqual(len(row["src"]), 300)
        self.assertNotIn("\n", row["kind"])
        for i in range(diag.MAX_LINES + 30):
            diag.cover({"src": f"/engine/cover/{i}", "kind": "failed"})
        lines = self.file.read_text().splitlines()
        self.assertEqual(len(lines), diag.MAX_LINES)
        self.assertIn(f"/engine/cover/{diag.MAX_LINES + 29}", lines[-1])


if __name__ == "__main__":
    unittest.main()
