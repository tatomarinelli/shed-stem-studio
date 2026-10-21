import ctypes
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

import resources
from resources import Sampler, LinuxPlatform, WindowsPlatform, NullPlatform

SMI_LINE = "0, NVIDIA GeForce RTX 5080, 37, 2765, 16303, 51, 120.50"


def write_cpu(root, v):
    (Path(root) / "stat").write_text("cpu  " + " ".join(map(str, v)) + "\ncpu0 1 1 1 1 1 0 0 0 0 0\ncpu1 1 1 1 1 1 0 0 0 0 0\n")


def fake_proc(root, cpu=(100, 0, 50, 800, 50, 0, 0, 0), mem=(32000000, 8000000, 24000000), pids=()):
    """Un /proc falso: stat, meminfo y procesos [(pid, ppid, nombre, cmd, ticks, rss_kb)]."""
    root = Path(root)
    write_cpu(root, cpu)
    (root / "meminfo").write_text(f"MemTotal: {mem[0]} kB\nMemFree: {mem[1]} kB\nMemAvailable: {mem[2]} kB\n")
    for pid, ppid, name, cmd, ticks, rss in pids:
        d = root / str(pid)
        d.mkdir(exist_ok=True)
        # el nombre con espacios y paréntesis a propósito
        (d / "stat").write_text(f"{pid} ({name} (x)) S {ppid} 1 1 0 -1 0 0 0 0 0 {ticks} 0 0 0 20 0 1 0 5000 0 0\n")
        (d / "status").write_text(f"Name:\t{name}\nVmRSS:\t{rss} kB\n")
        (d / "cmdline").write_bytes(cmd.replace(" ", "\0").encode())


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.samplers = []

    def tearDown(self):
        for s in self.samplers:
            s.stop()
        self._tmp.cleanup()

    def sampler(self, **kw):
        kw.setdefault("platform", LinuxPlatform(self.root, clk_tck=100))
        kw.setdefault("smi_path", None)
        kw.setdefault("drm_root", os.path.join(self.root, "drm"))
        s = Sampler(**kw)
        self.samplers.append(s)
        return s


class Parsing(unittest.TestCase):
    def test_gpu_csv(self):
        g = resources.parse_gpu_csv(SMI_LINE + "\n")[0]
        self.assertEqual((g["index"], g["name"], g["utilPercent"], g["tempC"], g["powerW"]), (0, "NVIDIA GeForce RTX 5080", 37.0, 51.0, 120.5))
        self.assertEqual(g["memUsedBytes"], 2765 * 1024 * 1024)
        self.assertEqual(g["memTotalBytes"], 16303 * 1024 * 1024)

    def test_gpu_csv_not_available_power(self):
        g = resources.parse_gpu_csv("0, NVIDIA GeForce RTX 5080, 3, 100, 16303, [N/A], [N/A]\n")[0]
        self.assertIsNone(g["powerW"])
        self.assertIsNone(g["tempC"])
        self.assertEqual(g["utilPercent"], 3.0)

    def test_gpu_csv_garbage_and_two_gpus(self):
        self.assertEqual(resources.parse_gpu_csv("NVIDIA-SMI has failed because it couldn't communicate\n"), [])
        two = resources.parse_gpu_csv(SMI_LINE + "\n1, Otra, 0, 1, 8000, 40, 10\n")
        self.assertEqual([g["index"] for g in two], [0, 1])

    def test_compute_apps(self):
        self.assertEqual(resources.parse_compute_apps("1282, 134\n355488, 7450\n"), {1282: 134 * 1048576, 355488: 7450 * 1048576})
        self.assertEqual(resources.parse_compute_apps("77, [N/A]\n"), {77: None})
        self.assertEqual(resources.parse_compute_apps("No devices were found\n"), {})


class Cpu(Base):
    def test_percent_from_deltas(self):
        fake_proc(self.root, cpu=(100, 0, 50, 800, 50, 0, 0, 0))  # total 1000, idle 850
        s = self.sampler()
        s._prime()
        write_cpu(self.root, (200, 0, 100, 850, 50, 0, 0, 0))     # total 1200 (+200), idle 900 (+50) -> 75 % ocupado
        s.tick()
        snap = s.snapshot(subscribe=False)
        self.assertEqual(snap["cpu"], {"percent": 75.0, "cores": 2})
        self.assertEqual(snap["history"]["cpu"][0], 75.0)

    def test_first_reading_has_no_percent(self):
        fake_proc(self.root)
        s = self.sampler()
        s.tick()
        self.assertIsNone(s._last["cpu"]["percent"])

    def test_ram(self):
        fake_proc(self.root, mem=(32000000, 8000000, 24000000))
        s = self.sampler()
        s.tick()
        r = s._last["ram"]
        self.assertEqual((r["totalBytes"], r["availableBytes"], r["usedBytes"], r["percent"]), (32000000 * 1024, 24000000 * 1024, 8000000 * 1024, 25.0))


class Failures(Base):
    def test_no_gpu(self):
        fake_proc(self.root)
        s = self.sampler()
        s.tick()
        snap = s.snapshot(subscribe=False)
        self.assertEqual(snap["gpus"], [])
        self.assertEqual(snap["history"]["gpuUtil"][0], None)
        self.assertIsNotNone(snap["ram"])

    def test_one_source_failing_does_not_break_others(self):
        fake_proc(self.root)
        os.remove(os.path.join(self.root, "meminfo"))  # la RAM falla
        s = self.sampler(jobs_fn=lambda: [{"kind": "separación"}])
        s.tick()
        snap = s.snapshot(subscribe=False)
        self.assertIsNone(snap["ram"])
        self.assertIn("ram", snap["errors"])
        self.assertIsNotNone(snap["cpu"])
        self.assertEqual(snap["jobs"], [{"kind": "separación"}])
        s.jobs_fn = lambda: 1 / 0  # y una falla en los trabajos tampoco tira el resto
        self.assertEqual(s.snapshot(subscribe=False)["jobs"], [])

    def test_other_platform_returns_nulls(self):
        s = self.sampler(platform=NullPlatform())
        s.tick()
        snap = s.snapshot(subscribe=False)
        self.assertIsNone(snap["cpu"])
        self.assertIsNone(snap["ram"])
        self.assertEqual(snap["processes"], [])

    def test_missing_proc_root(self):
        s = self.sampler(platform=LinuxPlatform(os.path.join(self.root, "nada")))
        s.tick()
        self.assertIsNone(s.snapshot(subscribe=False)["cpu"])

    def test_disks_dedupe_and_missing_dir(self):
        a = Path(self.root, "a")
        a.mkdir()
        s = self.sampler(paths_fn=lambda: {"dataDir": str(a), "ollamaModelsDir": str(a / "no" / "existe"), "separationEnvDir": str(a)})
        fake_proc(self.root)
        s.tick()
        d = s._last["disks"]
        self.assertEqual(len(d), 1)  # mismo disco: una sola fila
        self.assertEqual(sorted(d[0]["keys"]), ["dataDir", "ollamaModelsDir", "separationEnvDir"])
        self.assertGreater(d[0]["totalBytes"], 0)


class Buffer(Base):
    def test_ring_buffer_and_since(self):
        fake_proc(self.root)
        clock = Clock()
        s = self.sampler(clock=clock, history_sec=5, interval=1.0)
        for _ in range(8):
            clock.t += 1
            s.tick()
        h = s.snapshot(subscribe=False)["history"]
        self.assertEqual(len(h["t"]), 5)               # solo quedan las últimas 5
        self.assertEqual(h["t"][-1], 1008000)
        newer = s.snapshot(subscribe=False, since=h["t"][2])["history"]
        self.assertEqual(newer["t"], h["t"][3:])
        self.assertEqual(s.snapshot(subscribe=False, since=h["t"][-1])["history"]["t"], [])


class Subscribers(Base):
    def test_stops_by_itself_without_requests(self):
        fake_proc(self.root)
        s = self.sampler(interval=0.05, idle_sec=0.4)
        s.snapshot()
        time.sleep(0.2)
        self.assertTrue(s.running())
        s.snapshot()                    # renueva el plazo
        time.sleep(0.3)
        self.assertTrue(s.running())
        time.sleep(0.8)
        self.assertFalse(s.running())
        self.assertGreater(len(s.snapshot()["history"]["t"]), 0)  # y revive con un pedido nuevo
        self.assertTrue(s.running())

    def test_persistent_smi_runs_only_with_subscribers(self):
        fake_proc(self.root)
        script = f"import time\nwhile True:\n    print({SMI_LINE!r}, flush=True)\n    time.sleep(0.05)\n"
        s = self.sampler(interval=0.05, idle_sec=1.0, smi_path="x", smi_cmd=[sys.executable, "-c", script], apps_fn=lambda: {os.getpid(): 5 * 1048576})
        s.snapshot()
        time.sleep(0.5)
        proc = s.stream.proc
        self.assertIsNotNone(proc)
        self.assertIsNone(proc.poll())
        snap = s.snapshot()
        self.assertEqual(snap["gpus"][0]["name"], "NVIDIA GeForce RTX 5080")
        self.assertEqual(snap["history"]["gpuMem"][-1], 2765 * 1048576)
        time.sleep(2.0)                 # sin pedidos: se apaga y mata el proceso
        self.assertFalse(s.running())
        self.assertIsNotNone(proc.poll())

    def test_smi_that_cannot_start(self):
        fake_proc(self.root)
        s = self.sampler(smi_path="/no/existe/nvidia-smi")
        s.tick()
        self.assertEqual(s.snapshot()["gpus"], [])


class Processes(Base):
    def test_children_cpu_rss_and_gpu_mem(self):
        me = os.getpid()
        fake_proc(self.root, pids=[(me, 1, "python3", "python3 engine/server.py", 1000, 90000),
                                   (5001, me, "python", "/venv/bin/python /venv/bin/audio-separator x.wav", 500, 2000000),
                                   (5002, 5001, "ffmpeg", "ffmpeg -i x", 10, 4000),
                                   (5003, 5002, "nvidia-smi", "nvidia-smi --query", 1, 100),
                                   (6001, 1, "ollama", "/usr/bin/ollama serve", 5, 700000),
                                   (7001, 1, "bash", "bash", 1, 100)])
        clock = Clock()
        s = self.sampler(clock=clock, smi_path="x", apps_fn=lambda: {5001: 2765 * 1048576, 6001: 7450 * 1048576, 99999: 1})
        s.stream.latest = lambda: resources.parse_gpu_csv(SMI_LINE)
        s.stream.alive = lambda: True
        s.tick()
        first = {p["pid"]: p for p in s.snapshot(subscribe=False)["processes"]}
        self.assertIsNone(first[5001]["cpuPercent"])          # primera vista: sin diferencia
        self.assertEqual(first[5001]["role"], "Separación")
        self.assertEqual(first[5001]["rssBytes"], 2000000 * 1024)
        self.assertEqual(first[5001]["gpuMemBytes"], 2765 * 1048576)
        self.assertTrue(first[5001]["inApp"])
        self.assertEqual(first[me]["role"], "Motor")
        self.assertNotIn(5003, first)                          # nuestro propio nvidia-smi no figura
        self.assertNotIn(7001, first)                          # ajeno y sin GPU
        self.assertFalse(first[6001]["inApp"])                 # Ollama ajeno que usa la placa
        self.assertEqual(first[6001]["role"], "Ollama")
        self.assertNotIn(99999, first)                         # pid que no existe en este /proc
        # 2 s después: +200 ticks de 100 Hz = 100 % de un núcleo
        clock.t += 2
        (Path(self.root) / "5001" / "stat").write_text("5001 (python) S %d 1 1 0 -1 0 0 0 0 0 700 0 0 0 20 0 1 0 5000 0 0\n" % me)
        s.tick()
        s.tick()
        second = {p["pid"]: p for p in s.snapshot(subscribe=False)["processes"]}
        self.assertEqual(second[5001]["cpuPercent"], 100.0)

    def test_pid_reuse_does_not_give_garbage(self):
        me = os.getpid()
        fake_proc(self.root, pids=[(me, 1, "python3", "python3", 1000, 1), (5001, me, "x", "x", 50000, 1)])
        clock = Clock()
        s = self.sampler(clock=clock)
        s.tick()
        clock.t += 2
        # mismo pid, otro proceso (starttime distinto) con menos ticks: no debe dar un negativo ni un valor absurdo
        (Path(self.root) / "5001" / "stat").write_text("5001 (y) S %d 1 1 0 -1 0 0 0 0 0 10 0 0 0 20 0 1 0 9999 0 0\n" % me)
        s.tick()
        s.tick()
        p = {p["pid"]: p for p in s.snapshot(subscribe=False)["processes"]}[5001]
        self.assertIsNone(p["cpuPercent"])


class Amd(Base):
    def test_sysfs_fake_folder(self):
        dev = Path(self.root, "drm", "card0", "device")
        (dev / "hwmon" / "hwmon3").mkdir(parents=True)
        (dev / "gpu_busy_percent").write_text("42\n")
        (dev / "mem_info_vram_used").write_text(str(3 * 1024**3) + "\n")
        (dev / "mem_info_vram_total").write_text(str(16 * 1024**3) + "\n")
        (dev / "hwmon" / "hwmon3" / "temp1_input").write_text("61000\n")
        (dev / "hwmon" / "hwmon3" / "power1_average").write_text("85000000\n")
        Path(self.root, "drm", "card0-DP-1").mkdir()                    # conectores: se ignoran
        Path(self.root, "drm", "card1", "device").mkdir(parents=True)   # sin gpu_busy_percent: se ignora
        fake_proc(self.root)
        s = self.sampler()
        s.tick()
        g = s.snapshot(subscribe=False)["gpus"]
        self.assertEqual(len(g), 1)
        self.assertEqual((g[0]["vendor"], g[0]["utilPercent"], g[0]["memUsedBytes"], g[0]["memTotalBytes"], g[0]["tempC"], g[0]["powerW"]),
                         ("amd", 42.0, 3 * 1024**3, 16 * 1024**3, 61.0, 85.0))
        self.assertTrue(g[0]["unverified"])  # sin verificar en hardware real


class FakeK32:
    """kernel32 simulado: llena las estructuras que recibe por referencia."""
    def __init__(self, idle, kernel, user):
        self.v = (idle, kernel, user)

    def GetSystemTimes(self, i, k, u):
        for ref, val in zip((i, k, u), self.v):
            ref._obj.dwLowDateTime, ref._obj.dwHighDateTime = val & 0xFFFFFFFF, val >> 32
        return 1

    def GlobalMemoryStatusEx(self, ref):
        ref._obj.ullTotalPhys, ref._obj.ullAvailPhys = 16 * 1024**3, 6 * 1024**3
        return 1


class WindowsSimulated(unittest.TestCase):
    """Sin verificar en Windows: solo simulaciones."""

    def test_windll_is_lazy(self):
        if sys.platform != "win32":
            self.assertFalse(hasattr(ctypes, "windll"))
        WindowsPlatform(kernel32=None)  # fuera de Windows no existe windll: no debe romper

    def test_cpu_and_memory(self):
        p = WindowsPlatform(kernel32=FakeK32(idle=(1 << 32) + 500, kernel=(1 << 32) + 800, user=300))
        busy, total = p.cpu_times()
        self.assertEqual(total, (1 << 32) + 1100)
        self.assertEqual(busy, 600)    # (kernel + user) - ocioso
        m = p.memory()
        self.assertEqual((m["totalBytes"], m["usedBytes"]), (16 * 1024**3, 10 * 1024**3))

    def test_sampler_on_windows_platform(self):
        k = FakeK32(idle=100, kernel=200, user=100)
        s = Sampler(platform=WindowsPlatform(kernel32=k), smi_path=None)
        s._prime()
        k.v = (150, 300, 200)   # total +200, ocioso +50 -> 75 %
        s.tick()
        self.assertEqual(s._last["cpu"]["percent"], 75.0)
        self.assertEqual(s._last["ram"]["percent"], 62.5)


if __name__ == "__main__":
    unittest.main()
