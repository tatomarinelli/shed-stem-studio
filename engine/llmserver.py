"""Servidor de modelos (Ollama): si está instalado, si corre, con qué aceleración va a trabajar y, en Windows, su instalación.

Nunca se instala solo: `install_start()` la dispara un clic explícito. Se usa winget, que verifica el hash del instalador
oficial (Ollama.Ollama). La aceleración sale de las placas detectadas (hardware.py): CUDA en NVIDIA, Vulkan en AMD o Intel
dedicadas (medido en una RX 6700S: 4,2 veces más rápido que CPU) y CPU en el resto.
"""
import re
import shutil
import subprocess
import threading

import hardware
import jobs
import models
import osenv

WINGET_ID = "Ollama.Ollama"
APPROX_GB = 1.7  # tamaño del instalador oficial (OllamaSetup.exe, 1,66 GB en la 0.40.7)
_job = {"state": "idle", "percent": 0, "message": "", "step": "", "done": 0, "total": 0}
_lock = threading.Lock()
SIZE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(KB|MB|GB)\s*/\s*(\d+(?:[.,]\d+)?)\s*(KB|MB|GB)")
UNITS = {"KB": 1e3, "MB": 1e6, "GB": 1e9}


class LlmServerError(Exception):
    pass


def parse_progress(text):
    """Línea de winget ('  412 MB / 1.54 GB') -> (hecho, total) en bytes, o None."""
    m = SIZE.search(text)
    if not m:
        return None
    num = lambda s: float(s.replace(",", "."))
    return int(num(m.group(1)) * UNITS[m.group(2)]), int(num(m.group(3)) * UNITS[m.group(4)])


def can_install():
    return osenv.WINDOWS and bool(shutil.which("winget"))


def status():
    """Lo que devuelve GET /engine/llm/status."""
    gpus = hardware._gpus()
    best = next((g for g in sorted(gpus, key=lambda g: g.get("llmAccel") != "cuda") if g.get("llmAccel")), None)
    running = models.ollama_tags() is not None
    return {"installed": running or bool(osenv.find_ollama()), "running": running, "canInstall": can_install(), "approxGb": APPROX_GB,
            "accel": best["llmAccel"] if best else "cpu", "gpu": best["name"] if best else None, "job": jobs.public(_job)}


_procs = {}  # id(job) -> {"proc", "cancelled"}: el winget en curso de cada instalación


def classify(line):
    """Línea de winget -> fase en español, o None. 'Instalando' ya no se puede cortar sin dejar el paquete a medias."""
    low = line.lower()
    if "verified installer hash" in low or "hash del instalador" in low:
        return "Verificando"
    if "starting package install" in low or "iniciando la instalaci" in low:
        return "Instalando"
    return None


def start_winget(job, package, is_installed, after=None):
    """Instala `package` con winget en segundo plano, mostrando el avance en `job`. Solo Windows; solo por un clic."""
    if not can_install():
        raise LlmServerError("En este sistema se instala desde su sitio oficial.")
    with _lock:
        if job["state"] == "running":
            raise LlmServerError("Ya se está instalando.")
        if is_installed():
            raise LlmServerError("Ya está instalado.")
        jobs.start(job, state="running", percent=0, message="", step="Preparando", done=0, total=0, rate=0, cancelable=True)
        _procs[id(job)] = holder = {"proc": None, "cancelled": False}

    def work():
        try:
            proc = subprocess.Popen(["winget", "install", "--id", package, "-e", "--silent", "--disable-interactivity",
                                     "--accept-package-agreements", "--accept-source-agreements"],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **osenv.sys_flags())
            holder["proc"] = proc
            if holder["cancelled"]:  # el clic llegó antes de que arrancara
                osenv.kill_tree(proc)
            tail, buf = [], b""
            while True:
                chunk = proc.stdout.read(512)
                if not chunk:
                    break
                buf += chunk
                parts = re.split(rb"[\r\n]+", buf)
                buf = parts.pop()
                for raw in parts:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line:
                        continue
                    p = parse_progress(line)
                    phase = classify(line)
                    if p and p[1]:
                        jobs.update(job, done=p[0], total=p[1], percent=min(95, int(100 * p[0] / p[1])), step="Descargando")
                        jobs.rate(job, p[0])
                    elif phase == "Verificando":
                        jobs.update(job, step="Verificando", percent=95)
                    elif phase == "Instalando":
                        jobs.update(job, step="Instalando", percent=96, cancelable=False)
                    elif any(c.isalpha() for c in line):
                        tail = (tail + [line])[-4:]
            proc.wait()
            if holder["cancelled"]:
                jobs.update(job, state="cancelled", percent=0, message="Cancelado", step="", cancelable=False)
                return
            if proc.returncode != 0 or not is_installed():
                raise LlmServerError("La instalación falló: " + " | ".join(tail[-2:])[:200])
            if after:
                after()
            jobs.update(job, state="done", percent=100, step="Listo", cancelable=False)
        except Exception as e:
            jobs.update(job, state="error", cancelable=False, message=str(e) if isinstance(e, LlmServerError) else f"Falló: {type(e).__name__}")

    threading.Thread(target=work, daemon=True).start()
    return jobs.public(job)


def cancel_winget(job):
    """Corta la descarga. Una vez que el instalador empezó a instalar no se corta: dejaría el programa a medias."""
    holder = _procs.get(id(job))
    if job["state"] != "running" or not holder:
        raise LlmServerError("No hay una instalación en curso.")
    if not job.get("cancelable", True):
        raise LlmServerError("Ya está instalando: esperá a que termine, cortarla la dejaría a medias.")
    holder["cancelled"] = True
    job["cancelling"] = True
    osenv.kill_tree(holder.get("proc"))
    return {"state": "cancelling"}


def install_start():
    return start_winget(_job, WINGET_ID, lambda: bool(osenv.find_ollama()), models.ensure_ollama)


# ffmpeg: lo pide audio-separator hasta para bajar el modelo. Se instala con winget (Gyan.FFmpeg) solo con un clic.
_ffmpeg_job = {"state": "idle", "percent": 0, "message": "", "step": "", "done": 0, "total": 0}


def ffmpeg_status():
    return {"installed": bool(osenv.find_ffmpeg()), "canInstall": can_install(), "job": jobs.public(_ffmpeg_job)}


def ffmpeg_install_start():
    return start_winget(_ffmpeg_job, "Gyan.FFmpeg", lambda: bool(osenv.find_ffmpeg()), osenv.ensure_ffmpeg_on_path)


def install_cancel():
    return cancel_winget(_job)


def ffmpeg_install_cancel():
    return cancel_winget(_ffmpeg_job)
