"""Memoria de gustos con tamaño acotado. Formato y motivos en docs/memory-format.md.

Tres archivos en la carpeta de memoria (por defecto ~/.config/stemshed, o STEMSHED_MEMORY_DIR):
- events.jsonl: eventos crudos recientes del usuario (reacciones, deshacer, discos mostrados). Solo lo que HIZO él.
- taste.json: lo técnico. Pesos agregados por artista y género con fecha de referencia ("at"), que decaen con vida media
  configurable; los eventos viejos se pliegan acá y se borran del .jsonl. También la lista de discos ya clasificados.
- memory.md: resumen corto en lenguaje natural, generado con una plantilla a partir de datos (nunca texto del modelo).

Los favoritos de las fuentes NO se guardan como eventos: son un estado que se relee y se recalcula con su fecha de alta.
Todas las funciones de cálculo son puras (reciben fechas y rutas); las de archivo reciben la carpeta.
"""
import json
import math
import os
import osenv
import re
import threading
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

VERSION = 1
HALF_LIFE_DAYS = 180.0
PRUNE = 0.05            # peso efectivo por debajo del cual un gusto se recorta
RAW_DAYS = 60           # eventos más viejos que esto se compactan
RAW_MAX = 300           # y nunca quedan más que esto en events.jsonl
KNOWN_MAX = 400         # discos clasificados que se recuerdan para no repetir
REACTIONS = ("heard", "loved", "no")
# Cuánto suma cada reacción al artista y a cada género (MusicBrainz) del disco. "No me va" es solo sobre ESE disco:
# lo excluye, pero no resta al artista ni al género (reacciones por ítem, nunca por género).
DELTAS = {"loved": (3.0, 1.0), "heard": (0.5, 0.25), "no": (0.0, 0.0)}
# Favoritos de las fuentes: peso base en la fecha en que se agregaron.
SOURCE_W = {"album": (1.0, 0.5), "artist": (1.0, 0.0), "track": (0.3, 0.15)}
DECLARED_W = 2.0        # lo que el usuario declara en su perfil no decae (lo edita él)
LABELS = {"loved": "Me encantó", "heard": "Ya lo escuché", "no": "No me va"}

_lock = threading.Lock()


def norm(text):
    t = unicodedata.normalize("NFD", str(text).lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in t if not unicodedata.combining(c))).strip()


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def decay(w, from_ts, to_ts, half_life_days=HALF_LIFE_DAYS):
    """Peso `w` medido en `from_ts`, visto en `to_ts`. Hacia atrás no crece (to < from devuelve w)."""
    dt = max(0.0, to_ts - from_ts) / 86400.0
    return w * math.pow(0.5, dt / half_life_days)


def _add(buckets, key, name, delta, ts, hl):
    """Suma `delta` (ocurrido en ts) a un balde {w, at}. Lleva todo a la fecha más nueva de las dos."""
    if not key or not delta:
        return
    b = buckets.get(key)
    if not b:
        buckets[key] = {"name": name, "w": delta, "at": iso(ts)}
        return
    at = parse(b["at"])
    if ts >= at:
        b["w"], b["at"] = decay(b["w"], at, ts, hl) + delta, iso(ts)
    else:
        b["w"] = b["w"] + decay(delta, ts, at, hl)
    b["name"] = b.get("name") or name


def empty_taste(half_life_days=HALF_LIFE_DAYS):
    return {"version": VERSION, "halfLifeDays": half_life_days, "updatedAt": None, "compactedThrough": None,
            "artists": {}, "genres": {}, "known": {}}


# ---------------------------------------------------------------- eventos
def make_event(ts, type_, mbid, artist, album, action=None, genres=None, kind=None, preset=None):
    e = {"ts": iso(ts), "type": type_, "mbid": mbid, "artist": str(artist)[:160], "album": str(album)[:200]}
    if preset:
        e["preset"] = str(preset)[:30]  # con qué perfil de sugerencia se generó (contexto; la memoria es compartida)
    if action is not None:
        e["action"] = action
    if genres:
        e["genres"] = [str(g)[:60] for g in genres[:5]]
    if kind:
        e["kind"] = kind
    return e


def latest_reactions(events):
    """Última reacción por disco entre los eventos crudos (una reacción nueva reemplaza a la anterior; 'clear' la borra)."""
    out = {}
    for e in events:
        if e.get("type") == "reaction":
            out[e["mbid"]] = e
    return out


def _item_delta(buckets_a, buckets_g, e, sign, ts, hl):
    da, dg = DELTAS.get(e.get("action"), (0.0, 0.0))
    _add(buckets_a, norm(e["artist"]), e["artist"], sign * da, ts, hl)
    for g in e.get("genres", []):
        _add(buckets_g, norm(g), g, sign * dg, ts, hl)


def fold(taste, events, upto_ts=None):
    """Pliega eventos crudos en una copia de `taste` y devuelve (taste, eventos que quedan sin plegar).

    Con upto_ts=None pliega todo (vista "en vivo", no se guarda). Con upto_ts pliega solo las reacciones vigentes
    anteriores a esa fecha. Una reacción que reemplaza a una ya plegada descuenta el aporte de la anterior.
    """
    t = json.loads(json.dumps(taste))
    hl = t.get("halfLifeDays", HALF_LIFE_DAYS)
    latest = latest_reactions(events)
    keep = []
    for e in events:
        ts = parse(e["ts"])
        if upto_ts is not None and ts >= upto_ts:
            keep.append(e)
            continue
        if e.get("type") != "reaction" or latest.get(e["mbid"]) is not e:
            continue  # los "mostrados" viejos y las reacciones reemplazadas se descartan al compactar
        prev = t["known"].get(e["mbid"])
        if prev:  # cambio de opinión sobre un disco ya plegado: se saca su aporte
            _item_delta(t["artists"], t["genres"], prev, -1, parse(prev["at"]), hl)
            t["known"].pop(e["mbid"], None)
        if e.get("action") in REACTIONS:
            _item_delta(t["artists"], t["genres"], e, +1, ts, hl)
            t["known"][e["mbid"]] = {"artist": e["artist"], "album": e["album"], "action": e["action"], "at": e["ts"],
                                     "genres": e.get("genres", []), "preset": e.get("preset")}
    return t, keep


def prune(taste, now):
    hl = taste.get("halfLifeDays", HALF_LIFE_DAYS)
    for field in ("artists", "genres"):
        taste[field] = {k: b for k, b in taste[field].items() if abs(decay(b["w"], parse(b["at"]), now, hl)) >= PRUNE}
    if len(taste["known"]) > KNOWN_MAX:
        items = sorted(taste["known"].items(), key=lambda kv: kv[1]["at"], reverse=True)[:KNOWN_MAX]
        taste["known"] = dict(items)
    return taste


def compact(taste, events, now, raw_days=RAW_DAYS, raw_max=RAW_MAX):
    """Pliega en taste los eventos más viejos que raw_days (y los que sobran por encima de raw_max), poda lo que ya
    pesa menos que PRUNE y devuelve (taste, eventos restantes)."""
    cut = now - raw_days * 86400
    if len(events) > raw_max:
        cut = max(cut, parse(events[len(events) - raw_max]["ts"]))
    t, keep = fold(taste, events, upto_ts=cut)
    if len(keep) < len(events):
        t["compactedThrough"] = iso(cut)
    t["updatedAt"] = iso(now)
    return prune(t, now), keep


# ---------------------------------------------------------------- pesos combinados
def source_buckets(sources, genres_of, now, hl, decades=None):
    """Pesos desde los favoritos de las fuentes. sources: [{kind, artist, title, added(ts|None), year?}]."""
    a, g = {}, {}
    d = decades if decades is not None else {}
    for s in sources:
        wa, wg = SOURCE_W.get(s["kind"], (0, 0))
        ts = s.get("added") or now
        _add(a, norm(s["artist"]), s["artist"], wa, ts, hl)
        if s["kind"] == "album" and isinstance(s.get("year"), int) and 1900 < s["year"] < 2100:
            dec = f"{s['year'] // 10 * 10}s"
            _add(d, dec, dec, 0.5, ts, hl)
        if wg and s.get("title"):
            for x in genres_of(s["artist"], s["title"]) or []:
                _add(g, norm(x), x, wg, ts, hl)
    return a, g


def weights(taste, events, sources, declared, now, genres_of=lambda a, t: [], cut=PRUNE):
    """Pesos efectivos en `now`: reacciones (agregado + crudos) + favoritos (con decaimiento) + perfil declarado.

    Devuelve {"artists": [...], "genres": [...]}, cada ítem {name, w, last, from: [...]}, de mayor a menor peso.
    """
    hl = taste.get("halfLifeDays", HALF_LIFE_DAYS)
    live, _ = fold(taste, [e for e in events if parse(e["ts"]) <= now])
    sd = {}
    sa, sg = source_buckets([s for s in sources if (s.get("added") or now) <= now], genres_of, now, hl, sd)
    out = {}
    live.setdefault("decades", {})
    for field, src in (("artists", sa), ("genres", sg), ("decades", sd)):
        acc = {}
        for origin, buckets in (("reacciones", live[field]), ("favoritos", src)):
            for k, b in buckets.items():
                w = decay(b["w"], parse(b["at"]), now, hl)
                x = acc.setdefault(k, {"name": b["name"], "w": 0.0, "last": b["at"], "from": []})
                x["w"] += w
                x["last"] = max(x["last"], b["at"])
                if origin not in x["from"] and w > 0:
                    x["from"].append(origin)
        for name in declared.get(field, []) if field != "decades" else []:
            x = acc.setdefault(norm(name), {"name": name, "w": 0.0, "last": None, "from": []})
            x["w"] += DECLARED_W
            x["from"].append("perfil")
        out[field] = sorted((dict(v, w=round(v["w"], 3)) for v in acc.values() if v["w"] >= cut),
                            key=lambda v: (-v["w"], v["name"]))
    return out


def reactions_map(taste, events):
    """mbid -> reacción vigente (agregado + crudos)."""
    out = {k: v["action"] for k, v in taste["known"].items()}
    for mbid, e in latest_reactions(events).items():
        if e.get("action") in REACTIONS:
            out[mbid] = e["action"]
        else:
            out.pop(mbid, None)
    return out


def history(taste, events, limit=60):
    """Discos clasificados, del más nuevo al más viejo: [{mbid, artist, album, action, at}]."""
    items = {k: {"mbid": k, "artist": v["artist"], "album": v["album"], "action": v["action"], "at": v["at"], "preset": v.get("preset")}
             for k, v in taste["known"].items()}
    for mbid, e in latest_reactions(events).items():
        if e.get("action") in REACTIONS:
            items[mbid] = {"mbid": mbid, "artist": e["artist"], "album": e["album"], "action": e["action"], "at": e["ts"],
                           "preset": e.get("preset")}
        else:
            items.pop(mbid, None)
    return sorted(items.values(), key=lambda x: x["at"], reverse=True)[:limit]


def shown_recently(events):
    return {e["mbid"] for e in events if e.get("type") == "shown"}


# ---------------------------------------------------------------- resumen en lenguaje natural (plantilla)
def _names(items, n):
    return ", ".join(i["name"] for i in items[:n])


def summary(w_now, w_before, hist, declared_text, now, n=8, imported=None):
    """memory.md: solo datos (nombres de favoritos, géneros de MusicBrainz, reacciones). Sin texto del modelo."""
    day = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d")
    out = ["# Memoria de Shed Stem Studio", f"Generada el {day} a partir de tus fuentes, tu perfil y tus reacciones. Se regenera sola.", ""]
    if declared_text:
        out += ["## Perfil", declared_text, ""]
    out.append("## Lo que más pesa hoy")
    out.append(f"- Artistas: {_names(w_now['artists'], n) or '(sin datos)'}")
    out.append(f"- Géneros (MusicBrainz y tu perfil): {_names(w_now['genres'], n) or '(sin datos)'}")
    if w_now.get("decades"):
        out.append(f"- Décadas de tus discos: {_names(w_now['decades'], 4)}")
    # "Bajando" = su parte del total cayó a menos del 60 % de la que tenía hace una vida media (todo decae igual;
    # lo que importa es lo que dejó de renovarse frente a lo demás).
    tot_now = sum(g["w"] for g in w_now["genres"]) or 1.0
    tot_before = sum(g["w"] for g in w_before["genres"]) or 1.0
    now_g = {norm(g["name"]): g["w"] / tot_now for g in w_now["genres"]}
    falling = [g for g in w_before["genres"][:12]
               if "perfil" not in g["from"] and now_g.get(norm(g["name"]), 0) < 0.6 * g["w"] / tot_before]
    if falling:
        out += ["", "## Bajando (pesa mucho menos que hace medio año)", f"- {_names(falling, 6)}"]
    if imported and (imported.get("gustos") or imported.get("jazz")):
        out += ["", "## Del cliente anterior (importado; no verificado acá)"]
        out += [f"- {x}" for x in (imported.get("gustos") or []) + (imported.get("jazz") or [])][:10]
    if hist:
        out += ["", "## Reacciones recientes"]
        out += [f"- {LABELS[h['action']]}: {h['artist']} - {h['album']}" for h in hist[:8]]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- archivos
class Store:
    """Lectura y escritura de los archivos de memoria en una carpeta dada."""

    def __init__(self, folder):
        self.dir = Path(folder)
        self.events_file = self.dir / "events.jsonl"
        self.taste_file = self.dir / "taste.json"
        self.md_file = self.dir / "memory.md"

    def _write(self, path, text):
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        osenv.secure(tmp, 0o600)
        tmp.replace(path)

    def load_taste(self, half_life_days=HALF_LIFE_DAYS):
        try:
            t = json.loads(self.taste_file.read_text(encoding="utf-8"))
            if t.get("version") == VERSION:
                t["halfLifeDays"] = half_life_days
                return t
        except (OSError, ValueError):
            pass
        return empty_taste(half_life_days)

    def load_events(self):
        try:
            lines = self.events_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out = []
        for line in lines:
            try:
                e = json.loads(line)
                parse(e["ts"])
                out.append(e)
            except (ValueError, KeyError, TypeError):
                continue  # una línea rota (corte de luz) no tira la historia
        return out

    def append(self, event):
        with _lock:
            self.dir.mkdir(parents=True, exist_ok=True)
            new = not self.events_file.exists()
            with self.events_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
            if new:
                osenv.secure(self.events_file, 0o600)

    def compact(self, now, half_life_days=HALF_LIFE_DAYS):
        """Compacta y guarda. Devuelve (taste, eventos)."""
        with _lock:
            taste, events = self.load_taste(half_life_days), self.load_events()
            t2, keep = compact(taste, events, now)
            self._write(self.taste_file, json.dumps(t2, ensure_ascii=False, indent=1))
            if len(keep) != len(events):
                self._write(self.events_file, "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in keep))
            return t2, keep

    def write_md(self, text):
        self._write(self.md_file, text)

    def read_md(self):
        try:
            return self.md_file.read_text(encoding="utf-8")
        except OSError:
            return ""
