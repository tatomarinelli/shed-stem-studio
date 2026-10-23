"""Perfil declarado del usuario (cuestionario). Archivo propio: <carpeta de memoria>/profile.json, permisos 600.

El modelo primero lee las fuentes; el cuestionario complementa. Todo campo es opcional.
"""
import json
import os
import osenv
import time
from pathlib import Path

LEVELS = ("principiante", "intermedio", "avanzado", "profesional")
IMPROVE = ("teoria", "modos", "oido", "repertorio", "improvisacion", "ritmo", "lectura", "tecnica")
IMPROVE_LABEL = {"teoria": "teoría", "modos": "modos", "oido": "oído", "repertorio": "repertorio", "improvisacion": "improvisación",
                 "ritmo": "ritmo", "lectura": "lectura", "tecnica": "técnica"}
DISCOVERY = ("nada", "algo", "mucho")
LISTENING = ("discos", "temas", "ambos")
PACE = ("", "15", "30", "60", "90")

DEFAULTS = {
    "instrument": "", "level": "", "improve": [], "loves": [], "avoids": [], "essentials": [], "ownArtists": [],
    "discovery": "algo", "listening": "discos", "pace": "", "notes": "",
    "useTime": False, "useWeather": False, "city": "", "geo": None,
    "dismissed": False, "updatedAt": None,
    "seeded": False, "seedSeen": False,   # se completó solo con el historial importado; el aviso se cierra con seedSeen
    "imported": None,                     # texto del cliente anterior (sin verificar acá): {quien, gustos, jazz, noSabemos}
}

# Lo que se sabía del usuario antes del cuestionario (ya se usaba en el prompt). Solo si el perfil está vacío.
LEGACY = ("Músico que estudia su instrumento y quiere mejorar teoría y oído. Prefiere discos enteros y sacar temas de oído.")


class ProfileError(ValueError):
    pass


def load(path):
    data = json.loads(json.dumps(DEFAULTS))
    try:
        data.update(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return data


def _text(v, n, label):
    if not isinstance(v, str):
        raise ProfileError(f"{label}: tiene que ser texto.")
    return " ".join(v.split())[:n]


def _list(v, n_items, n_chars, label):
    if isinstance(v, str):
        v = [x for x in v.replace(";", ",").split(",")]
    if not isinstance(v, list):
        raise ProfileError(f"{label}: lista inválida.")
    out = []
    for x in v:
        x = _text(x, n_chars, label)
        if x and x.lower() not in (y.lower() for y in out):
            out.append(x)
    return out[:n_items]


def _choice(v, options, label):
    if v not in options:
        raise ProfileError(f"{label}: opción inválida.")
    return v


def validate(patch):
    """Solo los campos conocidos, normalizados y con tope. `geo` nunca viene del cliente: lo resuelve el motor."""
    if not isinstance(patch, dict):
        raise ProfileError("Perfil inválido.")
    out = {}
    if "instrument" in patch:
        out["instrument"] = _text(patch["instrument"], 40, "Instrumento")
    if "level" in patch:
        out["level"] = _choice(patch["level"], ("",) + LEVELS, "Nivel")
    if "improve" in patch:
        imp = patch["improve"] if isinstance(patch["improve"], list) else []
        out["improve"] = [x for x in IMPROVE if x in imp]
    for key, label in (("loves", "Estilos que amás"), ("avoids", "Estilos que evitás")):
        if key in patch:
            out[key] = _list(patch[key], 12, 60, label)
    if "ownArtists" in patch:  # su propia banda o proyecto: nunca se recomienda ni cuenta como gusto
        out["ownArtists"] = _list(patch["ownArtists"], 5, 60, "Tu banda o proyecto")
    if "essentials" in patch:
        out["essentials"] = _list(patch["essentials"], 15, 80, "Artistas imprescindibles")
    if "discovery" in patch:
        out["discovery"] = _choice(patch["discovery"], DISCOVERY, "Música nueva")
    if "listening" in patch:
        out["listening"] = _choice(patch["listening"], LISTENING, "Cómo escuchás")
    if "pace" in patch:
        out["pace"] = _choice(str(patch["pace"]), PACE, "Ritmo de estudio")
    if "notes" in patch:
        out["notes"] = _text(patch["notes"], 300, "Notas")
    for key in ("useTime", "useWeather", "dismissed", "seedSeen"):
        if key in patch:
            out[key] = bool(patch[key])
    if "city" in patch:
        out["city"] = _text(patch["city"], 80, "Ciudad")
    return out


def save(path, patch, geocode=None, now=None, extra=None):
    """Guarda el perfil. Si se activa el clima con una ciudad nueva, la ubica con `geocode(ciudad)` (lo único que sale).
    `extra`: campos que solo escribe el motor (geo, seeded, imported); nunca vienen del cliente."""
    clean = validate(patch)
    data = load(path)
    data.update(clean)
    data.update(extra or {})
    if data["useWeather"] and data["city"]:
        if geocode and (not data.get("geo") or data["geo"].get("query") != data["city"]):
            data["geo"] = {**geocode(data["city"]), "query": data["city"]}
    elif not data["city"]:
        data["geo"] = None
    if set(clean) - {"dismissed", "seedSeen"}:
        data["updatedAt"] = now or time.time()
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    osenv.secure(tmp, 0o600)
    tmp.replace(p)
    return data


def filled(data):
    return bool(data.get("updatedAt"))


def declared(data):
    """Lo que entra a los pesos sin decaer: artistas imprescindibles y estilos que ama."""
    return {"artists": data.get("essentials", []), "genres": data.get("loves", [])}


def describe(data, skip=()):
    """Texto corto para el prompt y para memory.md. Solo lo que el usuario escribió. `skip`: partes que no van según el tipo de pedido
    (instrument, pace, improve, loves, essentials): un pedido "parecido a este disco" no necesita que toque guitarra ni lo que quiere mejorar."""
    if not filled(data):
        return LEGACY
    parts = []
    if data["instrument"] and "instrument" not in skip:
        parts.append(f"Toca {data['instrument']}" + (f", nivel {data['level']}" if data["level"] else "") + ".")
    if data["improve"] and "improve" not in skip:
        parts.append("Quiere mejorar: " + ", ".join(IMPROVE_LABEL[x] for x in data["improve"]) + ".")
    if data["loves"] and "loves" not in skip:
        parts.append("Ama: " + ", ".join(data["loves"]) + ".")
    if data["avoids"]:
        parts.append("Evita: " + ", ".join(data["avoids"]) + ".")
    if data["essentials"] and "essentials" not in skip:
        parts.append("Imprescindibles: " + ", ".join(data["essentials"]) + ".")
    parts.append({"discos": "Escucha discos enteros.", "temas": "Escucha temas sueltos.", "ambos": "Escucha discos y temas sueltos."}[data["listening"]])
    parts.append({"nada": "No quiere salir de su zona.", "algo": "Quiere conocer algo de música nueva.",
                  "mucho": "Quiere conocer mucha música nueva."}[data["discovery"]])
    if data["pace"] and "pace" not in skip:
        parts.append(f"Estudia unos {data['pace']} minutos por día.")
    if data["notes"]:
        parts.append(f"Notas suyas: {data['notes']}")
    return " ".join(parts)
