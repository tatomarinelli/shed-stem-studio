"""Servidores de modelos de lenguaje que el usuario ya tiene (Ollama, llama.cpp, LM Studio): detectarlos y, con un clic, usarlos o prenderlos.

Solo mira: puertos de esta computadora, binarios en el PATH y carpetas conocidas. Nada se descarga ni se instala.
Los modelos son solo para las recomendaciones; la separación en instrumentos no usa modelos de lenguaje (docs/backends-separacion.md).
Las rutas y los binarios de cada sistema salen de osenv.py. La parte de llama-server está sin verificar contra un llama-server real.
"""
import json
import os
import socket
import subprocess
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import jobs
import models
import osenv

PORTS = (11434, 11500, 8080, 8081, 1234)  # Ollama, el Ollama propio, llama-server, el llama-server propio, LM Studio
OWN_LLAMA_PORTS = range(8081, 8090)
MIN_GGUF = 50 * 1024 * 1024    # por debajo no es un modelo de chat (tokenizadores, adaptadores)
MAX_GGUF = 200
CTX = 8192                     # el pedido de recomendaciones usa hasta ~4700 tokens (recs.CTX_LIMIT + salida)
_job = {"state": "idle", "percent": 0, "message": "", "step": ""}
_own = {"proc": None, "port": None, "model": None, "cancelled": False}
_lock = threading.Lock()
_cache = {"at": 0.0, "value": None}


class DetectError(Exception):
    pass


def _get(port, path, timeout=0.5):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as r:
            return json.load(r)
    except Exception:
        return None


def probe(port):
    """¿Qué servidor responde en 127.0.0.1:port? Se reconoce por la forma de la respuesta, no por el número de puerto."""
    v = _get(port, "/api/version")
    if isinstance(v, dict) and "version" in v:
        tags = _get(port, "/api/tags")
        names = [m.get("name") for m in (tags or {}).get("models", []) if "embed" not in str(m.get("name")).lower()]
        return {"kind": "ollama", "port": port, "version": v["version"], "models": names}
    props = _get(port, "/props")
    listed = _get(port, "/v1/models")
    data = listed.get("data", []) if isinstance(listed, dict) else []
    if isinstance(props, dict) and ("total_slots" in props or "default_generation_settings" in props or "build_info" in props):
        return {"kind": "llamacpp", "port": port, "version": props.get("build_info"), "models": [m.get("id") for m in data if m.get("id")]}
    if data:
        llama = any(m.get("owned_by") == "llamacpp" for m in data)
        return {"kind": "llamacpp" if llama else "openai", "port": port, "version": None, "models": [m.get("id") for m in data if m.get("id")]}
    return None


def scan_gguf(roots, max_files=MAX_GGUF, max_depth=6):
    """Archivos .gguf bajo `roots` (solo lectura, acotado). Sin los proyectores de imagen (mmproj) ni los muy chicos."""
    out = []

    def walk(folder, depth):
        if depth > max_depth or len(out) >= max_files:
            return
        try:
            entries = list(os.scandir(folder))
        except OSError:
            return
        for e in sorted(entries, key=lambda e: e.name):
            try:
                if e.is_dir(follow_symlinks=False):
                    walk(e.path, depth + 1)
                elif e.name.lower().endswith(".gguf") and "mmproj" not in e.name.lower():
                    size = e.stat().st_size  # un enlace (Hugging Face guarda enlaces a blobs): se sigue para saber el tamaño real
                    if size >= MIN_GGUF and len(out) < max_files:
                        out.append({"path": e.path, "name": e.name, "bytes": size, "folder": str(roots_by(e.path, roots))})
            except OSError:
                continue

    for root in roots:
        if Path(root).is_dir():
            walk(str(root), 0)
    return out


def roots_by(path, roots):
    return next((r for r in roots if str(path).startswith(str(r))), Path(path).parent)


def count_manifests(root):
    """Cantidad de modelos de Ollama en una carpeta de modelos (un manifiesto por modelo)."""
    base = Path(root) / "manifests"
    if not base.is_dir():
        return 0
    return sum(1 for p in base.rglob("*") if p.is_file())


def _port_free(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def detect(force=False, ttl=5.0):
    """Todo lo que ya hay en el equipo. Sondea unos pocos puertos locales con timeout corto; el resultado se guarda `ttl` segundos."""
    if not force and _cache["value"] and time.time() - _cache["at"] < ttl:
        return _cache["value"]
    ports = list(dict.fromkeys(list(PORTS) + [p for p in [_port_of(models.OLLAMA)] if p]))
    with ThreadPoolExecutor(max_workers=len(ports)) as pool:
        found = [f for f in pool.map(probe, ports) if f]
    for f in found:
        f["url"] = f"http://127.0.0.1:{f['port']}"
        f["current"] = f["url"] == models.OLLAMA
        f["own"] = (f["kind"] == "ollama" and f["url"] == models.OWN_URL and models._proc is not None) or (
            f["kind"] == "llamacpp" and f["port"] == _own["port"] and _alive())
    ollama_exe = osenv.find_ollama()
    llama_exe = osenv.find_llama_server()
    folders = [{"path": str(r), "models": count_manifests(r)} for r in osenv.ollama_model_roots() if (Path(r) / "manifests").is_dir()]
    value = {"servers": found, "binaries": {"ollama": ollama_exe, "llamaServer": llama_exe},
             "ollamaFolders": folders, "ggufs": scan_gguf(osenv.gguf_roots()), "own": own_status(), "current": models.OLLAMA,
             "provider": models.PROVIDER}
    _cache.update(at=time.time(), value=value)
    return value


def _port_of(url):
    try:
        return int(url.rsplit(":", 1)[1].split("/")[0])
    except (ValueError, IndexError):
        return None


def _alive():
    return _own["proc"] is not None and _own["proc"].poll() is None


def own_status():
    return {"running": _alive(), "port": _own["port"] if _alive() else None, "model": _own["model"] if _alive() else None,
            "job": jobs.public(_job)}


def start_llamacpp(model_path):
    """Prende llama-server con un modelo ya descargado. Solo por un clic: el modelo tiene que estar en lo detectado, el servidor
    escucha solo en esta computadora y no baja nada. Devuelve el estado de la tarea; el puerto queda en own_status()."""
    exe = osenv.find_llama_server()
    if not exe:
        raise DetectError("No encontré llama-server en este equipo.")
    known = {g["path"] for g in scan_gguf(osenv.gguf_roots())}
    if str(model_path) not in known:
        raise DetectError("Ese modelo no está entre los que encontré.")
    with _lock:
        if _alive() or _job["state"] == "running":
            raise DetectError("Ya hay un llama-server prendido o cargando.")
        port = next((p for p in OWN_LLAMA_PORTS if _port_free(p)), None)
        if port is None:
            raise DetectError("No hay un puerto libre entre 8081 y 8089.")
        jobs.start(_job, state="running", percent=0, message="", step="Cargando el modelo", cancelable=True)
        _own.update(port=port, model=Path(model_path).name, cancelled=False)
    cmd = [exe, "-m", str(model_path), "--host", "127.0.0.1", "--port", str(port), "-c", str(CTX), "--jinja", "-ngl", "99"]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **osenv.sys_flags())
    except OSError as e:
        jobs.update(_job, state="error", message=f"No se pudo prender llama-server: {e.strerror or type(e).__name__}", cancelable=False)
        return jobs.public(_job)
    _own["proc"] = proc

    def wait_ready():
        t0 = time.time()
        while time.time() - t0 < 600:
            if _own["cancelled"]:
                jobs.update(_job, state="cancelled", message="Cancelado", step="", cancelable=False)
                return
            if proc.poll() is not None:
                jobs.update(_job, state="error", cancelable=False,
                            message=f"llama-server se cerró (código {proc.returncode}): el modelo no entra en la memoria o no es compatible.")
                return
            health = _get(port, "/health", timeout=1)
            if isinstance(health, dict) and health.get("status") == "ok":
                jobs.update(_job, state="done", percent=100, step="Listo", cancelable=False)
                _cache["value"] = None
                return
            time.sleep(1)
        osenv.kill_tree(proc)
        jobs.update(_job, state="error", cancelable=False, message="llama-server no terminó de cargar en 10 minutos.")

    threading.Thread(target=wait_ready, daemon=True).start()
    return jobs.public(_job)


def stop_llamacpp():
    """Apaga el llama-server que prendió el motor (libera la memoria de la placa). Los de afuera no se tocan."""
    if _job["state"] == "running":
        _own["cancelled"] = True
        _job["cancelling"] = True
    osenv.kill_tree(_own["proc"])
    _own["proc"] = None
    _cache["value"] = None
    return {"state": "stopped"}
