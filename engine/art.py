"""Arte de los temas. No se guarda en disco: el navegador lo cachea (las respuestas llevan caché largo)."""
import subprocess
import urllib.request
from pathlib import Path

import library
import tidal_source

UA = "ShedStemStudio/0.0.1 (prototipo local)"
FOLDER_NAMES = ("cover.jpg", "folder.jpg", "front.jpg", "cover.png", "folder.png")


def _tidal(track_id):
    url = tidal_source.session().track(int(track_id)).album.image(320)
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=20) as r:
        return r.read()


def _local(track_id):
    path = library.path_for(track_id)
    if not path:
        return None
    run = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-an", "-frames:v", "1", "-vf", "scale=320:-2", "-f", "mjpeg", "pipe:1"],
                         capture_output=True, timeout=20)
    if run.returncode == 0 and run.stdout:
        return run.stdout
    for name in FOLDER_NAMES:  # sin imagen embebida: portada suelta en la carpeta
        f = Path(path).parent / name
        if f.is_file() and f.stat().st_size < 5_000_000:
            return f.read_bytes()
    return None


def for_track(track_id):
    """Bytes de la imagen o None. Cualquier falla de la fuente significa 'sin arte', no un error."""
    try:
        return _local(track_id) if str(track_id).startswith("L") else _tidal(track_id)
    except Exception:
        return None


def content_type(data):
    return "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"
