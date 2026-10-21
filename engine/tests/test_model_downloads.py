import tempfile
import unittest
from pathlib import Path

import models
import stems


class ModelDownloads(unittest.TestCase):
    def test_missing_separation_model_blocks_separation(self):
        old = stems.MODELS_DIR
        stems.MODELS_DIR = Path(tempfile.mkdtemp())
        try:
            self.assertFalse(stems.sep_model_present())
            with self.assertRaises(stems.StemsError) as cm:
                stems.separate(None, "1", lambda *a: None)
            self.assertIn("Descargalo en Ajustes", str(cm.exception))
            for f in stems.SEP_FILES:
                (stems.MODELS_DIR / f).write_bytes(b"x")
            self.assertTrue(stems.sep_model_present())
        finally:
            stems.MODELS_DIR = old

    def test_custom_ollama_names(self):
        ok = ["qwen3:8b", "mistral-nemo", "hf.co/user/model:Q4_K_M", "llama3.2:3b-instruct-q4_0"]
        bad = ["", "Qwen3 8b", "../x", "a;b", "http://x/y", "-x", "a" * 120]
        for n in ok:
            self.assertTrue(models.CUSTOM_NAME.match(n), n)
        for n in bad:
            self.assertFalse(models.CUSTOM_NAME.match(n) and len(n) <= 100, n)


if __name__ == "__main__":
    unittest.main()
