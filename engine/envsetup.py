"""Entorno de separación y análisis (torch, audio-separator, librosa): se instala desde Ajustes, a la carpeta elegida.

Nunca se instala solo. `start()` la dispara un clic explícito y `cancel()` la corta y limpia lo parcial.
Con `uv` (empaquetado en runtime/tools, o en el PATH en Windows) crea <ENV>/venv con un Python 3.13 propio: no hace falta Python
en el equipo, y el Python, la caché y el entorno quedan dentro de <ENV>. Sin `uv` (Linux, Docker) usa el Python del motor con venv y pip.
Instala el archivo de requisitos del motor elegido (backends.py): de 1 a varios GB, la interfaz avisa antes.
"""
import os
import osenv
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import backends
import hardware
import jobs
import stems

REQ = Path(__file__).with_name("requirements-env.txt")  # por defecto; start() elige el del motor (backends.py)
MARKER = "backend.txt"  # junto al venv: qué motor se instaló
PY_VERSION = "3.13"  # el que fija la guía de Windows (3.14 es el de más riesgo de dependencias sin rueda)
_job = {"state": "idle", "percent": 0, "message": "", "step": "", "done": 0, "total": 0, "rate": 0}
_lock = threading.Lock()
_holder = {}  # proceso de la instalación y si se canceló
PKG = re.compile(r"^(Collecting|Downloading|Installing collected packages)")
SIZE = re.compile(r"^\s*Downloading (\S+)\s+\((\d+(?:\.\d+)?) ([kMG])B\)")  # pip sangra la línea dentro de un "Collecting"
RAW = re.compile(r"^Progress (\d+) of (\d+)")
UNITS = {"k": 1e3, "M": 1e6, "G": 1e9}
APPROX_TOTAL = 4.6e9   # descarga total aproximada de requirements-env.txt (se muestra como estimación)


class EnvError(Exception):
    pass


class Cancelled(Exception):
    pass


def present():
    return osenv.env_bin(stems.ENV, "audio-separator").exists() and osenv.env_bin(stems.ENV, "python").exists()


def installed_backend():
    try:
        return (stems.ENV / MARKER).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def status():
    return {**_job, "present": present(), "path": str(stems.ENV / "venv"), "approxGb": 8, "backend": installed_backend() if present() else None}


def _count_requirements(req=None):
    return max(1, sum(1 for ln in (req or REQ).read_text().splitlines() if ln.strip() and not ln.startswith(("#", "--"))))


def _dir_bytes(path):
    total = 0
    for root, _, files in os.walk(path, onerror=lambda e: None):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                pass
    return total


def _run(cmd, env):
    """Corre un comando guardando el proceso (para cancelar). Devuelve (código, últimas líneas)."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", env=env, **osenv.sys_flags())
    _holder["proc"] = proc
    tail = []
    for line in proc.stdout:
        line = line.rstrip()
        if line.strip():
            tail = (tail + [line])[-8:]
    proc.wait()
    if _holder.get("cancelled"):
        raise Cancelled()
    return proc.returncode, tail


def _install_uv(uv, env, req, backend):
    """Python propio + entorno + paquetes con uv. El avance se mide por lo que va ocupando en disco (uv no da un total)."""
    venv = env / "venv"
    cache, pydir = env / "uv-cache", env / "python"
    uv_env = {**os.environ, "UV_CACHE_DIR": str(cache), "UV_PYTHON_INSTALL_DIR": str(pydir), "UV_NO_PROGRESS": "1", "NO_COLOR": "1",
              "UV_PYTHON_PREFERENCE": "only-managed", **osenv.tmp_env(stems.ROOT / "tmp")}
    (stems.ROOT / "tmp").mkdir(parents=True, exist_ok=True)
    approx = int(((backends.by_id(backend) or {}).get("approxGb") or 4) * 1e9) + 6e7
    stop = threading.Event()

    def watch():
        last_t, last_b = time.time(), 0
        while not stop.wait(1.0):
            done = _dir_bytes(cache) + _dir_bytes(venv) + _dir_bytes(pydir)
            now = time.time()
            if now - last_t >= 2:
                _job["rate"] = max(0, int((done - last_b) / (now - last_t)))
                last_t, last_b = now, done
            jobs.update(_job, done=int(done), total=int(approx), approx=True, percent=min(97, int(100 * done / approx)))

    threading.Thread(target=watch, daemon=True).start()
    try:
        jobs.update(_job, step=f"Descargando Python {PY_VERSION}")
        code, tail = _run([uv, "venv", str(venv), "--python", PY_VERSION, "--python-preference", "only-managed", "--no-progress"], uv_env)
        if code != 0:
            raise EnvError("No se pudo crear el entorno: " + (tail[-1] if tail else "sin salida")[:200])
        jobs.update(_job, step="Descargando e instalando los paquetes")
        py = str(osenv.env_bin(env, "python"))
        code, tail = _run([uv, "pip", "install", "--python", py, "--no-deps", "--index-strategy", "unsafe-best-match", "--no-progress", "-r", str(req)], uv_env)
        if code != 0 or not present():
            raise EnvError("La instalación falló: " + " | ".join(x.strip() for x in tail[-3:])[:240])
    finally:
        stop.set()
    shutil.rmtree(cache, ignore_errors=True)  # la caché de descargas ya no hace falta: el entorno quedó instalado


def _install_pip(env, req):
    """Respaldo sin uv: el Python que corre el motor, venv y pip (Linux y Docker)."""
    code = subprocess.run([sys.executable, "-m", "venv", str(env / "venv")], capture_output=True, text=True, **osenv.sys_flags())
    if code.returncode != 0:
        raise EnvError("No se pudo crear el entorno: " + (code.stderr.strip().splitlines() or ["sin salida"])[-1][:200])
    pip = str(osenv.env_bin(env, "pip"))
    proc = subprocess.Popen([pip, "install", "--no-cache-dir", "--progress-bar", "raw", "--no-deps", "-r", str(req)],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            env={**os.environ, "PIP_DISABLE_PIP_VERSION_CHECK": "1", **osenv.tmp_env(stems.ROOT / "tmp")},
                            **osenv.sys_flags())
    _holder["proc"] = proc
    (stems.ROOT / "tmp").mkdir(parents=True, exist_ok=True)
    tail, finished, current, name, last_t, last_b = [], 0, 0, "", time.time(), 0
    for line in proc.stdout:
        line = line.rstrip()
        tail = (tail + [line])[-8:]
        m = SIZE.match(line)
        if m and not m.group(1).endswith(".metadata"):
            finished += current  # el archivo anterior terminó
            name, current = m.group(1), 0
            jobs.update(_job, step="Descargando " + name.rsplit("/", 1)[-1][:60])
            continue
        m = RAW.match(line)
        if m:
            current = int(m.group(1))
            done = finished + current
            now = time.time()
            if now - last_t >= 1:
                _job["rate"] = int((done - last_b) / (now - last_t))
                last_t, last_b = now, done
            jobs.update(_job, done=int(done), total=int(APPROX_TOTAL), approx=True, percent=min(97, int(100 * done / APPROX_TOTAL)))
        elif line.startswith("Installing collected packages"):
            jobs.update(_job, step="Instalando los paquetes", percent=98)
    proc.wait()
    if _holder.get("cancelled"):
        raise Cancelled()
    if proc.returncode != 0 or not present():
        raise EnvError("La instalación falló: " + " | ".join(x.strip() for x in tail[-3:] if x.strip())[:240])


def start(backend=None):
    """`backend`: id de backends.CATALOG; sin él, el recomendado para este equipo. Solo se instala lo que existe de verdad."""
    gpus = hardware._gpus()
    backend = backend or backends.recommended_id(gpus)
    req = backends.requirements_for(backend)
    if req is None or not req.is_file():
        raise EnvError("Ese motor de separación todavía no se puede instalar.")
    if not backends.compatible(backend, gpus):
        raise EnvError("Tu equipo no es compatible con ese motor.")
    with _lock:
        if _job["state"] == "running":
            raise EnvError("Ya se está instalando.")
        if present():
            raise EnvError("El entorno ya está instalado.")
        jobs.start(_job, state="running", percent=0, message="", step="Creando el entorno", done=0, total=0, rate=0, approx=False)
        _holder.clear()

    def work():
        env = stems.ENV
        try:
            env.mkdir(parents=True, exist_ok=True)
            uv = osenv.find_uv()
            if uv:
                _install_uv(uv, env, req, backend)
            else:
                _install_pip(env, req)
            (env / MARKER).write_text(backend, encoding="utf-8")
            jobs.update(_job, state="done", percent=100, step="Listo")
        except Cancelled:
            # lo parcial no sirve y ocupa disco: se borra (el entorno todavía no era usable: `present()` era falso al empezar)
            for sub in ("venv", "uv-cache", "python"):
                shutil.rmtree(env / sub, ignore_errors=True)
            jobs.update(_job, state="cancelled", percent=0, message="Cancelado", step="")
        except Exception as e:
            jobs.update(_job, state="error", message=str(e) if isinstance(e, EnvError) else f"Falló: {type(e).__name__}")

    threading.Thread(target=work, daemon=True).start()
    return dict(_job)


def cancel():
    if _job["state"] != "running":
        raise EnvError("No hay una instalación en curso.")
    _holder["cancelled"] = True
    _job["cancelling"] = True
    osenv.kill_tree(_holder.get("proc"))
    return {"state": "cancelling"}
