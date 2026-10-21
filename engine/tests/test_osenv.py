"""Diferencias de plataforma (osenv): se simulan Windows y Linux cambiando WINDOWS; nada de esto toca el sistema real."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import osenv  # noqa: E402
import settings  # noqa: E402


class OsenvTest(unittest.TestCase):
    def test_env_bin_linux_y_windows(self):
        with mock.patch.object(osenv, "WINDOWS", False):
            self.assertEqual(osenv.env_bin("/e", "python"), Path("/e/venv/bin/python"))
        with mock.patch.object(osenv, "WINDOWS", True):
            self.assertEqual(osenv.env_bin("/e", "pip").parts[-3:], ("venv", "Scripts", "pip.exe"))
            self.assertEqual(osenv.env_rel("python"), "venv\\Scripts\\python.exe")

    def test_config_dir(self):
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/x"}):
            self.assertEqual(osenv.config_dir(), Path("/x/stemshed"))
        env = {k: v for k, v in os.environ.items() if k != "XDG_CONFIG_HOME"}
        with mock.patch.dict(os.environ, {**env, "APPDATA": "/ap"}, clear=True), mock.patch.object(osenv, "WINDOWS", True):
            self.assertEqual(osenv.config_dir(), Path("/ap/ShedStemStudio"))

    def test_carpetas_prohibidas_en_windows_sin_mayusculas(self):
        with mock.patch.object(osenv, "WINDOWS", True):
            self.assertTrue(osenv.is_forbidden("c:\\windows\\system32", osenv._WIN_FORBIDDEN))
            self.assertTrue(osenv.is_forbidden("C:\\Program Files\\x", osenv._WIN_FORBIDDEN))
            self.assertFalse(osenv.is_forbidden("C:\\Windows10", osenv._WIN_FORBIDDEN))
            self.assertFalse(osenv.is_forbidden("D:\\Música", osenv._WIN_FORBIDDEN))

    def test_ruta_absoluta_de_windows(self):
        with mock.patch.object(osenv, "WINDOWS", True):
            self.assertTrue(osenv.is_absolute("D:\\Música"))
            self.assertTrue(osenv.is_absolute("D:/Música"))
            self.assertFalse(osenv.is_absolute("Música"))

    def test_secure_no_toca_nada_en_windows(self):
        with mock.patch.object(osenv, "WINDOWS", True), mock.patch("os.chmod") as chmod:
            osenv.secure("/x", 0o600)
            chmod.assert_not_called()
        with mock.patch.object(osenv, "WINDOWS", False), mock.patch("os.chmod") as chmod:
            osenv.secure("/x", 0o600)
            chmod.assert_called_once_with("/x", 0o600)

    def test_flags_de_subproceso(self):
        with mock.patch.object(osenv, "WINDOWS", False):
            self.assertEqual(osenv.sys_flags(True), {})
        with mock.patch.object(osenv, "WINDOWS", True), mock.patch("subprocess.CREATE_NO_WINDOW", 0x08000000, create=True), \
                mock.patch("subprocess.BELOW_NORMAL_PRIORITY_CLASS", 0x4000, create=True):
            self.assertEqual(osenv.sys_flags()["creationflags"], 0x08000000)
            self.assertEqual(osenv.sys_flags(True)["creationflags"], 0x08004000)

    def test_id_de_archivo_igual_con_otra_escritura_en_windows(self):
        import library
        with mock.patch.object(osenv, "WINDOWS", True):
            self.assertEqual(library.file_id("D:\\Música\\A.flac"), library.file_id("d:/música/a.flac"))
        with mock.patch.object(osenv, "WINDOWS", False):
            self.assertNotEqual(library.file_id("/m/A.flac"), library.file_id("/m/a.flac"))

    def test_tmp_env(self):
        self.assertEqual(set(osenv.tmp_env("/t")), {"TMPDIR", "TEMP", "TMP"})

    def test_selector_de_carpetas_lista_unidades_en_windows(self):
        with mock.patch.object(osenv, "WINDOWS", True), mock.patch("os.path.exists", side_effect=lambda r: r in ("C:\\", "D:\\")), \
                mock.patch("shutil.disk_usage", return_value=mock.Mock(free=5e9)):
            out = settings.list_dirs("/")
        self.assertEqual(out["dirs"], ["C:\\", "D:\\"])
        self.assertTrue(out["drives"])

    def test_no_se_acepta_carpeta_del_sistema_en_ajustes(self):
        with mock.patch.object(settings, "FORBIDDEN", osenv._WIN_FORBIDDEN), mock.patch.object(osenv, "WINDOWS", True):
            with self.assertRaises(settings.SettingsError):
                settings._abs_dir("C:\\Windows\\Temp", "Datos")


if __name__ == "__main__":
    unittest.main()
