"""Separación en stems desde TIDAL: baja el tema a un temporal, lo separa con un modelo local y guarda solo los stems.

Adaptado de tidalrecs/stems.py (código propio del cliente de TIDAL para Linux). El audio original vive únicamente
mientras se separa y se borra enseguida; los stems (que suman la mezcla) son lo único que se conserva.
Uso personal con la sesión del propio usuario.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(os.environ.get("STEMSHED_DATA", "/mnt/plexdata/stemshed"))  # caché nueva: la vieja es de solo lectura
ENV = Path(os.environ.get("STEMS_ENV", "/mnt/plexdata/tidal-stems"))     # venv y modelos ya instalados
MODEL = "roformer"
MODEL_FILE = "BS-Roformer-SW.ckpt"
STEM_NAMES = ["guitar", "bass", "drums", "piano", "vocals", "other"]
SILENT_DB = -60.0
SAMPLE_RATE = 44100
TQDM_BAR = re.compile(r"(\d{1,3})%\|[^|]*\|")

CACHE = ROOT / "cache"
MODELS_DIR = ENV / "models"   # modelos de separación; se descargan solo desde Ajustes (nunca solos)
SEP_FILES = (MODEL_FILE, "BS-Roformer-SW.yaml")
OLD_CACHE = ENV / "cache"  # caché del cliente de TIDAL: solo lectura, nunca se escribe
LOCAL_ID = re.compile(r"^L[0-9a-f]{12}$")


def configure(data_dir, env_dir, models_dir=None):
    """Aplica las carpetas elegidas en Ajustes."""
    global ROOT, ENV, CACHE, OLD_CACHE, MODELS_DIR
    ROOT, ENV = Path(data_dir), Path(env_dir)
    CACHE, OLD_CACHE = ROOT / "cache", ENV / "cache"
    MODELS_DIR = Path(models_dir) if models_dir else ENV / "models"


def sep_model_present():
    return all((MODELS_DIR / f).is_file() for f in SEP_FILES)


_dl = {"state": "idle", "percent": 0, "message": "", "done": 0, "total": 0, "rate": 0}
_dl_lock = threading.Lock()


def sep_download_status():
    return dict(_dl)


def sep_download_start():
    """Descarga el modelo de separación a la carpeta elegida. Solo la dispara un clic explícito en Ajustes."""
    py_sep = ENV / "venv" / "bin" / "audio-separator"
    if not py_sep.exists():
        raise StemsError("Falta el entorno de separación en " + str(ENV))
    with _dl_lock:
        if _dl["state"] == "running":
            raise StemsError("Ya hay una descarga en curso.")
        _dl.update(state="running", percent=0, message="", done=0, total=0, rate=0)

    def work():
        try:
            MODELS_DIR.mkdir(parents=True, exist_ok=True)

            def progress(kind, pct):
                _dl["percent"] = pct

            def on_line(line):
                got = parse_transfer(line)
                if got:
                    _dl.update(got)

            code, tail = run_separator([str(py_sep), "--download_model_only", "--model_filename", MODEL_FILE, "--model_file_dir", str(MODELS_DIR)],
                                       {**os.environ}, progress, on_line)
            if code != 0 or not sep_model_present():
                raise StemsError("No se pudo descargar: " + (tail.strip().splitlines() or ["sin salida"])[-1][:200])
            _dl.update(state="done", percent=100)
        except Exception as e:
            _dl.update(state="error", message=str(e) if isinstance(e, StemsError) else f"No se pudo descargar: {type(e).__name__}")

    threading.Thread(target=work, daemon=True).start()
    return dict(_dl)


def norm_id(track_id):
    """Id de TIDAL (numérico) o de un archivo local (L + 12 hex). Cualquier otra cosa es un error."""
    track_id = str(track_id)
    if LOCAL_ID.match(track_id):
        return track_id
    return str(int(track_id))


class StemsError(Exception):
    pass


def cache_dir(track_id):
    return CACHE / norm_id(track_id) / MODEL


def is_cached(track_id):
    return (cache_dir(track_id) / "manifest.json").exists() or (OLD_CACHE / norm_id(track_id) / MODEL / "manifest.json").exists()


def canonical(filename):
    found = re.search(r"\(([^)]+)\)", filename)
    name = found.group(1).lower() if found else ""
    if name not in STEM_NAMES:
        raise StemsError(f"El modelo devolvió un stem desconocido: {filename}")
    return name


def fetch_source(session, track_id, out_wav, tmp):
    """El tema en calidad lossless como WAV estéreo de 44,1 kHz (BTS es una URL; DASH necesita su MPD)."""
    import tidalapi

    session.config.quality = tidalapi.Quality.high_lossless
    stream = session.track(int(track_id)).get_stream()
    manifest = stream.get_stream_manifest()
    if manifest.is_bts:
        if manifest.encryption_type not in (None, "", "NONE"):
            raise StemsError("TIDAL devolvió un stream cifrado; no se puede usar.")
        source, extra = manifest.get_urls()[0], []
    else:
        mpd = Path(tmp) / "track.mpd"
        mpd.write_text(stream.get_manifest_data())
        source, extra = str(mpd), ["-protocol_whitelist", "file,http,https,tcp,tls,crypto"]
    run = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *extra, "-i", source, "-ar", str(SAMPLE_RATE), "-ac", "2",
                          "-c:a", "pcm_s16le", str(out_wav)], capture_output=True, text=True)
    if run.returncode != 0:
        raise StemsError("No pude bajar el audio del tema: " + (run.stderr.strip().splitlines() or ["ffmpeg falló"])[-1])


UNITS = {"": 1, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9}
TRANSFER = re.compile(r"(\d+(?:\.\d+)?)([kKMG]?)B?/(\d+(?:\.\d+)?)([kKMG]?)B?\s*\[[^\]]*?(\d+(?:\.\d+)?)\s?([kKMG]?)B/s\]")


def parse_transfer(line):
    """Línea de tqdm de una descarga ("45%|...| 300M/670M [00:10<00:12, 25.1MB/s]") -> bytes hechos, totales y velocidad."""
    m = TRANSFER.search(line)
    if not m:
        return None
    n = lambda v, u: float(v) * UNITS.get(u, 1)
    return {"done": int(n(m.group(1), m.group(2))), "total": int(n(m.group(3), m.group(4))), "rate": int(n(m.group(5), m.group(6)))}


def parse_progress(chunk):
    found = TQDM_BAR.search(chunk)
    if not found:
        return None
    return ("model" if "iB/s" in chunk or "iB]" in chunk else "separate", int(found.group(1)))


def run_separator(cmd, env, progress, on_line=None):
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    tail, last, buffer = [], None, b""
    while True:
        data = proc.stdout.read1(4096)
        if not data:
            break
        buffer += data
        parts = re.split(rb"[\r\n]", buffer)
        buffer = parts.pop()
        for raw in parts:
            line = raw.decode("utf-8", "replace")
            if not line.strip():
                continue
            tail = (tail + [line])[-12:]
            if on_line:
                on_line(line)
            event = parse_progress(line)
            if event and event != last:
                last = event
                progress(*event)
    proc.wait()
    return proc.returncode, "\n".join(tail)


def track_meta(session, track_id):
    try:
        track = session.track(int(track_id))
        return {"title": track.name, "artist": track.artist.name if track.artist else ""}
    except Exception:
        return {"title": str(track_id), "artist": ""}


def fetch_local(path, out_wav):
    run = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-ar", str(SAMPLE_RATE), "-ac", "2",
                          "-c:a", "pcm_s16le", str(out_wav)], capture_output=True, text=True)
    if run.returncode != 0:
        raise StemsError("No pude leer el archivo: " + (run.stderr.strip().splitlines() or ["ffmpeg falló"])[-1])


def separate(session, track_id, progress):
    py, sep = ENV / "venv" / "bin" / "python", ENV / "venv" / "bin" / "audio-separator"
    if not py.exists() or not sep.exists():
        raise StemsError("Falta el entorno de separación en " + str(ENV))
    if not sep_model_present():  # sin esto, audio-separator lo bajaría solo
        raise StemsError("Falta el modelo de separación. Descargalo en Ajustes.")
    (ROOT / "tmp").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as tmp:  # el audio original no sale de este bloque
        source = Path(tmp) / "source.wav"
        if LOCAL_ID.match(str(track_id)):
            import library

            path = library.path_for(track_id)
            if not path:
                raise StemsError("Ese archivo ya no está en la biblioteca. Volvé a escanear la carpeta.")
            progress("download", 0)
            meta = library.meta_for(track_id)
            fetch_local(path, source)
        else:
            progress("download", 0)
            meta = track_meta(session, track_id)
            fetch_source(session, track_id, source, tmp)
        out = Path(tmp) / "out"
        out.mkdir()
        progress("separate", 0)
        code, tail = run_separator(
            [str(sep), str(source), "--model_filename", MODEL_FILE, "--model_file_dir", str(MODELS_DIR),
             "--output_dir", str(out), "--output_format", "FLAC"], {**os.environ, "TMPDIR": str(ROOT / "tmp")}, progress)
        files = sorted(out.glob("*.flac"))
        if code != 0 or not files:
            raise StemsError("La separación falló: " + (tail.strip().splitlines() or ["sin salida"])[-1][:200])
        target = cache_dir(track_id)
        shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True)
        for path in files:
            shutil.move(str(path), target / f"{canonical(path.name)}.flac")
    progress("measure", 100)
    probe = subprocess.run([str(py), str(Path(__file__).with_name("stems_probe.py")), str(target)], capture_output=True, text=True)
    if probe.returncode != 0:
        shutil.rmtree(target, ignore_errors=True)
        raise StemsError("No pude medir los stems: " + (probe.stderr.strip().splitlines() or ["sin salida"])[-1][:200])
    measured = json.loads(probe.stdout)
    stems = [{"name": n, "file": f"{n}.flac", "rms_db": round(measured[f"{n}.flac"]["rms_db"], 1),
              "silent": measured[f"{n}.flac"]["rms_db"] < SILENT_DB} for n in STEM_NAMES if f"{n}.flac" in measured]
    manifest = {"track_id": norm_id(track_id), "model": MODEL, "label": "RoFormer (mejor separación)",
                "duration": max(m["duration"] for m in measured.values()), "dir": str(target), "stems": stems,
                "created": time.time(), **meta}
    (target / "manifest.json").write_text(json.dumps(manifest))
    return manifest


# --- un solo trabajo a la vez (la GPU es una sola)
_jobs = {}
_jobs_lock = threading.Lock()


def start(session, track_id):
    track_id = norm_id(track_id)
    if LOCAL_ID.match(track_id):
        import library

        if not library.path_for(track_id):
            raise StemsError("Ese archivo no está en la biblioteca. Volvé a leer las carpetas e intentá de nuevo.")
    with _jobs_lock:
        if is_cached(track_id):
            return {"state": "done", "cached": True}
        if any(j["state"] == "running" for j in _jobs.values()):
            raise StemsError("Ya hay una separación en curso: esperá a que termine.")
        _jobs[track_id] = {"state": "running", "stage": "download", "percent": 0, "message": ""}

    def progress(stage, percent):
        _jobs[track_id].update(stage=stage, percent=percent)

    def work():
        try:
            separate(session, track_id, progress)
            _jobs[track_id].update(state="done", stage="done", percent=100)
        except Exception as e:
            _jobs[track_id].update(state="error", message=str(e) if isinstance(e, StemsError) else f"Falló: {type(e).__name__}")

    threading.Thread(target=work, daemon=True).start()
    return dict(_jobs[track_id])


def job_status(track_id):
    track_id = norm_id(track_id)
    job = _jobs.get(track_id)
    if job:
        return dict(job)
    return {"state": "done", "cached": True} if is_cached(track_id) else {"state": "idle"}


def list_separated():
    """Todo lo separado en las dos cachés, con tamaño y si se puede borrar (la caché vieja es de solo lectura)."""
    out = {}
    for base, writable in ((CACHE, True), (OLD_CACHE, False)):
        if not base.exists():
            continue
        for d in base.iterdir():
            mf = d / MODEL / "manifest.json"
            if d.name in out or not mf.exists():
                continue
            try:
                m = json.loads(mf.read_text())
            except (OSError, ValueError):
                continue
            size = sum(f.stat().st_size for f in (d / MODEL).rglob("*") if f.is_file())
            out[d.name] = {"id": d.name, "title": m.get("title") or d.name, "artist": m.get("artist") or "", "duration": m.get("duration"),
                           "bytes": size, "writable": writable, "created": m.get("created")}
    return sorted(out.values(), key=lambda x: -(x["created"] or 0))


def stem_file(track_id, filename):
    """Archivo de un tema separado (manifest.json o <stem>.flac): primero la caché nueva, después la vieja. None si no existe."""
    track_id = norm_id(track_id)
    if not re.fullmatch(r"manifest\.json|[a-z]+\.flac", filename):
        return None
    for base in (CACHE, OLD_CACHE):
        f = base / track_id / MODEL / filename
        if f.is_file():
            return f
    return None


def tracks_index():
    """Lo separado, con los nombres de sus stems: lo que necesita el reproductor para cargar un tema."""
    out = []
    for t in list_separated():
        mf = stem_file(t["id"], "manifest.json")
        try:
            names = [x["name"] for x in json.loads(mf.read_text())["stems"]]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        out.append({"id": t["id"], "title": t["title"], "artist": t["artist"], "duration": t["duration"], "stems": names})
    return out


def delete_separated(track_id):
    """Borra los stems de un tema de la caché NUEVA. La vieja no se toca."""
    track_id = norm_id(track_id)
    target = CACHE / track_id
    if not target.exists():
        if (OLD_CACHE / track_id).exists():
            raise StemsError("Ese tema está en la caché anterior, que es de solo lectura.")
        raise StemsError("Ese tema no está separado.")
    with _jobs_lock:
        if _jobs.get(track_id, {}).get("state") == "running":
            raise StemsError("Se está separando ahora mismo.")
    shutil.rmtree(target)
    return {"deleted": track_id}
