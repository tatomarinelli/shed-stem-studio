"""Ciclo de vida del motor: al cerrarse (señal, Ctrl+C, apagado normal o caída) no deben quedar procesos hijos huérfanos.

Problema real (2026-10-22): el motor lanza su propio Ollama (y llama-server, la separación, ffmpeg, pip) y no hacía nada al cerrarse: con `kill` o Ctrl+C el Ollama quedaba vivo,
ocupaba el puerto 11500 con la carpeta de modelos equivocada y el motor siguiente no veía los modelos. En Windows ya existe un Job Object (`osenv.kill_children_on_exit`); esto es el equivalente
para Linux y macOS:
  1. se registran los hijos que corresponden (lista cerrada de programas: nunca un navegador ni el explorador de archivos que el usuario abrió desde la app);
  2. SIGTERM / SIGINT / SIGHUP y la salida normal apagan el servidor y después a esos hijos (SIGTERM, y SIGKILL si no responden);
  3. como un SIGKILL del motor no se puede atrapar, los hijos quedan anotados en `children.json` (pid + momento de inicio) y el motor siguiente termina los que sigan vivos antes de arrancar.
`start()` se llama solo desde el arranque del servidor (los tests no lo activan).
"""
import atexit
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import osenv

# Programas que el motor lanza y que tienen que morir con él (por nombre de ejecutable). Todo lo demás (navegador, explorador de archivos, xdg-open) es del usuario y no se toca.
TRACK = ("ollama", "llama-server", "ffmpeg", "ffprobe", "nvidia-smi", "pip", "audio-separator", "python")
_children = {}          # pid -> Popen
_lock = threading.Lock()
_state = {"started": False, "httpd": None, "cleaned": False}


def file():
    return osenv.config_dir() / "children.json"


def exe_name(argv0):
    n = os.path.basename(str(argv0)).lower()
    return n[:-4] if n.endswith(".exe") else n


def should_track(args):
    """¿Es un hijo que tiene que morir con el motor? Por el nombre del programa (lista cerrada)."""
    argv0 = args[0] if isinstance(args, (list, tuple)) and args else args if isinstance(args, str) else ""
    n = exe_name(str(argv0).split()[0] if isinstance(argv0, str) and " " in str(argv0) else argv0)
    return any(n == t or (t == "python" and n.startswith("python")) for t in TRACK)


def _start_ticks(pid):
    """Momento de inicio del proceso (ticks desde el arranque, /proc/<pid>/stat) para no confundir un pid reciclado con el que anotamos. None si no hay /proc o no existe."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        return int(stat.rsplit(")", 1)[1].split()[19])
    except (OSError, ValueError, IndexError):
        return None


def _read():
    try:
        data = json.loads(file().read_text())
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _write(items):
    try:
        f = file()
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_name(f"{f.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(items))
        tmp.replace(f)
    except OSError:
        pass


def register(proc, label=None):
    """Anota un hijo para apagarlo al cerrar (y, si hay /proc, en children.json por si el motor cae de golpe)."""
    with _lock:
        _children[proc.pid] = proc
        ticks = _start_ticks(proc.pid)
        if ticks is not None:
            items = [i for i in _read() if i.get("pid") != proc.pid and _alive(i)]
            items.append({"pid": proc.pid, "ticks": ticks, "exe": label or exe_name(getattr(proc, "args", [""])[0] if isinstance(getattr(proc, "args", None), (list, tuple)) else "")})
            _write(items)


def _alive(item):
    return _start_ticks(item["pid"]) == item.get("ticks")


def reap_stale():
    """Termina los hijos de un motor anterior que sigan vivos (cierre brusco). Solo los que siguen siendo el mismo proceso (mismo pid y mismo momento de inicio). Devuelve los pids terminados."""
    killed = []
    for item in _read():
        pid = item.get("pid")
        if not isinstance(pid, int) or pid == os.getpid() or not _alive(item):
            continue
        try:
            os.kill(pid, signal.SIGTERM)
            killed.append(pid)
        except OSError:
            continue
    deadline = time.time() + 5
    while killed and time.time() < deadline and any(_start_ticks(p) is not None for p in killed):
        time.sleep(0.1)
    for pid in killed:
        if _start_ticks(pid) is not None:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
    _write([])
    return killed


def terminate_all(timeout=5.0):
    """SIGTERM a los hijos registrados que sigan vivos y, a los que no respondan, SIGKILL. Devuelve cuántos había vivos."""
    with _lock:
        procs = [p for p in _children.values() if p.poll() is None]
    for p in procs:
        try:
            p.terminate()
        except OSError:
            pass
    deadline = time.time() + timeout
    for p in procs:
        try:
            p.wait(max(0.0, deadline - time.time()))
        except subprocess.TimeoutExpired:
            try:
                p.kill()
            except OSError:
                pass
    with _lock:
        _children.clear()
    _write([i for i in _read() if _alive(i)])
    return len(procs)


def cleanup():
    """Apaga lo que levantó el motor. Seguro de llamar varias veces (señal + salida normal)."""
    with _lock:
        if _state["cleaned"]:
            return
        _state["cleaned"] = True
    for name, fn in (("models", "stop_own_ollama"), ("llmdetect", "stop_llamacpp")):
        try:
            getattr(__import__(name), fn)()
        except Exception:
            pass
    try:
        __import__("resources").SAMPLER.stop()
    except Exception:
        pass
    terminate_all()


class _TrackedPopen(subprocess.Popen):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        if should_track(a[0] if a else k.get("args")):
            register(self)


def _on_signal(signum, _frame):
    httpd = _state["httpd"]
    if httpd:
        threading.Thread(target=httpd.shutdown, daemon=True).start()  # serve_forever vuelve y el arranque llama a cleanup()
    else:
        sys.exit(0)  # todavía no hay servidor: la salida normal dispara atexit -> cleanup()


def start():
    """Activa el ciclo de vida: termina hijos viejos, registra los nuevos, atrapa las señales y limpia al salir. Solo desde el arranque del motor."""
    if _state["started"]:
        return
    _state["started"] = True
    reap_stale()
    subprocess.Popen = _TrackedPopen
    atexit.register(cleanup)
    if threading.current_thread() is threading.main_thread():
        for name in ("SIGTERM", "SIGINT", "SIGHUP"):
            sig = getattr(signal, name, None)
            if sig is not None:
                signal.signal(sig, _on_signal)


def bind(httpd):
    _state["httpd"] = httpd
