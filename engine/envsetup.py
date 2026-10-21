"""Entorno de separación y análisis (torch + CUDA, audio-separator, librosa): se instala desde Ajustes, a la carpeta elegida.

Nunca se instala solo. `start()` la dispara un clic explícito. Crea <ENV>/venv con el mismo Python que corre el motor
y le instala engine/requirements-env.txt (varios GB: la interfaz avisa el tamaño antes).
"""
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import stems

REQ = Path(__file__).with_name("requirements-env.txt")
_job = {"state": "idle", "percent": 0, "message": "", "step": "", "done": 0, "total": 0, "rate": 0}
_lock = threading.Lock()
PKG = re.compile(r"^(Collecting|Downloading|Installing collected packages)")
SIZE = re.compile(r"^\s*Downloading (\S+)\s+\((\d+(?:\.\d+)?) ([kMG])B\)")  # pip sangra la línea dentro de un "Collecting"
RAW = re.compile(r"^Progress (\d+) of (\d+)")
UNITS = {"k": 1e3, "M": 1e6, "G": 1e9}
APPROX_TOTAL = 4.6e9   # descarga total aproximada de requirements-env.txt (se muestra como estimación)


class EnvError(Exception):
    pass


def present():
    return (stems.ENV / "venv" / "bin" / "audio-separator").exists() and (stems.ENV / "venv" / "bin" / "python").exists()


def status():
    return {**_job, "present": present(), "path": str(stems.ENV / "venv"), "approxGb": 8}


def _count_requirements():
    return max(1, sum(1 for ln in REQ.read_text().splitlines() if ln.strip() and not ln.startswith(("#", "--"))))


def start():
    with _lock:
        if _job["state"] == "running":
            raise EnvError("Ya se está instalando.")
        if present():
            raise EnvError("El entorno ya está instalado.")
        _job.update(state="running", percent=0, message="", step="Creando el entorno", done=0, total=0, rate=0, approx=False)

    def work():
        try:
            env = stems.ENV
            env.mkdir(parents=True, exist_ok=True)
            code = subprocess.run([sys.executable, "-m", "venv", str(env / "venv")], capture_output=True, text=True)
            if code.returncode != 0:
                raise EnvError("No se pudo crear el entorno: " + (code.stderr.strip().splitlines() or ["sin salida"])[-1][:200])
            pip = str(env / "venv" / "bin" / "pip")
            proc = subprocess.Popen([pip, "install", "--no-cache-dir", "--progress-bar", "raw", "--no-deps", "-r", str(REQ)],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                    env={**os.environ, "PIP_DISABLE_PIP_VERSION_CHECK": "1", "TMPDIR": str(stems.ROOT / "tmp")})
            (stems.ROOT / "tmp").mkdir(parents=True, exist_ok=True)
            tail, finished, current, name, last_t, last_b = [], 0, 0, "", time.time(), 0
            for line in proc.stdout:
                line = line.rstrip()
                tail = (tail + [line])[-8:]
                m = SIZE.match(line)
                if m and not m.group(1).endswith(".metadata"):
                    finished += current  # el archivo anterior terminó
                    name, current = m.group(1), 0
                    _job.update(step="Descargando " + name.rsplit("/", 1)[-1][:60])
                    continue
                m = RAW.match(line)
                if m:
                    current = int(m.group(1))
                    done = finished + current
                    now = time.time()
                    if now - last_t >= 1:
                        _job["rate"] = int((done - last_b) / (now - last_t))
                        last_t, last_b = now, done
                    _job.update(done=int(done), total=int(APPROX_TOTAL), approx=True, percent=min(97, int(100 * done / APPROX_TOTAL)))
                elif line.startswith("Installing collected packages"):
                    _job.update(step="Instalando los paquetes", percent=98)
            proc.wait()
            if proc.returncode != 0 or not present():
                raise EnvError("La instalación falló: " + " | ".join(x.strip() for x in tail[-3:] if x.strip())[:240])
            _job.update(state="done", percent=100, step="Listo")
        except Exception as e:
            _job.update(state="error", message=str(e) if isinstance(e, EnvError) else f"Falló: {type(e).__name__}")

    threading.Thread(target=work, daemon=True).start()
    return dict(_job)
