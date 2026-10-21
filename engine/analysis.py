"""Análisis musical (tonalidad, tempo y compases, acordes) de un tema ya separado. Solo librería estándar.

El trabajo pesado lo hace analyze.py en el venv de separación (numpy/librosa), como subproceso con CPU y prioridad
baja; acá se lanza, se sigue el progreso y se guarda el resultado en <dataDir>/analysis/<trackId>.json. Nunca escribe
en las cachés de stems. Un trabajo a la vez (es CPU intensivo, aunque tarda segundos).

Uso desde server.py:
    import analysis
    analysis.configure(s["dataDir"], s["separationEnvDir"])   # junto con stems.configure
    analysis.get(id) -> dict | None ; analysis.start(id, force=False) ; analysis.job_status(id)
Errores para el usuario: AnalysisError (mensaje en español). Ids inválidos: ValueError (de stems.norm_id).
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import stems

VERSION = 1                     # el mismo "version" que escribe analyze.py; otro valor = hay que reanalizar
TIMEOUT = 900                   # segundos; un tema de 15 min tarda ~10 s, esto es solo un seguro
SCRIPT = Path(__file__).with_name("analyze.py")
PROGRESS = re.compile(r"^PROGRESS (\w+) (\d{1,3})$")

_data_dir = None                # None = la carpeta de datos de stems (stems.ROOT)
_python = None                  # None = <separationEnvDir>/venv/bin/python (stems.ENV)


class AnalysisError(Exception):
    pass


def configure(data_dir, env_dir=None, python=None):
    """Aplica las carpetas de Ajustes. `python` permite forzar el intérprete (pruebas)."""
    global _data_dir, _python
    _data_dir = Path(data_dir)
    if python:
        _python = Path(python)
    elif env_dir:
        _python = Path(env_dir) / "venv" / "bin" / "python"


def data_dir():
    return _data_dir or stems.ROOT


def python_path():
    return _python or (stems.ENV / "venv" / "bin" / "python")


def result_path(track_id):
    return data_dir() / "analysis" / f"{stems.norm_id(track_id)}.json"


def stems_dir(track_id):
    """Carpeta con los stems del tema (caché nueva o vieja de solo lectura), o None si no está separado."""
    track_id = stems.norm_id(track_id)
    for d in (stems.cache_dir(track_id), stems.OLD_CACHE / track_id / stems.MODEL):
        if (d / "manifest.json").exists():
            return d
    return None


def get(track_id):
    """Resultado guardado, o None si no hay o es de otra versión del formato."""
    path = result_path(track_id)
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return data if data.get("version") == VERSION else None


# --- un solo trabajo a la vez
_jobs = {}
_lock = threading.Lock()


def start(track_id, force=False):
    track_id = stems.norm_id(track_id)
    with _lock:
        if not force and get(track_id) is not None:
            return {"state": "done", "cached": True}
        if any(j["state"] == "running" for j in _jobs.values()):
            raise AnalysisError("Ya hay un análisis en curso: esperá a que termine.")
        folder = stems_dir(track_id)
        if folder is None:
            raise AnalysisError("Ese tema no está separado: separalo primero.")
        py = python_path()
        if not py.exists():
            raise AnalysisError("Falta el entorno de análisis (Python del venv de separación) en " + str(py))
        _jobs[track_id] = {"state": "running", "stage": "load", "percent": 0, "message": ""}

    def work():
        try:
            run(track_id, folder, py)
            _jobs[track_id].update(state="done", stage="done", percent=100)
        except Exception as e:  # noqa: BLE001 - el hilo no debe morir en silencio
            _jobs[track_id].update(state="error",
                                   message=str(e) if isinstance(e, AnalysisError) else f"Falló: {type(e).__name__}")

    threading.Thread(target=work, daemon=True).start()
    return dict(_jobs[track_id])


def job_status(track_id):
    track_id = stems.norm_id(track_id)
    job = _jobs.get(track_id)
    if job:
        return dict(job)
    return {"state": "done", "cached": True} if get(track_id) is not None else {"state": "idle"}


def _env():
    tmp = data_dir() / "tmp"
    env = {**os.environ, "STEMSHED_DATA": str(data_dir()), "CUDA_VISIBLE_DEVICES": "",
           "NUMBA_CACHE_DIR": str(tmp / "numba"), "TMPDIR": str(tmp)}
    for var in ("NUMBA_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        env[var] = "8"
    return env


def run(track_id, folder, py):
    out = result_path(track_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    (data_dir() / "tmp").mkdir(parents=True, exist_ok=True)
    cmd = [str(py), str(SCRIPT), str(folder), "--out", str(out), "--track-id", track_id]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, env=_env())
    try:  # prioridad baja (sin preexec_fn, que no es seguro con hilos)
        os.setpriority(os.PRIO_PROCESS, proc.pid, 10)
    except (AttributeError, OSError):
        pass
    killer = threading.Timer(TIMEOUT, proc.kill)
    killer.start()
    tail = []
    try:
        with proc.stderr:
            for line in proc.stderr:
                line = line.strip()
                m = PROGRESS.match(line)
                if m:
                    _jobs[track_id].update(stage=m.group(1), percent=min(100, int(m.group(2))))
                elif line:
                    tail = (tail + [line])[-8:]
        proc.wait()
    finally:
        killer.cancel()
    if proc.returncode != 0:
        if proc.returncode < 0:
            raise AnalysisError(f"El análisis tardó más de {TIMEOUT // 60} minutos y lo corté.")
        raise AnalysisError("El análisis falló: " + (tail[-1][:200] if tail else "sin salida"))
    if get(track_id) is None:
        raise AnalysisError("El análisis no dejó un resultado válido.")
    return out


def delete(track_id):
    """Borra el análisis guardado (por ejemplo, para reanalizar). No toca los stems."""
    path = result_path(track_id)
    with _lock:
        if _jobs.get(stems.norm_id(track_id), {}).get("state") == "running":
            raise AnalysisError("Se está analizando ahora mismo.")
        _jobs.pop(stems.norm_id(track_id), None)
    try:
        path.unlink()
    except FileNotFoundError:
        return {"deleted": False}
    return {"deleted": True}


if __name__ == "__main__":  # prueba manual: python3 analysis.py <trackId>
    tid = sys.argv[1]
    print(start(tid, force="--force" in sys.argv))
    while job_status(tid)["state"] == "running":
        time.sleep(0.5)
    print(job_status(tid))
