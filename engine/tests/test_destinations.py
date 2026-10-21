"""Destinos de guardado con destinos FALSOS en memoria: nunca toca cuentas reales."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import destinations as D  # noqa: E402
from perms import assert_private  # noqa: E402


class Fake(D.Destination):
    caps = {"album": True, "playlist": True}

    def __init__(self, id_, state="connected", fail=False, have=()):
        self.id, self.label, self.state, self.fail, self.have, self.writes = id_, id_, state, fail, set(have), []

    def status(self):
        return {"state": self.state, "note": "nota"}

    def save_album(self, artist, album, dry=False):
        if self.fail:
            raise RuntimeError("boom")
        if album not in self.have:
            return {"ok": False, "saved": 0, "notFound": [f"{artist} - {album}"]}
        if not dry:
            self.writes.append(album)
        return {"ok": True, "saved": 1, "notFound": []}

    def save_playlist(self, name, tracks, dry=False):
        found = [t for t in tracks if t["title"] in self.have]
        if not dry:
            self.writes.append((name, [t["title"] for t in found]))
        return {"ok": bool(found), "saved": len(found), "notFound": [t["title"] for t in tracks if t["title"] not in self.have]}


class Save(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = os.path.join(self.tmp.name, "saved.jsonl")
        self.a, self.b, self.c = Fake("a", have={"X"}), Fake("b", fail=True), Fake("c", state="unavailable")
        self.reg = {d.id: d for d in (self.a, self.b, self.c)}

    def tearDown(self):
        self.tmp.cleanup()

    def test_independent_destinations(self):
        r = D.save("album", [{"artist": "Y", "album": "X"}], ["a", "b", "c", "zz"], None, self.log, self.reg, dry=False)
        self.assertTrue(r["a"]["ok"])
        self.assertEqual(r["b"]["error"], "Falló: RuntimeError")   # uno falla, los otros siguen
        self.assertEqual(r["c"]["error"], "nota")                   # no conectado: no se intenta
        self.assertEqual(r["zz"]["error"], "Destino desconocido.")
        self.assertEqual(self.a.writes, ["X"])
        log = [json.loads(x) for x in open(self.log)]
        self.assertEqual(len(log), 1)
        assert_private(self, self.log)

    def test_dry_run_never_writes(self):
        r = D.save("album", [{"artist": "Y", "album": "X"}], ["a"], None, self.log, self.reg, dry=True)
        self.assertTrue(r["a"]["ok"] and r["a"]["dry"])
        self.assertEqual(self.a.writes, [])

    def test_playlist_reports_missing(self):
        r = D.save("playlist", [{"artist": "Y", "title": "X"}, {"artist": "Y", "title": "Z"}], ["a"], "Mi lista", self.log, self.reg, dry=False)
        self.assertEqual((r["a"]["saved"], r["a"]["notFound"]), (1, ["Z"]))
        self.assertEqual(self.a.writes, [("Mi lista", ["X"])])

    def test_validation(self):
        for args in (("album", [], ["a"], None), ("playlist", [{"artist": "a", "title": "b"}], ["a"], ""), ("album", [{"artist": "a", "album": "b"}], [], None), ("x", [], ["a"], None)):
            with self.assertRaises(ValueError):
                D.save(*args, self.log, self.reg, dry=True)
        self.assertFalse(os.path.exists(self.log))


if __name__ == "__main__":
    unittest.main()
