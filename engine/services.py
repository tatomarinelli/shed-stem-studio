"""Qué está corriendo y en qué puerto, y el apagado ordenado del motor."""
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import analysis
import envsetup
import models
import recs
import settings
import stems
import tidal_source

START = time.time()
_server = {"host": "", "port": 0, "origins": [], "httpd": None}


def bind(httpd, host, port, origins):
    _server.update(httpd=httpd, host=host, port=port, origins=sorted(origins))


HOST_VARS = {"dataDir": ("STEMSHED_HOST_DATA", "STEMSHED_DATA"), "ollamaModelsDir": ("STEMSHED_HOST_LLM_MODELS", "STEMSHED_LLM_MODELS"),
             "separationModelsDir": ("STEMSHED_HOST_SEP_MODELS", "STEMSHED_SEP_MODELS"), "separationEnvDir": ("STEMSHED_HOST_ENV", "STEMSHED_ENV")}


def host_paths():
    """En Docker: dónde está cada carpeta en el equipo (la define el docker-compose, no Ajustes) y con qué variable se cambia."""
    out = {}
    for key, (env, var) in HOST_VARS.items():
        if os.environ.get(env):
            out[key] = {"path": os.environ[env], "var": var}
    return out


def in_docker():
    return Path("/.dockerenv").exists()


def active_jobs():
    """Lo que está trabajando ahora: [{kind, label, percent?}]. Si hay algo, el apagado pide esperar."""
    jobs = []
    for tid, j in list(stems._jobs.items()):
        if j.get("state") == "running":
            jobs.append({"kind": "separación", "label": f"Tema {tid}", "percent": j.get("percent"), "step": j.get("stage")})
    for tid, j in list(analysis._jobs.items()):
        if j.get("state") == "running":
            jobs.append({"kind": "análisis", "label": f"Tema {tid}", "percent": j.get("percent")})
    for mid, j in list(models._pulls.items()):
        if j.get("state") == "running":
            jobs.append({"kind": "descarga", "label": mid, "percent": j.get("percent")})
    if stems._dl["state"] == "running":
        jobs.append({"kind": "descarga", "label": "Modelo de separación", "percent": stems._dl["percent"]})
    if envsetup._job["state"] == "running":
        jobs.append({"kind": "instalación", "label": "Entorno de separación", "percent": envsetup._job["percent"]})
    if recs._state.get("state") == "running":
        jobs.append({"kind": "recomendación", "label": "Generando un disco", "step": recs._state.get("step")})
    return jobs


def report():
    s = settings.effective()
    tags = models.ollama_tags()
    return {
        "engine": {"host": _server["host"], "port": _server["port"], "pid": os.getpid(), "uptimeSec": int(time.time() - START),
                   "docker": in_docker(), "origins": _server["origins"], "hostPaths": host_paths()},
        "llm": {"url": models.OLLAMA, "running": tags is not None, "own": models._proc is not None and models._proc.poll() is None,
                "loaded": models.loaded() if tags is not None else [], "installed": len(tags or [])},
        "tidal": {"connected": bool(tidal_source.status().get("connected"))},
        "scheduler": {"auto": bool(s.get("recsAuto")), "cadenceHours": s.get("recsCadenceHours")},
        "jobs": active_jobs(),
    }


def shutdown():
    """Apaga el motor y el Ollama propio, solo si no hay trabajo en curso. Devuelve la lista de lo que lo impide."""
    jobs = active_jobs()
    if jobs:
        return {"ok": False, "jobs": jobs}
    httpd = _server["httpd"]

    def stop():
        time.sleep(0.4)  # deja salir la respuesta
        models.stop_own_ollama()
        if httpd:
            httpd.shutdown()

    threading.Thread(target=stop, daemon=True).start()
    return {"ok": True}


OPENABLE = ("dataDir", "separationEnvDir", "separationModelsDir", "ollamaModelsDir")


class OpenError(Exception):
    pass


def open_folder(key):
    """Abre una de las carpetas de Ajustes en el explorador de archivos del sistema. Solo claves conocidas: nunca una ruta que mande el cliente."""
    if in_docker():
        raise OpenError("Con Docker las carpetas están en tu equipo: abrilas desde el explorador de archivos.")
    if key not in OPENABLE:
        raise OpenError("Carpeta desconocida.")
    path = Path(settings.effective()[key])
    if not path.is_dir():
        raise OpenError("La carpeta todavía no existe.")
    if sys.platform == "win32":
        os.startfile(str(path))  # noqa: S606 (solo Windows)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        opener = shutil.which("xdg-open")
        if not opener or not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            raise OpenError("No hay un explorador de archivos disponible desde el motor.")
        subprocess.Popen([opener, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return {"ok": True}
