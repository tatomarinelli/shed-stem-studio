"""Motores de separación: qué se recomienda según el hardware y que nunca se ofrezca instalar lo que no existe."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import backends as B  # noqa: E402
import envsetup  # noqa: E402
import osenv  # noqa: E402

NV = {"name": "NVIDIA GeForce RTX 5080", "vendor": "nvidia", "accel": "cuda", "integrated": False, "vramGB": 16.0}
AMD = {"name": "AMD Radeon RX 6700S", "vendor": "amd", "accel": None, "integrated": False, "vramGB": 8.0}
AMD_NEW = {"name": "AMD Radeon RX 7800 XT", "vendor": "amd", "accel": None, "integrated": False, "vramGB": 16.0}
IGPU = {"name": "AMD Radeon(TM) Graphics", "vendor": "amd", "accel": None, "integrated": True, "vramGB": 0.5}


def opts(rep):
    return {o["id"]: o for o in rep["options"]}


class Recommend(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(osenv, "WINDOWS", True)
        p.start()
        self.addCleanup(p.stop)

    def test_nvidia_recomienda_cuda(self):
        r = B.report([NV, IGPU])
        self.assertEqual(r["recommended"], "cuda")
        self.assertTrue(opts(r)["cuda"]["recommended"] and opts(r)["cuda"]["installable"])
        self.assertIn("RTX 5080", r["reason"])

    def test_amd_recomienda_cpu_y_lo_explica(self):
        r = B.report([AMD, IGPU])
        self.assertEqual(r["recommended"], "cpu")
        self.assertIn("RX 6700S", r["reason"])
        self.assertIn("RX 6700S", opts(r)["directml"]["note"])
        self.assertIn("no figura", opts(r)["rocm"]["note"])

    def test_amd_reciente_no_promete_nada(self):
        note = opts(B.report([AMD_NEW]))["rocm"]["note"]
        self.assertIn("sin verificar", note)
        self.assertFalse(opts(B.report([AMD_NEW]))["rocm"]["installable"])

    def test_sin_gpu(self):
        r = B.report([])
        self.assertEqual(r["recommended"], "cpu")
        self.assertIn("Sin placa", r["reason"])

    def test_solo_se_ofrece_lo_instalable_y_nada_esta_verificado_en_windows(self):
        r = B.report([NV])
        self.assertEqual({i for i, o in opts(r).items() if o["installable"]}, {"cuda", "cpu"})
        self.assertFalse(any(o["verified"] for o in r["options"] if o["installable"]))
        self.assertIsNone(B.requirements_for("directml"))
        self.assertIsNone(B.requirements_for("rocm"))
        self.assertIsNone(B.requirements_for("inventado"))

    def test_lo_incompatible_con_el_hardware_se_marca_y_se_rechaza(self):
        o = opts(B.report([AMD, IGPU]))
        self.assertFalse(o["cuda"]["compatible"])
        self.assertEqual(o["cuda"]["requires"], "Requiere NVIDIA")
        self.assertTrue(o["cpu"]["compatible"])
        self.assertTrue(opts(B.report([NV]))["cuda"]["compatible"])
        self.assertFalse(B.compatible("rocm", [IGPU]))
        self.assertTrue(B.compatible("rocm", [AMD]))

    def test_archivos_de_requisitos_existen(self):
        self.assertEqual(B.requirements_for("cuda").name, "requirements-env.win-nvidia.txt")
        self.assertEqual(B.requirements_for("cpu").name, "requirements-env.win-cpu.txt")
        self.assertTrue(B.requirements_for("cuda").is_file() and B.requirements_for("cpu").is_file())

    def test_en_linux_no_hay_directml_y_los_requisitos_son_los_de_siempre(self):
        with mock.patch.object(osenv, "WINDOWS", False):
            r = B.report([NV])
            self.assertNotIn("directml", opts(r))
            self.assertEqual(B.requirements_for("cuda").name, "requirements-env.txt")
            self.assertTrue(opts(r)["cuda"]["verified"])


class Start(unittest.TestCase):
    def test_rechaza_un_motor_en_estudio_sin_tocar_el_disco(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(envsetup.stems, "ENV", Path(d)):
            for bad in ("directml", "rocm", "inventado"):
                with self.assertRaises(envsetup.EnvError):
                    envsetup.start(bad)
            self.assertEqual(list(Path(d).iterdir()), [])
            self.assertEqual(envsetup._job["state"], "idle")

    def test_rechaza_cuda_sin_nvidia_sin_tocar_el_disco(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(envsetup.stems, "ENV", Path(d)),                 mock.patch.object(envsetup.hardware, "_gpus", return_value=[AMD]):
            with self.assertRaises(envsetup.EnvError) as cm:
                envsetup.start("cuda")
            self.assertIn("compatible", str(cm.exception))
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_el_estado_dice_que_motor_hay_instalado(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(envsetup.stems, "ENV", Path(d)):
            self.assertIsNone(envsetup.status()["backend"])
            (Path(d) / envsetup.MARKER).write_text("cpu", encoding="utf-8")
            self.assertEqual(envsetup.installed_backend(), "cpu")
            for b in ("python", "audio-separator"):
                exe = osenv.env_bin(Path(d), b)
                exe.parent.mkdir(parents=True, exist_ok=True)
                exe.write_bytes(b"x")
            self.assertEqual(envsetup.status()["backend"], "cpu")


if __name__ == "__main__":
    unittest.main()
