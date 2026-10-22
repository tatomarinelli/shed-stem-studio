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
import jobs
import stems

OWN_URL = "http://127.0.0.1:11500"
OLLAMA = os.environ.get("STEMSHED_OLLAMA", OWN_URL)
OLLAMA_MODELS = stems.ROOT / "models" / "ollama"
_proc = None  # el Ollama que levantó el motor (si lo levantó él)
PROVIDER = "ollama"  # "ollama" o "llamacpp" (llama-server, API compatible con OpenAI): ver llmdetect.py
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
    _proc = subprocess.Popen([osenv.find_ollama() or "ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             env={**os.environ, "OLLAMA_MODELS": str(OLLAMA_MODELS), "OLLAMA_HOST": OLLAMA.split("//")[1]},
                             **osenv.sys_flags())
    for _ in range(40):  # hasta ~8 s
        if ollama_tags() is not None:
            return
        time.sleep(0.2)


def ensure_ollama():
    """Levanta el Ollama propio si no responde. Solo para la dirección propia; un servidor externo se respeta."""
    if PROVIDER == "ollama" and OLLAMA == OWN_URL and ollama_tags() is None and osenv.find_ollama():
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
    """Modelos cargados en memoria ahora (GPU/RAM), según Ollama. llama-server tiene un solo modelo cargado: no hay lista que mostrar."""
    if PROVIDER != "ollama":
        return []
    try:
        with _ollama("/api/ps") as r:
            return [{"name": m["name"], "bytes": m.get("size_vram") or m.get("size") or 0} for m in json.load(r).get("models", [])]
    except Exception:
        return None


def configure(models_dir, url, provider="ollama"):
    """Aplica los ajustes. Devuelve True si hay que reiniciar Ollama a mano (lo levantó otro proceso)."""
    global OLLAMA, OLLAMA_MODELS, _proc, PROVIDER
    changed = Path(models_dir) != OLLAMA_MODELS or url != OLLAMA or provider != PROVIDER
    OLLAMA, OLLAMA_MODELS, PROVIDER = url, Path(models_dir), provider
    if not changed:
        return False
    if _proc and _proc.poll() is None:
        _proc.terminate()
        _proc.wait(10)
        _proc = None
        ensure_ollama()
        return False
    return PROVIDER == "ollama" and OLLAMA == OWN_URL and ollama_tags() is not None  # corre, pero no es nuestro: no lo reiniciamos


# Modelo por defecto cuando el usuario no eligió uno: el primero de esta lista que esté instalado (ver docs/model-comparison.md).
PREFERRED = ("mistral-nemo",)


def ollama_tags():
    """Modelos instalados, con el preferido primero: quien tome "el primero" usa el predeterminado, no el que Ollama liste antes."""
    if PROVIDER != "ollama":
        return openai_models()
    try:
        with _ollama("/api/tags") as r:
            tags = json.load(r)["models"]
    except Exception:
        return None  # instancia apagada
    tags = [m for m in tags if "embed" not in m["name"].lower()]  # los modelos de embeddings no son modelos de chat: no se ofrecen para elegir
    rank = lambda m: next((i for i, p in enumerate(PREFERRED) if m["name"].split(":")[0] == p), len(PREFERRED))
    return sorted(tags, key=rank)


def _openai(path, body=None, timeout=3):
    req = urllib.request.Request(OLLAMA + path, data=json.dumps(body).encode() if body else None, headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout)


def openai_models():
    """Modelos de un servidor compatible con OpenAI (llama-server) con la forma de /api/tags; None si no responde."""
    try:
        with _openai("/v1/models") as r:
            data = json.load(r).get("data", [])
    except Exception:
        return None
    return [{"name": m["id"], "size": 0, "capabilities": ["completion"]} for m in data if m.get("id")]


def chat(model, system, user, schema, temperature, num_predict, timeout=600, keep_alive="10m"):
    """Un pedido de chat con salida JSON según `schema`, en el idioma de cada servidor.
    Devuelve (texto, tokens del pedido, tokens generados). La interfaz de llama-server está sin verificar en una máquina real."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    if PROVIDER == "ollama":
        body = {"model": model, "stream": False, "format": schema, "keep_alive": keep_alive, "messages": messages,
                "options": {"temperature": temperature, "num_predict": num_predict}}
        with _ollama("/api/chat", body, timeout=timeout) as r:
            reply = json.load(r)
        return reply["message"]["content"], reply.get("prompt_eval_count"), reply.get("eval_count")
    body = {"model": model, "stream": False, "messages": messages, "temperature": temperature, "max_tokens": num_predict,
            "response_format": {"type": "json_schema", "json_schema": {"name": "respuesta", "strict": True, "schema": schema}}}
    with _openai("/v1/chat/completions", body, timeout=timeout) as r:
        reply = json.load(r)
    usage = reply.get("usage") or {}
    return reply["choices"][0]["message"]["content"], usage.get("prompt_tokens"), usage.get("completion_tokens")


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


def provider_label():
    if PROVIDER == "llamacpp":
        return f"llama.cpp (llama-server) en {OLLAMA.split('//')[-1]}"
    return "Ollama local (instancia propia)" if OLLAMA == OWN_URL else f"Ollama en {OLLAMA.split('//')[-1]}"


def report():
    tags = ollama_tags()
    import settings

    chosen = settings.load()["llmModel"]
    names = [m["name"] for m in (tags or [])]
    in_use = chosen if chosen in names else (names[0] if names else None)
    rec = {"provider": provider_label(), "running": tags is not None, "path": str(OLLAMA_MODELS), "inUse": in_use,
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
_pull_ctl = {}  # model_id -> {"resp", "cancelled"}
_lock = threading.Lock()


CUSTOM_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]*(/[a-z0-9][a-z0-9._-]*){0,2}(:[A-Za-z0-9._-]{1,40})?$")


def pull_phase(status):
    """Estado de /api/pull de Ollama (en inglés) -> fase en español. Nunca se muestra el texto crudo (lleva hashes)."""
    low = (status or "").lower()
    if low == "success":
        return "Listo"
    if low.startswith("verifying"):
        return "Verificando"
    if low.startswith(("writing manifest", "removing")):
        return "Terminando"
    if low == "pulling manifest":
        return "Preparando"
    if low.startswith("pulling"):
        return "Descargando"
    return "Trabajando"


def pull_start(model_id):
    """Descarga un modelo de Ollama: uno del catálogo o cualquier nombre válido que el usuario escriba (siempre por un clic)."""
    if PROVIDER != "ollama":
        raise ValueError("Este servidor de modelos no descarga modelos desde acá: usá los que ya tiene.")
    if not (any(m["id"] == model_id for m in hardware.CATALOG) or (len(model_id) <= 100 and CUSTOM_NAME.match(model_id))):
        raise ValueError("Ese nombre de modelo no es válido.")
    if ollama_tags() is None:
        raise ValueError("El servidor de modelos está apagado: prendelo antes de descargar.")
    with _lock:
        running = next((k for k, p in _pulls.items() if p["state"] == "running"), None)
        if running:
            raise ValueError(f"Ya se está descargando {running}: esperá a que termine.")
        job = jobs.start(_pulls.setdefault(model_id, {}), state="running", percent=0, message="", step="Preparando", done=0, total=0, rate=0, cancelable=True)
        _pull_ctl[model_id] = ctl = {"resp": None, "cancelled": False}

    def work():
        layers = {}  # digest -> (hecho, total): el porcentaje sale de la suma de todas las capas, no salta atrás en cada una
        try:
            OLLAMA_MODELS.mkdir(parents=True, exist_ok=True)
            with _ollama("/api/pull", {"name": model_id, "stream": True}, timeout=3600) as r:
                ctl["resp"] = r
                for line in r:
                    if ctl["cancelled"]:
                        break
                    ev = json.loads(line)
                    if ev.get("error"):
                        raise RuntimeError(str(ev["error"])[:200])
                    phase = pull_phase(ev.get("status"))
                    if ev.get("total"):
                        layers[ev.get("digest") or ev.get("status")] = (ev.get("completed", 0), ev["total"])
                    done, total = sum(c for c, _ in layers.values()), sum(t for _, t in layers.values())
                    if total:
                        jobs.update(job, done=done, total=total, percent=min(99, int(100 * done / total)), step=phase)
                        jobs.rate(job, done)
                    else:
                        jobs.update(job, step=phase)
            if ctl["cancelled"]:
                jobs.update(job, state="cancelled", percent=0, step="", message="Cancelado", cancelable=False)
            else:
                jobs.update(job, state="done", percent=100, step="Listo", cancelable=False)
        except Exception as e:
            if ctl["cancelled"]:  # cortar la conexión puede lanzar un error de lectura: no es una falla
                jobs.update(job, state="cancelled", percent=0, step="", message="Cancelado", cancelable=False)
            else:
                why = str(e)[:200] if isinstance(e, RuntimeError) else f"no pude hablar con el servidor de modelos ({type(e).__name__})"
                jobs.update(job, state="error", cancelable=False, message=f"No se pudo descargar: {why}")

    threading.Thread(target=work, daemon=True).start()
    return jobs.public(job)


def pull_cancel(model_id):
    """Corta la conexión con /api/pull: Ollama aborta la descarga. Lo ya bajado queda en su carpeta (sin verificar que se retome)."""
    job, ctl = _pulls.get(model_id), _pull_ctl.get(model_id)
    if not job or job["state"] != "running" or not ctl:
        raise ValueError("No hay una descarga en curso.")
    ctl["cancelled"] = True
    job["cancelling"] = True
    try:
        if ctl["resp"] is not None:
            ctl["resp"].close()
    except Exception:
        pass
    return {"state": "cancelling"}


def pull_status(model_id):
    return jobs.public(_pulls.get(model_id, {"state": "idle"}))
