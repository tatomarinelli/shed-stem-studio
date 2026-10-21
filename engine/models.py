"""Modelos locales: qué hay instalado, cuánto pesa y dónde está; y descarga de modelos del catálogo vía Ollama propio."""
import json
import os
import osenv
import re
import shutil
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

import hardware
import stems

OWN_URL = "http://127.0.0.1:11500"
OLLAMA = os.environ.get("STEMSHED_OLLAMA", OWN_URL)
OLLAMA_MODELS = stems.ROOT / "models" / "ollama"
_proc = None  # el Ollama que levantó el motor (si lo levantó él)
CONFIG_DIR = osenv.config_dir()
_size_cache = {}


def dir_size(path, ttl=60):
    """Tamaño de una carpeta (sin seguir enlaces), con caché corta: recorrer el venv tarda."""
    path = str(path)
    hit = _size_cache.get(path)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    total = 0
    if os.path.isfile(path):
        total = os.lstat(path).st_size
    else:
        for root, _, files in os.walk(path, onerror=lambda e: None):
            for name in files:
                try:
                    total += os.lstat(os.path.join(root, name)).st_size
                except OSError:
                    pass
    _size_cache[path] = (time.time(), total)
    return total


def _ollama(path, body=None, timeout=3):
    req = urllib.request.Request(OLLAMA + path, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout)


def _spawn():
    global _proc
    OLLAMA_MODELS.mkdir(parents=True, exist_ok=True)
    _proc = subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             env={**os.environ, "OLLAMA_MODELS": str(OLLAMA_MODELS), "OLLAMA_HOST": OLLAMA.split("//")[1]},
                             **osenv.sys_flags())
    for _ in range(40):  # hasta ~8 s
        if ollama_tags() is not None:
            return
        time.sleep(0.2)


def ensure_ollama():
    """Levanta el Ollama propio si no responde. Solo para la dirección propia; un servidor externo se respeta."""
    if OLLAMA == OWN_URL and ollama_tags() is None and shutil.which("ollama"):
        _spawn()


def stop_own_ollama():
    """Apaga el Ollama que levantó el motor (si lo levantó él). Un servidor externo no se toca."""
    global _proc
    if _proc and _proc.poll() is None:
        _proc.terminate()
        try:
            _proc.wait(10)
        except subprocess.TimeoutExpired:
            _proc.kill()
    _proc = None


def loaded():
    """Modelos cargados en memoria ahora (GPU/RAM), según Ollama."""
    try:
        with _ollama("/api/ps") as r:
            return [{"name": m["name"], "bytes": m.get("size_vram") or m.get("size") or 0} for m in json.load(r).get("models", [])]
    except Exception:
        return None


def configure(models_dir, url):
    """Aplica los ajustes. Devuelve True si hay que reiniciar Ollama a mano (lo levantó otro proceso)."""
    global OLLAMA, OLLAMA_MODELS, _proc
    changed = Path(models_dir) != OLLAMA_MODELS or url != OLLAMA
    OLLAMA, OLLAMA_MODELS = url, Path(models_dir)
    if not changed:
        return False
    if _proc and _proc.poll() is None:
        _proc.terminate()
        _proc.wait(10)
        _proc = None
        ensure_ollama()
        return False
    return OLLAMA == OWN_URL and ollama_tags() is not None  # corre, pero no es nuestro: no lo reiniciamos


# Modelo por defecto cuando el usuario no eligió uno: el primero de esta lista que esté instalado (ver docs/model-comparison.md).
PREFERRED = ("mistral-nemo",)


def ollama_tags():
    """Modelos instalados, con el preferido primero: quien tome "el primero" usa el predeterminado, no el que Ollama liste antes."""
    try:
        with _ollama("/api/tags") as r:
            tags = json.load(r)["models"]
    except Exception:
        return None  # instancia apagada
    tags = [m for m in tags if "embed" not in m["name"].lower()]  # los modelos de embeddings no son modelos de chat: no se ofrecen para elegir
    rank = lambda m: next((i for i, p in enumerate(PREFERRED) if m["name"].split(":")[0] == p), len(PREFERRED))
    return sorted(tags, key=rank)


def separation_models():
    models = ENV_MODELS = stems.MODELS_DIR
    items = [
        {"label": "RoFormer (BS-Roformer-SW)", "files": ["BS-Roformer-SW.ckpt", "BS-Roformer-SW.yaml"]},
        {"label": "Demucs 6 stems (htdemucs_6s)", "files": ["htdemucs_6s.yaml", "5c90dfd2-34c22ccb.th"]},
    ]
    out = []
    for it in items:
        paths = [ENV_MODELS / f for f in it["files"]]
        present = all(p.exists() for p in paths)
        out.append({"label": it["label"], "where": "GPU local", "path": str(ENV_MODELS), "present": present,
                    "bytes": sum(p.stat().st_size for p in paths if p.exists())})
    return out


def report():
    tags = ollama_tags()
    import settings

    chosen = settings.load()["llmModel"]
    names = [m["name"] for m in (tags or [])]
    in_use = chosen if chosen in names else (names[0] if names else None)
    rec = {"provider": "Ollama local (instancia propia)", "running": tags is not None, "path": str(OLLAMA_MODELS), "inUse": in_use,
           "models": [{"label": m["name"], "where": "GPU local", "path": str(OLLAMA_MODELS), "present": True,
                       "bytes": m["size"]} for m in (tags or [])]}
    storage = [
        {"label": "Stems nuevos", "path": str(stems.CACHE), "bytes": dir_size(stems.CACHE) if stems.CACHE.exists() else 0, "writable": True},
        {"label": "Stems anteriores", "path": str(stems.OLD_CACHE), "bytes": dir_size(stems.OLD_CACHE) if stems.OLD_CACHE.exists() else 0, "writable": False},
        {"label": "Entorno de separación", "path": str(stems.ENV / "venv"), "bytes": dir_size(stems.ENV / "venv"), "writable": False},
        {"label": "Modelos de separación", "path": str(stems.MODELS_DIR), "bytes": dir_size(stems.MODELS_DIR) if stems.MODELS_DIR.exists() else 0, "writable": True},
        {"label": "Modelos de recomendación", "path": str(OLLAMA_MODELS), "bytes": dir_size(OLLAMA_MODELS) if OLLAMA_MODELS.exists() else 0, "writable": True},
        {"label": "Sesión de TIDAL", "path": str(CONFIG_DIR), "bytes": dir_size(CONFIG_DIR) if CONFIG_DIR.exists() else 0, "writable": True},
    ]
    import envsetup

    return {"env": envsetup.status(), "separation": separation_models(), "separationInUse": "RoFormer (BS-Roformer-SW)", "recommendations": rec, "storage": storage}


# --- descarga de modelos del catálogo (nunca de un nombre arbitrario)
_pulls = {}
_lock = threading.Lock()


CUSTOM_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]*(/[a-z0-9][a-z0-9._-]*){0,2}(:[A-Za-z0-9._-]{1,40})?$")


def pull_start(model_id):
    """Descarga un modelo de Ollama: uno del catálogo o cualquier nombre válido que el usuario escriba (siempre por un clic)."""
    if not (any(m["id"] == model_id for m in hardware.CATALOG) or (len(model_id) <= 100 and CUSTOM_NAME.match(model_id))):
        raise ValueError("Ese nombre de modelo no es válido.")
    with _lock:
        if any(p["state"] == "running" for p in _pulls.values()):
            raise ValueError("Ya hay una descarga en curso.")
        _pulls[model_id] = {"state": "running", "percent": 0, "message": ""}

    def work():
        try:
            OLLAMA_MODELS.mkdir(parents=True, exist_ok=True)
            with _ollama("/api/pull", {"name": model_id, "stream": True}, timeout=3600) as r:
                for line in r:
                    ev = json.loads(line)
                    if ev.get("error"):
                        raise RuntimeError(ev["error"])
                    if ev.get("total"):
                        now, done = time.time(), ev.get("completed", 0)
                        job = _pulls[model_id]
                        if now - job.get("t", now) >= 1 and done >= job.get("done", 0):
                            job["rate"] = int((done - job.get("done", 0)) / (now - job["t"]))
                        if "t" not in job or now - job["t"] >= 1:
                            job["t"], job["done"] = now, done
                        job.update(percent=int(100 * done / ev["total"]), done=done, total=ev["total"], step=ev.get("status", ""))
            _pulls[model_id].update(state="done", percent=100)
        except Exception as e:
            _pulls[model_id].update(state="error", message=f"No se pudo descargar: {type(e).__name__}")

    threading.Thread(target=work, daemon=True).start()
    return dict(_pulls[model_id])


def pull_status(model_id):
    return dict(_pulls.get(model_id, {"state": "idle"}))
