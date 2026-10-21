"""Ayuda para las pruebas de permisos: los modos Unix no existen en Windows, donde la privacidad la da la carpeta del usuario (y DPAPI para TIDAL)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import osenv  # noqa: E402


def assert_private(test, path):
    if osenv.WINDOWS:
        test.assertTrue(os.path.exists(path))
        return
    test.assertEqual(oct(os.stat(path).st_mode & 0o777), "0o600")
