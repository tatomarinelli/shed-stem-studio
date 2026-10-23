"""Diagnóstico de la interfaz: cuando una portada falla o tarda demasiado, el navegador avisa y queda una línea en <dataDir>/diag/covers.log.

Es solo local y acotado (últimas 200 líneas, 300 caracteres por campo). Sirve para saber POR QUÉ falla una portada en el navegador real del usuario
(conexiones ocupadas, lentitud, error del motor...) cuando no se puede reproducir en una prueba. No guarda nada del contenido de la música.
"""
import json
import re
import time
from pathlib import Path

import settings

MAX_LINES = 200
FIELDS = ("src", "kind", "tries", "ms", "online", "visible", "connections", "screen")


def _clean(v):
    return v if isinstance(v, (bool, int, float)) else re.sub(r"[\x00-\x1f]", " ", str(v))[:300]


def cover(body):
    """Registra un aviso de portada. Devuelve True si se guardó. Ignora cuerpos inválidos."""
    if not isinstance(body, dict) or not str(body.get("src") or "").startswith("/engine/"):
        return False
    entry = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), **{k: _clean(body[k]) for k in FIELDS if k in body}}
    f = Path(settings.effective()["dataDir"]) / "diag" / "covers.log"
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        lines = (f.read_text(encoding="utf-8").splitlines() if f.exists() else [])[-(MAX_LINES - 1):]
        f.write_text("\n".join(lines + [json.dumps(entry, ensure_ascii=False)]) + "\n", encoding="utf-8")
        return True
    except OSError:
        return False
