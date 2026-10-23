import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import lifecycle  # noqa: E402


def alive(pid):
    return lifecycle._start_ticks(pid) is not None


class LifecycleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        p = mock.patch.object(lifecycle.osenv, "config_dir", lambda: self.tmp)
        p.start()
        self.addCleanup(p.stop)
        lifecycle._children.clear()

    def sleeper(self):
        p = subprocess.Popen(["sleep", "60"])
        self.addCleanup(lambda: p.poll() is None and p.kill())
        return p

    def test_only_known_programs_are_tracked(self):
        for ok in (["ollama", "serve"], ["/usr/bin/ffmpeg", "-i", "x"], ["/x/venv/bin/python3.14", "-m", "y"]):
            self.assertTrue(lifecycle.should_track(ok), ok)
        for no in (["xdg-open", "/tmp"], ["chromium", "url"], ["nautilus"], ["open", "x"]):
            self.assertFalse(lifecycle.should_track(no), no)

    def test_terminate_all_stops_registered_children(self):
        p = self.sleeper()
        lifecycle.register(p, "sleep")
        self.assertEqual(lifecycle.terminate_all(), 1)
        self.assertIsNotNone(p.poll())

    def test_reap_stale_kills_a_child_left_by_a_dead_engine(self):
        p = self.sleeper()
        lifecycle.register(p, "sleep")
        lifecycle._children.clear()  # simula el motor nuevo: no conoce el objeto Popen, solo el archivo
        self.assertEqual(lifecycle.reap_stale(), [p.pid])
        p.wait(5)
        self.assertEqual(lifecycle._read(), [])

    def test_reap_stale_ignores_a_recycled_pid(self):
        p = self.sleeper()
        lifecycle.register(p, "sleep")
        items = lifecycle._read()
        items[0]["ticks"] += 1  # mismo pid pero otro momento de inicio: no es el que anotamos
        lifecycle._write(items)
        self.assertEqual(lifecycle.reap_stale(), [])
        self.assertIsNone(p.poll())


if __name__ == "__main__":
    unittest.main()
