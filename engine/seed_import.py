"""Importador de una sola vez de profile-seed.json (perfil deducido del historial del usuario por otro proceso).

Mapea los campos de la semilla (nombres orientativos, en español) al esquema propio: cuestionario -> profile.json,
perfiles -> presets.json, eventos iniciales -> events.jsonl, memoria en lenguaje natural -> profile["imported"].
No pisa lo que el usuario ya editó y nunca modifica la semilla. Las funciones de mapeo son puras.
"""
import re
import unicodedata
from datetime import datetime

DAY = {"lun": 0, "mar": 1, "mie": 2, "jue": 3, "vie": 4, "sab": 5, "dom": 6}
IMPROVE = {"modos": "modos", "teoria": "teoria", "oido": "oido", "improvisacion": "improvisacion", "repertorio": "repertorio",
           "ritmo": "ritmo", "lectura": "lectura", "tecnica": "tecnica"}
INTENT = {"estudiar": "estudiar", "concentrarme": "concentrarme", "sorprenderme": "sorprenderme", "libre": "libre"}
DISCOVERY = {"nada": "nada", "poco": "nada", "algo": "algo", "mucho": "mucho", "mucha": "mucho"}
ACTION = {"me encanto": "loved", "le encanto": "loved", "ya lo escuche": "heard", "no me va": "no", "no me gusto": "no"}


def _as_list(v):
    return [x for x in (v if isinstance(v, list) else [v]) if x]


def _plain(s):
    s = unicodedata.normalize("NFD", str(s).lower())
    return "".join(c for c in s if not unicodedata.combining(c)).strip()


def _improve(items):
    out = []
    for x in items or []:
        p = _plain(x)
        key = next((v for k, v in IMPROVE.items() if p.startswith(k)), None)
        if key and key not in out:
            out.append(key)
    return out


def map_profile(seed):
    """Cuestionario de la semilla -> patch para profile.save (sin `geo`: lo resuelve el motor)."""
    q = seed.get("cuestionario") or {}
    ctx = q.get("contexto") or {}
    listen = _plain(q.get("comoEscucha", ""))
    notes = []
    if q.get("nivel"):
        notes.append(f"Nivel: {q['nivel']}")
    if "oido" in listen:
        notes.append("a veces saca temas de oído")
    if q.get("ritmoDeEstudio"):
        notes.append(f"estudia {q['ritmoDeEstudio']}")
    patch = {
        "instrument": str(q.get("instrumento") or ""),
        "improve": _improve(q.get("mejorar")),
        "loves": list(q.get("estilosQueAma") or []),
        "avoids": list(q.get("estilosQueEvita") or []),
        "ownArtists": [str(a) for a in _as_list(q.get("miBanda"))][:5],
        "essentials": [a for a in q.get("artistasImprescindibles") or [] if _plain(a) not in {_plain(b) for b in _as_list(q.get("miBanda"))}],
        "discovery": DISCOVERY.get(_plain(q.get("musicaNueva", "algo")), "algo"),
        "listening": "discos" if "disco" in listen and "tema" not in listen.split(";")[0] else ("temas" if "tema" in listen else "ambos"),
        "notes": "; ".join(notes)[:300],
        "useTime": bool(ctx.get("horarioYDia")),
        "useWeather": bool(ctx.get("ubicacionYClima")),
        "city": str(ctx.get("ciudad") or ""),
    }
    coords = {"latitude": ctx.get("lat"), "longitude": ctx.get("lon")} if isinstance(ctx.get("lat"), (int, float)) else None
    return patch, coords


def map_imported(seed):
    m = seed.get("memoriaNatural") or {}
    return {"quien": str(m.get("quienSoy") or "")[:400],
            "gustos": [str(x)[:300] for x in (m.get("gustosConEvidencia") or [])][:8],
            "jazz": [str(x)[:200] for x in (m.get("jazzPrimerasSenales") or [])][:5],
            "noSabemos": [str(x)[:200] for x in (m.get("noSabemos") or [])][:5],
            "origen": str(seed.get("origen") or "")[:300]}


def map_presets(seed):
    """Perfiles de la semilla -> datos para presets.save. El por defecto: el que su 'porQue' dice "por defecto";
    si no, el de menor prioridad sin horario."""
    out = []
    for p in seed.get("perfiles") or []:
        favor = list(p.get("favorecer") or [])
        out.append({
            "name": p.get("nombre", ""), "intent": INTENT.get(_plain(p.get("intencion", "")), "libre"),
            "schedule": [{"days": sorted({DAY[_plain(d)[:3]] for d in r.get("dias", []) if _plain(d)[:3] in DAY}),
                          "start": r.get("desde"), "end": r.get("hasta")} for r in p.get("horario") or []],
            "priority": int(p.get("prioridad") or 0),
            "discovery": DISCOVERY.get(_plain(p.get("novedad", "")), None),
            "favor": favor, "avoid": list(p.get("evitar") or []), "examples": list(p.get("ejemplosDeGusto") or []),
            "instrumental": any("instrumental" in _plain(f) for f in favor),
            "prompt": p.get("consigna", ""), "note": p.get("porQue", ""),
        })
    default = next((i for i, p in enumerate(seed.get("perfiles") or []) if "por defecto" in _plain(p.get("porQue", ""))), None)
    if default is None:
        cands = [i for i, p in enumerate(out) if not p["schedule"]]
        default = min(cands, key=lambda i: out[i]["priority"]) if cands else 0
    return {"presets": out, "defaultIndex": default}


def map_events(seed):
    """Eventos iniciales -> [(ts, artista, disco, reacción)]. 'guardó' no es una reacción: cuenta solo si no hay otra."""
    best = {}
    for e in seed.get("eventosIniciales") or []:
        if _plain(e.get("tipo", "album")) != "album" or not e.get("artista") or not e.get("titulo"):
            continue
        act = ACTION.get(_plain(e.get("accion", "")))
        try:
            ts = datetime.fromisoformat(e["ts"]).timestamp()  # sin huso: hora local de esta máquina
        except (KeyError, ValueError):
            continue
        key = (_plain(e["artista"]), _plain(e["titulo"]))
        if act:
            best[key] = (ts, e["artista"], e["titulo"], act)
        elif key not in best and re.match(r"guard", _plain(e.get("accion", ""))):
            best[key] = (ts, e["artista"], e["titulo"], "loved")
    return list(best.values())
