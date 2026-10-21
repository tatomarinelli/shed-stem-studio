"""Fuentes de audio: de dónde sale el sonido para escuchar y separar.

Un tema que se ve en cualquier lista (favoritos, playlists, recomendaciones) es una REFERENCIA (artista, título, disco).
La config global `audioSources` define el orden en que se busca el audio. Si algún proveedor ya tiene el tema
separado, se usa ese: el orden solo decide de dónde se baja el audio nuevo.
"""
import library
import settings
import stems
import tidal_source

LABELS = {"local": "Mis archivos", "tidal": "TIDAL"}


def status():
    folders = settings.load()["musicFolders"]
    try:
        tidal_ok = tidal_source.status()["connected"]
    except Exception:
        tidal_ok = False
    detail = {"local": f"{len(folders)} carpeta{'s' if len(folders) != 1 else ''}" if folders else "sin carpetas",
              "tidal": "conectado" if tidal_ok else "sin conectar"}
    available = {"local": bool(folders), "tidal": tidal_ok}
    order = settings.load()["audioSources"]
    return [{"id": k, "label": LABELS[k], "enabled": k in order, "available": available[k], "detail": detail[k]}
            for k in order + [k for k in LABELS if k not in order]]


def _find(source, artist, title, album):
    try:
        if source == "local":
            t = library.find_track(artist, title, album)
        else:
            t = tidal_source.find_track(artist, title, album)
    except Exception:
        return None
    return {"id": t["id"], "source": source} if t else None


def resolve_track(artist, title, album=""):
    """Devuelve {id, source, cached} del mejor proveedor para esta referencia, o {id: None}."""
    found = []
    for source in settings.load()["audioSources"]:
        hit = _find(source, artist, title, album)
        if hit:
            hit["cached"] = stems.is_cached(hit["id"])
            if hit["cached"]:
                return hit  # ya separado: se usa ese sin importar el orden
            found.append(hit)
    return found[0] if found else {"id": None, "source": None, "cached": False}


def resolve_album(artist, album):
    """Los temas del disco en el primer proveedor que lo tenga."""
    for source in settings.load()["audioSources"]:
        try:
            if source == "local":
                tracks = library.find_album(artist, album)
                if tracks:
                    return {"source": source, "tracks": [{"id": t["id"], "title": t["title"], "artist": t["artist"], "album": t["album"], "duration": t["duration"]} for t in tracks]}
            else:
                r = tidal_source.album_tracks(artist, album)
                if r["album"]:
                    return {"source": source, "tracks": r["tracks"]}
        except Exception:
            continue
    return {"source": None, "tracks": []}


def pick(ids):
    """De los ids de un mismo tema (uno por fuente) elige el que se usa: primero uno ya separado; si no, el primero según el orden global."""
    # Se descartan ids que no corresponden a nada: un archivo que ya no está en la biblioteca o un id de TIDAL mal formado.
    ids = {k: v for k, v in ids.items() if (k == "local" and library.path_for(v)) or (k == "tidal" and str(v).isdigit())}
    order = [k for k in settings.load()["audioSources"] if k in ids]
    for k in order:
        if stems.is_cached(ids[k]):
            return {"id": ids[k], "source": k, "cached": True}
    if order:
        return {"id": ids[order[0]], "source": order[0], "cached": False}
    return {"id": None, "source": None, "cached": False}
