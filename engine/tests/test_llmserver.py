"""Servidor de modelos: aceleración según las placas e instalación (solo con un clic, solo en Windows con winget)."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import llmserver as L  # noqa: E402
import osenv  # noqa: E402

AMD = {"name": "AMD Radeon RX 6700S", "vendor": "amd", "accel": None, "llmAccel": "vulkan", "integrated": False, "vramGB": 8.0}
IGPU = {"name": "AMD Radeon(TM) Graphics", "vendor": "amd", "accel": None, "llmAccel": None, "integrated": True, "vramGB": 0.5}
NV = {"name": "RTX 5080", "vendor": "nvidia", "accel": "cuda", "llmAccel": "cuda", "integrated": False, "vramGB": 16.0}


class Status(unittest.TestCase):
    def status(self, gpus, running=False, exe=None):
        with mock.patch.object(L.hardware, "_gpus", return_value=gpus), mock.patch.object(L.models, "ollama_tags", return_value=[] if running else None), \
                mock.patch.object(osenv, "find_ollama", return_value=exe):
            return L.status()

    def test_amd_dedicada_usa_vulkan(self):
        s = self.status([AMD, IGPU], exe="C:/o.exe")
        self.assertEqual((s["accel"], s["gpu"], s["installed"], s["running"]), ("vulkan", "AMD Radeon RX 6700S", True, False))

    def test_nvidia_gana_a_amd(self):
        self.assertEqual(self.status([AMD, NV])["accel"], "cuda")

    def test_solo_integrada_o_sin_placa_es_cpu(self):
        for g in ([IGPU], []):
            s = self.status(g)
            self.assertEqual((s["accel"], s["gpu"]), ("cpu", None))

    def test_corriendo_cuenta_como_instalado(self):
        self.assertTrue(self.status([], running=True)["installed"])
        self.assertFalse(self.status([])["installed"])


class Progress(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(L.parse_progress("  412 MB / 1.54 GB"), (412_000_000, 1_540_000_000))
        self.assertEqual(L.parse_progress("██▒▒  1,5 GB / 1,66 GB"), (1_500_000_000, 1_660_000_000))
        self.assertIsNone(L.parse_progress("Successfully installed"))


class Install(unittest.TestCase):
    def setUp(self):
        L._job.update(state="idle")

    def test_no_instala_fuera_de_windows_ni_sin_winget(self):
        with mock.patch.object(osenv, "WINDOWS", False), mock.patch("subprocess.Popen") as popen:
            with self.assertRaises(L.LlmServerError):
                L.install_start()
            popen.assert_not_called()
        with mock.patch.object(osenv, "WINDOWS", True), mock.patch("shutil.which", return_value=None), mock.patch("subprocess.Popen") as popen:
            with self.assertRaises(L.LlmServerError):
                L.install_start()
            popen.assert_not_called()

    def test_no_reinstala_si_ya_esta(self):
        with mock.patch.object(L, "can_install", return_value=True), mock.patch.object(osenv, "find_ollama", return_value="C:/o.exe"), \
                mock.patch("subprocess.Popen") as popen:
            with self.assertRaises(L.LlmServerError):
                L.install_start()
            popen.assert_not_called()
            self.assertEqual(L._job["state"], "idle")


if __name__ == "__main__":
    unittest.main()
