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


def tzinfo(name):
    """Huso IANA por nombre, o None si no se puede cargar (Windows no trae la base de husos: hace falta el paquete tzdata). Quien llama cae a la hora local."""
    if not name:
        return None
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        return None


def find_ollama():
    """Ejecutable de Ollama: el del PATH o, en Windows, el del instalador oficial (un proceso que ya estaba abierto no ve el PATH nuevo)."""
    import shutil
    found = shutil.which("ollama")
    if found or not WINDOWS:
        return found
    for base in (os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramFiles")):
        if base:
            cand = Path(base) / ("Programs" if base == os.environ.get("LOCALAPPDATA") else "") / "Ollama" / "ollama.exe"
            if cand.is_file():
                return str(cand)
    return None


def home():
    return Path(os.environ.get("USERPROFILE") or Path.home()) if WINDOWS else Path.home()


def find_executable(name, extra_dirs=()):
    """`name` en el PATH o en `extra_dirs` (con .exe en Windows). Solo mira; no ejecuta nada. None si no está."""
    import shutil
    found = shutil.which(name)
    if found:
        return found
    exe = name + (".exe" if WINDOWS else "")
    for d in extra_dirs:
        cand = Path(d) / exe
        if cand.is_file():
            return str(cand)
    return None


def llama_server_dirs():
    """Carpetas donde suele quedar llama-server (llama.cpp) fuera del PATH."""
    h = home()
    if WINDOWS:
        import glob
        local = os.environ.get("LOCALAPPDATA")
        dirs = [h / "llama.cpp", h / "llama.cpp" / "build" / "bin" / "Release", h / "llama.cpp" / "build" / "bin"]
        if local:
            dirs += [Path(local) / "Programs" / "llama.cpp", Path(local) / "Microsoft" / "WinGet" / "Links"]
            dirs += [Path(p) for p in sorted(glob.glob(os.path.join(local, "Microsoft", "WinGet", "Packages", "*LlamaCpp*")))]
        return dirs
    return [h / ".local" / "bin", Path("/usr/local/bin"), Path("/opt/llama.cpp/bin"), h / "llama.cpp" / "build" / "bin"]


def find_llama_server():
    """llama-server: STEMSHED_LLAMA_SERVER, el PATH o las carpetas habituales de cada sistema."""
    forced = os.environ.get("STEMSHED_LLAMA_SERVER")
    if forced and Path(forced).is_file():
        return forced
    return find_executable("llama-server", llama_server_dirs())


def gguf_roots():
    """Carpetas donde otros programas dejan modelos .gguf (llama.cpp, LM Studio, Hugging Face). Solo se leen."""
    h = home()
    roots = []
    if os.environ.get("LLAMA_CACHE"):
        roots.append(Path(os.environ["LLAMA_CACHE"]))
    if WINDOWS and os.environ.get("LOCALAPPDATA"):
        roots.append(Path(os.environ["LOCALAPPDATA"]) / "llama.cpp")
    else:
        roots.append(Path(os.environ.get("XDG_CACHE_HOME") or h / ".cache") / "llama.cpp")
    roots += [h / ".lmstudio" / "models", h / ".cache" / "lm-studio" / "models",
              Path(os.environ.get("HF_HOME") or h / ".cache" / "huggingface") / "hub"]
    return roots


def ollama_model_roots():
    """Carpetas de modelos de un Ollama ya instalado (la de OLLAMA_MODELS, la del usuario y, en Linux, la del servicio)."""
    roots = []
    if os.environ.get("OLLAMA_MODELS"):
        roots.append(Path(os.environ["OLLAMA_MODELS"]))
    roots.append(home() / ".ollama" / "models")
    if not WINDOWS:
        roots.append(Path("/usr/share/ollama/.ollama/models"))
    return roots


def find_ffmpeg():
    """Carpeta de ffmpeg: la del PATH o, en Windows, donde lo deja winget (un proceso ya abierto no ve el PATH nuevo)."""
    import glob
    import shutil
    found = shutil.which("ffmpeg")
    if found or not WINDOWS:
        return str(Path(found).parent) if found else None
    local = os.environ.get("LOCALAPPDATA")
    if local:
        for pattern in (os.path.join(local, "Microsoft", "WinGet", "Links", "ffmpeg.exe"),
                        os.path.join(local, "Microsoft", "WinGet", "Packages", "*FFmpeg*", "**", "bin", "ffmpeg.exe")):
            for hit in sorted(glob.glob(pattern, recursive=True)):
                return str(Path(hit).parent)
    return None


def ensure_ffmpeg_on_path():
    """audio-separator lo necesita (incluso para bajar el modelo). Lo agrega al PATH de este proceso y de sus hijos. True si lo encontró."""
    folder = find_ffmpeg()
    if folder and folder.lower() not in os.environ.get("PATH", "").lower():
        os.environ["PATH"] = folder + os.pathsep + os.environ.get("PATH", "")
    return bool(folder)


def use_bundled_ca():
    """Windows: que urllib (y los procesos hijos) también confíen en los certificados de `certifi`. Python en Windows lee solo el almacén
    del sistema, y en una PC recién instalada todavía no tiene las autoridades raíz de la CDN de TIDAL: el audio falla con
    URLError (CERTIFICATE_VERIFY_FAILED) aunque el inicio de sesión (requests, que trae certifi) ande. Devuelve True si lo aplicó."""
    if not WINDOWS or os.environ.get("SSL_CERT_FILE"):
        return False
    try:
        import certifi
        bundle = certifi.where()
    except Exception:
        return False
    if not os.path.isfile(bundle):
        return False
    os.environ["SSL_CERT_FILE"] = bundle  # OpenSSL lo suma al almacén del sistema: ssl.create_default_context() lo lee
    return True


def find_uv():
    """`uv` (Astral): el empaquetado en runtime/tools junto al motor, STEMSHED_UV, o el del PATH solo en Windows. None si no hay:
    entonces el entorno se crea con venv y pip, como siempre (Linux y Docker no cambian)."""
    import shutil
    name = "uv.exe" if WINDOWS else "uv"
    for cand in (os.environ.get("STEMSHED_UV"), str(Path(__file__).resolve().parent.parent / "tools" / name)):
        if cand and Path(cand).is_file():
            return cand
    return shutil.which("uv") if WINDOWS else None


def kill_tree(proc):
    """Termina un proceso hijo y todo lo que lanzó (el separador, uv, pip). Windows: taskkill /T; el resto: terminate y kill."""
    if proc is None or proc.poll() is not None:
        return
    if WINDOWS:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()


VENDORS = {0x10DE: "nvidia", 0x1002: "amd", 0x1022: "amd", 0x8086: "intel"}


def _dxgi_adapters():
    """Lista las placas con DXGI (ctypes, sin dependencias). Da la VRAM real de 64 bits, que WMI trunca a 4 GB."""
    import ctypes
    from ctypes import c_int32, c_size_t, c_uint, c_uint16, c_uint32, c_ubyte, c_void_p, c_wchar

    class GUID(ctypes.Structure):
        _fields_ = [("a", c_uint32), ("b", c_uint16), ("c", c_uint16), ("d", c_ubyte * 8)]

    class Desc(ctypes.Structure):
        _fields_ = [("Description", c_wchar * 128), ("VendorId", c_uint), ("DeviceId", c_uint), ("SubSysId", c_uint),
                    ("Revision", c_uint), ("Dedicated", c_size_t), ("DedicatedSys", c_size_t), ("Shared", c_size_t),
                    ("LuidLow", c_uint32), ("LuidHigh", c_int32), ("Flags", c_uint)]

    def method(obj, index, *argtypes):  # llamada a un método COM por su posición en la tabla virtual
        vtbl = ctypes.cast(c_void_p(obj), ctypes.POINTER(c_void_p))[0]
        return ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, *argtypes)(ctypes.cast(vtbl, ctypes.POINTER(c_void_p))[index])

    iid = GUID(0x770AAE78, 0xF26F, 0x4DBA, (c_ubyte * 8)(0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87))  # IDXGIFactory1
    dxgi = ctypes.WinDLL("dxgi")
    dxgi.CreateDXGIFactory1.argtypes = [ctypes.POINTER(GUID), ctypes.POINTER(c_void_p)]
    dxgi.CreateDXGIFactory1.restype = ctypes.c_long
    factory = c_void_p()
    if dxgi.CreateDXGIFactory1(ctypes.byref(iid), ctypes.byref(factory)) != 0:
        return []
    out = []
    try:
        for i in range(16):
            adapter = c_void_p()
            if method(factory.value, 12, c_uint, ctypes.POINTER(c_void_p))(factory.value, i, ctypes.byref(adapter)) != 0:  # EnumAdapters1; error al llegar al final
                break
            try:
                d = Desc()
                if method(adapter.value, 10, ctypes.POINTER(Desc))(adapter.value, ctypes.byref(d)) != 0:  # GetDesc1
                    continue
                if d.Flags & 2:  # DXGI_ADAPTER_FLAG_SOFTWARE (Microsoft Basic Render Driver)
                    continue
                out.append({"name": d.Description.strip(), "vendor": VENDORS.get(d.VendorId, "other"), "vramBytes": int(d.Dedicated),
                            "integrated": d.Dedicated < 1024**3,  # una integrada reserva a lo sumo unos cientos de MB propios
                            "luid": f"0x{d.LuidHigh & 0xFFFFFFFF:08X}_0x{d.LuidLow:08X}"})
            finally:
                method(adapter.value, 2)(adapter.value)  # Release
    finally:
        method(factory.value, 2)(factory.value)
    return out


def gpu_adapters():
    """Placas de video del equipo (NVIDIA, AMD, Intel) en Windows: [{name, vendor, vramBytes, integrated, luid}]. [] en otros sistemas o si falla."""
    if not WINDOWS:
        return []
    try:
        return _dxgi_adapters()
    except Exception:
        return []


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


# ------------------------------------------------------------------------------------------ Windows: DPAPI y Job Object
# SIN VERIFICAR EN WINDOWS: escrito contra la documentación de la API (CryptProtectData, JobObjects).

_DPAPI_MAGIC = b"STEMSHED-DPAPI1\n"


def _blob(data):
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
    buf = ctypes.create_string_buffer(data, len(data))
    return Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _dpapi(data, protect):
    import ctypes
    inb, _keep = _blob(data)
    out = type(inb)()
    fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    if not fn(ctypes.byref(inb), None, None, None, None, 0, ctypes.byref(out)):
        raise OSError("DPAPI falló")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def protect_file(path):
    """Cifra el archivo con DPAPI (solo lo abre el mismo usuario de Windows). En otros sistemas no hace nada."""
    if not WINDOWS:
        return
    p = Path(path)
    raw = p.read_bytes()
    if raw.startswith(_DPAPI_MAGIC):
        return
    p.write_bytes(_DPAPI_MAGIC + _dpapi(raw, True))


def read_protected(path):
    """Contenido del archivo; si está cifrado con DPAPI lo descifra. Un archivo en claro se lee tal cual."""
    raw = Path(path).read_bytes()
    if raw.startswith(_DPAPI_MAGIC):
        if not WINDOWS:
            raise OSError("Archivo cifrado con DPAPI: solo se abre en Windows.")
        return _dpapi(raw[len(_DPAPI_MAGIC):], False)
    return raw


_job = None


def kill_children_on_exit():
    """Windows: mete al motor en un Job Object que mata a todos sus procesos hijos cuando el motor termina
    (también si lo matan de golpe), así no quedan separadores ni Ollama huérfanos. Devuelve True si quedó activo."""
    global _job
    if not WINDOWS or _job:
        return bool(_job)
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.windll.kernel32

    class Basic(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

    class IoCounters(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in ("a", "b", "c", "d", "e", "f")]

    class Extended(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", IoCounters), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]
    # Sin argtypes ctypes pasa los HANDLE como int de 32 bits y se desborda (GetCurrentProcess devuelve el pseudo-handle -1).
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    job = k32.CreateJobObjectW(None, None)
    if not job:
        return False
    info = Extended()
    info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):  # 9 = ExtendedLimitInformation
        return False
    if not k32.AssignProcessToJobObject(job, k32.GetCurrentProcess()):
        return False
    _job = job  # el handle vive mientras viva el proceso
    return True
