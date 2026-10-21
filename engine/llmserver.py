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
            "accel": best["llmAccel"] if best else "cpu", "gpu": best["name"] if best else None, "job": dict(_job)}


def install_start():
    if not can_install():
        raise LlmServerError("En este sistema Ollama se instala desde ollama.com.")
    with _lock:
        if _job["state"] == "running":
            raise LlmServerError("Ya se está instalando.")
        if osenv.find_ollama():
            raise LlmServerError("Ollama ya está instalado.")
        _job.update(state="running", percent=0, message="", step="Descargando Ollama", done=0, total=0)

    def work():
        try:
            proc = subprocess.Popen(["winget", "install", "--id", WINGET_ID, "-e", "--silent", "--disable-interactivity",
                                     "--accept-package-agreements", "--accept-source-agreements"],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **osenv.sys_flags())
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
                    if p and p[1]:
                        _job.update(done=p[0], total=p[1], percent=min(95, int(100 * p[0] / p[1])), step="Descargando Ollama")
                    elif re.search(r"install", line, re.I) and "Starting" in line:
                        _job.update(step="Instalando", percent=96)
                    elif any(c.isalpha() for c in line):
                        tail = (tail + [line])[-4:]
            proc.wait()
            if proc.returncode != 0 or not osenv.find_ollama():
                raise LlmServerError("La instalación falló: " + " | ".join(tail[-2:])[:200])
            models.ensure_ollama()
            _job.update(state="done", percent=100, step="Listo")
        except Exception as e:
            _job.update(state="error", message=str(e) if isinstance(e, LlmServerError) else f"Falló: {type(e).__name__}")

    threading.Thread(target=work, daemon=True).start()
    return dict(_job)
