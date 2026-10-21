"""Destinos donde GUARDAR lo recomendado (un álbum o una playlist), uno o varios a la vez.

Guardar ESCRIBE en las cuentas del usuario: solo pasa con un pedido explícito (POST /engine/save con confirm=true desde la
interfaz, después de una confirmación que dice qué y dónde). Nunca lo dispara la cadencia ni una reacción, y nunca borra
nada. Cada guardado queda en un historial local (<carpeta de memoria>/saved.jsonl).

Para sumar un destino: una clase con id, label, status() y save_album()/save_playlist(), registrada en DESTINATIONS.
La interfaz lista lo que devuelve GET /engine/destinations; no hay que tocarla.

STEMSHED_SAVE_DRYRUN=1: todos los destinos resuelven (lectura) pero NO escriben; para pruebas.
"""
import json
import os
import osenv
import threading
import time
from pathlib import Path

import tidal_source

DRY = bool(os.environ.get("STEMSHED_SAVE_DRYRUN"))
_lock = threading.Lock()


class Destination:
    id = ""
    label = ""
    caps = {"album": False, "playlist": False}

    def status(self):
        return {"state": "unavailable", "note": ""}

    def info(self):
        return {"id": self.id, "label": self.label, "caps": self.caps, **self.status()}


class Tidal(Destination):
    id, label = "tidal", "TIDAL"
    caps = {"album": True, "playlist": True}

    def status(self):
        try:
            st = tidal_source.status()
        except Exception:
            st = {"connected": False}
        return {"state": "connected", "note": ""} if st.get("connected") else {"state": "disconnected", "note": "Conectalo en Fuentes."}

    def save_album(self, artist, album, dry=False):
        """Lo agrega a favoritos. Resuelve el disco con el mismo criterio que la escucha (artista y título exactos)."""
        found = tidal_source.album_tracks(artist, album)["album"]
        if not found:
            return {"ok": False, "saved": 0, "notFound": [f"{artist} - {album}"]}
        if not dry:
            tidal_source.session().user.favorites.add_album(int(found["id"]))
        return {"ok": True, "saved": 1, "notFound": [], "ref": found["id"]}

    def save_playlist(self, name, tracks, dry=False):
        """Crea una playlist PROPIA nueva (nunca modifica otra) con los temas que encuentre."""
        ids, missing = [], []
        for t in tracks:
            hit = tidal_source.find_track(t["artist"], t["title"], t.get("album", ""))
            (ids.append(int(hit["id"])) if hit else missing.append(f"{t['artist']} - {t['title']}"))
        if not ids:
            return {"ok": False, "saved": 0, "notFound": missing}
        ref = None
        if not dry:
            pl = tidal_source.session().user.create_playlist(name, "Guardada desde Shed Stem Studio")
            pl.add(ids)
            ref = str(pl.id)
        return {"ok": True, "saved": len(ids), "notFound": missing, "ref": ref}


class Spotify(Destination):
    """Diseñado, no implementado: falta el conector (OAuth PKCE con un Client ID registrado por el usuario).
    Al implementarlo, verificar en developer.spotify.com los endpoints actuales de biblioteca (en 2026 se unificaron
    guardar/seguir en endpoints genéricos por URI) y los alcances (scopes) mínimos."""
    id, label = "spotify", "Spotify"
    caps = {"album": True, "playlist": True}

    def status(self):
        return {"state": "unavailable", "note": "Todavía no se puede conectar."}


DESTINATIONS = {d.id: d for d in (Tidal(), Spotify())}


def listing():
    return [d.info() for d in DESTINATIONS.values()]


def clean_items(kind, items):
    if kind == "album":
        it = items[0] if isinstance(items, list) and items else items
        if not isinstance(it, dict) or not str(it.get("artist", "")).strip() or not str(it.get("album", "")).strip():
            raise ValueError("Falta el disco.")
        return [{"artist": str(it["artist"])[:160], "album": str(it["album"])[:200]}]
    if kind == "playlist":
        if not isinstance(items, list) or not 1 <= len(items) <= 200:
            raise ValueError("La playlist necesita entre 1 y 200 temas.")
        out = []
        for t in items:
            if isinstance(t, dict) and t.get("artist") and t.get("title"):
                out.append({"artist": str(t["artist"])[:160], "title": str(t["title"])[:200], "album": str(t.get("album") or "")[:200]})
        if not out:
            raise ValueError("No hay temas válidos.")
        return out
    raise ValueError("Tipo inválido.")


def save(kind, items, dest_ids, name, log_file, registry=None, dry=None):
    """Guarda en cada destino pedido, de forma independiente (si uno falla, los demás siguen). Devuelve {id: resultado}."""
    registry = registry or DESTINATIONS
    dry = DRY if dry is None else dry
    items = clean_items(kind, items)
    if kind == "playlist":
        name = " ".join(str(name or "").split())[:80]
        if not name:
            raise ValueError("Poné un nombre para la playlist.")
    if not isinstance(dest_ids, list) or not dest_ids:
        raise ValueError("Elegí al menos un destino.")
    results = {}
    for did in dict.fromkeys(dest_ids):
        d = registry.get(did)
        if not d:
            results[did] = {"ok": False, "saved": 0, "notFound": [], "error": "Destino desconocido."}
            continue
        st = d.status()
        if st["state"] != "connected" or not d.caps.get(kind):
            results[did] = {"ok": False, "saved": 0, "notFound": [], "error": st.get("note") or "No disponible."}
            continue
        try:
            r = d.save_album(items[0]["artist"], items[0]["album"], dry=dry) if kind == "album" else d.save_playlist(name, items, dry=dry)
        except Exception as e:
            r = {"ok": False, "saved": 0, "notFound": [], "error": f"Falló: {type(e).__name__}"}
        r["dry"] = dry
        results[did] = r
    entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": kind, "name": name if kind == "playlist" else None,
             "items": items[:50], "results": results, "dry": dry}
    with _lock:
        p = Path(log_file)
        p.parent.mkdir(parents=True, exist_ok=True)
        new = not p.exists()
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if new:
            osenv.secure(p, 0o600)
    return results
