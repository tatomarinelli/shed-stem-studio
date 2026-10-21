import json
import tempfile
import unittest
from pathlib import Path

import stems


class StemFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.old = (stems.CACHE, stems.OLD_CACHE)
        stems.CACHE, stems.OLD_CACHE = self.tmp / "new", self.tmp / "old"

    def tearDown(self):
        stems.CACHE, stems.OLD_CACHE = self.old

    def make(self, base, tid, title="T"):
        d = base / tid / stems.MODEL
        d.mkdir(parents=True)
        (d / "manifest.json").write_text(json.dumps({"title": title, "artist": "A", "duration": 10, "created": 1,
                                                     "stems": [{"name": "bass", "file": "bass.flac"}]}))
        (d / "bass.flac").write_bytes(b"x")

    def test_finds_new_then_old(self):
        self.make(stems.OLD_CACHE, "5", "viejo")
        self.assertEqual(stems.stem_file("5", "bass.flac").parent.parent.parent, stems.OLD_CACHE)
        self.make(stems.CACHE, "5", "nuevo")
        self.assertEqual(stems.stem_file("5", "bass.flac").parent.parent.parent, stems.CACHE)

    def test_rejects_other_names(self):
        self.make(stems.CACHE, "5")
        for bad in ("../manifest.json", "x.wav", "bass.flac/../../a", "a/b.flac", ""):
            self.assertIsNone(stems.stem_file("5", bad))
        with self.assertRaises(ValueError):
            stems.stem_file("../5", "bass.flac")

    def test_index_lists_stems(self):
        self.make(stems.CACHE, "7", "uno")
        self.assertEqual(stems.tracks_index(), [{"id": "7", "title": "uno", "artist": "A", "duration": 10, "stems": ["bass"]}])


if __name__ == "__main__":
    unittest.main()
