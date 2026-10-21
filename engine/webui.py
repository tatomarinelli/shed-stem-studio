"""Sirve la interfaz construida (proto/player/dist) desde el motor, con el aislamiento de origen (COOP/COEP) que necesita el reproductor.
Es lo que hace nginx en Docker; en el escritorio la ventana carga esta misma dirección. Solo lectura y solo dentro de la carpeta de la interfaz."""
import mimetypes
import os
from pathlib import Path

mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")

ISOLATION = {"Cross-Origin-Opener-Policy": "same-origin", "Cross-Origin-Embedder-Policy": "require-corp"}


def root():
    """STEMSHED_UI manda; si no, la compilación del repo. None si no hay interfaz construida."""
    env = os.environ.get("STEMSHED_UI")
    p = Path(env) if env else Path(__file__).resolve().parent.parent / "proto" / "player" / "dist"
    return p if (p / "index.html").is_file() else None


def resolve(ui_root, url_path):
    """Archivo de la interfaz para una ruta, o None. Nunca sale de la carpeta (../, rutas absolutas, enlaces)."""
    rel = url_path.lstrip("/") or "index.html"
    try:
        f = (ui_root / rel).resolve()
        f.relative_to(ui_root.resolve())
    except (ValueError, OSError):
        return None
    return f if f.is_file() else None


def headers_for(f):
    """(tipo, cabeceras): lo versionado por Vite (assets/) se cachea; el resto, no."""
    mime = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
    h = dict(ISOLATION)
    h["Cache-Control"] = "public, max-age=31536000, immutable" if f.parent.name == "assets" else "no-store"
    return mime, h
