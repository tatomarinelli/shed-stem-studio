#!/usr/bin/env python3
"""Modo desarrollo "en caliente" para Windows: abrí http://127.0.0.1:5173/ en el navegador.

  - Interfaz (proto/player): servidor de Vite; cada cambio en src/ se ve al instante, sin compilar.
  - Motor (engine/*.py): se reinicia solo al guardar un .py (Python no recarga módulos). Los cambios de motor tardan ~2 s.
Sin ventanas: solo procesos de fondo. Ctrl+C corta los dos. La tarea diaria automática no corre en este modo.
Uso:  python windows/dev.py [puerto_del_motor]   (por defecto 8770)
"""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE, UI = ROOT / "engine", ROOT / "proto" / "player"
PORT = sys.argv[1] if len(sys.argv) > 1 else "8770"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def snapshot():
    return {p: p.stat().st_mtime_ns for p in ENGINE.glob("*.py")}


def start_engine():
    env = {**os.environ, "STEMSHED_NO_SCHEDULER": "1", "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1"}
    return subprocess.Popen([sys.executable, str(ENGINE / "server.py"), PORT], cwd=ENGINE, env=env, creationflags=NO_WINDOW)


def kill_tree(proc):
    if proc.poll() is None:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)


def main():
    if not (UI / "node_modules").exists():
        subprocess.run("npm install", cwd=UI, shell=True, check=True)
    npm = "npm.cmd" if os.name == "nt" else "npm"
    env = {**os.environ, "STEMSHED_ENGINE_URL": f"http://127.0.0.1:{PORT}"}
    vite = subprocess.Popen([npm, "run", "dev"], cwd=UI, env=env, creationflags=NO_WINDOW)
    engine, seen = start_engine(), snapshot()
    print(f"Interfaz: http://127.0.0.1:5173/   Motor: http://127.0.0.1:{PORT}  (Ctrl+C para cortar)", flush=True)
    try:
        while True:
            time.sleep(1)
            now = snapshot()
            if now != seen:
                time.sleep(0.5)  # el editor puede estar escribiendo varios archivos
                seen = snapshot()
                print("Cambió el motor: reiniciando…", flush=True)
                kill_tree(engine)
                engine = start_engine()
            elif engine.poll() is not None:
                print("El motor se cerró (probablemente un error). Guardá un cambio para reintentar.", flush=True)
                seen = now
                while snapshot() == seen and vite.poll() is None:
                    time.sleep(1)
                seen = snapshot()
                engine = start_engine()
            if vite.poll() is not None:
                print("Vite se cerró.", flush=True)
                break
    except KeyboardInterrupt:
        pass
    finally:
        kill_tree(engine)
        kill_tree(vite)


if __name__ == "__main__":
    main()
