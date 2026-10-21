"""Diferencias entre sistemas operativos en un solo lugar: rutas del entorno, carpeta de configuración, permisos y subprocesos."""
import os
import subprocess
import sys
from pathlib import Path

WINDOWS = sys.platform == "win32"

_WIN_FORBIDDEN = ("C:\\Windows", "C:\\Program Files", "C:\\Program Files (x86)", "C:\\ProgramData")
_UNIX_FORBIDDEN = ("/etc", "/usr", "/bin", "/sbin", "/lib", "/lib64", "/boot", "/proc", "/sys", "/dev", "/root", "/var/lib")
FORBIDDEN = _WIN_FORBIDDEN if WINDOWS else _UNIX_FORBIDDEN


def config_dir():
    """XDG_CONFIG_HOME manda (pruebas y Linux); si no, %APPDATA% en Windows y ~/.config en el resto."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "stemshed"
    if WINDOWS:
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "ShedStemStudio"
    return Path.home() / ".config" / "stemshed"


def default_root(name):
    """Carpeta de datos por defecto: en Windows bajo %LOCALAPPDATA%; en Linux, la ruta de la máquina de desarrollo."""
    if WINDOWS:
        return str(Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "ShedStemStudio" / name)
    return "/mnt/plexdata/" + name


def env_bin(env_dir, name):
    """Ejecutable dentro del venv de separación: venv/bin/<name> o venv\\Scripts\\<name>.exe."""
    base = Path(env_dir) / "venv"
    return base / "Scripts" / (name + ".exe") if WINDOWS else base / "bin" / name


def env_rel(name):
    """Ruta del ejecutable relativa al directorio del entorno, para los mensajes."""
    return ("venv\\Scripts\\" + name + ".exe") if WINDOWS else "venv/bin/" + name


def is_forbidden(path, forbidden=None):
    """¿Es una carpeta del sistema (o está dentro de una)? En Windows no distingue mayúsculas."""
    p = str(path)
    for f in forbidden or FORBIDDEN:
        a, b = (p.lower(), f.lower()) if WINDOWS else (p, f)
        b = b.rstrip("\\/")
        if a == b or (a.startswith(b) and a[len(b)] in "\\/"):
            return True
    return False


def is_absolute(value):
    return Path(value).is_absolute() or (WINDOWS and len(value) > 2 and value[1] == ":" and value[2] in "\\/")


def secure(path, mode):
    """chmod que en Windows no hace nada (los permisos Unix no existen); los datos quedan en la carpeta del usuario."""
    if WINDOWS:
        return
    os.chmod(path, mode)


def sys_flags(low_priority=False):
    """Argumentos de Popen: sin consola en Windows y, si se pide, prioridad baja."""
    if not WINDOWS:
        return {}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if low_priority:
        flags |= getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
    return {"creationflags": flags}


def norm_key(path):
    """Ruta normalizada para calcular ids: en Windows, sin mayúsculas y con '/'."""
    if not WINDOWS:
        return str(path)
    return os.path.normpath(str(path)).replace("\\", "/").lower()


def tmp_env(path):
    """Variables de carpeta temporal: TMPDIR en Unix; TEMP y TMP en Windows."""
    p = str(path)
    return {"TMPDIR": p, "TEMP": p, "TMP": p}


def ram_bytes():
    """(total, disponible) en bytes en Windows, con ctypes; None si no se pudo."""
    import ctypes

    class MemStatus(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong), ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
    m = MemStatus()
    m.dwLength = ctypes.sizeof(MemStatus)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
        return None
    return m.ullTotalPhys, m.ullAvailPhys


def cpu_name():
    """Nombre del procesador en Windows (registro); vacío si no se pudo."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
            return winreg.QueryValueEx(k, "ProcessorNameString")[0].strip()
    except (ImportError, OSError):
        return ""
