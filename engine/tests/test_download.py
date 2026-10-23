"""Descarga de un tema a un archivo y "abrir en carpeta", con TIDAL simulado y carpetas temporales (sin red, sin tocar los datos reales
del usuario y SIN abrir nunca un explorador de archivos).

Correr: cd engine && python3 -m unittest discover -s tests -v
"""
import errno
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import download  # noqa: E402
import library  # noqa: E402
import settings  # noqa: E402
import stems  # noqa: E402
import tidal_source  # noqa: E402

ORIG_EFFECTIVE = settings.effective
HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
ORIG_PROBE = download._probe
HAS_MP3 = HAS_FFMPEG and "libmp3lame" in subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
_patches = []
BASE = {}


def setUpModule():
    """Nada de este módulo lee ni escribe la configuración ni la carpeta de datos REAL; y el explorador de archivos nunca se abre."""
    root = Path(tempfile.mkdtemp(prefix="stemshed-test-dl-"))
    BASE.update(root=root, data=root / "data", music=root / "music", dl=root / "data" / "downloads")
    BASE["music"].mkdir()
    eff = {**settings.DEFAULTS, "dataDir": str(BASE["data"]), "downloadDir": str(BASE["dl"]), "musicFolders": [str(BASE["music"])]}
    for p in (mock.patch.object(settings, "load", lambda: dict(settings.DEFAULTS)),
              mock.patch.object(settings, "effective", lambda d=None: dict(eff)),
              mock.patch.object(stems, "CACHE", root / "cache"), mock.patch.object(stems, "OLD_CACHE", root / "oldcache"),
              mock.patch.dict(os.environ, {"STEMSHED_OPEN_DRYRUN": "1"}),
              mock.patch.object(download, "_probe", lambda f: {}),          # por defecto no se lanza ffprobe: los tests que lo necesitan lo piden (real())
              mock.patch.object(download, "have_ffmpeg", lambda: True),
              mock.patch.object(download, "has_mp3_encoder", lambda: True),
              mock.patch.object(subprocess, "Popen", side_effect=AssertionError("los tests no pueden lanzar procesos reales"))):
        p.start()
        _patches.append(p)
    BASE["eff"] = eff


def tearDownModule():
    while _patches:
        _patches.pop().stop()
    shutil.rmtree(BASE["root"], ignore_errors=True)


def wait(track_id, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        st = download.status(track_id)
        if st["state"] != "running":
            return st
        time.sleep(0.05)
    raise AssertionError("la descarga no terminó")




_REAL_POPEN = subprocess.Popen


def real():
    """Para los tests que usan ffmpeg/ffprobe de verdad (con audio de prueba generado): se destapa Popen y ffprobe solo ahí."""
    from contextlib import ExitStack
    st = ExitStack()
    st.enter_context(mock.patch.object(subprocess, "Popen", _REAL_POPEN))
    st.enter_context(mock.patch.object(download, "_probe", ORIG_PROBE))
    return st


def ff(*args):
    with mock.patch.object(subprocess, "Popen", _REAL_POPEN):
        return subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def probe_json(path, entries):
    with mock.patch.object(subprocess, "Popen", _REAL_POPEN):
        out = subprocess.run(["ffprobe", "-v", "error", *entries, "-of", "json", str(path)], capture_output=True, text=True).stdout
    return json.loads(out)


def wait(track_id, timeout=20, key="original"):
    end = time.time() + timeout
    while time.time() < end:
        st = download.status(track_id, key)
        if st["state"] != "running":
            return st
        time.sleep(0.05)
    raise AssertionError("la descarga no terminó")


def wait_batch(timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        b = download.batch_status()
        if b and b["state"] != "running":
            return b
        time.sleep(0.05)
    raise AssertionError("el lote no terminó")


class Base(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(BASE["dl"], ignore_errors=True)
        BASE["data"].mkdir(parents=True, exist_ok=True)
        for f in BASE["music"].iterdir():
            f.unlink()
        download._jobs.clear()
        download._holders.clear()
        download._batch.clear()
        download._index_file().unlink(missing_ok=True)
        self.files = {}
        p1 = mock.patch.object(library, "path_for", lambda i: self.files.get(i, {}).get("path"))
        p2 = mock.patch.object(library, "meta_for", lambda i: {"title": self.files[i]["title"], "artist": self.files[i]["artist"]} if i in self.files else {"title": i, "artist": ""})
        p3 = mock.patch.dict(library._state["tracks"], {}, clear=True)
        for p in (p1, p2, p3):
            p.start()
            self.addCleanup(p.stop)

    def local(self, name, content=b"audio", tid="L" + "a" * 12, title="Tema", artist="Artista", seconds=None):
        f = BASE["music"] / name
        if isinstance(content, bytes):
            f.write_bytes(content)
        self.files[tid] = {"path": str(f), "title": title, "artist": artist}
        library._state["tracks"][tid] = {"id": tid, "title": title, "artist": artist, "duration": seconds}
        return f, tid

    def tidal_info(self, **extra):
        meta = {"title": "Ojos así", "artist": "Shakira", "album": "Dónde están", "track": 3, "year": 1998}
        return {"urls": ["https://example.invalid/a"], "bts": True, "ext": ".flac", "meta": meta, "cover": None, **extra}

    def fake_download(self, content):
        def go(urls, dest, progress=None, cancelled=None):
            if isinstance(content, Path):
                shutil.copy(content, dest)
            else:
                Path(dest).write_bytes(content)
            if progress:
                progress("download", 50)
            return 1
        return go

    def tidal(self, content=b"x", **info_extra):
        """TIDAL simulado: sesión, datos del tema y bajada del audio."""
        stack = []
        for p in (mock.patch.object(tidal_source, "session", lambda: object()),
                  mock.patch.object(tidal_source, "download_info", mock.Mock(side_effect=lambda tid, lossless=True: self.tidal_info(**info_extra))),
                  mock.patch.object(stems, "download_source", self.fake_download(content))):
            p.start()
            self.addCleanup(p.stop)
            stack.append(p)
        return tidal_source.download_info


class Names(unittest.TestCase):
    def test_sanitize_and_stem(self):
        self.assertEqual(download.file_stem("AC/DC", "Back: In Black?"), "AC_DC - Back_ In Black_")
        self.assertEqual(download.file_stem("", "Solo título"), "Solo título")
        self.assertEqual(download.file_stem("Artista", ""), "Artista")
        self.assertEqual(download.file_stem("", ""), "Tema")
        self.assertEqual(download.file_stem("", "CON"), "_CON")
        self.assertEqual(download.file_stem("A", "t.. "), "A - t")
        self.assertLessEqual(len(download.file_stem("ñ" * 300, "x").encode()), 180)

    def test_ipod_names_are_simple(self):
        n = download.file_stem("Björk", "Hyperballad ✨ (live) / “mix”", ipod=True)
        self.assertEqual(n, "Bjork - Hyperballad (live) mix")
        self.assertTrue(n.isascii())
        self.assertLessEqual(len(download.file_stem("a" * 300, "b" * 300, ipod=True)), 163)

    def test_reserve_never_overwrites(self):
        d = Path(tempfile.mkdtemp())
        try:
            a = download.reserve(d, "A - B", ".flac")
            b = download.reserve(d, "A - B", ".flac")
            c = download.reserve(d, "A - B", ".flac")
            self.assertEqual([a.name, b.name, c.name], ["A - B.flac", "A - B (2).flac", "A - B (3).flac"])
        finally:
            shutil.rmtree(d)

    def test_friendly_errors(self):
        self.assertIn("No hay espacio", download.friendly_os_error(OSError(errno.ENOSPC, "x"), "/d"))
        self.assertIn("No hay permiso", download.friendly_os_error(OSError(errno.EACCES, "x"), "/d"))

    def test_album_folder_layout(self):
        d = Path(tempfile.mkdtemp())
        try:
            opts = {"quality": "mp3_128", "ipod": False, "key": "mp3_128", "folders": True}
            p = download._dest(d, {"title": "Ojos así", "artist": "AC/DC", "album": "Dónde: están", "track": 3}, ".mp3", opts, "Tema")
            self.assertEqual(p.relative_to(d).as_posix(), "AC_DC/Dónde_ están/03 - Ojos así.mp3")
            p2 = download._dest(d, {"title": "Sin número", "artist": "", "album": ""}, ".mp3", opts, "Tema")
            self.assertEqual(p2.relative_to(d).as_posix(), "Sin artista/Sin álbum/Sin número.mp3")
            p3 = download._dest(d, {"title": "Ojos así", "artist": "AC/DC", "album": "Dónde", "track": 3}, ".mp3", opts, "Tema")
            p4 = download._dest(d, {"title": "Ojos así", "artist": "AC/DC", "album": "Dónde", "track": 3}, ".mp3", opts, "Tema")
            self.assertEqual(p4.name, "03 - Ojos así (2).mp3")
            self.assertNotIn("..", p.relative_to(d).parts)
        finally:
            shutil.rmtree(d)


class LocalCopy(Base):
    def test_copies_with_real_extension_and_name(self):
        f, tid = self.local("cualquiera.opus", b"x" * 3000)
        download.start(tid)
        st = wait(tid)
        self.assertEqual(st["state"], "done", st)
        out = BASE["dl"] / "Artista - Tema.opus"
        self.assertEqual(out.read_bytes(), f.read_bytes())
        self.assertTrue(f.exists())
        self.assertEqual(download.status(tid)["file"], str(out))
        self.assertEqual(download.report()["items"][f"{tid}|original"]["file"], str(out))
        self.assertEqual([p.name for p in BASE["dl"].iterdir()], ["Artista - Tema.opus"])   # sin temporales sueltos

    def test_second_click_same_quality_does_not_redownload_and_other_track_gets_suffix(self):
        f, tid = self.local("a.flac")
        download.start(tid)
        wait(tid)
        self.assertTrue(download.start(tid)["already"])
        f2, tid2 = self.local("b.flac", b"otro", tid="L" + "b" * 12)
        download.start(tid2)
        self.assertEqual(wait(tid2)["state"], "done")
        self.assertEqual(sorted(p.name for p in BASE["dl"].iterdir()), ["Artista - Tema (2).flac", "Artista - Tema.flac"])

    def test_legacy_index_entries_count_as_original(self):
        f, tid = self.local("a.flac")
        out = BASE["dl"]; out.mkdir(parents=True)
        (out / "viejo.flac").write_bytes(b"1")
        download._index_file().write_text(json.dumps({tid: {"file": str(out / "viejo.flac"), "title": "T", "artist": "A", "at": 1}}))
        self.assertTrue(download.start(tid)["already"])

    def test_missing_file(self):
        with self.assertRaises(download.DownloadError) as cm:
            download.start("L" + "c" * 12)
        self.assertIn("ya no está en la biblioteca", str(cm.exception))

    def test_disk_full_message(self):
        f, tid = self.local("a.flac", b"x" * 100)
        with mock.patch("shutil.disk_usage", lambda p: mock.Mock(free=0)):
            download.start(tid)
            st = wait(tid)
        self.assertEqual(st["state"], "error")
        self.assertIn("No hay espacio", st["message"])
        self.assertEqual(list(BASE["dl"].iterdir()), [])

    def test_no_permission_message(self):
        f, tid = self.local("a.flac")
        with mock.patch.object(download, "_process", side_effect=PermissionError(errno.EACCES, "denegado")):
            download.start(tid)
            st = wait(tid)
        self.assertEqual(st["state"], "error")
        self.assertIn("No hay permiso", st["message"])

    def test_cancel_leaves_nothing(self):
        f, tid = self.local("a.flac", b"x" * (6 * 1024 * 1024))
        real_update = download.jobs.update
        started = threading.Event()

        def slow(job, **kw):
            if kw.get("percent") is not None and job.get("step") == "Copiando":
                started.set()
                time.sleep(0.2)
            return real_update(job, **kw)
        with mock.patch.object(download.jobs, "update", slow):
            download.start(tid)
            self.assertTrue(started.wait(5))
            download.cancel(tid)
            st = wait(tid)
        self.assertEqual(st["state"], "cancelled")
        self.assertEqual(list(BASE["dl"].iterdir()), [])
        self.assertIsNone(download.downloaded(tid))

    def test_only_one_at_a_time(self):
        f, tid = self.local("a.flac")
        download._jobs["999"] = {"state": "running"}
        with self.assertRaises(download.DownloadError) as cm:
            download.start(tid)
        self.assertIn("Ya hay una descarga", str(cm.exception))


class FakeTidal(Base):
    @unittest.skipUnless(HAS_FFMPEG, "falta ffmpeg")
    def test_tidal_original_tags_and_name(self):
        src = BASE["root"] / "src.flac"
        ff("-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:a", "flac", str(src))
        self.tidal(src)
        with real():
            download.start("123456")
            st = wait("123456")
        self.assertEqual(st["state"], "done", st)
        out = BASE["dl"] / "Shakira - Ojos así.flac"
        self.assertTrue(out.is_file())
        self.assertTrue(st["tagged"])
        tags = {k.lower(): v for k, v in probe_json(out, ["-show_entries", "format_tags"])["format"]["tags"].items()}
        self.assertEqual((tags["title"], tags["artist"], tags["album"], tags["track"], tags["date"]), ("Ojos así", "Shakira", "Dónde están", "3", "1998"))
        self.assertEqual([p.name for p in BASE["dl"].iterdir()], ["Shakira - Ojos así.flac"])

    def test_without_ffmpeg_keeps_file_untagged(self):
        self.tidal(b"fLaC-bytes")
        with mock.patch.object(download, "have_ffmpeg", lambda: False):
            download.start("123456")
            st = wait("123456")
        self.assertEqual(st["state"], "done", st)
        self.assertFalse(st["tagged"])
        self.assertIn("sin etiquetas", st["note"])
        self.assertEqual((BASE["dl"] / "Shakira - Ojos así.flac").read_bytes(), b"fLaC-bytes")
        self.assertEqual(len(list(BASE["dl"].iterdir())), 1)

    def test_no_tidal_session(self):
        err = tidal_source.SourceError("no_session", "Todavía no conectaste TIDAL. Tocá Conectar TIDAL para iniciar sesión.")
        with mock.patch.object(tidal_source, "session", side_effect=err):
            with self.assertRaises(tidal_source.SourceError):
                download.start("123456")
        self.assertFalse(BASE["dl"].exists() and any(BASE["dl"].iterdir()))

    def test_track_not_available(self):
        class ObjectNotFound(Exception):
            pass
        with mock.patch.object(tidal_source, "session", lambda: object()), \
                mock.patch.object(tidal_source, "download_info", side_effect=ObjectNotFound("404")):
            download.start("123456")
            st = wait("123456")
        self.assertEqual(st["message"], "Ese tema no está disponible en TIDAL.")

    def test_network_error_message(self):
        self.tidal()
        with mock.patch.object(stems, "download_source", side_effect=urllib.error.URLError("sin red")):
            download.start("123456")
            st = wait("123456")
        self.assertIn("No pude conectar con TIDAL", st["message"])
        self.assertEqual(list(BASE["dl"].iterdir()), [])

    def test_cancel_during_download_removes_partials(self):
        self.tidal()

        def slow(urls, dest, progress=None, cancelled=None):
            Path(dest).write_bytes(b"parcial")
            for _ in range(100):
                if cancelled():
                    raise stems.Cancelled()
                time.sleep(0.05)
        with mock.patch.object(stems, "download_source", slow):
            download.start("123456")
            time.sleep(0.3)
            download.cancel("123456")
            st = wait("123456")
        self.assertEqual(st["state"], "cancelled")
        self.assertEqual(list(BASE["dl"].iterdir()), [])

    def test_never_separates(self):
        self.tidal()
        with mock.patch.object(stems, "start", side_effect=AssertionError("no separa")), mock.patch.object(stems, "separate", side_effect=AssertionError("no separa")), \
                mock.patch.object(download, "have_ffmpeg", lambda: False):
            download.start("123456")
            self.assertEqual(wait("123456")["state"], "done")
        self.assertEqual(stems._jobs.get("123456"), None)

    def test_aac_asks_tidal_for_the_320_stream(self):
        info = self.tidal()
        with mock.patch.object(download, "have_ffmpeg", lambda: True), mock.patch.object(download, "_run_ffmpeg", lambda *a, **k: (False, "x")):
            download.start("123456", "aac")
            wait("123456", key="aac")
        self.assertEqual(info.call_args.kwargs, {"lossless": False})   # pide el stream AAC 320 de TIDAL, no el lossless


@unittest.skipUnless(HAS_MP3, "falta ffmpeg con libmp3lame")
class Conversions(Base):
    """Convierte de verdad con ffmpeg (audio de prueba generado) y compara el peso real con la estimación."""

    SECONDS = 60

    def make_source(self, with_cover=True, name="fuente.flac", title="Canción", artist="Intérprete", album="Álbum"):
        f = BASE["music"] / name
        cover = BASE["root"] / "cover.jpg"
        ff("-f", "lavfi", "-i", "color=c=0x336699:s=900x900:d=1", "-frames:v", "1", str(cover))
        args = ["-f", "lavfi", "-i", f"anoisesrc=d={self.SECONDS}:c=pink:r=44100:a=0.3"]
        if with_cover:
            args += ["-i", str(cover), "-map", "0:a", "-map", "1:v", "-disposition:v:0", "attached_pic"]
        args += ["-ac", "2", "-c:a", "flac", "-metadata", f"title={title}", "-metadata", f"artist={artist}", "-metadata", f"album={album}", "-metadata", "track=7", str(f)]
        ff(*args)
        return f

    def run_one(self, tid, quality, profile=None):
        ipod = profile == "ipod"
        if ipod and quality not in download.IPOD_QUALITIES:
            quality = "mp3_128"     # el perfil iPod fuerza MP3 128
        with real():
            download.start(tid, quality, "ipod" if ipod else None)
            return wait(tid, key=download.qkey(quality, ipod))

    def test_mp3_128_ipod_profile(self):
        f = self.make_source()
        _, tid = self.local("x", content=None, title="Canción ✨", artist="Intérprete", seconds=self.SECONDS)
        self.files[tid]["path"] = str(f)
        st = self.run_one(tid, "mp3_256", "ipod")     # el perfil iPod fuerza MP3 128
        self.assertEqual(st["state"], "done", st)
        out = Path(st["file"])
        self.assertEqual(out.name, "Interprete - Cancion.mp3")   # nombre simple, sin acentos ni símbolos
        self.assertEqual(out.read_bytes()[:4], b"ID3\x03")       # ID3v2.3
        info = probe_json(out, ["-show_entries", "stream=codec_name,sample_rate,channels,width,height,bit_rate", "-show_entries", "format=bit_rate"])
        audio = [s for s in info["streams"] if s["codec_name"] == "mp3"][0]
        self.assertEqual((audio["sample_rate"], audio["channels"]), ("44100", 2))
        self.assertAlmostEqual(int(info["format"]["bit_rate"]) / 1000, 128, delta=8)
        pics = [s for s in info["streams"] if s["codec_name"] == "mjpeg"]
        self.assertEqual(len(pics), 1)
        self.assertLessEqual(max(pics[0]["width"], pics[0]["height"]), 500)
        self.assertEqual(st["format"], "mp3")

    def test_covers_omitted_when_source_has_none(self):
        f = self.make_source(with_cover=False)
        _, tid = self.local("x", content=None, seconds=self.SECONDS)
        self.files[tid]["path"] = str(f)
        st = self.run_one(tid, "mp3_192")
        self.assertEqual(st["state"], "done", st)
        self.assertIn("sin carátula", st["note"])
        self.assertEqual([s for s in probe_json(st["file"], ["-show_entries", "stream=codec_name"])["streams"] if s["codec_name"] == "mjpeg"], [])

    def test_estimate_vs_real_sizes(self):
        f = self.make_source()
        _, tid = self.local("x", content=None, seconds=self.SECONDS)
        self.files[tid]["path"] = str(f)
        report = {}
        for q in ("original", "aac", "mp3_320", "mp3_256", "mp3_192", "mp3_128"):
            st = self.run_one(tid, q)
            self.assertEqual(st["state"], "done", (q, st))
            real_size = Path(st["file"]).stat().st_size
            est = download.estimate_item(tid, self.SECONDS, q)["bytes"]
            report[q] = (est, real_size, 100 * (est - real_size) / real_size)
        print("\nestimado vs real (60 s):", {q: f"{e} vs {r} ({d:+.1f} %)" for q, (e, r, d) in report.items()})
        self.assertEqual(report["original"][0], report["original"][1])   # archivo propio: tamaño exacto
        for q in ("mp3_320", "mp3_256", "mp3_192", "mp3_128"):
            self.assertLess(abs(report[q][2]), 6, q)

    def test_same_track_two_qualities_are_two_files(self):
        f = self.make_source()
        _, tid = self.local("x", content=None, seconds=self.SECONDS)
        self.files[tid]["path"] = str(f)
        a = self.run_one(tid, "original")
        b = self.run_one(tid, "mp3_128")
        self.assertNotEqual(a["file"], b["file"])
        self.assertEqual(sorted(p.suffix for p in BASE["dl"].iterdir()), [".flac", ".mp3"])
        self.assertTrue(download.start(tid, "mp3_128")["already"])      # misma calidad: no baja de nuevo
        self.assertTrue(download.start(tid, "original")["already"])
        self.assertEqual(len(download.report()["items"]), 2)
        self.assertEqual(download.reveal(None, tid, key="mp3_128")["path"], str(Path(b["file"]).resolve()))

    def test_tidal_mp3_in_album_folder_with_cover(self):
        src = BASE["root"] / "src.flac"
        ff("-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-c:a", "flac", str(src))
        cover = BASE["root"] / "tcover.jpg"
        ff("-f", "lavfi", "-i", "color=c=red:s=640x640:d=1", "-frames:v", "1", str(cover))
        self.tidal(src, cover="https://resources.tidal.com/images/x/640x640.jpg")
        with mock.patch.object(download, "_fetch_cover", lambda url, dst: shutil.copy(cover, dst) or True):
            with real():
                download.batch_start([{"id": "123456", "seconds": 3}], "mp3_192", None, True)
                b = wait_batch()
        self.assertEqual(b["items"][0]["state"], "done", b)
        out = BASE["dl"] / "Shakira" / "Dónde están" / "03 - Ojos así.mp3"
        self.assertTrue(out.is_file())
        tags = {k.lower(): v for k, v in probe_json(out, ["-show_entries", "format_tags"])["format"]["tags"].items()}
        self.assertEqual((tags["title"], tags["album"], tags["track"]), ("Ojos así", "Dónde están", "3"))
        self.assertTrue([s for s in probe_json(out, ["-show_entries", "stream=codec_name"])["streams"] if s["codec_name"] == "mjpeg"])


class Options(Base):
    def test_mp3_unavailable_has_a_reason(self):
        with mock.patch.object(download, "has_mp3_encoder", lambda: False):
            o = {q["id"]: q for q in download.options()["qualities"]}
            self.assertFalse(o["mp3_128"]["available"])
            self.assertIn("libmp3lame", o["mp3_128"]["reason"])
            self.assertTrue(o["original"]["available"] and o["aac"]["available"])
            f, tid = self.local("a.flac")
            with self.assertRaises(download.DownloadError) as cm:
                download.start(tid, "mp3_320")
            self.assertIn("MP3", str(cm.exception))
            with self.assertRaises(download.DownloadError):
                download.batch_start([{"id": tid}], "mp3_128")

    def test_no_ffmpeg_disables_everything_but_original(self):
        with mock.patch.object(download, "have_ffmpeg", lambda: False):
            o = {q["id"]: q for q in download.options()["qualities"]}
            self.assertEqual([k for k, v in o.items() if v["available"]], ["original"])
            self.assertIn("ffmpeg", o["aac"]["reason"])

    def test_ipod_profile_and_bad_values(self):
        o = download.options()
        self.assertEqual(o["ipod"]["qualities"], ["mp3_128", "mp3_192"])
        f, tid = self.local("a.flac")
        with self.assertRaises(download.DownloadError):
            download.start(tid, "no-existe")
        with self.assertRaises(download.DownloadError):
            download.start(tid, "original", "otro")


class Estimates(Base):
    def test_unknown_durations_are_not_invented(self):
        f, tid = self.local("a.flac", b"x" * 1000)
        e = download.estimate([{"id": "111", "seconds": 200}, {"id": "222"}, {"id": tid}], "mp3_128")
        self.assertEqual(e["unknown"], 2)             # el de TIDAL sin duración y el local sin duración en la biblioteca
        self.assertEqual(e["bytes"], 200 * 128 * 125 + download.TAGS_BYTES)
        self.assertTrue(e["items"][0]["exact"] and e["items"][1]["bytes"] is None)
        e = download.estimate([{"id": tid}, {"id": "111", "seconds": 100}], "original")
        self.assertEqual(e["items"][0]["bytes"], 1000)           # archivo propio: tamaño real
        self.assertEqual(e["items"][1]["bytes"], 100 * download.LOSSLESS_KBPS * 125)
        self.assertTrue(e["approx"])

    def test_picks_the_id_with_the_source_order(self):
        f, tid = self.local("a.flac", seconds=100)
        with mock.patch("sources.pick", lambda ids: {"id": ids.get("local") or ids.get("tidal")}):
            e = download.estimate([{"ids": {"local": tid, "tidal": "555"}}], "mp3_320")
        self.assertEqual(e["bytes"], 100 * 320 * 125 + download.TAGS_BYTES)

    def test_refuses_when_there_is_no_room(self):
        f, tid = self.local("a.flac", seconds=100)
        with mock.patch.object(download, "free_bytes", lambda: 10_000_000):
            e = download.estimate([{"id": "111", "seconds": 2000}], "original")
            self.assertFalse(e["enough"])
            with self.assertRaises(download.DownloadError) as cm:
                download.batch_start([{"id": "111", "seconds": 2000}], "original")
            self.assertIn("No alcanza el espacio", str(cm.exception))
        self.assertIsNone(download.batch_status())


class Batch(Base):
    def locals(self, n):
        ids = []
        for i in range(n):
            f, tid = self.local(f"{i}.flac", b"x" * 500, tid="L" + f"{i:012x}", title=f"Tema {i}", artist="Artista", seconds=10)
            ids.append(tid)
        return ids

    def test_serial_with_progress_summary_and_already(self):
        ids = self.locals(4)
        download.start(ids[0]); wait(ids[0])               # este ya estaba
        running, peak = [0], [0]
        real_process = download._process

        def tracked(*a, **k):
            running[0] += 1; peak[0] = max(peak[0], running[0])
            time.sleep(0.05)
            try:
                return real_process(*a, **k)
            finally:
                running[0] -= 1
        with mock.patch.object(download, "_process", tracked):
            download.batch_start([{"id": i} for i in ids] + [{"id": "L" + "f" * 12}], "original")
            b = wait_batch()
        self.assertEqual(peak[0], 1)                        # de a uno, nunca en paralelo
        self.assertEqual((b["state"], b["done"], b["total"]), ("done", 5, 5))
        self.assertEqual([i["state"] for i in b["items"]], ["already", "done", "done", "done", "error"])
        self.assertEqual(b["summary"], "3 listos · 1 ya estaba · 1 falló (Ese archivo ya no está en la biblioteca. Volvé a leer las carpetas e intentá de nuevo.)")
        self.assertEqual(len(list(BASE["dl"].glob("*.flac"))), 4)

    def test_one_failure_does_not_cut_the_batch(self):
        ids = self.locals(3)
        real_process = download._process

        def flaky(tid, *a, **k):
            if tid == ids[1]:
                raise OSError(errno.ENOSPC, "x")
            return real_process(tid, *a, **k)
        with mock.patch.object(download, "_process", flaky):
            download.batch_start([{"id": i} for i in ids], "original")
            b = wait_batch()
        self.assertEqual([i["state"] for i in b["items"]], ["done", "error", "done"])
        self.assertIn("No hay espacio", b["items"][1]["message"])

    def test_cancel_all_leaves_the_rest_undone(self):
        ids = self.locals(4)
        gate = threading.Event()
        real_process = download._process

        def slowfirst(tid, *a, **k):
            if tid == ids[0]:
                gate.set()
                for _ in range(100):
                    if download._holders[tid].get("cancelled"):
                        raise stems.Cancelled()
                    time.sleep(0.05)
            return real_process(tid, *a, **k)
        with mock.patch.object(download, "_process", slowfirst):
            download.batch_start([{"id": i} for i in ids], "original")
            self.assertTrue(gate.wait(5))
            download.batch_cancel("all")
            b = wait_batch()
        self.assertEqual(b["state"], "cancelled")
        self.assertEqual([i["state"] for i in b["items"]], ["cancelled"] * 4)
        self.assertEqual(list(BASE["dl"].iterdir()), [])

    def test_cancel_current_continues_with_the_next(self):
        ids = self.locals(3)
        gate = threading.Event()
        real_process = download._process

        def slowfirst(tid, *a, **k):
            if tid == ids[0]:
                gate.set()
                for _ in range(100):
                    if download._holders[tid].get("cancelled"):
                        raise stems.Cancelled()
                    time.sleep(0.05)
            return real_process(tid, *a, **k)
        with mock.patch.object(download, "_process", slowfirst):
            download.batch_start([{"id": i} for i in ids], "original")
            self.assertTrue(gate.wait(5))
            download.batch_cancel("current")
            b = wait_batch()
        self.assertEqual([i["state"] for i in b["items"]], ["cancelled", "done", "done"])
        self.assertEqual(b["summary"], "2 listos · 1 cancelado")

    def test_rate_limit_retries_then_succeeds(self):
        class TooManyRequests(Exception):
            pass
        self.tidal(b"fLaC")
        calls = [0]
        real_info = tidal_source.download_info

        def limited(tid, lossless=True):
            calls[0] += 1
            if calls[0] <= 2:
                raise TooManyRequests("429")
            return real_info(tid, lossless)
        with mock.patch.object(tidal_source, "download_info", limited), mock.patch.object(download, "RATE_WAITS", (0, 0, 0)), \
                mock.patch.object(download, "have_ffmpeg", lambda: False):
            download.batch_start([{"id": "123456"}], "original")
            b = wait_batch()
        self.assertEqual((b["items"][0]["state"], calls[0]), ("done", 3))

    def test_rate_limit_that_persists_cuts_the_batch_with_a_clear_message(self):
        class TooManyRequests(Exception):
            pass
        self.tidal()
        with mock.patch.object(tidal_source, "download_info", side_effect=TooManyRequests("429")), mock.patch.object(download, "RATE_WAITS", (0, 0)):
            download.batch_start([{"id": "111"}, {"id": "222"}, {"id": "333"}], "original")
            b = wait_batch()
        self.assertEqual([i["state"] for i in b["items"]], ["error", "pending", "pending"])
        self.assertIn("se cortó el lote, faltan 2", b["summary"])
        self.assertIn("TIDAL sigue pidiendo esperar", b["summary"])

    def test_rejects_bad_requests(self):
        for bad in (None, [], "x"):
            with self.assertRaises(download.DownloadError):
                download.batch_start(bad)
        with self.assertRaises(download.DownloadError):
            download.batch_start([{"id": "1"}] * (download.MAX_BATCH + 1))
        with self.assertRaises(download.DownloadError):
            download.batch_start([{"nada": 1}])
        with self.assertRaises(download.DownloadError):
            download.batch_cancel()

    def test_cant_start_while_another_runs(self):
        ids = self.locals(1)
        download._batch.update(state="running")
        with self.assertRaises(download.DownloadError):
            download.batch_start([{"id": ids[0]}])
        with self.assertRaises(download.DownloadError):
            download.start(ids[0])
        download._batch.clear()

    def test_without_tidal_session_fails_before_starting(self):
        err = tidal_source.SourceError("no_session", "Todavía no conectaste TIDAL.")
        with mock.patch.object(tidal_source, "session", side_effect=err):
            with self.assertRaises(tidal_source.SourceError):
                download.batch_start([{"id": "123456"}])
        self.assertIsNone(download.batch_status())


class Reveal(Base):
    def test_inside_known_folders(self):
        f, tid = self.local("a.flac")
        r = download.reveal(str(f))
        self.assertTrue(r["dryRun"])
        self.assertEqual(r["path"], str(f.resolve()))
        self.assertEqual(r["command"][-1], str(f.parent)) if r["command"][0] == "xdg-open" else self.assertIn(str(f.resolve().as_uri()), r["command"][-2])
        self.assertTrue(download.reveal(str(BASE["music"]))["dryRun"])        # una carpeta también
        self.assertTrue(download.reveal(None, tid)["dryRun"])                  # por id de un tema local

    def test_downloaded_by_id(self):
        f, tid = self.local("a.flac")
        download.start(tid)
        wait(tid)
        self.assertEqual(download.reveal(None, tid)["path"], str((BASE["dl"] / "Artista - Tema.flac").resolve()))

    def test_original_of_a_downloaded_local_track(self):
        f, tid = self.local("a.flac")
        download.start(tid)
        wait(tid)
        self.assertEqual(download.reveal(None, tid, original=True)["path"], str(f.resolve()))

    def test_rejects_outside_traversal_and_symlinks(self):
        outside = BASE["root"] / "afuera"
        outside.mkdir(exist_ok=True)
        secret = outside / "secreto.txt"
        secret.write_text("x")
        (BASE["music"] / "link").symlink_to(outside)
        (BASE["music"] / "flink.txt").symlink_to(secret)
        for bad in (str(secret), str(BASE["music"] / ".." / "afuera" / "secreto.txt"), str(BASE["music"] / "link" / "secreto.txt"),
                    str(BASE["music"] / "flink.txt"), "/etc/passwd", "relativa/x", "", "a\x00b", None, 5):
            with self.assertRaises(download.RevealError, msg=repr(bad)):
                download.reveal(bad)
        with self.assertRaises(download.RevealError):
            download.reveal(str(BASE["music"] / "no-existe.flac"))
        with self.assertRaises(download.RevealError):
            download.reveal(None, "123456")                                    # id de TIDAL sin descargar

    def test_commands_per_platform(self):
        f = BASE["music"] / "x.flac"
        f.write_bytes(b"1")
        self.assertEqual(download.reveal_command(f, "darwin"), ["open", "-R", str(f)])
        self.assertEqual(download.reveal_command(f, "win32"), ["explorer", f"/select,{f}"])
        self.assertEqual(download.reveal_command(BASE["music"], "win32"), ["explorer", str(BASE["music"])])
        with mock.patch.object(shutil, "which", lambda n: None):
            self.assertEqual(download.reveal_command(f, "linux"), ["xdg-open", str(BASE["music"])])

    def test_real_open_path_is_never_taken_in_tests(self):
        f, _ = self.local("a.flac")
        with mock.patch.dict(os.environ, {"STEMSHED_OPEN_DRYRUN": ""}):
            self.assertFalse(download.open_dry())     # solo comprueba la bandera; no se llama a reveal() sin dry-run


class Settings(unittest.TestCase):
    def test_download_dir_default_and_validation(self):
        out = ORIG_EFFECTIVE({**settings.DEFAULTS, "dataDir": "/tmp/xx-datos"})   # effective() real: <dataDir>/downloads
        self.assertEqual(out["downloadDir"], "/tmp/xx-datos/downloads")
        out = ORIG_EFFECTIVE({**settings.DEFAULTS, "dataDir": "/tmp/xx-datos", "downloadDir": "/tmp/otra"})
        self.assertEqual(out["downloadDir"], "/tmp/otra")
        d = Path(tempfile.mkdtemp())
        try:
            self.assertEqual(settings.validate({"downloadDir": str(d / "nueva")}), {"downloadDir": str(d / "nueva")})
            self.assertTrue((d / "nueva").is_dir())
            self.assertEqual(settings.validate({"downloadDir": ""}), {"downloadDir": ""})
            with self.assertRaises(settings.SettingsError):
                settings.validate({"downloadDir": "relativa"})
            with self.assertRaises(settings.SettingsError):
                settings.validate({"downloadDir": "/etc/x"})
        finally:
            shutil.rmtree(d)


class Http(Base):
    """Las rutas del motor, con un servidor de verdad en un puerto libre."""

    @classmethod
    def setUpClass(cls):
        import server
        cls.server = server
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def call(self, method, path, body=None, origin="http://127.0.0.1:5173"):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method=method, data=json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None))
        if origin:
            req.add_header("Origin", origin)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_flow_and_origin(self):
        f, tid = self.local("a.flac")
        self.assertEqual(self.call("POST", f"/engine/download/{tid}/start", origin="http://evil.example")[0], 403)
        self.assertEqual(self.call("POST", f"/engine/download/{tid}/start", origin=None)[0], 403)
        code, body = self.call("POST", f"/engine/download/{tid}/start")
        self.assertEqual(code, 200, body)
        wait(tid)
        code, st = self.call("GET", f"/engine/download/{tid}/status")
        self.assertEqual((code, st["state"]), (200, "done"))
        code, rep = self.call("GET", "/engine/downloads")
        self.assertEqual(rep["dir"], str(BASE["dl"]))
        self.assertIn(f"{tid}|original", rep["items"])
        code, r = self.call("POST", "/engine/reveal", {"id": tid})
        self.assertEqual((code, r["dryRun"]), (200, True))

    def test_reveal_rejections(self):
        self.assertEqual(self.call("POST", "/engine/reveal", {"path": "/etc/passwd"})[0], 409)
        self.assertEqual(self.call("POST", "/engine/reveal", {"id": "../x"})[0], 400)
        self.assertEqual(self.call("POST", "/engine/reveal", {"path": "/etc/passwd"}, origin="http://evil.example")[0], 403)

    def test_errors_come_as_spanish_409(self):
        err = tidal_source.SourceError("no_session", "Todavía no conectaste TIDAL. Tocá Conectar TIDAL para iniciar sesión.")
        with mock.patch.object(tidal_source, "session", side_effect=err):
            code, body = self.call("POST", "/engine/download/777/start")
        self.assertEqual(code, 409)
        self.assertIn("Todavía no conectaste TIDAL", body["message"])
        code, body = self.call("POST", "/engine/download/777/cancel")
        self.assertEqual(code, 409)



if __name__ == "__main__":
    unittest.main()
