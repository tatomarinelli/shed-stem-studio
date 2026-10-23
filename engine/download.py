"""Descarga de temas a archivos de audio (uno o varios) y "abrir en carpeta".

Solo la dispara un clic del usuario (nada se baja solo). Para TIDAL usa la misma sesión propia que ya usa la separación
(tidal_source) y la misma bajada (stems.download_source); para un archivo local, copia o convierte. El resultado es
`Artista - Título.ext` (o `Artista/Álbum/NN - Título.ext`) en la carpeta `downloadDir` de Ajustes, sin pisar nada que ya exista.
No separa: eso se decide después.

Calidades: original (lo que entrega la fuente), AAC alta y MP3 (320, 256, 192, 128) con ffmpeg. El perfil "iPod" fija MP3 128 o 192
CBR, ID3v2.3, 44,1 kHz, estéreo y nombres simples. Un lote baja de a un tema, en serie (TIDAL limita pedidos); una falla no corta el lote.
Si TIDAL pide esperar (límite de pedidos) se pausa y se reintenta ese tema con esperas de 30, 60 y 120 s; si sigue pidiendo, el lote se
corta con un mensaje claro y lo que falta queda sin bajar.

El audio original NO se guarda en ninguna caché del motor (la separación lo borra al terminar): un tema de TIDAL siempre se baja de nuevo.
Lo que sí se recuerda es lo ya descargado (índice en la carpeta de datos, por tema Y calidad), para no bajarlo dos veces.
"""
import errno
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

import jobs
import library
import osenv
import settings
import stems
import tidal_source

WINDOWS_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
MAX_STEM_BYTES = 180   # el nombre completo (con extensión) tiene que entrar en 255 bytes del sistema de archivos
AUDIO_EXTS = {".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav", ".aac", ".aiff", ".aif", ".mp4"}
COVER_PX = 500          # la carátula incrustada se achica a este lado máximo (JPEG)
RATE_WAITS = (30, 60, 120)   # segundos de espera si TIDAL pide esperar, antes de cortar
MAX_BATCH = 500

# Calidades: kbps = tasa fija (CBR) que se usa para estimar; TIDAL entrega AAC 320 en "alta".
QUALITIES = {
    "original": {"label": "Original (sin pérdida)", "hint": "FLAC o lo que entregue la fuente", "kind": "orig"},
    "aac": {"label": "AAC alta", "hint": "≈ 256-320 kbps, .m4a", "kind": "aac"},
    "mp3_320": {"label": "MP3 320", "hint": "CBR", "kind": "mp3", "kbps": 320},
    "mp3_256": {"label": "MP3 256", "hint": "CBR", "kind": "mp3", "kbps": 256},
    "mp3_192": {"label": "MP3 192", "hint": "CBR", "kind": "mp3", "kbps": 192},
    "mp3_128": {"label": "MP3 128", "hint": "CBR, el más chico", "kind": "mp3", "kbps": 128},
}
IPOD_QUALITIES = ("mp3_128", "mp3_192")
# Estimación del peso (duración x tasa de bits). Sin pérdida: FLAC 16 bits/44,1 kHz estéreo pesa ~60 % del PCM (1411 kbps), o sea ~850 kbps.
LOSSLESS_KBPS = 850
AAC_LOCAL_KBPS, AAC_TIDAL_KBPS = 256, 320
TAGS_BYTES = 40_000     # etiquetas y carátula de ≈500 px en MP3/AAC


class DownloadError(Exception):
    pass


class RateLimited(DownloadError):
    pass


_lock = threading.Lock()
_jobs = {}      # id del tema -> trabajo (estado, porcentaje, archivo...)
_holders = {}   # id del tema -> {"cancelled": bool, "proc": Popen}
_index_lock = threading.Lock()
_batch = {}     # el lote actual o el último (vacío si no hubo)


# --- carpetas e índice
def download_dir():
    return Path(settings.effective()["downloadDir"])


def _index_file():
    return Path(settings.effective()["dataDir"]) / "downloads-index.json"


def _read_index():
    """{ "id|calidad": {file, title, artist, quality, at} }. Las entradas viejas (solo el id) eran siempre la calidad original."""
    try:
        data = json.loads(_index_file().read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {(k if "|" in k else f"{k}|original"): v for k, v in data.items() if isinstance(v, dict) and v.get("file")}


def qkey(quality="original", ipod=False):
    """Clave de calidad en el índice: el mismo tema en FLAC y en MP3 son archivos distintos."""
    return quality + (":ipod" if ipod else "")


def _remember(track_id, key, file, title, artist):
    with _index_lock:
        index = _read_index()
        index[f"{track_id}|{key}"] = {"file": str(file), "title": title, "artist": artist, "quality": key, "at": time.time()}
        f = _index_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(index))
        os.replace(tmp, f)


def downloaded(track_id, key="original"):
    """Dato del archivo ya descargado de ese tema en esa calidad, o None si no está (o ya no existe en disco)."""
    hit = _read_index().get(f"{track_id}|{key}")
    if hit and Path(hit["file"]).is_file():
        return hit
    return None


# --- nombres
def sanitize(text):
    """Un pedazo de nombre de archivo que sirve en Linux, Windows y macOS."""
    t = re.sub(r'[\x00-\x1f\x7f<>:"/\\|?*]', "_", str(text or "")).strip()
    t = re.sub(r"\s+", " ", t).strip(" .")
    return t


def simple_name(text, limit=80):
    """Nombre para dispositivos viejos: sin acentos ni símbolos raros y corto."""
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9 ._()&,'+-]", "", t)
    t = re.sub(r"\s+", " ", t).strip(" .")
    return t[:limit].rstrip(" .")


def _clip(name, fallback):
    while len(name.encode("utf-8")) > MAX_STEM_BYTES:
        name = name[:-1]
    name = name.rstrip(" .") or fallback
    if name.split(".")[0].lower() in WINDOWS_RESERVED:
        name = "_" + name
    return name


def file_stem(artist, title, fallback="Tema", ipod=False):
    clean = simple_name if ipod else sanitize
    a, t = clean(artist), clean(title)
    name = f"{a} - {t}" if a and t else (t or a or fallback)
    return _clip(name, fallback)


def reserve(directory, stem, ext):
    """Crea (vacío) y devuelve un archivo nuevo `stem.ext`, o `stem (2).ext`, `stem (3).ext`... Nunca pisa uno existente."""
    n = 1
    while True:
        name = f"{stem}{ext}" if n == 1 else f"{stem} ({n}){ext}"
        path = Path(directory) / name
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644))
            return path
        except FileExistsError:
            n += 1


def friendly_os_error(e, directory):
    if e.errno == errno.ENOSPC:
        return f"No hay espacio en el disco de {directory}. Liberá lugar o elegí otra carpeta en Ajustes."
    if e.errno in (errno.EACCES, errno.EPERM, errno.EROFS):
        return f"No hay permiso para escribir en {directory}. Elegí otra carpeta en Ajustes."
    return f"No se pudo guardar en {directory}: {e.strerror or type(e).__name__}."


# --- calidades, ffmpeg y estimación
_encoders = {}


def have_ffmpeg():
    return bool(shutil.which("ffmpeg") or osenv.ensure_ffmpeg_on_path())


def has_mp3_encoder():
    """¿Este ffmpeg trae libmp3lame? (se mira una vez)"""
    if "mp3" not in _encoders:
        ok = False
        if have_ffmpeg():
            try:
                out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=15, **osenv.sys_flags()).stdout
                ok = "libmp3lame" in out
            except (OSError, subprocess.TimeoutExpired):
                ok = False
        _encoders["mp3"] = ok
    return _encoders["mp3"]


def options():
    """Calidades que ofrece la interfaz, con el motivo si alguna no se puede, y el espacio libre de la carpeta de descargas."""
    ff, mp3 = have_ffmpeg(), None
    mp3 = ff and has_mp3_encoder()
    out = []
    for qid, q in QUALITIES.items():
        reason = ""
        if q["kind"] != "orig" and not ff:
            reason = "Falta ffmpeg. Instalalo desde el asistente."
        elif q["kind"] == "mp3" and not mp3:
            reason = "Este ffmpeg no trae el codificador MP3 (libmp3lame)."
        out.append({"id": qid, "label": q["label"], "hint": q["hint"], "kind": q["kind"], "kbps": q.get("kbps"), "available": not reason, "reason": reason})
    return {"dir": str(download_dir()), "free": free_bytes(), "ffmpeg": ff, "mp3": bool(mp3), "qualities": out,
            "ipod": {"label": "iPod / dispositivo viejo", "hint": "MP3 128 o 192 CBR, ID3v2.3, 44,1 kHz, estéreo y nombres simples", "qualities": list(IPOD_QUALITIES)}}


def free_bytes():
    p = download_dir()
    while not p.exists() and p != p.parent:
        p = p.parent
    try:
        return shutil.disk_usage(p).free
    except OSError:
        return 0


def check_quality(quality, ipod):
    if quality not in QUALITIES:
        raise DownloadError("Calidad inválida.")
    if ipod and quality not in IPOD_QUALITIES:
        raise DownloadError("El perfil iPod usa MP3 128 o 192.")
    kind = QUALITIES[quality]["kind"]
    if kind != "orig" and not have_ffmpeg():
        raise DownloadError("Falta ffmpeg. Instalalo desde el asistente para convertir.")
    if kind == "mp3" and not has_mp3_encoder():
        raise DownloadError("Este ffmpeg no trae el codificador MP3 (libmp3lame). Elegí otra calidad.")


def item_id(item):
    """El id de audio de un pedido: directo, o el que elige el orden de fuentes entre sus ids. None si todavía hay que buscarlo."""
    import sources
    if isinstance(item.get("id"), str) and re.fullmatch(r"\d{1,12}|L[0-9a-f]{12}", item["id"]):
        return item["id"]
    ids = item.get("ids")
    if isinstance(ids, dict):
        got = sources.pick({k: v for k, v in ids.items() if k in ("local", "tidal") and isinstance(v, str)})
        return got["id"]
    return None


def _seconds(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 < v < 36000 else None


def estimate_item(track_id, seconds, quality, ipod=False):
    """Peso estimado de un tema: {bytes|None, exact, why}. Sin dato no se inventa: bytes None."""
    kind = QUALITIES[quality]["kind"]
    local = bool(track_id and stems.LOCAL_ID.match(track_id))
    path = library.path_for(track_id) if local else None
    if local:
        lib = library._state["tracks"].get(track_id) or {}
        seconds = lib.get("duration") or seconds
        if kind == "orig":
            try:
                return {"bytes": os.path.getsize(path), "exact": True, "why": "tamaño del archivo"}
            except (OSError, TypeError):
                return {"bytes": None, "exact": False, "why": "sin dato"}
    if not track_id:
        return {"bytes": None, "exact": False, "why": "sin dato"}
    if not seconds:
        return {"bytes": None, "exact": False, "why": "sin dato"}
    if kind == "orig":
        return {"bytes": int(seconds * LOSSLESS_KBPS * 125), "exact": False, "why": f"duración x {LOSSLESS_KBPS} kbps (FLAC típico)"}
    kbps = QUALITIES[quality].get("kbps") or (AAC_LOCAL_KBPS if local else AAC_TIDAL_KBPS)
    return {"bytes": int(seconds * kbps * 125) + TAGS_BYTES, "exact": kind == "mp3", "why": f"duración x {kbps} kbps"}


def estimate(items, quality, ipod=False):
    """Peso estimado de una selección. `items`: [{id | ids, seconds?}]. Devuelve el detalle por tema, el total, el espacio libre y si alcanza."""
    check_quality(quality, ipod)
    out, total, unknown, exact = [], 0, 0, True
    for it in items[:MAX_BATCH]:
        e = estimate_item(item_id(it) if isinstance(it, dict) else None, _seconds((it or {}).get("seconds")), quality, ipod)
        out.append(e)
        if e["bytes"] is None:
            unknown += 1
        else:
            total += e["bytes"]
            exact = exact and e["exact"]
    free = free_bytes()
    return {"items": out, "bytes": total, "unknown": unknown, "approx": not exact, "free": free, "enough": total + 50_000_000 <= free, "dir": str(download_dir())}


# --- trabajo
def _cancelled(track_id):
    return lambda: bool(_holders.get(track_id, {}).get("cancelled"))


def _check_dir():
    d = download_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise DownloadError(friendly_os_error(e, d))
    if not os.access(d, os.W_OK):
        raise DownloadError(f"No hay permiso para escribir en {d}. Elegí otra carpeta en Ajustes.")
    return d


def _busy():
    return any(j.get("state") == "running" for j in _jobs.values()) or _batch.get("state") == "running"


def _opts(quality, profile):
    ipod = profile == "ipod"
    if profile not in (None, "", "ipod"):
        raise DownloadError("Perfil inválido.")
    if ipod and quality not in IPOD_QUALITIES:
        quality = "mp3_128"
    check_quality(quality, ipod)
    return {"quality": quality, "ipod": ipod, "key": qkey(quality, ipod), "folders": False}


def _local_file(track_id):
    path = library.path_for(track_id)
    if not path or not os.path.isfile(path):
        raise DownloadError("Ese archivo ya no está en la biblioteca. Volvé a leer las carpetas e intentá de nuevo.")
    return path


def start(track_id, quality="original", profile=None):
    """Arranca la descarga de un tema (id de TIDAL o de un archivo local). Una a la vez."""
    track_id = stems.norm_id(track_id)
    opts = _opts(quality, profile)
    local_path = _local_file(track_id) if stems.LOCAL_ID.match(track_id) else None
    if not local_path:
        tidal_source.session()  # sin sesión de TIDAL falla ya, con el motivo (SourceError)
    hit = downloaded(track_id, opts["key"])
    if hit:
        return {"state": "done", "percent": 100, "already": True, "id": track_id, "file": hit["file"], "dir": str(download_dir())}
    directory = _check_dir()
    with _lock:
        if _busy():
            raise DownloadError("Ya hay una descarga en curso: esperá a que termine.")
        job = _new_job(track_id, directory, opts)
    threading.Thread(target=_run_job, args=(track_id, local_path, directory, job, opts), daemon=True).start()
    return jobs.public(job)


def _new_job(track_id, directory, opts):
    job = _jobs[track_id] = {}
    jobs.start(job, state="running", id=track_id, step="Preparando", percent=0, message="", title="", artist="", dir=str(directory),
               quality=opts["key"])
    _holders[track_id] = {}
    return job


def _is_rate_limited(e):
    status = getattr(getattr(e, "response", None), "status_code", None)
    return type(e).__name__ == "TooManyRequests" or status == 429 or (isinstance(e, urllib.error.HTTPError) and e.code == 429)


def _wait(job, track_id, seconds):
    end = time.time() + seconds
    cancelled = _cancelled(track_id)
    while time.time() < end:
        if cancelled():
            raise stems.Cancelled()
        jobs.update(job, step=f"TIDAL pidió esperar: reintento en {int(end - time.time()) + 1} s")
        time.sleep(1)


def _run_job(track_id, local_path, directory, job, opts):
    """Hace un tema de punta a punta y deja el resultado en `job` (done, error o cancelled). No lanza."""
    try:
        attempt = 0
        while True:
            try:
                _process(track_id, local_path, directory, job, opts)
                break
            except Exception as e:
                if _is_rate_limited(e) and not local_path:
                    if attempt >= len(RATE_WAITS):
                        raise RateLimited("TIDAL sigue pidiendo esperar (demasiados pedidos). Probá en unos minutos.")
                    jobs.update(job, percent=0)
                    _wait(job, track_id, RATE_WAITS[attempt])
                    attempt += 1
                    continue
                raise
        jobs.update(job, state="done", percent=100, step="Listo")
    except stems.Cancelled:
        jobs.update(job, state="cancelled", message="Cancelado", percent=0)
    except Exception as e:
        msg = _explain(e, directory)
        if not isinstance(e, (DownloadError, tidal_source.SourceError, OSError)):
            print(f"Descarga {track_id} falló: {e!r}"[:300], file=sys.stderr, flush=True)  # queda en engine.log
        jobs.update(job, state="error", message=msg, rate=isinstance(e, RateLimited))
    finally:
        _holders.pop(track_id, None)


def _explain(e, directory):
    if isinstance(e, DownloadError):
        return str(e)
    if isinstance(e, tidal_source.SourceError):
        return e.message
    if isinstance(e, stems.StemsError):
        return str(e)
    if isinstance(e, OSError) and not isinstance(e, urllib.error.URLError):
        return friendly_os_error(e, directory)
    if isinstance(e, urllib.error.HTTPError):
        return "TIDAL rechazó el pedido del audio (la dirección venció o no hay permiso). Probá de nuevo." if e.code in (401, 403) else f"TIDAL respondió con un error ({e.code})."
    if isinstance(e, (urllib.error.URLError, TimeoutError)):
        return "No pude conectar con TIDAL. Revisá la conexión."
    name = type(e).__name__
    status = getattr(getattr(e, "response", None), "status_code", None)
    if name in ("ObjectNotFound", "MetadataNotAvailable") or status == 404:
        return "Ese tema no está disponible en TIDAL."
    if _is_rate_limited(e):
        return "TIDAL pidió esperar un rato (demasiados pedidos). Probá en unos minutos."
    if status in (401, 403):
        return "TIDAL rechazó el pedido: reconectá la cuenta en Fuentes."
    return f"Falló la descarga ({name})."


# --- lectura de metadatos y armado del archivo
def _probe(file):
    """{codec, seconds, tags{title,artist,album,track,date}} de un archivo con ffprobe ({} si no se puede)."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                              "stream=codec_name:format=duration:format_tags", "-of", "json", str(file)],
                             capture_output=True, text=True, timeout=30, **osenv.sys_flags()).stdout
        data = json.loads(out)
        tags = {k.lower(): v for k, v in (data.get("format", {}).get("tags") or {}).items()}
        dur = data.get("format", {}).get("duration")
        return {"codec": (data.get("streams") or [{}])[0].get("codec_name", ""), "seconds": float(dur) if dur else None, "tags": tags}
    except (OSError, ValueError, KeyError, IndexError, subprocess.TimeoutExpired):
        return {}


def _int(v):
    m = re.match(r"\s*(\d+)", str(v or ""))
    return int(m.group(1)) if m else None


def _local_meta(track_id, path, probed):
    lib = library.meta_for(track_id)
    tags = probed.get("tags", {})
    year = _int(str(tags.get("date", ""))[:4])
    return {"title": lib["title"], "artist": lib["artist"], "album": tags.get("album", ""), "track": _int(tags.get("track")), "year": year}


def _tag_args(meta):
    tags = {"title": meta.get("title"), "artist": meta.get("artist"), "album": meta.get("album"),
            "track": meta.get("track"), "date": meta.get("year")}
    out = []
    for k, v in tags.items():
        if v not in (None, "", 0):
            out += ["-metadata", f"{k}={v}"]
    return out


CODEC_EXT = {"flac": ".flac", "aac": ".m4a", "alac": ".m4a", "mp3": ".mp3", "opus": ".opus", "vorbis": ".ogg"}
FORMATS = {".flac": "flac", ".m4a": "ipod", ".mp3": "mp3", ".opus": "opus", ".ogg": "ogg"}


def _run_ffmpeg(cmd, holder, seconds, job, lo=0, hi=99):
    """Corre ffmpeg con progreso (`-progress`); cancelable. Devuelve (ok, última línea de error)."""
    err = tempfile.TemporaryFile()
    proc = subprocess.Popen(cmd + ["-progress", "pipe:1", "-nostats"], stdout=subprocess.PIPE, stderr=err, text=True, **osenv.sys_flags())
    holder["proc"] = proc
    try:
        for line in proc.stdout:
            if holder.get("cancelled"):
                break
            if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                us = _int(line.split("=", 1)[1])
                if seconds and us:
                    jobs.update(job, percent=min(hi, lo + int((hi - lo) * (us / 1e6) / seconds)))
        proc.wait()
    finally:
        holder.pop("proc", None)
        if proc.poll() is None:
            osenv.kill_tree(proc)
        proc.stdout.close()
    if holder.get("cancelled"):
        err.close()
        raise stems.Cancelled()
    err.seek(0)
    tail = (err.read().decode("utf-8", "replace").strip().splitlines() or [""])[-1]
    err.close()
    return proc.returncode == 0, tail


def _make_cover(src, dst, holder, from_media):
    """Carátula JPEG de hasta COVER_PX px (baseline, sirve en iPods viejos). True si quedó; si no hay o falla, se omite."""
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src)]
    if from_media:
        cmd += ["-an", "-map", "0:v:0"]
    cmd += ["-frames:v", "1", "-vf", f"scale=min({COVER_PX}\\,iw):-2", "-pix_fmt", "yuvj420p", "-q:v", "3", str(dst)]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **osenv.sys_flags())
        holder["proc"] = p
        try:
            p.wait(timeout=30)
        except subprocess.TimeoutExpired:
            osenv.kill_tree(p)
            return False
        finally:
            holder.pop("proc", None)
        return p.returncode == 0 and Path(dst).exists() and Path(dst).stat().st_size > 0
    except OSError:
        return False


def _fetch_cover(url, dst):
    if not url or not str(url).startswith("https://resources.tidal.com/"):
        return False
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ShedStemStudio/0.0.3"})
        with urllib.request.urlopen(req, timeout=20) as r, open(dst, "wb") as f:
            f.write(r.read(5_000_000))
        return True
    except (OSError, urllib.error.URLError, TimeoutError):
        return False


def _dest(directory, meta, ext, opts, fallback_title):
    """Carpeta y nombre final (nuevo, sin pisar): plano, o Artista/Álbum/NN - Título con el número de pista."""
    clean = simple_name if opts["ipod"] else sanitize
    title, artist = meta.get("title") or fallback_title, meta.get("artist") or ""
    if opts["folders"]:
        folder = Path(directory) / _clip(clean(artist) or "Sin artista", "Sin artista") / _clip(clean(meta.get("album")) or "Sin álbum", "Sin álbum")
        folder.mkdir(parents=True, exist_ok=True)
        n = meta.get("track")
        t = clean(title) or fallback_title
        stem = _clip(f"{int(n):02d} - {t}" if n else t, fallback_title)
    else:
        folder, stem = Path(directory), file_stem(artist, title, ipod=opts["ipod"])
    return reserve(folder, stem, ext)


def _process(track_id, local_path, directory, job, opts):
    q, kind = opts["quality"], QUALITIES[opts["quality"]]["kind"]
    holder = _holders.setdefault(track_id, {})
    cancelled = _cancelled(track_id)
    tmp = Path(tempfile.mkdtemp(prefix=".descarga-", dir=directory))   # todo lo parcial vive acá y se borra al final
    try:
        cover_url = None
        if local_path:
            src = Path(local_path)
            probed = _probe(src)
            meta = _local_meta(track_id, src, probed)
            jobs.update(job, title=meta["title"], artist=meta["artist"])
            ext_src = src.suffix.lower()
        else:
            jobs.update(job, step="Pidiendo el tema a TIDAL")
            info = tidal_source.download_info(track_id, lossless=(kind != "aac"))
            meta, cover_url = info["meta"], info.get("cover")
            jobs.update(job, title=meta["title"], artist=meta["artist"], step="Bajando")
            src = tmp / "raw"
            encoding = kind != "orig"
            scale = 60 if encoding else 99

            def progress(_k, pct):
                jobs.update(job, percent=int(pct * scale / 100))
            stems.download_source(info["urls"], src, progress, cancelled)
            if cancelled():
                raise stems.Cancelled()
            probed = _probe(src)
            ext_src = (info["ext"] if info["bts"] and info["ext"].lower() in AUDIO_EXTS else "")
        seconds = probed.get("seconds")
        codec = probed.get("codec", "")
        title, artist = meta["title"], meta["artist"]
        if local_path:   # lo que falta en el disco se ve antes de empezar a copiar o convertir
            est = estimate_item(track_id, seconds, q, opts["ipod"])["bytes"] or os.path.getsize(src)
            if shutil.disk_usage(directory).free < est + 10_000_000:
                raise OSError(errno.ENOSPC, "sin espacio")
        out = tmp / "out"
        notes = []
        tagged = False
        if kind == "orig" and local_path:
            ext = ext_src
            jobs.update(job, step="Copiando")
            _copy_chunks(src, out, job, cancelled)
            tagged = True   # el archivo propio ya trae sus etiquetas
        else:
            ext = {"orig": CODEC_EXT.get(codec, "") or ext_src or ".m4a", "aac": ".m4a", "mp3": ".mp3"}[kind]
            if kind == "orig" and not have_ffmpeg():   # sin ffmpeg: el archivo tal cual, sin etiquetas
                shutil.move(str(src), out)
            else:
                if not have_ffmpeg():
                    raise DownloadError("Falta ffmpeg. Instalalo desde el asistente para convertir.")
                cover = None
                if kind != "orig":
                    jobs.update(job, step="Preparando la carátula")
                    cov = tmp / "cover.jpg"
                    if cover_url and _fetch_cover(cover_url, tmp / "cover.src"):
                        cover = cov if _make_cover(tmp / "cover.src", cov, holder, False) else None
                    elif local_path:
                        cover = cov if _make_cover(src, cov, holder, True) else None
                    if not cover:
                        notes.append("sin carátula")
                audio = ["-c:a", "copy"]
                if kind == "mp3":
                    audio = ["-c:a", "libmp3lame", "-b:a", f"{QUALITIES[q]['kbps']}k", "-ar", "44100", "-ac", "2"]
                elif kind == "aac" and (local_path or codec != "aac"):
                    audio = ["-c:a", "aac", "-b:a", f"{AAC_LOCAL_KBPS}k"]
                cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src)]
                if cover:
                    cmd += ["-i", str(cover)]
                cmd += ["-map", "0:a:0"] + (["-map", "1:v:0", "-c:v", "copy", "-disposition:v:0", "attached_pic",
                                             "-metadata:s:v", "title=Cover", "-metadata:s:v", "comment=Cover (front)"] if cover else [])
                cmd += ["-map_metadata", "0" if local_path else "-1", *audio]
                if kind == "mp3":
                    cmd += ["-id3v2_version", "3", "-write_id3v1", "1"]
                cmd += _tag_args(meta if not local_path else {k: meta[k] for k in ("title", "artist")})   # un archivo propio conserva sus otras etiquetas
                cmd += ["-f", FORMATS.get(ext, "ipod"), str(out)]
                jobs.update(job, step="Convirtiendo" if kind != "orig" else "Guardando", percent=60 if not local_path else 0)
                ok, why = _run_ffmpeg(cmd, holder, seconds, job, lo=60 if not local_path else 0)
                if not ok or not out.exists() or out.stat().st_size == 0:
                    if kind == "orig" and not local_path:   # no se pudo etiquetar: el archivo tal cual
                        out.unlink(missing_ok=True)
                        shutil.move(str(src), out)
                    else:
                        raise DownloadError(f"No pude convertir el tema: {why[:160] or 'ffmpeg falló'}")
                else:
                    tagged = True
        jobs.update(job, step="Guardando", percent=99)
        final = _dest(directory, meta, ext, opts, title or "Tema")
        try:
            os.replace(out, final)
        except OSError:
            final.unlink(missing_ok=True)
            raise
        if not tagged:
            notes.append("sin etiquetas")
        jobs.update(job, file=str(final), name=final.name, tagged=tagged, note=", ".join(notes), format=ext.lstrip("."))
        _remember(track_id, opts["key"], final, title, artist)
        return final
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _copy_chunks(path, out, job, cancelled):
    total = os.path.getsize(path)
    with open(out, "wb") as o, open(path, "rb") as src:
        done = 0
        while True:
            if cancelled():
                raise stems.Cancelled()
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            o.write(chunk)
            done += len(chunk)
            jobs.update(job, percent=min(99, int(100 * done / total)) if total else 50)
    shutil.copystat(path, out)


def cancel(track_id):
    track_id = stems.norm_id(track_id)
    with _lock:
        if _jobs.get(track_id, {}).get("state") != "running":
            raise DownloadError("No hay una descarga en curso para ese tema.")
        holder = _holders.setdefault(track_id, {})
        holder["cancelled"] = True
        _jobs[track_id]["cancelling"] = True
    osenv.kill_tree(holder.get("proc"))
    return {"state": "cancelling"}


def status(track_id, key="original"):
    track_id = stems.norm_id(track_id)
    job = _jobs.get(track_id)
    if job and job.get("state") in ("running", "error", "cancelled"):
        return jobs.public(job)
    hit = downloaded(track_id, key)
    if hit:
        return {**(jobs.public(job) if job else {}), "state": "done", "percent": 100, "id": track_id, "file": hit["file"], "dir": str(Path(hit["file"]).parent)}
    return {"state": "idle"}


def report():
    """Carpeta de descargas, lo ya descargado (por tema y calidad, que sigue en disco), los trabajos y el lote."""
    items = {k: {"file": h["file"], "dir": str(download_dir()), "title": h.get("title", ""), "artist": h.get("artist", ""), "quality": h.get("quality", "original")}
             for k, h in _read_index().items() if Path(h["file"]).is_file()}
    return {"dir": str(download_dir()), "items": items, "jobs": [jobs.public(j) for j in _jobs.values()], "batch": batch_status()}


# --- lote
def batch_start(items, quality="original", profile=None, folders=False):
    """Baja varios temas en serie. Una falla no corta el lote (salvo el límite de pedidos de TIDAL). Devuelve el estado del lote."""
    if not isinstance(items, list) or not items:
        raise DownloadError("No hay temas elegidos.")
    if len(items) > MAX_BATCH:
        raise DownloadError(f"Son muchos temas: el máximo por tanda es {MAX_BATCH}.")
    opts = _opts(quality, profile)
    opts["folders"] = bool(folders)
    est = estimate([i if isinstance(i, dict) else {} for i in items], opts["quality"], opts["ipod"])
    if not est["enough"]:
        raise DownloadError(f"No alcanza el espacio: hacen falta ≈ {_mb(est['bytes'])} y hay {_mb(est['free'])} libres en {est['dir']}.")
    directory = _check_dir()
    queue = []
    for it in items:
        it = it if isinstance(it, dict) else {}
        queue.append({"it": it, "id": item_id(it), "title": str(it.get("title") or "")[:200], "artist": str(it.get("artist") or "")[:200],
                      "state": "pending", "message": ""})
    if any(q["id"] is None and not (q["it"].get("artist") and q["it"].get("title")) for q in queue):
        raise DownloadError("Hay temas sin fuente de audio.")
    if any(q["id"] is None or not stems.LOCAL_ID.match(q["id"]) for q in queue):
        tidal_source.session()
    with _lock:
        if _busy():
            raise DownloadError("Ya hay una descarga en curso: esperá a que termine.")
        _batch.clear()
        jobs.start(_batch, state="running", total=len(queue), done=0, current=None, quality=opts["key"], folders=opts["folders"], dir=str(directory),
                   summary="", _queue=queue, _cancel=False, _opts=opts)
    threading.Thread(target=_batch_work, args=(_batch, directory), daemon=True).start()
    return batch_status()


def _mb(n):
    return f"{n / 1e9:.1f} GB" if n >= 1e9 else f"{max(1, round(n / 1e6))} MB"


def _batch_work(batch, directory):
    queue, opts = batch["_queue"], batch["_opts"]
    stop_msg = ""
    try:
        for n, q in enumerate(queue):
            if batch["_cancel"] or stop_msg:
                q["state"] = "cancelled" if batch["_cancel"] else "pending"
                continue
            tid = q["id"]
            try:
                if tid is None:  # tema solo de una cuenta: se busca el audio en las fuentes
                    import sources
                    tid = sources.resolve_track(q["it"].get("artist", ""), q["it"].get("title", ""), str(q["it"].get("album") or ""))["id"]
                if not tid:
                    raise DownloadError("No encontré el audio de este tema en tus fuentes.")
                q["id"] = tid
                local_path = _local_file(tid) if stems.LOCAL_ID.match(tid) else None
                if downloaded(tid, opts["key"]):
                    q.update(state="already")
                    jobs.update(batch, done=batch["done"] + 1)
                    continue
                q["state"] = "running"
                jobs.update(batch, current=tid)
                with _lock:
                    job = _new_job(tid, directory, opts)
                _run_job(tid, local_path, directory, job, opts)
                q.update(state=job["state"], message=job.get("message", ""), title=job.get("title") or q["title"], artist=job.get("artist") or q["artist"])
                if job.get("rate"):
                    stop_msg = job["message"]
            except Exception as e:
                q.update(state="error", message=_explain(e, directory))
            jobs.update(batch, done=batch["done"] + 1, current=None)
        counts = {s: sum(1 for q in queue if q["state"] == s) for s in ("done", "already", "error", "cancelled", "pending")}
        parts = []
        if counts["done"]:
            parts.append(f"{counts['done']} listo{'s' if counts['done'] != 1 else ''}")
        if counts["already"]:
            parts.append(f"{counts['already']} ya estaba{'n' if counts['already'] != 1 else ''}")
        if counts["error"]:
            first = next(q["message"] for q in queue if q["state"] == "error")
            extra = f" y {counts['error'] - 1} más" if counts["error"] > 1 else ""
            parts.append(f"{counts['error']} falló ({first}{extra})" if counts["error"] == 1 else f"{counts['error']} fallaron ({first}{extra})")
        if counts["cancelled"]:
            parts.append(f"{counts['cancelled']} cancelado{'s' if counts['cancelled'] != 1 else ''}")
        if stop_msg:
            parts.append(f"se cortó el lote, faltan {counts['pending']}: {stop_msg}")
        jobs.update(batch, state="cancelled" if batch["_cancel"] else "done", summary=" · ".join(parts) or "Nada para bajar.", counts=counts)
    except Exception as e:   # un fallo inesperado del lote no puede dejarlo "en curso" para siempre
        print(f"Lote falló: {e!r}"[:300], file=sys.stderr, flush=True)
        jobs.update(batch, state="error", summary=f"Se cortó el lote ({type(e).__name__}).")


def batch_status():
    if not _batch:
        return None
    out = jobs.public(_batch)
    out["items"] = [{k: q[k] for k in ("id", "title", "artist", "state", "message")} for q in _batch["_queue"]]
    cur = _batch.get("current")
    if cur and cur in _jobs:
        j = _jobs[cur]
        out["currentJob"] = {"id": cur, "title": j.get("title", ""), "artist": j.get("artist", ""), "percent": j.get("percent", 0), "step": j.get("step", "")}
    return out


def batch_cancel(mode="all"):
    """`all`: corta el lote (lo que falta queda sin bajar). `current`: corta solo el tema actual y sigue con el siguiente."""
    if _batch.get("state") != "running":
        raise DownloadError("No hay un lote en curso.")
    if mode == "all":
        _batch["_cancel"] = True
    cur = _batch.get("current")
    if cur and _jobs.get(cur, {}).get("state") == "running":
        cancel(cur)
    return {"state": "cancelling"}


# --- abrir en carpeta
class RevealError(Exception):
    pass


def open_dry():
    return bool(os.environ.get("STEMSHED_OPEN_DRYRUN"))


def known_roots():
    """Carpetas donde el usuario puede pedir "abrir en carpeta": descargas, música y la caché del motor."""
    s = settings.effective()
    roots = [Path(s["downloadDir"]), *(Path(f) for f in s.get("musicFolders", [])), stems.CACHE, stems.OLD_CACHE]
    out = []
    for r in roots:
        try:
            out.append(Path(os.path.realpath(r)))
        except (OSError, ValueError):
            pass
    return out


def safe_path(value):
    """La ruta real (sin atajos ni symlinks) si está dentro de una carpeta conocida y existe; si no, RevealError."""
    if not isinstance(value, str) or not value or "\x00" in value or not osenv.is_absolute(value):
        raise RevealError("Ruta inválida.")
    try:
        real = Path(os.path.realpath(value))
    except (OSError, ValueError):
        raise RevealError("Ruta inválida.")
    if not any(real == r or r in real.parents for r in known_roots()):
        raise RevealError("Esa ruta no está en una carpeta de Shed Stem Studio.")
    if not real.exists():
        raise RevealError("Ese archivo o carpeta ya no existe.")
    return real


def path_for_id(track_id, original=False, key=None):
    """Dónde está el archivo de un tema: el descargado (en esa calidad, o el más nuevo), o el original si es un archivo local (o si se pide `original`)."""
    track_id = str(track_id)
    hit = None
    if not original and (track_id.isdigit() or stems.LOCAL_ID.match(track_id)):
        if key:
            hit = downloaded(track_id, key)
        else:
            mine = [h for k, h in _read_index().items() if k.split("|")[0] == track_id and Path(h["file"]).is_file()]
            hit = max(mine, key=lambda h: h.get("at", 0)) if mine else None
    if hit:
        return hit["file"]
    if stems.LOCAL_ID.match(track_id):
        return library.path_for(track_id)
    return None


def reveal_command(path, platform=None):
    """Qué se ejecutaría para mostrar `path` en el administrador de archivos (archivo seleccionado, o la carpeta abierta)."""
    platform = platform or sys.platform
    p = str(path)
    is_dir = os.path.isdir(p)
    if platform == "win32":
        return ["explorer", p] if is_dir else ["explorer", f"/select,{p}"]
    if platform == "darwin":
        return ["open", p] if is_dir else ["open", "-R", p]
    folder = p if is_dir else str(Path(p).parent)
    if not is_dir and shutil.which("gdbus"):
        uri = Path(p).as_uri().replace("'", "%27")
        return ["gdbus", "call", "--session", "--timeout", "5", "--dest", "org.freedesktop.FileManager1", "--object-path", "/org/freedesktop/FileManager1",
                "--method", "org.freedesktop.FileManager1.ShowItems", f"['{uri}']", ""]
    return ["xdg-open", folder]


def reveal(value=None, track_id=None, original=False, key=None):
    """Abre el administrador de archivos mostrando el archivo. Por id (tema descargado o local) o por ruta dentro de una carpeta conocida.
    Con STEMSHED_OPEN_DRYRUN=1 no abre nada y devuelve lo que habría ejecutado."""
    if track_id is not None:
        value = path_for_id(track_id, original, key)
        if not value:
            raise RevealError("No encontré el archivo de ese tema.")
    if isinstance(value, str) and value and os.path.normpath(value) == os.path.normpath(str(download_dir())):
        download_dir().mkdir(parents=True, exist_ok=True)  # la carpeta de descargas elegida, aunque todavía no se haya bajado nada
    real = safe_path(value)
    cmd = reveal_command(real)
    if open_dry():
        return {"ok": True, "dryRun": True, "path": str(real), "command": cmd}
    from services import in_docker
    if in_docker():
        raise RevealError("Con Docker los archivos están en tu equipo: abrilos desde el explorador de archivos.")
    if sys.platform not in ("win32", "darwin") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        raise RevealError("No hay un explorador de archivos disponible desde el motor.")
    if cmd[0] == "gdbus":
        try:
            ok = subprocess.run(cmd, capture_output=True, timeout=8).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            ok = False
        if ok:
            return {"ok": True}
        cmd = ["xdg-open", str(real.parent)]  # nadie atiende ese servicio: se abre la carpeta contenedora
    if cmd[0] != "explorer" and not shutil.which(cmd[0]):
        raise RevealError("No hay un explorador de archivos disponible desde el motor.")
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=not osenv.WINDOWS)
    return {"ok": True}
