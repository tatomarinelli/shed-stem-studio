"""Hardware: placas NVIDIA/AMD/Intel, aceleración asumida y espacio de disco de carpetas que todavía no existen."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import hardware as H  # noqa: E402

NV = {"name": "RTX 5080", "vendor": "nvidia", "accel": "cuda", "integrated": False, "vramGB": 16.0, "usedGB": 1.0}
AMD = {"name": "AMD Radeon RX 6700S", "vendor": "amd", "accel": None, "llmAccel": "vulkan", "integrated": False, "vramGB": 8.0, "usedGB": None}
IGPU = {"name": "AMD Radeon(TM) Graphics", "vendor": "amd", "accel": None, "llmAccel": None, "integrated": True, "vramGB": 0.5, "usedGB": None}
ADAPTERS = [{"name": "AMD Radeon RX 6700S", "vendor": "amd", "vramBytes": 8 * 1024**3, "integrated": False, "luid": "a"},
            {"name": "AMD Radeon(TM) Graphics", "vendor": "amd", "vramBytes": 512 * 1024**2, "integrated": True, "luid": "b"},
            {"name": "NVIDIA GeForce RTX 5080", "vendor": "nvidia", "vramBytes": 16 * 1024**3, "integrated": False, "luid": "c"}]


class Gpus(unittest.TestCase):
    def test_amd_se_muestra_pero_sin_aceleracion(self):
        with mock.patch.object(H, "_nvidia_gpus", return_value=[]), mock.patch.object(H.osenv, "gpu_adapters", return_value=ADAPTERS[:2]):
            g = H._gpus()
        self.assertEqual([x["name"] for x in g], ["AMD Radeon RX 6700S", "AMD Radeon(TM) Graphics"])  # la dedicada primero
        self.assertTrue(all(x["accel"] is None for x in g))
        self.assertEqual([x["llmAccel"] for x in g], ["vulkan", None])  # Ollama descarta la integrada
        self.assertEqual(g[0]["vramGB"], 8.0)

    def test_nvidia_no_se_duplica_y_va_primero(self):
        with mock.patch.object(H, "_nvidia_gpus", return_value=[dict(NV)]), mock.patch.object(H.osenv, "gpu_adapters", return_value=ADAPTERS):
            g = H._gpus()
        self.assertEqual([x["vendor"] for x in g], ["nvidia", "amd", "amd"])
        self.assertEqual(g[0]["usedGB"], 1.0)  # quedó la lectura de nvidia-smi

    def test_nvidia_por_dxgi_si_falta_nvidia_smi(self):
        with mock.patch.object(H, "_nvidia_gpus", return_value=[]), mock.patch.object(H.osenv, "gpu_adapters", return_value=[ADAPTERS[2]]):
            self.assertEqual(H._gpus()[0]["accel"], "cuda")


class Recommend(unittest.TestCase):
    DISKS = [{"path": "/d", "totalGB": 900, "freeGB": 500, "usedPct": 40}]

    def test_con_nvidia_cabe_y_se_recomienda(self):
        out = H.recommend([NV], self.DISKS, "/d")
        self.assertTrue(next(m for m in out if m["id"] == "mistral-nemo")["fits"])
        self.assertTrue(any(m["recommended"] for m in out))

    def test_con_amd_dedicada_los_modelos_usan_la_placa_por_vulkan(self):
        out = {m["id"]: m for m in H.recommend([AMD, IGPU], self.DISKS, "/d")}
        self.assertFalse(out["gemma3:27b"]["fits"])  # 17 GB no entran ni repartidos en 8 GB
        self.assertIn("8 GB", out["gemma3:27b"]["reasons"][0])
        self.assertTrue(out["mistral-nemo"]["fits"] and out["mistral-nemo"]["partial"])  # medido: 82 % en placa, 19,8 tok/s
        self.assertTrue(out["mistral-nemo"]["recommended"])
        small = {**AMD, "vramGB": 16.0}
        self.assertFalse(next(m for m in H.recommend([small], self.DISKS, "/d") if m["id"] == "mistral-nemo")["partial"])
        self.assertTrue(next(m for m in H.recommend([small], self.DISKS, "/d") if m["id"] == "mistral-nemo")["fits"])
        self.assertTrue(next(m for m in H.recommend([small], self.DISKS, "/d") if m["id"] == "mistral-nemo")["withSeparation"])  # la separación va por CPU: no compite por la VRAM

    def test_con_cuda_no_cambia_nada_un_modelo_mas_grande_que_la_vram_sigue_bloqueado(self):
        small = {**NV, "vramGB": 8.0}
        m = next(m for m in H.recommend([small], self.DISKS, "/d") if m["id"] == "mistral-nemo")
        self.assertFalse(m["fits"] or m["partial"])
        self.assertIn("8 GB", m["reasons"][0])

    def test_solo_integrada_no_acelera_nada(self):
        m = H.recommend([IGPU], self.DISKS, "/d")[0]
        self.assertFalse(m["fits"] or m["withSeparation"])
        self.assertIn("no hay aceleración", m["reasons"][0])

    def test_sin_gpu_mantiene_el_mensaje(self):
        self.assertIn("No se detectó una GPU", H.recommend([], self.DISKS, "/d")[0]["reasons"][0])

    def test_gpu_sin_clave_accel_cuenta_como_cuda(self):
        old = {"name": "x", "vramGB": 16.0, "usedGB": 0}
        self.assertTrue(H.recommend([old], self.DISKS, "/d")[0]["fits"])

    def test_carpeta_de_datos_inexistente_usa_el_disco_donde_se_creara(self):
        with tempfile.TemporaryDirectory() as d:
            target = os.path.join(d, "no", "existe", "todavia")
            m = H.recommend([NV], [], target)[0]
            self.assertFalse(any("quedan 0 GB" in r for r in m["reasons"]))
            self.assertIsNotNone(H._usage(target))


if __name__ == "__main__":
    unittest.main()
