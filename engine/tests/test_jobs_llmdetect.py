"""Tareas largas (estado honesto, cancelar), servidores de modelos detectados y llama-server. Todo simulado: no baja ni prende nada real."""
import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import backends  # noqa: E402
import jobs  # noqa: E402
import llmdetect as D  # noqa: E402
import llmserver as L  # noqa: E402
import models  # noqa: E402
import osenv  # noqa: E402
import services  # noqa: E402
import settings  # noqa: E402


def wait_for(cond, secs=3):
    end = time.time() + secs
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


class Jobs(unittest.TestCase):
    def test_updated_solo_cambia_si_avanza(self):
        j = {}
        jobs.update(j, state="running", done=1, percent=1)
        t = j["updated"]
        time.sleep(0.01)
        jobs.update(j, rate=500)  # la velocidad sola no cuenta como avance
        self.assertEqual(j["updated"], t)
        jobs.update(j, done=2)
        self.assertGreater(j["updated"], t)

    def test_rate_mide_entre_muestras(self):
        j = {}
        jobs.rate(j, 0, now=100)
        jobs.rate(j, 5_000_000, now=102)
        self.assertEqual(j["rate"], 2_500_000)
        jobs.rate(j, 5_000_001, now=102.2)  # muy seguido: no cambia
        self.assertEqual(j["rate"], 2_500_000)

    def test_public_oculta_internos(self):
        self.assertEqual(jobs.public({"a": 1, "_t": 2}), {"a": 1})


class FakeResp:
    def __init__(self, events, hold=None):
        self.lines = [json.dumps(e).encode() for e in events]
        self.closed = False
        self.hold = hold

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.closed = True

    def __iter__(self):
        for ln in self.lines:
            if self.hold:
                self.hold.wait(2)
            yield ln

    def close(self):
        self.closed = True


class Pull(unittest.TestCase):
    def setUp(self):
        models._pulls.clear()
        self.patches = [mock.patch.object(models, "ollama_tags", return_value=[]), mock.patch.object(models, "OLLAMA_MODELS", Path(tempfile.mkdtemp()))]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_fases_en_espanol(self):
        P = models.pull_phase
        self.assertEqual([P("pulling manifest"), P("pulling 8eeb52dfb3bb"), P("verifying sha256 digest"), P("writing manifest"), P("success")],
                         ["Preparando", "Descargando", "Verificando", "Terminando", "Listo"])

    def test_progreso_suma_capas_y_no_retrocede(self):
        ev = [{"status": "pulling manifest"},
              {"status": "pulling aaa", "digest": "aaa", "total": 1000, "completed": 400},
              {"status": "pulling aaa", "digest": "aaa", "total": 1000, "completed": 1000},
              {"status": "pulling bbb", "digest": "bbb", "total": 10, "completed": 0},  # capa chica: no vuelve a 0 %
              {"status": "verifying sha256 digest"}, {"status": "writing manifest"}, {"status": "success"}]
        seen = []
        with mock.patch.object(models, "_ollama", return_value=FakeResp(ev)):
            models.pull_start("qwen3:8b")
            self.assertTrue(wait_for(lambda: models.pull_status("qwen3:8b")["state"] == "done"))
        st = models.pull_status("qwen3:8b")
        self.assertEqual((st["percent"], st["step"], st["total"]), (100, "Listo", 1010))
        self.assertNotIn("_t", st)
        self.assertIn("startedAt", st)

    def test_error_conserva_el_motivo(self):
        with mock.patch.object(models, "_ollama", return_value=FakeResp([{"error": "pull model manifest: file does not exist"}])):
            models.pull_start("nada:1")
            self.assertTrue(wait_for(lambda: models.pull_status("nada:1")["state"] == "error"))
        self.assertIn("file does not exist", models.pull_status("nada:1")["message"])

    def test_servidor_apagado_se_avisa_antes(self):
        with mock.patch.object(models, "ollama_tags", return_value=None):
            with self.assertRaisesRegex(ValueError, "apagado"):
                models.pull_start("qwen3:8b")

    def test_una_sola_descarga_a_la_vez_dice_cual(self):
        import threading
        gate = threading.Event()
        with mock.patch.object(models, "_ollama", return_value=FakeResp([{"status": "pulling manifest"}] * 3, hold=gate)):
            models.pull_start("a:1")
            with self.assertRaisesRegex(ValueError, "a:1"):
                models.pull_start("b:1")
            gate.set()
            wait_for(lambda: models.pull_status("a:1")["state"] != "running")

    def test_cancelar_corta_y_deja_cancelled(self):
        import threading
        gate = threading.Event()
        resp = FakeResp([{"status": "pulling x", "digest": "x", "total": 100, "completed": i} for i in range(5)], hold=gate)
        with mock.patch.object(models, "_ollama", return_value=resp):
            models.pull_start("c:1")
            self.assertTrue(wait_for(lambda: models._pull_ctl["c:1"]["resp"] is not None))
            self.assertEqual(models.pull_cancel("c:1"), {"state": "cancelling"})
            self.assertTrue(models.pull_status("c:1")["cancelling"])
            gate.set()
            self.assertTrue(wait_for(lambda: models.pull_status("c:1")["state"] == "cancelled"))
        self.assertTrue(resp.closed)
        with self.assertRaises(ValueError):
            models.pull_cancel("c:1")

    def test_llamacpp_no_descarga(self):
        with mock.patch.object(models, "PROVIDER", "llamacpp"):
            with self.assertRaisesRegex(ValueError, "no descarga"):
                models.pull_start("qwen3:8b")


class Winget(unittest.TestCase):
    class Proc:
        def __init__(self, chunks, code=0):
            self.stdout = io.BytesIO(b"".join(chunks))
            self.returncode = code
            self.pid = 1

        def wait(self):
            return self.returncode

        def poll(self):
            return self.returncode

    def run_job(self, out, installed=lambda: True):
        job = {"state": "idle"}
        state = {"n": 0}

        def is_installed():  # falso al empezar, según `installed` al terminar
            state["n"] += 1
            return False if state["n"] == 1 else installed()

        proc = self.Proc([out])
        with mock.patch.object(L, "can_install", return_value=True), mock.patch.object(L.subprocess, "Popen", return_value=proc):
            L.start_winget(job, "X.Y", is_installed)
            wait_for(lambda: job["state"] != "running")
        return job

    def test_fases_y_final(self):
        job = self.run_job(b"Found X\r\n  412 MB / 1.54 GB\r\nSuccessfully verified installer hash\r\nStarting package install...\r\n")
        self.assertEqual((job["state"], job["step"], job["percent"]), ("done", "Listo", 100))
        self.assertEqual(job["total"], 1_540_000_000)

    def test_error_con_motivo(self):
        job = self.run_job(b"Algo salio mal\r\n", installed=lambda: False)
        self.assertEqual(job["state"], "error")
        self.assertIn("Algo salio mal", job["message"])

    def test_no_se_corta_mientras_instala(self):
        job = {"state": "running", "cancelable": False}
        L._procs[id(job)] = {"proc": None, "cancelled": False}
        with self.assertRaisesRegex(L.LlmServerError, "a medias"):
            L.cancel_winget(job)

    def test_cancelar_durante_la_descarga(self):
        job = {"state": "running", "cancelable": True}
        L._procs[id(job)] = holder = {"proc": object(), "cancelled": False}
        with mock.patch.object(osenv, "kill_tree") as kt:
            L.cancel_winget(job)
        kt.assert_called_once()
        self.assertTrue(holder["cancelled"] and job["cancelling"])

    def test_fuera_de_windows_no_instala(self):
        with mock.patch.object(L, "can_install", return_value=False):
            with self.assertRaises(L.LlmServerError):
                L.start_winget({"state": "idle"}, "X", lambda: False)


class ActiveJobs(unittest.TestCase):
    def test_incluye_instalaciones_de_winget_y_llama_server(self):
        with mock.patch.dict(L._ffmpeg_job, {"state": "running", "percent": 10}), mock.patch.dict(D._job, {"state": "running", "step": "Cargando el modelo"}):
            labels = [j["label"] for j in services.active_jobs()]
        self.assertIn("ffmpeg", labels)
        self.assertIn("llama-server", labels)


class Probe(unittest.TestCase):
    def probe(self, answers):
        with mock.patch.object(D, "_get", side_effect=lambda port, path, timeout=0.5: answers.get(path)):
            return D.probe(8080)

    def test_ollama_por_su_respuesta(self):
        r = self.probe({"/api/version": {"version": "0.30"}, "/api/tags": {"models": [{"name": "mistral-nemo:latest"}, {"name": "nomic-embed-text"}]}})
        self.assertEqual((r["kind"], r["models"]), ("ollama", ["mistral-nemo:latest"]))

    def test_llama_server_por_props(self):
        r = self.probe({"/props": {"total_slots": 1}, "/v1/models": {"data": [{"id": "m.gguf"}]}})
        self.assertEqual((r["kind"], r["models"]), ("llamacpp", ["m.gguf"]))

    def test_llama_server_por_owned_by(self):
        self.assertEqual(self.probe({"/v1/models": {"data": [{"id": "m", "owned_by": "llamacpp"}]}})["kind"], "llamacpp")

    def test_otro_servidor_openai_no_se_confunde(self):
        self.assertEqual(self.probe({"/v1/models": {"data": [{"id": "x", "owned_by": "organization_owner"}]}})["kind"], "openai")

    def test_puerto_ocupado_por_otra_cosa_no_cuenta(self):
        self.assertIsNone(self.probe({}))


class Gguf(unittest.TestCase):
    def test_escaneo_acotado(self):
        root = Path(tempfile.mkdtemp())
        (root / "a" / "b").mkdir(parents=True)
        big = 60 * 1024 * 1024
        for rel, size in (("a/modelo.gguf", big), ("a/b/otro.GGUF", big), ("a/mmproj-x.gguf", big), ("chico.gguf", 10), ("a/notas.txt", big)):
            with open(root / rel, "wb") as f:
                f.truncate(size)
        names = sorted(g["name"] for g in D.scan_gguf([root]))
        self.assertEqual(names, ["modelo.gguf", "otro.GGUF"])
        self.assertEqual(len(D.scan_gguf([root], max_files=1)), 1)
        self.assertEqual(D.scan_gguf([root / "no-existe"]), [])

    def test_manifiestos_de_ollama(self):
        root = Path(tempfile.mkdtemp())
        m = root / "manifests" / "registry.ollama.ai" / "library" / "gemma3"
        m.mkdir(parents=True)
        (m / "4b").write_text("{}")
        self.assertEqual(D.count_manifests(root), 1)
        self.assertEqual(D.count_manifests(root / "otro"), 0)


class Plataformas(unittest.TestCase):
    """Rutas de cada sistema, simuladas con osenv.WINDOWS (el módulo no tiene `if sys.platform` sueltos)."""

    def test_linux_carpetas(self):
        with mock.patch.object(osenv, "WINDOWS", False), mock.patch.dict(os.environ, {"HOME": "/home/u"}, clear=True):
            with mock.patch.object(osenv.Path, "home", return_value=Path("/home/u")):
                roots = [str(r) for r in osenv.gguf_roots()]
                self.assertIn(str(Path("/home/u/.cache/llama.cpp")), roots)
                self.assertIn(str(Path("/home/u/.lmstudio/models")), roots)
                self.assertIn(str(Path("/usr/share/ollama/.ollama/models")), [str(r) for r in osenv.ollama_model_roots()])
                self.assertIn(Path("/usr/local/bin"), osenv.llama_server_dirs())

    def test_windows_carpetas(self):
        env = {"LOCALAPPDATA": "C:/Users/u/AppData/Local", "USERPROFILE": "C:/Users/u"}
        with mock.patch.object(osenv, "WINDOWS", True), mock.patch.dict(os.environ, env, clear=True):
            roots = [str(r) for r in osenv.gguf_roots()]
            self.assertIn(str(Path("C:/Users/u/AppData/Local") / "llama.cpp"), roots)
            self.assertTrue(any(".lmstudio" in r for r in roots))
            self.assertNotIn(str(Path("/usr/share/ollama/.ollama/models")), [str(r) for r in osenv.ollama_model_roots()])
            self.assertTrue(any("WinGet" in str(d) for d in osenv.llama_server_dirs()))

    def test_busca_con_extension_exe_en_windows(self):
        d = Path(tempfile.mkdtemp())
        (d / "llama-server.exe").write_bytes(b"x")
        (d / "llama-server").write_bytes(b"x")
        with mock.patch.object(osenv, "WINDOWS", True), mock.patch("shutil.which", return_value=None):
            self.assertEqual(osenv.find_executable("llama-server", [d]), str(d / "llama-server.exe"))
        with mock.patch.object(osenv, "WINDOWS", False), mock.patch("shutil.which", return_value=None):
            self.assertEqual(osenv.find_executable("llama-server", [d]), str(d / "llama-server"))

    def test_variable_de_entorno_manda(self):
        f = Path(tempfile.mkdtemp()) / "mi-server"
        f.write_bytes(b"x")
        with mock.patch.dict(os.environ, {"STEMSHED_LLAMA_SERVER": str(f)}):
            self.assertEqual(osenv.find_llama_server(), str(f))


class LlamaCpp(unittest.TestCase):
    def setUp(self):
        D._job.clear()
        D._job.update(state="idle", percent=0, message="", step="")
        D._own.update(proc=None, port=None, model=None, cancelled=False)
        self.root = Path(tempfile.mkdtemp())
        self.model = self.root / "m.gguf"
        with open(self.model, "wb") as f:
            f.truncate(60 * 1024 * 1024)
        p = mock.patch.object(osenv, "gguf_roots", return_value=[self.root])
        p.start()
        self.addCleanup(p.stop)

    def test_sin_binario(self):
        with mock.patch.object(osenv, "find_llama_server", return_value=None):
            with self.assertRaisesRegex(D.DetectError, "llama-server"):
                D.start_llamacpp(str(self.model))

    def test_modelo_fuera_de_lo_detectado_se_rechaza(self):
        with mock.patch.object(osenv, "find_llama_server", return_value="/x/llama-server"):
            with self.assertRaisesRegex(D.DetectError, "no está entre"):
                D.start_llamacpp("/etc/passwd")

    def test_prende_en_loopback_y_queda_listo(self):
        proc = mock.Mock(returncode=None)
        proc.poll.return_value = None
        with mock.patch.object(osenv, "find_llama_server", return_value="/x/llama-server"), mock.patch.object(D, "_port_free", return_value=True), \
                mock.patch.object(D.subprocess, "Popen", return_value=proc) as popen, \
                mock.patch.object(D, "_get", return_value={"status": "ok"}):
            D.start_llamacpp(str(self.model))
            self.assertTrue(wait_for(lambda: D._job["state"] == "done"))
        cmd = popen.call_args[0][0]
        self.assertEqual(cmd[cmd.index("--host") + 1], "127.0.0.1")
        self.assertEqual(cmd[cmd.index("--port") + 1], "8081")
        self.assertEqual(cmd[cmd.index("-m") + 1], str(self.model))
        self.assertEqual(D.own_status()["model"], "m.gguf")

    def test_si_se_cierra_dice_por_que(self):
        proc = mock.Mock()
        proc.poll.return_value = 1
        proc.returncode = 1
        with mock.patch.object(osenv, "find_llama_server", return_value="/x/llama-server"), mock.patch.object(D, "_port_free", return_value=True), \
                mock.patch.object(D.subprocess, "Popen", return_value=proc), mock.patch.object(D, "_get", return_value=None):
            D.start_llamacpp(str(self.model))
            self.assertTrue(wait_for(lambda: D._job["state"] == "error"))
        self.assertIn("código 1", D._job["message"])

    def test_cancelar_mientras_carga(self):
        proc = mock.Mock()
        proc.poll.return_value = None
        with mock.patch.object(osenv, "find_llama_server", return_value="/x/llama-server"), mock.patch.object(D, "_port_free", return_value=True), \
                mock.patch.object(D.subprocess, "Popen", return_value=proc), mock.patch.object(D, "_get", return_value={"status": "loading model"}), \
                mock.patch.object(osenv, "kill_tree") as kt:
            D.start_llamacpp(str(self.model))
            D.stop_llamacpp()
            self.assertTrue(wait_for(lambda: D._job["state"] == "cancelled"))
        kt.assert_called()

    def test_sin_puertos_libres(self):
        with mock.patch.object(osenv, "find_llama_server", return_value="/x/llama-server"), mock.patch.object(D, "_port_free", return_value=False):
            with self.assertRaisesRegex(D.DetectError, "puerto"):
                D.start_llamacpp(str(self.model))


class Provider(unittest.TestCase):
    def tearDown(self):
        models.PROVIDER = "ollama"

    def test_chat_openai(self):
        models.PROVIDER = "llamacpp"
        seen = {}

        def fake(path, body=None, timeout=3):
            seen.update(path=path, body=body)
            return FakeJson({"choices": [{"message": {"content": "{\"a\":1}"}}], "usage": {"prompt_tokens": 7, "completion_tokens": 3}})

        with mock.patch.object(models, "_openai", fake):
            out = models.chat("m", "sys", "user", {"type": "object"}, 0.5, 100)
        self.assertEqual(out, ('{"a":1}', 7, 3))
        self.assertEqual(seen["path"], "/v1/chat/completions")
        self.assertEqual(seen["body"]["response_format"]["json_schema"]["schema"], {"type": "object"})

    def test_chat_ollama_mantiene_su_formato(self):
        seen = {}

        def fake(path, body=None, timeout=3):
            seen.update(path=path, body=body)
            return FakeJson({"message": {"content": "{}"}, "prompt_eval_count": 4, "eval_count": 2})

        with mock.patch.object(models, "_ollama", fake):
            self.assertEqual(models.chat("m", "s", "u", {"x": 1}, 0.7, 50), ("{}", 4, 2))
        self.assertEqual((seen["path"], seen["body"]["format"], seen["body"]["options"]["num_predict"]), ("/api/chat", {"x": 1}, 50))

    def test_lista_de_modelos_y_en_memoria(self):
        models.PROVIDER = "llamacpp"
        with mock.patch.object(models, "_openai", lambda *a, **k: FakeJson({"data": [{"id": "m.gguf"}]})):
            self.assertEqual(models.ollama_tags()[0]["name"], "m.gguf")
        self.assertEqual(models.loaded(), [])
        with mock.patch.object(models, "_openai", side_effect=OSError):
            self.assertIsNone(models.ollama_tags())

    def test_ajuste_validado(self):
        self.assertEqual(settings.validate({"llmProvider": "llamacpp"}), {"llmProvider": "llamacpp"})
        with self.assertRaises(settings.SettingsError):
            settings.validate({"llmProvider": "otro"})
        with self.assertRaises(settings.SettingsError):
            settings.validate({"llmUrl": "http://example.com:8080"})


class FakeJson(io.BytesIO):
    def __init__(self, data):
        super().__init__(json.dumps(data).encode())

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


class OrdenDeMotores(unittest.TestCase):
    def test_recomendado_primero_y_proximamente_al_final(self):
        gpus = [{"name": "AMD Radeon RX 6700S", "vendor": "amd", "accel": None, "integrated": False, "vramGB": 8.0}]
        for win in (True, False):
            with mock.patch.object(osenv, "WINDOWS", win):
                opts = backends.report(gpus)["options"]
            self.assertTrue(opts[0]["recommended"])
            groups = [o["group"] for o in opts]
            self.assertEqual(groups, sorted(groups, key=["available", "incompatible", "soon"].index))
            self.assertEqual(opts[-1]["group"], "soon")


if __name__ == "__main__":
    unittest.main()
