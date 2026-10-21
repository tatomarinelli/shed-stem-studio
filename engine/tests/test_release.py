"""Instalación del entorno con uv, cancelación de trabajos y ffmpeg: todo con procesos simulados, nada se descarga."""
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["STEMSHED_NO_SCHEDULER"] = "1"
import backends  # noqa: E402
import envsetup  # noqa: E402
import llmserver  # noqa: E402
import osenv  # noqa: E402
import stems  # noqa: E402

NV_FREE = [{"name": "x", "vendor": "intel", "accel": None, "llmAccel": None, "integrated": True, "vramGB": 0.1}]


def wait(cond, secs=5):
    end = time.time() + secs
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


class FindUv(unittest.TestCase):
    def test_empaquetado_junto_al_motor_y_variable(self):
        with tempfile.TemporaryDirectory() as d:
            exe = Path(d, "uv.exe" if osenv.WINDOWS else "uv")
            exe.write_bytes(b"x")
            with mock.patch.dict(os.environ, {"STEMSHED_UV": str(exe)}):
                self.assertEqual(osenv.find_uv(), str(exe))

    def test_sin_uv_en_linux_queda_el_camino_de_pip(self):
        with mock.patch.object(osenv, "WINDOWS", False), mock.patch.dict(os.environ, {"STEMSHED_UV": ""}), mock.patch("shutil.which", return_value="/usr/bin/uv"):
            real = Path(osenv.__file__).resolve().parent.parent / "tools" / "uv"
            if not real.is_file():
                self.assertIsNone(osenv.find_uv())  # el uv del PATH no se usa fuera de Windows: Linux y Docker no cambian


class KillTree(unittest.TestCase):
    def test_windows_usa_taskkill_con_arbol(self):
        proc = mock.Mock(pid=4321)
        proc.poll.return_value = None
        with mock.patch.object(osenv, "WINDOWS", True), mock.patch("subprocess.run") as run:
            osenv.kill_tree(proc)
            args = run.call_args[0][0]
            self.assertEqual(args[:2], ["taskkill", "/PID"])
            self.assertIn("/T", args)
            self.assertIn("/F", args)

    def test_en_otros_sistemas_termina_y_ya_terminado_no_hace_nada(self):
        proc = mock.Mock()
        proc.poll.return_value = None
        with mock.patch.object(osenv, "WINDOWS", False):
            osenv.kill_tree(proc)
            proc.terminate.assert_called_once()
        done = mock.Mock()
        done.poll.return_value = 0
        osenv.kill_tree(done)
        done.terminate.assert_not_called()
        osenv.kill_tree(None)


class EnvSetup(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.env = Path(self._tmp.name) / "env"
        self.addCleanup(self._tmp.cleanup)
        for p in (mock.patch.object(envsetup.stems, "ENV", self.env), mock.patch.object(envsetup.stems, "ROOT", Path(self._tmp.name) / "root"),
                  mock.patch.object(envsetup.hardware, "_gpus", return_value=NV_FREE)):
            p.start()
            self.addCleanup(p.stop)
        envsetup._job.update(state="idle", percent=0, message="", step="")
        envsetup._holder.clear()

    def fake_present(self):
        for b in ("python", "audio-separator"):
            exe = osenv.env_bin(self.env, b)
            exe.parent.mkdir(parents=True, exist_ok=True)
            exe.write_bytes(b"x")

    def test_con_uv_crea_el_entorno_con_su_propio_python_y_todo_dentro_de_la_carpeta(self):
        calls = []

        def fake_run(cmd, env):
            calls.append((cmd, env))
            if "pip" in cmd:
                self.fake_present()
            return 0, []
        (self.env / "uv-cache").mkdir(parents=True)
        with mock.patch.object(osenv, "find_uv", return_value="UV"), mock.patch.object(envsetup, "_run", side_effect=fake_run):
            envsetup.start("cpu")
            self.assertTrue(wait(lambda: envsetup._job["state"] in ("done", "error")))
        self.assertEqual(envsetup._job["state"], "done", envsetup._job["message"])
        venv_cmd, pip_cmd = calls[0][0], calls[1][0]
        self.assertEqual(venv_cmd[:2], ["UV", "venv"])
        self.assertIn("only-managed", venv_cmd)
        self.assertEqual(venv_cmd[venv_cmd.index("--python") + 1], envsetup.PY_VERSION)
        self.assertEqual(pip_cmd[:3], ["UV", "pip", "install"])
        self.assertIn("--no-deps", pip_cmd)
        self.assertIn("unsafe-best-match", pip_cmd)
        self.assertTrue(pip_cmd[-1].endswith("requirements-env.win-cpu.txt") or pip_cmd[-1].endswith("requirements-env.txt"))
        for key in ("UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR"):
            self.assertTrue(calls[0][1][key].startswith(str(self.env)), key)  # nada fuera de la carpeta elegida
        self.assertFalse((self.env / "uv-cache").exists())  # la caché se limpia al terminar
        self.assertEqual(envsetup.installed_backend(), "cpu")

    def test_sin_uv_usa_venv_y_pip(self):
        with mock.patch.object(osenv, "find_uv", return_value=None), mock.patch.object(envsetup, "_install_pip", side_effect=lambda e, r: self.fake_present()) as pip, \
                mock.patch.object(envsetup, "_install_uv") as uv:
            envsetup.start("cpu")
            self.assertTrue(wait(lambda: envsetup._job["state"] in ("done", "error")))
        pip.assert_called_once()
        uv.assert_not_called()
        self.assertEqual(envsetup._job["state"], "done")

    def test_cancelar_corta_el_proceso_borra_lo_parcial_y_no_es_un_error(self):
        started = threading.Event()

        def fake_install(uv, env, req, backend):
            (env / "venv").mkdir(parents=True)
            (env / "venv" / "parcial.txt").write_text("x")
            (env / "uv-cache").mkdir()
            started.set()
            envsetup._holder["proc"] = mock.Mock()
            wait(lambda: envsetup._holder.get("cancelled"))
            raise envsetup.Cancelled()
        with mock.patch.object(osenv, "find_uv", return_value="UV"), mock.patch.object(envsetup, "_install_uv", side_effect=fake_install), \
                mock.patch.object(osenv, "kill_tree") as kill:
            envsetup.start("cpu")
            self.assertTrue(started.wait(5))
            self.assertEqual(envsetup.cancel(), {"state": "cancelling"})
            self.assertTrue(wait(lambda: envsetup._job["state"] != "running"))
            kill.assert_called_once()
        self.assertEqual(envsetup._job["state"], "cancelled")
        self.assertFalse((self.env / "venv").exists() or (self.env / "uv-cache").exists())
        self.assertIsNone(envsetup.installed_backend())

    def test_cancelar_sin_instalacion_en_curso(self):
        with self.assertRaises(envsetup.EnvError):
            envsetup.cancel()


class Separation(unittest.TestCase):
    def setUp(self):
        stems._jobs.clear()
        stems._holders.clear()
        self.addCleanup(stems._jobs.clear)
        self.addCleanup(stems._holders.clear)

    def test_cancelar_marca_corta_el_proceso_y_el_listado_no_lo_muestra(self):
        stems._jobs["123"] = {"state": "running", "stage": "separate", "percent": 10, "message": ""}
        proc = mock.Mock()
        stems._holders["123"] = {"proc": proc}
        with mock.patch.object(osenv, "kill_tree") as kill:
            self.assertEqual(stems.cancel("123"), {"state": "cancelling"})
            kill.assert_called_once_with(proc)
        self.assertTrue(stems._holders["123"]["cancelled"])
        stems._jobs["123"].update(state="cancelled", finishedAt=time.time())
        self.assertEqual(stems.jobs_report(), [])

    def test_cancelar_algo_que_no_corre_o_un_id_invalido(self):
        with self.assertRaises(stems.StemsError):
            stems.cancel("999")
        with self.assertRaises(ValueError):
            stems.cancel("../x")

    def test_la_cancelacion_durante_la_descarga_impide_lanzar_el_separador(self):
        stems._jobs["7"] = {"state": "running", "stage": "download", "percent": 0, "message": ""}
        holder = stems._holders["7"] = {"cancelled": True}
        # el progreso de "separate" levanta Cancelled en lugar de dejar que arranque el separador
        with mock.patch.object(stems, "run_separator") as run:
            def progress(stage, percent):
                if holder.get("cancelled") and stage != "download":
                    raise stems.Cancelled()
            with self.assertRaises(stems.Cancelled):
                progress("separate", 0)
            run.assert_not_called()

    def test_sin_ffmpeg_el_error_es_claro(self):
        with mock.patch.object(osenv, "ensure_ffmpeg_on_path", return_value=False):
            with self.assertRaises(stems.StemsError) as cm:
                stems.require_ffmpeg()
            self.assertIn("ffmpeg", str(cm.exception))
        with mock.patch.object(osenv, "ensure_ffmpeg_on_path", return_value=True):
            stems.require_ffmpeg()


class Ffmpeg(unittest.TestCase):
    def test_estado_e_instalacion_solo_si_falta(self):
        with mock.patch.object(osenv, "find_ffmpeg", return_value="C:/ff"), mock.patch.object(llmserver, "can_install", return_value=True):
            self.assertTrue(llmserver.ffmpeg_status()["installed"])
            with mock.patch("subprocess.Popen") as popen:
                with self.assertRaises(llmserver.LlmServerError):
                    llmserver.ffmpeg_install_start()
                popen.assert_not_called()
        with mock.patch.object(osenv, "find_ffmpeg", return_value=None), mock.patch.object(llmserver, "can_install", return_value=False):
            self.assertFalse(llmserver.ffmpeg_status()["installed"])
            with self.assertRaises(llmserver.LlmServerError):
                llmserver.ffmpeg_install_start()


class Certificados(unittest.TestCase):
    """PC recién instalada: Python en Windows solo ve el almacén del sistema, que puede no tener las raíces de la CDN de TIDAL."""

    def test_en_windows_apunta_openssl_a_certifi_y_no_pisa_lo_que_ya_hay(self):
        with tempfile.TemporaryDirectory() as d:
            bundle = Path(d, "cacert.pem")
            bundle.write_text("x")
            fake = mock.Mock()
            fake.where.return_value = str(bundle)
            env = {k: v for k, v in os.environ.items() if k != "SSL_CERT_FILE"}
            with mock.patch.object(osenv, "WINDOWS", True), mock.patch.dict(sys.modules, {"certifi": fake}), mock.patch.dict(os.environ, env, clear=True):
                self.assertTrue(osenv.use_bundled_ca())
                self.assertEqual(os.environ["SSL_CERT_FILE"], str(bundle))
                self.assertFalse(osenv.use_bundled_ca())  # ya estaba puesto: no lo pisa

    def test_fuera_de_windows_no_cambia_nada(self):
        env = {k: v for k, v in os.environ.items() if k != "SSL_CERT_FILE"}
        with mock.patch.object(osenv, "WINDOWS", False), mock.patch.dict(os.environ, env, clear=True):
            self.assertFalse(osenv.use_bundled_ca())
            self.assertNotIn("SSL_CERT_FILE", os.environ)

    def test_sin_certifi_no_falla(self):
        env = {k: v for k, v in os.environ.items() if k != "SSL_CERT_FILE"}
        with mock.patch.object(osenv, "WINDOWS", True), mock.patch.dict(sys.modules, {"certifi": None}), mock.patch.dict(os.environ, env, clear=True):
            self.assertFalse(osenv.use_bundled_ca())

    def test_ssl_carga_de_verdad_los_certificados_del_paquete(self):
        try:
            import certifi
        except ImportError:
            self.skipTest("certifi no está instalado en este Python")
        import ssl
        env = {k: v for k, v in os.environ.items() if k != "SSL_CERT_FILE"}
        with mock.patch.dict(os.environ, env, clear=True):
            sin = ssl.create_default_context().cert_store_stats()["x509_ca"]
        with mock.patch.dict(os.environ, {**env, "SSL_CERT_FILE": certifi.where()}, clear=True):
            con = ssl.create_default_context().cert_store_stats()["x509_ca"]
        self.assertGreaterEqual(con, sin)
        self.assertGreater(con, 50)  # el paquete trae ~140 raíces


class MensajeDeError(unittest.TestCase):
    def test_un_urlerror_dice_la_causa(self):
        import ssl
        import urllib.error
        import server
        cert = urllib.error.URLError(ssl.SSLCertVerificationError("unable to get local issuer certificate"))
        self.assertIn("certificado", server.error_detail(cert))
        self.assertIn("URLError", server.error_detail(cert))
        refused = urllib.error.URLError(ConnectionRefusedError("no hay nadie"))
        self.assertIn("ConnectionRefusedError", server.error_detail(refused))
        self.assertEqual(server.error_detail(ValueError("x")), "ValueError")
        self.assertEqual(server.error_detail(urllib.error.URLError("texto suelto")), "URLError")


if __name__ == "__main__":
    unittest.main()
