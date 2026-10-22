"""Catálogo unificado de música: junta lo que aportan las fuentes (archivos locales y TIDAL) en una sola vista.

Un ítem es una referencia (artista, título, disco) con la lista de fuentes que lo tienen. Los duplicados entre fuentes
se unen por clave normalizada. El género sale de las etiquetas de los archivos o, si no hay, de MusicBrainz (en segundo
plano, con caché): son géneros aportados por usuarios de MusicBrainz, así que son una estimación.
"""
import json
import os
import re
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import library
import recs
import settings
import extart
import providers
import tidal_source

_lock = threading.Lock()
_version = 0
_cache = {"v": -1, "data": None}
_tidal = {"fetchedAt": None, "refreshing": False, "error": "", "albums": [], "tracks": []}
_ext = {}  # proveedor (spotify, ytmusic) -> {fetchedAt, refreshing, error, albums, tracks}
EXT_IDS = ("spotify", "ytmusic")
_genres = {}  # clave de disco -> {"genres": [...], "at": ts}
_genre_job = {"running": False, "done": 0, "total": 0}
_pause = threading.Event()   # mientras está activo, el enriquecimiento de géneros cede MusicBrainz a una recomendación


def pause_enrichment():
    _pause.set()


def resume_enrichment():
    _pause.clear()


def norm(text):
    t = unicodedata.normalize("NFD", str(text).lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in t if not unicodedata.combining(c))).strip()


def _dir():
    return Path(settings.effective()["dataDir"]) / "catalog"


def album_key(artist, album):
    return f"{norm(artist)}|{norm(album)}"


def _bump():
    global _version
    _version += 1


# ---------------------------------------------------------------- persistencia
def load_state():
    try:
        snap = json.loads((_dir() / "tidal.json").read_text())
        _tidal.update(fetchedAt=snap.get("fetchedAt"), albums=snap.get("albums", []), tracks=snap.get("tracks", []))
    except (OSError, ValueError):
        pass
    for pid in EXT_IDS:
        try:
            snap = json.loads((_dir() / f"{pid}.json").read_text())
            _ext_state(pid).update(fetchedAt=snap.get("fetchedAt"), albums=snap.get("albums", []), tracks=snap.get("tracks", []))
        except (OSError, ValueError):
            pass
    try:
        _genres.update(json.loads((_dir() / "genres.json").read_text()))
    except (OSError, ValueError):
        pass
    _bump()


def _save(name, data):
    _dir().mkdir(parents=True, exist_ok=True)
    (_dir() / name).write_text(json.dumps(data))


# ---------------------------------------------------------------- TIDAL
def refresh_tidal():
    """Trae favoritos y el contenido de las playlists a un snapshot local. Corre en segundo plano."""
    with _lock:
        if _tidal["refreshing"]:
            return
        _tidal.update(refreshing=True, error="")

    def work():
        try:
            tidal_source.clear_cache()
            lib = tidal_source.library()
            tracks, skipped = {}, 0
            for t in lib["tracks"]:
                tracks[t["id"]] = {**t, "collections": ["Favoritos"]}
            for p in lib["playlists"]:
                try:
                    items = tidal_source.playlist_tracks(p["id"])["tracks"]
                except tidal_source.SourceError:
                    raise
                except Exception:  # una playlist rota (borrada, sin permiso) no debe tirar abajo toda la actualización
                    skipped += 1
                    continue
                for t in items:
                    tracks.setdefault(t["id"], {**t, "collections": []})["collections"].append(p["name"])
            _tidal.update(albums=lib["albums"], tracks=list(tracks.values()), fetchedAt=time.time(),
                          error=f"No pude leer {skipped} playlist{'s' if skipped != 1 else ''}." if skipped else "")
            _save("tidal.json", {"fetchedAt": _tidal["fetchedAt"], "albums": _tidal["albums"], "tracks": _tidal["tracks"]})
            _bump()
            enrich_genres()
        except tidal_source.SourceError as e:
            _tidal["error"] = e.message
        except Exception as e:
            _tidal["error"] = f"No pude leer TIDAL ({type(e).__name__})."
        finally:
            _tidal["refreshing"] = False

    threading.Thread(target=work, daemon=True).start()


def _ext_state(pid):
    return _ext.setdefault(pid, {"fetchedAt": None, "refreshing": False, "error": "", "albums": [], "tracks": []})


def refresh_providers():
    """Trae la biblioteca de las cuentas conectadas (Spotify, YouTube Music). Solo lectura; una cuenta que falla no frena a las demás."""
    for pid in EXT_IDS:
        try:
            p = providers.get(pid)
            ready = p.configured() and p.connected()
        except providers.ProviderError:
            continue
        if not ready:
            st = _ext_state(pid)
            if st["albums"] or st["tracks"]:  # se desconectó: lo guardado de esa cuenta deja de mostrarse
                st.update(albums=[], tracks=[], fetchedAt=None, error="")
                _save(f"{pid}.json", {"fetchedAt": None, "albums": [], "tracks": []})
                _bump()
            continue
        with _lock:
            st = _ext_state(pid)
            if st["refreshing"]:
                continue
            st.update(refreshing=True, error="")
        threading.Thread(target=_refresh_one, args=(pid, p), daemon=True).start()


def _refresh_one(pid, p):
    st = _ext_state(pid)
    try:
        lib = p.library()
        st.update(albums=lib.get("albums", []), tracks=lib.get("tracks", []), fetchedAt=time.time())
        _save(f"{pid}.json", {"fetchedAt": st["fetchedAt"], "albums": st["albums"], "tracks": st["tracks"]})
        _bump()
        enrich_genres()
    except providers.ProviderError as e:
        st["error"] = e.message
    except Exception as e:
        st["error"] = f"No pude leer {p.label} ({type(e).__name__})."
    finally:
        st["refreshing"] = False


def forget_provider(pid):
    """Al desconectar una cuenta se borra su copia local."""
    st = _ext_state(pid)
    st.update(albums=[], tracks=[], fetchedAt=None, error="")
    try:
        (_dir() / f"{pid}.json").unlink()
    except OSError:
        pass
    _bump()


# ---------------------------------------------------------------- géneros
def _split_genres(raw):
    return [g.strip().lower() for g in re.split(r"[;/,]", raw or "") if g.strip()][:3]


def enrich_genres():
    """Busca en MusicBrainz el género de los discos que no lo tienen (1 consulta por segundo, con caché)."""
    with _lock:
        if _genre_job["running"]:
            return
        _genre_job.update(running=True, done=0, total=0)

    def work():
        try:
            todo = []
            for a in _albums_raw():
                if a["genres"]:
                    continue
                k = album_key(a["artist"], a["title"])
                hit = _genres.get(k)
                if not hit or time.time() - hit["at"] > 90 * 86400:
                    todo.append((k, a["artist"], a["title"]))
            _genre_job["total"] = len(todo)
            for k, artist, title in todo:
                while _pause.is_set():  # una recomendación en curso usa MusicBrainz primero
                    time.sleep(0.5)
                _genres[k] = {"genres": _mb_genres(artist, title), "at": time.time()}
                _genre_job["done"] += 1
                if _genre_job["done"] % 10 == 0:
                    _save("genres.json", _genres)
                    _bump()
                time.sleep(1.1)
            _save("genres.json", _genres)
            _bump()
        finally:
            _genre_job["running"] = False

    threading.Thread(target=work, daemon=True).start()


def _mb_genres(artist, album):
    try:
        for g in recs.mb_search(artist, album):
            credit = " ".join(a.get("name", "") for a in g.get("artist-credit", []) if isinstance(a, dict))
            if g.get("score", 0) >= 90 and norm(g.get("title", "")) == norm(album) and norm(artist) in norm(credit):
                time.sleep(1.1)
                url = f"https://musicbrainz.org/ws/2/release-group/{g['id']}?inc=genres&fmt=json"
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": recs.UA}), timeout=20) as r:
                    gs = sorted(json.load(r).get("genres", []), key=lambda x: -x.get("count", 0))
                return [x["name"].lower() for x in gs[:3]]
    except Exception:
        return []
    return []


# ---------------------------------------------------------------- catálogo unificado
def _albums_raw():
    """Discos de todas las fuentes, ya unidos por clave, con sus géneros."""
    albums = {}
    for t in library.report()["tracks"]:
        if not t["album"]:
            continue
        k = album_key(t["artist"], t["album"])
        a = albums.setdefault(k, {"key": k, "title": t["album"], "artist": t["artist"], "year": t.get("year"), "genres": [],
                                  "sources": [], "localIds": [], "tidalId": None, "artUrl": f"/engine/art/{t['id']}"})
        if "local" not in a["sources"]:
            a["sources"].append("local")
        a["localIds"].append(t["id"])
        a["genres"] = a["genres"] or _split_genres(t.get("genre"))
    for rank, t in enumerate(_tidal["albums"]):  # la lista de TIDAL viene del más recién guardado al más viejo
        k = album_key(t["artist"], t["title"])
        a = albums.setdefault(k, {"key": k, "title": t["title"], "artist": t["artist"], "year": t.get("year"), "genres": [],
                                  "sources": [], "localIds": [], "tidalId": None, "artUrl": f"/engine/albumart/{t['id']}"})
        if "tidal" not in a["sources"]:
            a["sources"].append("tidal")
        a["tidalId"] = t["id"]
        a["savedAt"], a["rank"] = t.get("savedAt"), rank
        a["year"] = a["year"] or t.get("year")
    for pid in EXT_IDS:
        for rank, t in enumerate(_ext_state(pid)["albums"]):
            k = album_key(t["artist"], t["title"])
            a = albums.setdefault(k, {"key": k, "title": t["title"], "artist": t["artist"], "year": t.get("year"), "genres": [],
                                      "sources": [], "localIds": [], "tidalId": None})
            if pid not in a["sources"]:
                a["sources"].append(pid)
            a.setdefault("extIds", {})[pid] = t["id"]
            if not a.get("artUrl") and extart.url_for(t.get("thumb")):
                a["artUrl"] = extart.url_for(t["thumb"])
            if t.get("addedAt") and not a.get("savedAt"):
                a["savedAt"] = t["addedAt"]
            a.setdefault("rank", rank)
            a["year"] = a["year"] or t.get("year")
    for k, a in albums.items():
        a["genres"] = a["genres"] or (_genres.get(k) or {}).get("genres", [])
    return list(albums.values())


def _tracks_raw():
    tracks = {}
    for t in library.report()["tracks"]:
        k = f"{norm(t['artist'])}|{norm(t['title'])}"
        x = tracks.setdefault(k, {"key": k, "title": t["title"], "artist": t["artist"], "album": t["album"], "duration": t["duration"],
                                  "genres": _split_genres(t.get("genre")), "sources": [], "ids": {}, "collections": []})
        x["sources"].append("local") if "local" not in x["sources"] else None
        x["ids"]["local"] = t["id"]
    for rank, t in enumerate(_tidal["tracks"]):
        k = f"{norm(t['artist'])}|{norm(t['title'])}"
        x = tracks.setdefault(k, {"key": k, "title": t["title"], "artist": t["artist"], "album": t["album"], "duration": t["duration"],
                                  "genres": [], "sources": [], "ids": {}, "collections": []})
        if "rank" not in x:
            x["savedAt"], x["rank"] = t.get("savedAt"), rank
        x["sources"].append("tidal") if "tidal" not in x["sources"] else None
        x["ids"]["tidal"] = t["id"]
        for c in t.get("collections", []):
            if c not in x["collections"]:
                x["collections"].append(c)
    for pid in EXT_IDS:
        for rank, t in enumerate(_ext_state(pid)["tracks"]):
            k = f"{norm(t['artist'])}|{norm(t['title'])}"
            x = tracks.setdefault(k, {"key": k, "title": t["title"], "artist": t["artist"], "album": t.get("album", ""), "duration": t.get("duration"),
                                      "genres": [], "sources": [], "ids": {}, "collections": []})
            if "rank" not in x:
                x["savedAt"], x["rank"] = t.get("addedAt"), rank
            if pid not in x["sources"]:
                x["sources"].append(pid)
            x.setdefault("refs", {})[pid] = t["id"]  # referencia a la cuenta: no es audio, no va en `ids`
    for x in tracks.values():
        x["genres"] = x["genres"] or (_genres.get(album_key(x["artist"], x["album"])) or {}).get("genres", [])
        base = x["ids"].get("local") or x["ids"].get("tidal")
        if base:  # sin archivo local ni TIDAL no hay portada: la interfaz dibuja la inicial
            x["artUrl"] = f"/engine/art/{base}"
    return list(tracks.values())


def snapshot():
    with _lock:
        if _cache["v"] == _version:
            return _cache["data"]
    albums, tracks = _albums_raw(), _tracks_raw()
    data = {"albums": albums, "tracks": tracks}
    with _lock:
        _cache.update(v=_version, data=data)
    return data


SORTS = ("saved", "alpha", "artist")


def _ts(v):
    """Fecha de guardado como número (para comparar fuentes con formatos distintos); None si no hay o no se entiende."""
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def sort_items(hits, sort):
    """saved: lo último que guardaste primero, mezclando fuentes por fecha (lo que no trae fecha sigue el orden de su
    fuente y después lo que solo está en tus archivos); alpha: por título; artist: por artista y título."""
    title = lambda i: norm(i["title"])
    if sort == "alpha":
        return sorted(hits, key=lambda i: (title(i), norm(i["artist"])))
    if sort == "artist":
        return sorted(hits, key=lambda i: (norm(i["artist"]), title(i)))

    def key(i):
        ts = _ts(i.get("savedAt"))
        if ts is not None:
            return (0, -ts, 0, "")
        if "rank" in i:
            return (1, 0, i["rank"], "")
        return (2, 0, 0, norm(i["artist"]) + "|" + title(i))
    return sorted(hits, key=key)


def query(kind="albums", q="", source="", artist="", genre="", limit=60, offset=0, sort="saved"):
    data = snapshot()
    items = data["albums" if kind == "albums" else "tracks"]
    nq = norm(q)

    def match(i, ignore=()):
        if nq and nq not in norm(f"{i['title']} {i['artist']} {i.get('album', '')} {' '.join(i['genres'])}"):
            return False
        if source and source not in i["sources"] and "source" not in ignore:
            return False
        if artist and norm(i["artist"]) != norm(artist) and "artist" not in ignore:
            return False
        if genre and genre not in i["genres"] and "genre" not in ignore:
            return False
        return True

    hits = [i for i in items if match(i)]
    hits = sort_items(hits, sort if sort in SORTS else "saved")
    # Facetas calculadas sin el filtro propio, para que el selector siga mostrando las demás opciones.
    count = lambda field, ignore: _count([i for i in items if match(i, (ignore,))], field)
    return {"total": len(hits), "items": hits[offset:offset + limit],
            "facets": {"artists": count("artist", "artist")[:300], "genres": count("genres", "genre")[:60],
                       "sources": {s: sum(1 for i in items if s in i["sources"]) for s in ("local", "tidal", *EXT_IDS)}},
            "status": status()}


def _count(items, field):
    c = {}
    for i in items:
        for v in (i[field] if isinstance(i[field], list) else [i[field]]):
            if v:
                c[v] = c.get(v, 0) + 1
    return [{"name": k, "count": n} for k, n in sorted(c.items(), key=lambda kv: (-kv[1], norm(kv[0])))]


def status():
    return {"tidal": {"fetchedAt": _tidal["fetchedAt"], "refreshing": _tidal["refreshing"], "error": _tidal["error"],
                      "albums": len(_tidal["albums"]), "tracks": len(_tidal["tracks"])},
            "providers": {pid: {"fetchedAt": st["fetchedAt"], "refreshing": st["refreshing"], "error": st["error"],
                                "albums": len(st["albums"]), "tracks": len(st["tracks"])} for pid, st in ((p, _ext_state(p)) for p in EXT_IDS)},
            "local": {k: library.report()[k] for k in ("scanning", "scanned", "total")},
            "genres": dict(_genre_job)}


_album_cache = {}  # (cuenta, id de disco) -> temas; lo que no se pudo leer no se guarda


def _ext_album_tracks(pid, album_id):
    k = (pid, album_id)
    if k not in _album_cache:
        try:
            _album_cache[k] = providers.get(pid).album_tracks(album_id)["tracks"]
        except Exception:  # sin sesión, sin red o disco que la cuenta no entrega: se muestra lo que haya
            return []
    return _album_cache[k]


def album_detail(key):
    """Temas de un disco, uniendo las fuentes que lo tienen. Cada tema trae los ids por fuente."""
    a = next((x for x in snapshot()["albums"] if x["key"] == key), None)
    if not a:
        return None
    tracks = {}
    for t in library.report()["tracks"]:
        if album_key(t["artist"], t["album"]) == key:
            x = tracks.setdefault(norm(t["title"]), {"title": t["title"], "artist": t["artist"], "album": a["title"], "duration": t["duration"], "ids": {}, "order": t["rel"]})
            x["ids"]["local"] = t["id"]
    if a["tidalId"]:
        try:
            for i, t in enumerate(tidal_source.album_by_id(a["tidalId"])["tracks"]):
                x = tracks.setdefault(norm(t["title"]), {"title": t["title"], "artist": t["artist"], "album": a["title"], "duration": t["duration"], "ids": {}, "order": f"{i:03d}"})
                x["ids"]["tidal"] = t["id"]
        except Exception:
            pass
    if not a["tidalId"]:  # sin TIDAL: se pide el disco a la cuenta que lo tiene (Spotify / YouTube Music)
        for pid, album_id in (a.get("extIds") or {}).items():
            for i, t in enumerate(_ext_album_tracks(pid, album_id) or []):
                x = tracks.setdefault(norm(t["title"]), {"title": t["title"], "artist": t["artist"], "album": a["title"], "duration": t.get("duration"), "ids": {}, "order": f"~{i:03d}"})
                x.setdefault("refs", {})[pid] = t["id"]
    for pid in EXT_IDS:  # respaldo: los temas guardados de esa cuenta que son de este disco
        for i, t in enumerate(_ext_state(pid)["tracks"]):
            if album_key(t["artist"], t.get("album", "")) != key:
                continue
            if norm(t["title"]) in tracks:
                tracks[norm(t["title"])].setdefault("refs", {}).setdefault(pid, t["id"])
            else:
                tracks[norm(t["title"])] = {"title": t["title"], "artist": t["artist"], "album": a["title"], "duration": t.get("duration"), "ids": {}, "refs": {pid: t["id"]}, "order": f"~{i:03d}"}
    return {"album": a, "tracks": sorted(tracks.values(), key=lambda t: t["order"])}
