"""Similitud entre géneros con embeddings locales (nomic-embed-text en el Ollama propio, 274 MB, Apache-2.0).

Medido (docs/memory-format.md): en 40 pares etiquetados, el cruce por palabras separa relacionados de no relacionados
con AUC 0,55 (detecta 2 de 20 pares relacionados, p. ej. no ve soul jazz ~ hard bop); los embeddings, AUC 0,96.
Los no relacionados llegan a coseno 0,85, así que el coseno se usa como peso SUAVE, no como sí/no.
Vectores en caché (<dataDir>/recs/genre-emb.json): el vocabulario de géneros es chico. Sin el modelo, vuelve a palabras.
"""
import json
import math
import threading
import urllib.request
from pathlib import Path

MODEL = "nomic-embed-text"
LOW, HIGH = 0.83, 0.93   # coseno -> similitud: < LOW = 0, >= HIGH = 1, lineal en el medio
_cache = {}
_lock = threading.Lock()
_state = {"file": None, "ok": None}


def cos(a, b):
    return sum(x * y for x, y in zip(a, b)) / math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))


def soft(c):
    return max(0.0, min(1.0, (c - LOW) / (HIGH - LOW)))


def configure(data_dir, ollama_url):
    _state.update(file=Path(data_dir) / "recs" / "genre-emb.json", url=ollama_url)
    try:
        _cache.update(json.loads(_state["file"].read_text()))
    except (OSError, ValueError):
        pass


def _embed(texts):
    body = {"model": MODEL, "input": [f"classification: music genre {t}" for t in texts]}
    req = urllib.request.Request(_state["url"] + "/api/embed", json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["embeddings"]


def vectors(names):
    """{nombre: vector} para los que se pudo; vacío si el modelo no está."""
    if _state["ok"] is False or not _state.get("url"):
        return {}
    missing = [n for n in dict.fromkeys(names) if n not in _cache]
    if missing:
        try:
            for i in range(0, len(missing), 64):
                for n, v in zip(missing[i:i + 64], _embed(missing[i:i + 64])):
                    _cache[n] = [round(x, 5) for x in v]
            _state["ok"] = True
            with _lock:
                _state["file"].parent.mkdir(parents=True, exist_ok=True)
                _state["file"].write_text(json.dumps(_cache))
        except Exception:
            _state["ok"] = False  # sin el modelo: queda el cruce por palabras hasta reiniciar
            return {}
    return {n: _cache[n] for n in names if n in _cache}


def similarity(a, b, vecs, token_match):
    """Lo mejor entre el cruce por palabras y el coseno suavizado."""
    t = token_match(a, b)
    if a in vecs and b in vecs:
        return max(t, soft(cos(vecs[a], vecs[b])))
    return t
