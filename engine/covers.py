"""Portadas de los discos recomendados.

Orden: caché en disco → TIDAL (CDN rápido, solo si hay sesión y el disco está) → Cover Art Archive (depende de archive.org, que a veces
tarda mucho). Lo que no se encuentra se recuerda unas horas para no volver a esperar. Se prepara en segundo plano apenas hay
recomendación, así cuando la pantalla las pide ya están. Las imágenes se guardan en `<dataDir>/covers`.
"""
import threading
import time
import urllib.request
from pathlib import Path

import settings

UA = "ShedStemStudio/0.0.1 (prototipo local)"
NEG_TTL = 6 * 3600       # tiempo que se recuerda que un disco no tiene portada
CAA_TIMEOUT = 15
MIN_BYTES = 800          # menos que esto no es una imagen
_inflight = {}
_lock = threading.Lock()


def _dir():
    return Path(settings.effective()["dataDir"]) / "covers"


def _read_cache(mbid):
    """bytes si hay portada guardada; b"" si se sabe que no hay (y es reciente); None si no hay nada guardado."""
    d = _dir()
    f = d / f"{mbid}.img"
    if f.is_file():
        return f.read_bytes()
    n = d / f"{mbid}.none"
    if n.is_file() and time.time() - n.stat().st_mtime < NEG_TTL:
        return b""
    return None


def _write(mbid, data):
    d = _dir()
    d.mkdir(parents=True, exist_ok=True)
    if data:
        (d / f"{mbid}.img").write_bytes(data)
        (d / f"{mbid}.none").unlink(missing_ok=True)
    else:
        (d / f"{mbid}.none").write_bytes(b"")


def _tidal(artist, album):
    import tidal_source

    r = tidal_source.album_tracks(artist, album)
    if not r.get("album"):
        return None
    return tidal_source.album_art(r["album"]["id"])


def _caa(mbid):
    req = urllib.request.Request(f"https://coverartarchive.org/release-group/{mbid}/front-500", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=CAA_TIMEOUT) as r:
        return r.read()


def _meta(mbid):
    """(artista, disco) de una recomendación reciente, para buscar en TIDAL."""
    import recs

    last = recs._read_json(recs.LAST, {}) or {}
    for kind in ("daily", "request"):
        res = last.get(kind) or {}
        for it in [res.get("pick"), *(res.get("alternatives") or [])]:
            if it and it.get("mbid") == mbid:
                return it["artist"], it["album"]
    return None, None


def get(mbid, artist=None, album=None):
    """bytes de la imagen o None. Una sola búsqueda a la vez por disco; las demás esperan y leen la caché."""
    hit = _read_cache(mbid)
    if hit is not None:
        return hit or None
    with _lock:
        waiting = _inflight.get(mbid)
        if waiting is None:
            _inflight[mbid] = threading.Event()
    if waiting is not None:
        waiting.wait(40)
        hit = _read_cache(mbid)
        return hit or None
    try:
        if artist is None:
            artist, album = _meta(mbid)
        data = None
        if artist and album:
            try:
                data = _tidal(artist, album)
            except Exception:
                data = None
        if not data or len(data) < MIN_BYTES:
            try:
                data = _caa(mbid)
            except Exception:
                data = None
        data = data if data and len(data) >= MIN_BYTES else None
        _write(mbid, data)
        return data
    finally:
        with _lock:
            _inflight.pop(mbid).set()


def prefetch(items):
    """items: [(mbid, artista, disco)]. Las baja en segundo plano, de a una por hilo."""
    for mbid, artist, album in items:
        threading.Thread(target=get, args=(mbid, artist, album), daemon=True).start()
