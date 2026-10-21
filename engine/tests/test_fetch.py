"""Bajar el tema de TIDAL: Python descarga (certifi) y ffmpeg solo convierte un archivo local. Servidor HTTP local, nada sale a internet."""
import io
import os
import sys
import tempfile
import threading
import time
import unittest
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["STEMSHED_NO_SCHEDULER"] = "1"
import osenv  # noqa: E402
import stems  # noqa: E402

BIG = os.urandom(600 * 1024)
FLAKY_HITS = {"n": 0}


def make_wav():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(48000)
        w.writeframes(b"\x00\x10\x00\xf0" * 48000)  # 1 s a 48 kHz: ffmpeg lo pasa a 44,1 kHz
    return buf.getvalue()


WAV = make_wav()


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body, code = None, 200
        if self.path == "/big":
            body = BIG
        elif self.path.startswith("/seg"):
            body = f"[{self.path}]".encode() * 50
        elif self.path == "/flaky":
            FLAKY_HITS["n"] += 1
            if FLAKY_HITS["n"] == 1:
                code, body = 503, b"mal"
            else:
                body = b"ok-despues-de-reintentar"
        elif self.path == "/x.wav":
            body = WAV
        else:
            code, body = 404, b"no"
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class Download(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        FLAKY_HITS["n"] = 0

    def test_un_archivo_con_progreso(self):
        seen = []
        n = stems.download_source([self.base + "/big"], self.tmp / "a.bin", lambda s, p: seen.append((s, p)))
        self.assertEqual((self.tmp / "a.bin").read_bytes(), BIG)
        self.assertEqual(n, len(BIG))
        self.assertTrue(seen and all(s == "download" for s, _ in seen))
        self.assertEqual(seen, sorted(seen, key=lambda x: x[1]))
        self.assertLessEqual(seen[-1][1], 99)

    def test_los_segmentos_se_concatenan_en_orden(self):
        seen = []
        stems.download_source([self.base + f"/seg{i}" for i in range(3)], self.tmp / "d.bin", lambda s, p: seen.append(p))
        self.assertEqual((self.tmp / "d.bin").read_bytes(), b"".join(f"[/seg{i}]".encode() * 50 for i in range(3)))
        self.assertEqual(seen, [33, 66, 99])

    def test_un_fallo_temporal_se_reintenta_sin_duplicar_bytes(self):
        with mock.patch.object(time, "sleep"):
            stems.download_source([self.base + "/flaky"], self.tmp / "f.bin")
        self.assertEqual((self.tmp / "f.bin").read_bytes(), b"ok-despues-de-reintentar")
        self.assertEqual(FLAKY_HITS["n"], 2)

    def test_si_siempre_falla_se_rinde_con_el_error_de_red(self):
        import urllib.error
        with mock.patch.object(time, "sleep"), self.assertRaises(urllib.error.URLError):
            stems.download_source([self.base + "/no-existe"], self.tmp / "g.bin")

    def test_cancelar_corta_la_descarga(self):
        calls = {"n": 0}

        def cancelled():
            calls["n"] += 1
            return calls["n"] > 2
        with self.assertRaises(stems.Cancelled):
            stems.download_source([self.base + "/big"], self.tmp / "h.bin", cancelled=cancelled)
        self.assertLess((self.tmp / "h.bin").stat().st_size, len(BIG))

    def test_solo_direcciones_web(self):
        with self.assertRaises(stems.StemsError):
            stems.download_source(["file:///C:/Windows/win.ini"], self.tmp / "i.bin")
        self.assertFalse(any(self.tmp.glob("*")) and (self.tmp / "i.bin").stat().st_size)


class FakeStream:
    def __init__(self, manifest, mpd="<MPD/>"):
        self._m, self._mpd = manifest, mpd

    def get_stream_manifest(self):
        return self._m

    def get_manifest_data(self):
        return self._mpd


def fake_session(manifest):
    s = mock.Mock()
    s.track.return_value.get_stream.return_value = FakeStream(manifest)
    return s


def manifest(urls, bts=True, enc="NONE", ext=".flac"):
    m = mock.Mock()
    m.is_bts, m.encryption_type, m.file_extension = bts, enc, ext
    m.get_urls.return_value = urls
    return m


class Fetch(unittest.TestCase):
    base = Download.base if hasattr(Download, "base") else None

    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        fake = mock.Mock()
        fake.Quality.high_lossless = "LOSSLESS"
        p = mock.patch.dict(sys.modules, {"tidalapi": fake})
        p.start()
        self.addCleanup(p.stop)

    def run_fetch(self, m, ffmpeg_effects=None):
        calls = []

        def fake_ffmpeg(args, out_wav, what):
            calls.append((list(args), what))
            if ffmpeg_effects and len(calls) <= len(ffmpeg_effects) and ffmpeg_effects[len(calls) - 1]:
                raise ffmpeg_effects[len(calls) - 1]
            Path(out_wav).write_bytes(b"RIFFfake")
        with mock.patch.object(stems, "_ffmpeg_to_wav", side_effect=fake_ffmpeg):
            stems.fetch_source(fake_session(m), "123", self.tmp / "out.wav", self.tmp)
        return calls

    def test_ffmpeg_recibe_un_archivo_local_no_la_direccion_de_tidal(self):
        calls = self.run_fetch(manifest([self.base + "/big"]))
        self.assertEqual(len(calls), 1)
        arg = calls[0][0][calls[0][0].index("-i") + 1]
        self.assertTrue(arg.startswith(str(self.tmp)) and arg.endswith("source.flac"))
        self.assertNotIn("http", arg)
        self.assertNotIn("-protocol_whitelist", calls[0][0])
        self.assertEqual((self.tmp / "source.flac").read_bytes(), BIG)

    def test_dash_baja_los_segmentos_a_un_solo_archivo(self):
        calls = self.run_fetch(manifest([self.base + f"/seg{i}" for i in range(3)], bts=False, ext=".flac"))
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][0][-1].endswith("source.bin"))  # la extensión no engaña a ffmpeg: es un MP4 fragmentado
        self.assertEqual((self.tmp / "source.bin").read_bytes(), b"".join(f"[/seg{i}]".encode() * 50 for i in range(3)))

    def test_si_la_descarga_falla_cae_al_camino_viejo_y_lo_dice(self):
        import urllib.error
        with mock.patch.object(stems, "download_source", side_effect=urllib.error.URLError(OSError("sin red"))):
            calls = self.run_fetch(manifest([self.base + "/big"]))
        self.assertEqual(len(calls), 2 - 1)  # un solo ffmpeg: el viejo, con la URL
        self.assertEqual(calls[0][0], ["-i", self.base + "/big"])
        self.assertIn("la descarga directa falló: URLError, OSError", calls[0][1])

    def test_el_camino_viejo_con_https_lleva_los_certificados_de_certifi(self):
        import urllib.error
        fake_certifi = mock.Mock()
        fake_certifi.where.return_value = "/ruta/cacert.pem"
        with mock.patch.object(stems, "download_source", side_effect=urllib.error.URLError(OSError("sin red"))),                 mock.patch.dict(sys.modules, {"certifi": fake_certifi}):
            calls = self.run_fetch(manifest(["https://cdn.ejemplo.com/a.flac"]))
        self.assertEqual(calls[0][0], ["-ca_file", "/ruta/cacert.pem", "-i", "https://cdn.ejemplo.com/a.flac"])

    def test_si_la_conversion_falla_en_dash_cae_al_mpd(self):
        urls = [self.base + f"/seg{i}" for i in range(2)]
        calls = self.run_fetch(manifest(urls, bts=False), ffmpeg_effects=[stems.StemsError("moov atom not found")])
        self.assertEqual(len(calls), 2)
        self.assertIn("-protocol_whitelist", calls[1][0])
        self.assertTrue(calls[1][0][-1].endswith("track.mpd"))
        self.assertIn("el camino directo falló: moov atom not found", calls[1][1])

    def test_cifrado_se_rechaza_antes_de_bajar_nada(self):
        with mock.patch.object(stems, "download_source") as dl, self.assertRaises(stems.StemsError):
            self.run_fetch(manifest([self.base + "/big"], enc="AES"))
        dl.assert_not_called()

    def test_cancelar_durante_la_descarga_no_cae_al_camino_viejo(self):
        with mock.patch.object(stems, "download_source", side_effect=stems.Cancelled()), mock.patch.object(stems, "_ffmpeg_to_wav") as ff:
            with self.assertRaises(stems.Cancelled):
                stems.fetch_source(fake_session(manifest([self.base + "/big"])), "123", self.tmp / "out.wav", self.tmp)
            ff.assert_not_called()

    def test_conversion_real_con_ffmpeg(self):
        if not osenv.ensure_ffmpeg_on_path():
            self.skipTest("no hay ffmpeg en este equipo")
        stems.fetch_source(fake_session(manifest([self.base + "/x.wav"], ext=".wav")), "123", self.tmp / "out.wav", self.tmp)
        with wave.open(str(self.tmp / "out.wav")) as w:
            self.assertEqual((w.getframerate(), w.getnchannels(), w.getsampwidth()), (stems.SAMPLE_RATE, 2, 2))
            self.assertGreater(w.getnframes(), 40000)


class Registro(unittest.TestCase):
    def test_un_fallo_de_separacion_queda_en_el_log_del_motor(self):
        stems._jobs.pop("999999991", None)
        err = io.StringIO()
        with mock.patch.object(stems, "separate", side_effect=stems.StemsError("No pude bajar el audio del tema: Input/output error")), \
                mock.patch.object(stems, "is_cached", return_value=False), mock.patch.object(sys, "stderr", err):
            stems.start(mock.Mock(), "999999991")
            end = time.time() + 5
            while stems._jobs["999999991"]["state"] == "running" and time.time() < end:
                time.sleep(0.02)
        self.assertEqual(stems._jobs["999999991"]["state"], "error")
        self.assertIn("Separación 999999991 falló: No pude bajar el audio del tema: Input/output error", err.getvalue())
        stems._jobs.pop("999999991", None)


if __name__ == "__main__":
    unittest.main()
