"""Biblioteca de música local: recorre las carpetas elegidas y lee etiquetas con ffprobe (con índice en disco)."""
import hashlib
import json
import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import settings

EXTS = {".flac", ".mp3", ".m4a", ".wav", ".ogg", ".opus", ".aac", ".aiff", ".aif"}
INDEX = settings.CONFIG_DIR / "library-index.json"
_lock = threading.Lock()
_state = {"scanning": False, "scanned": 0, "total": 0, "tracks": {}}
_paths = {}  # id -> ruta. Solo el motor conoce las rutas: la interfaz nunca manda una ruta, manda un id.


def file_id(path):
    return "L" + hashlib.sha1(path.encode()).hexdigest()[:12]


def path_for(track_id):
    return _paths.get(track_id)


def _load_index():
    try:
        return json.loads(INDEX.read_text())
    except (OSError, ValueError):
        return {}


def _probe(path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:format_tags=title,artist,album,album_artist,genre,date",
                              "-of", "json", path], capture_output=True, text=True, timeout=20).stdout
        fmt = json.loads(out).get("format", {})
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    tags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}
    stem = Path(path).stem
    return {"title": tags.get("title") or stem, "artist": tags.get("artist") or tags.get("album_artist") or "",
            "album": tags.get("album") or "", "duration": round(float(fmt["duration"])) if fmt.get("duration") else None,
            "genre": tags.get("genre") or "", "year": int(tags["date"][:4]) if tags.get("date", "")[:4].isdigit() else None}


def scan():
    with _lock:
        if _state["scanning"]:
            return
        _state.update(scanning=True, scanned=0, total=0)
    threading.Thread(target=_work, daemon=True).start()


def _work():
    try:
        folders = settings.load()["musicFolders"]
        files = []
        for folder in folders:
            for root, _, names in os.walk(folder, onerror=lambda e: None):
                for n in names:
                    if Path(n).suffix.lower() in EXTS:
                        files.append((folder, os.path.join(root, n)))
        _state["total"] = len(files)
        index, new_index, tracks = _load_index(), {}, {}

        def one(item):
            folder, path = item
            try:
                st = os.stat(path)
            except OSError:
                return
            key = f"{st.st_mtime_ns}:{st.st_size}"
            hit = index.get(path)
            meta = hit["meta"] if hit and hit["key"] == key and "genre" in hit["meta"] else _probe(path)
            _state["scanned"] += 1
            if meta:
                new_index[path] = {"key": key, "meta": meta}
                tid = file_id(path)
                _paths[tid] = path
                tracks[tid] = {"id": tid, **meta, "folder": folder, "rel": os.path.relpath(path, folder)}

        with ThreadPoolExecutor(4) as ex:
            list(ex.map(one, files))
        settings.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        INDEX.write_text(json.dumps(new_index))
        os.chmod(INDEX, 0o600)
        _state["tracks"] = tracks
    finally:
        _state["scanning"] = False


def report():
    return {"scanning": _state["scanning"], "scanned": _state["scanned"], "total": _state["total"],
            "folders": settings.load()["musicFolders"],
            "tracks": sorted(_state["tracks"].values(), key=lambda t: (t["artist"].lower(), t["title"].lower()))}


def meta_for(track_id):
    t = _state["tracks"].get(track_id)
    return {"title": t["title"], "artist": t["artist"]} if t else {"title": track_id, "artist": ""}


def _norm(text):
    import re
    import unicodedata

    t = unicodedata.normalize("NFD", str(text).lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in t if not unicodedata.combining(c))).strip()


def find_track(artist, title, album=""):
    """Un archivo local que coincida con la referencia (título y artista normalizados)."""
    wt, wa, wb = _norm(title), _norm(artist), _norm(album)
    best = None
    for t in _state["tracks"].values():
        if _norm(t["title"]) == wt and (not t["artist"] or wa in _norm(t["artist"]) or _norm(t["artist"]) in wa):
            if wb and _norm(t["album"]) == wb:
                return t
            best = best or t
    return best


def find_album(artist, album):
    wb, wa = _norm(album), _norm(artist)
    tracks = [t for t in _state["tracks"].values() if _norm(t["album"]) == wb and (not t["artist"] or wa in _norm(t["artist"]) or _norm(t["artist"]) in wa)]
    return sorted(tracks, key=lambda t: t["rel"])
