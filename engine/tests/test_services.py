import unittest

import envsetup
import models
import services
import stems


class Services(unittest.TestCase):
    def test_parse_transfer(self):
        got = stems.parse_transfer(" 45%|████▌     | 300M/670M [00:10<00:12, 25.1MB/s]")
        self.assertEqual(got, {"done": 300_000_000, "total": 670_000_000, "rate": 25_100_000})
        got = stems.parse_transfer("100%|██| 1.5G/1.5G [01:00<00:00, 800kB/s]")
        self.assertEqual((got["done"], got["rate"]), (1_500_000_000, 800_000))
        got = stems.parse_transfer(" 12%|█▏        | 83.5M/667M [00:01<00:12, 50.2MiB/s]")  # unidades binarias de tqdm
        self.assertEqual((got["done"], got["total"], got["rate"]), (83_500_000, 667_000_000, 50_200_000))
        self.assertIsNone(stems.parse_transfer("Loading model..."))

    def test_shutdown_refuses_with_jobs(self):
        models._pulls["x"] = {"state": "running", "percent": 10}
        try:
            res = services.shutdown()
            self.assertFalse(res["ok"])
            self.assertEqual(res["jobs"][0]["kind"], "descarga")
        finally:
            models._pulls.pop("x")

    def test_idle_has_no_jobs(self):
        self.assertEqual([j for j in services.active_jobs() if j["kind"] == "descarga"], [])
        self.assertIn("present", envsetup.status())


if __name__ == "__main__":
    unittest.main()
