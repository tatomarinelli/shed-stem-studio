"""El motor tiene que poder importarse en un intérprete limpio, en cualquier orden de imports (un alias a nivel de módulo entre `recs` y
`catalog` ya rompió el arranque del servidor sin que ningún otro test lo notara, porque los tests importan en otro orden)."""
import os
import subprocess
import sys
import tempfile
import unittest

ENGINE = os.path.join(os.path.dirname(__file__), "..")


class Startup(unittest.TestCase):
    def run_code(self, code):
        with tempfile.TemporaryDirectory() as d:
            env = {**os.environ, "STEMSHED_MEMORY_DIR": d, "XDG_CONFIG_HOME": d, "STEMSHED_NO_SCHEDULER": "1", "PYTHONDONTWRITEBYTECODE": "1"}
            return subprocess.run([sys.executable, "-c", code], cwd=ENGINE, env=env, capture_output=True, text=True, timeout=90)

    def test_server_imports_cleanly(self):
        r = self.run_code("import server")
        self.assertEqual(r.returncode, 0, r.stderr[-800:])

    def test_catalog_first_then_recs(self):
        r = self.run_code("import catalog, recs")
        self.assertEqual(r.returncode, 0, r.stderr[-800:])

    def test_recs_first_then_catalog(self):
        r = self.run_code("import recs, catalog")
        self.assertEqual(r.returncode, 0, r.stderr[-800:])


if __name__ == "__main__":
    unittest.main()
