import tempfile
import threading
import time
import unittest
from unittest import mock

import covers

IMG = b"\xff\xd8" + b"x" * 2000
MB = "8e8a594f-2175-38c7-a871-abb68ec363e7"


class Covers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = [mock.patch.object(covers.settings, "effective", return_value={"dataDir": self.tmp})]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()

    def test_tidal_first_and_cached_on_disk(self):
        with mock.patch.object(covers, "_tidal", return_value=IMG) as t, mock.patch.object(covers, "_caa") as c:
            self.assertEqual(covers.get(MB, "Miles Davis", "Kind of Blue"), IMG)
            self.assertEqual(covers.get(MB, "Miles Davis", "Kind of Blue"), IMG)
        self.assertEqual(t.call_count, 1)   # la segunda sale del disco
        c.assert_not_called()

    def test_falls_back_to_caa_when_tidal_fails(self):
        with mock.patch.object(covers, "_tidal", side_effect=RuntimeError("sin sesión")), mock.patch.object(covers, "_caa", return_value=IMG):
            self.assertEqual(covers.get(MB, "A", "B"), IMG)

    def test_negative_cache_avoids_waiting_again(self):
        with mock.patch.object(covers, "_tidal", return_value=None), mock.patch.object(covers, "_caa", side_effect=TimeoutError) as c:
            self.assertIsNone(covers.get(MB, "A", "B"))
            self.assertIsNone(covers.get(MB, "A", "B"))
        self.assertEqual(c.call_count, 1)

    def test_tiny_response_is_not_an_image(self):
        with mock.patch.object(covers, "_tidal", return_value=b"tiny"), mock.patch.object(covers, "_caa", return_value=None):
            self.assertIsNone(covers.get(MB, "A", "B"))

    def test_concurrent_requests_fetch_once(self):
        calls = []

        def slow(artist, album):
            calls.append(1)
            time.sleep(0.3)
            return IMG

        with mock.patch.object(covers, "_tidal", side_effect=slow):
            out = []
            ts = [threading.Thread(target=lambda: out.append(covers.get(MB, "A", "B"))) for _ in range(5)]
            [t.start() for t in ts]
            [t.join() for t in ts]
        self.assertEqual(len(calls), 1)
        self.assertEqual(out, [IMG] * 5)


if __name__ == "__main__":
    unittest.main()
