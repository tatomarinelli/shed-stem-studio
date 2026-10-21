"""Pruebas del análisis musical con audio sintético de verdad conocida.

Correr con el venv de separación (necesita numpy/librosa):
    cd engine && /mnt/plexdata/tidal-stems/venv/bin/python -m unittest tests.test_analysis -v
    /mnt/plexdata/tidal-stems/venv/bin/python engine/tests/test_analysis.py --report   # tabla de métricas

Los stems sintéticos se generan en un directorio temporal (respeta TMPDIR) y se borran al terminar.
También prueba engine/analysis.py (envoltorio de la librería estándar) con un trabajo real.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ENGINE))

import synth  # noqa: E402

PY = os.environ.get("STEMSHED_ANALYSIS_PY", "/mnt/plexdata/tidal-stems/venv/bin/python")

# nombre: (progresión, bpm, kwargs de make_song, tónica esperada, modos aceptados)
CASES = {
    "pop_C_120": (["C", "G", "Am", "F"], 120, {}, "C", {"major"}),
    "jazz_iiVI_Bb_140_swing": (["Cm7", "F7", "Bbmaj7", "Bbmaj7"], 140, {"swing": True, "walking": True}, "Bb", {"major"}),
    "minor_iiV_A_120": (["Bm7b5", "E7", "Am7", "Am7"], 120, {}, "A", {"minor", "harmonicMinor", "dorian"}),
    "dorian_vamp_D_100": (["Dm7", "Dm7", "G7", "Dm7"], 100,
                          {"melody_scale": (0, 2, 3, 5, 7, 9, 10), "tonic": 2}, "D", {"dorian"}),
    "dorian_DmG_equal_96": (["Dm7", "G7"], 96, {"melody_scale": (0, 2, 3, 5, 7, 9, 10), "tonic": 2, "repeats": 8},
                            "D", {"dorian"}),
    "ballad_F_70": (["Fmaj7", "Dm7", "Gm7", "C7"], 70, {"repeats": 3}, "F", {"major"}),
    "blues_G_110": (["G7", "C7", "G7", "G7", "C7", "C7", "G7", "G7", "D7", "C7", "G7", "D7"], 110, {"repeats": 1},
                    "G", {"mixolydian"}),
    "accel_Em_100_106": (["Em", "C", "G", "D"], 100, {"bpm_end": 106, "repeats": 5}, "E", {"minor", "dorian"}),
    "aeolian_Am_90": (["Am", "F", "C", "G"], 90, {"melody_scale": (0, 2, 3, 5, 7, 8, 10), "tonic": 9}, "A", {"minor"}),
}
NOTE = synth.NOTE


def run_case(name, tmp, extra=()):
    prog, bpm, kw, tonic, modes = CASES[name]
    kw = dict(kw)
    folder = Path(tmp) / name
    truth = synth.make_song(folder, prog, bpm, seed=sum(map(ord, name)), title=name, **kw)
    out = folder / "analysis.json"
    t = time.time()
    p = subprocess.run([PY, str(ENGINE / "analyze.py"), str(folder), "--out", str(out), *extra], capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-3000:])
    res = json.loads(out.read_text())
    bpm_true = bpm if "bpm_end" not in kw else None
    beat_f = synth.beat_f1(truth["beats"], res["tempo"]["beats"])
    db_f = synth.beat_f1(truth["downbeats"], res["tempo"]["downbeats"])
    return {
        "name": name, "elapsed": time.time() - t, "res": res, "truth": truth,
        "key_ok": NOTE[res["key"]["tonic"]] == NOTE[tonic] and res["key"]["mode"] in modes,
        "tonic_ok": NOTE[res["key"]["tonic"]] == NOTE[tonic],
        "bpm_err": None if bpm_true is None else abs(res["tempo"]["bpm"] - bpm_true) / bpm_true,
        "beat_f1": beat_f, "downbeat_f1": db_f,
        "chord_acc": synth.chord_accuracy(truth["chords"], res["chords"]),
        "root_acc": synth.chord_accuracy(truth["chords"], res["chords"], root_only=True),
    }


class SynthTests(unittest.TestCase):
    tmp = None
    results = {}

    @classmethod
    def setUpClass(cls):
        cls._td = tempfile.TemporaryDirectory(prefix="stemshed-analysis-")
        cls.tmp = cls._td.name

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()

    def get(self, name):
        if name not in self.results:
            self.results[name] = run_case(name, self.tmp)
        return self.results[name]

    def check(self, name, min_chord=0.75):
        r = self.get(name)
        res = r["res"]
        self.assertTrue(r["key_ok"], f"{name}: key {res['key']['tonic']} {res['key']['mode']} alts={res['key']['alternatives']}")
        if r["bpm_err"] is not None:
            self.assertLess(r["bpm_err"], 0.02, f"{name}: bpm {res['tempo']['bpm']}")
        self.assertGreater(r["beat_f1"], 0.9, f"{name}: beat F1 {r['beat_f1']:.2f}")
        self.assertGreaterEqual(r["chord_acc"], min_chord, f"{name}: chord acc {r['chord_acc']:.2f}")
        self.assertEqual(res["version"], 1)
        for c in res["chords"]:
            self.assertLessEqual(c["start"], c["end"])
        return r

    def test_pop_major(self):
        self.check("pop_C_120")

    def test_jazz_ii_V_I_sevenths_swing(self):
        self.check("jazz_iiVI_Bb_140_swing")

    def test_minor_ii_V_m7b5(self):
        self.check("minor_iiV_A_120")

    def test_dorian_vamp(self):
        self.check("dorian_vamp_D_100")

    def test_dorian_equal_two_chord_vamp(self):
        self.check("dorian_DmG_equal_96")

    def test_ballad_no_double_time(self):
        r = self.check("ballad_F_70")
        self.assertLess(r["res"]["tempo"]["bpm"], 100)

    def test_blues(self):
        r = self.check("blues_G_110")
        self.assertTrue(r["res"]["key"]["blues"])

    def test_accelerando_unstable(self):
        r = self.check("accel_Em_100_106")
        self.assertFalse(r["res"]["tempo"]["stable"])

    def test_aeolian(self):
        self.check("aeolian_Am_90")

    def test_without_drums(self):
        # tema sin batería (stem mudo y marcado silent): no se cae, el pulso sale de bajo + armonía
        with tempfile.TemporaryDirectory(prefix="stemshed-nodrums-", dir=self.tmp) as td:
            truth = synth.make_song(td, ["C", "Am", "F", "G"], 110, silent=("drums",), seed=7)
            res = self.analyze_dir(td)
        self.assertEqual(NOTE[res["key"]["tonic"]], 0)
        bpms = [res["tempo"]["bpm"]] + [a["bpm"] for a in res["tempo"]["alternatives"]]
        self.assertTrue(any(abs(b - 110) / 110 < 0.02 for b in bpms), bpms)
        self.assertGreater(synth.chord_accuracy(truth["chords"], res["chords"], root_only=True), 0.7)
        self.assertNotIn("drums", res["stats"]["stems"])

    def test_without_bass(self):
        with tempfile.TemporaryDirectory(prefix="stemshed-nobass-", dir=self.tmp) as td:
            truth = synth.make_song(td, ["Dm7", "G7", "Cmaj7", "Cmaj7"], 120, silent=("bass",), seed=8)
            res = self.analyze_dir(td)
        self.assertEqual(NOTE[res["key"]["tonic"]], 0)
        self.assertLess(abs(res["tempo"]["bpm"] - 120) / 120, 0.02)
        self.assertGreater(synth.chord_accuracy(truth["chords"], res["chords"]), 0.7)

    def analyze_dir(self, folder):
        out = Path(folder) / "analysis.json"
        p = subprocess.run([PY, str(ENGINE / "analyze.py"), str(folder), "--out", str(out)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr[-2000:])
        return json.loads(out.read_text())

    def test_downbeats(self):
        # la fase del 1 se acierta en la mayoría de los casos (no se exige en todos: es una estimación)
        names = ["pop_C_120", "jazz_iiVI_Bb_140_swing", "ballad_F_70", "blues_G_110", "aeolian_Am_90"]
        ok = sum(self.get(n)["downbeat_f1"] > 0.9 for n in names)
        self.assertGreaterEqual(ok, 4)


class WrapperTests(unittest.TestCase):
    """analysis.py con la librería estándar: lanza analyze.py en el venv y guarda el JSON en <dataDir>/analysis/."""

    def test_job_roundtrip(self):
        import analysis
        import stems

        with tempfile.TemporaryDirectory(prefix="stemshed-wrap-") as td:
            data, env = Path(td) / "data", Path(td) / "env"
            folder = data / "cache" / "123" / "roformer"
            synth.make_song(folder, ["C", "F", "G", "C"], 120, repeats=2)
            old = (stems.ROOT, stems.ENV, stems.CACHE, stems.OLD_CACHE)
            try:
                stems.configure(str(data), str(env))
                analysis.configure(str(data), python=PY)
                self.assertIsNone(analysis.get("123"))
                self.assertEqual(analysis.job_status("123")["state"], "idle")
                st = analysis.start("123")
                self.assertEqual(st["state"], "running")
                with self.assertRaises(analysis.AnalysisError):
                    analysis.start("123")
                for _ in range(600):
                    st = analysis.job_status("123")
                    if st["state"] != "running":
                        break
                    time.sleep(0.2)
                self.assertEqual(st["state"], "done", st)
                res = analysis.get("123")
                self.assertEqual(res["version"], 1)
                self.assertEqual(res["trackId"], "123")
                self.assertTrue((data / "analysis" / "123.json").exists())
                self.assertEqual(analysis.start("123")["state"], "done")  # ya analizado: no relanza
                with self.assertRaises(analysis.AnalysisError):
                    analysis.start("999")  # no separado
                with self.assertRaises(ValueError):
                    analysis.start("../etc")
            finally:
                stems.ROOT, stems.ENV, stems.CACHE, stems.OLD_CACHE = old


def report(extra=()):
    with tempfile.TemporaryDirectory(prefix="stemshed-analysis-") as tmp:
        rows = [run_case(n, tmp, extra) for n in CASES]
    print(f"variante: {' '.join(extra) or 'por defecto'}")
    print(f"{'caso':26} {'key':16} {'ok':3} {'bpm':>7} {'err%':>5} {'stable':6} {'beatF':>5} {'dbF':>4} {'acorde':>6} {'raíz':>5} {'s':>4}")
    for r in rows:
        k, t = r["res"]["key"], r["res"]["tempo"]
        err = "-" if r["bpm_err"] is None else f"{100 * r['bpm_err']:.1f}"
        print(f"{r['name']:26} {k['tonic'] + ' ' + k['mode']:16} {'sí' if r['key_ok'] else 'NO':3} {t['bpm']:7.2f} {err:>5} "
              f"{str(t['stable']):6} {r['beat_f1']:5.2f} {r['downbeat_f1']:4.2f} {r['chord_acc']:6.2f} {r['root_acc']:5.2f} {r['elapsed']:4.1f}")
    n = len(rows)
    print(f"key {sum(r['key_ok'] for r in rows)}/{n}  tónica {sum(r['tonic_ok'] for r in rows)}/{n}  "
          f"bpm±2% {sum(r['bpm_err'] is not None and r['bpm_err'] < .02 for r in rows)}/{sum(r['bpm_err'] is not None for r in rows)}  "
          f"acorde medio {sum(r['chord_acc'] for r in rows) / n:.3f}  raíz media {sum(r['root_acc'] for r in rows) / n:.3f}  "
          f"downbeat {sum(r['downbeat_f1'] > .9 for r in rows)}/{n}")
    if "-v" in sys.argv:
        for r in rows:
            print(r["name"], " ".join(f"{c['label']}@{c['start']:.1f}" for c in r["res"]["chords"][:24]))
    return rows


if __name__ == "__main__":
    if "--report" in sys.argv:
        report([a for a in sys.argv[1:] if a.startswith("--") and a != "--report"])
    else:
        unittest.main()
