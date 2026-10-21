"""Perfiles de sugerencia: cambian la INTENCIÓN y los filtros según el día y la hora (los gustos salen del cuestionario,
las fuentes y la memoria, compartidos). Archivo: <carpeta de memoria>/presets.json, permisos 600.

Un perfil: {id, name, intent, schedule: [{days: [0..6 lunes=0], start: "HH:MM", end: "HH:MM"}], priority, discovery|null,
favor: [estilos], avoid: [estilos], examples: [artistas], instrumental: bool, prompt: str, note: str}. Un rango con
end <= start cruza la medianoche: pertenece al día en que empieza. Selección: el perfil con un rango que contiene "ahora";
si hay varios, primero se respeta lo que el usuario eligió explícitamente ("over": este perfil manda sobre esos ids),
después gana el rango más corto (más específico), después la prioridad más alta y después el que está más arriba;
si ninguno, el perfil por defecto.
"""
import json
import os
import osenv
import re
from pathlib import Path

INTENTS = ("estudiar", "concentrarme", "sorprenderme", "libre")
DAYS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MAX_PRESETS, MAX_RANGES = 8, 6
HHMM = re.compile(r"^([01]\d|2[0-4]):([0-5]\d)$")

DEFAULTS = {
    "version": 1,
    "default": "estudio",
    "presets": [
        {"id": "trabajo", "name": "Trabajo", "intent": "concentrarme", "schedule": [{"days": [0, 1, 2, 3, 4], "start": "09:00", "end": "18:00"}],
         "discovery": None, "favor": [], "avoid": [], "instrumental": True, "prompt": ""},
        {"id": "estudio", "name": "Estudio", "intent": "estudiar",
         "schedule": [{"days": [0, 1, 2, 3, 4, 6], "start": "18:00", "end": "02:00"}, {"days": [5, 6], "start": "00:00", "end": "24:00"}],
         "discovery": None, "favor": [], "avoid": [], "instrumental": False, "prompt": ""},
        {"id": "descubrir", "name": "Descubrir", "intent": "sorprenderme", "schedule": [], "discovery": "mucho",
         "favor": [], "avoid": [], "instrumental": False, "prompt": ""},
    ],
}


class PresetError(ValueError):
    pass


def minutes(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _range_len(r):
    a, b = minutes(r["start"]), minutes(r["end"])
    return b - a if b > a else 1440 - a + b


def in_range(r, weekday, minute):
    """¿El momento (día 0-6, minuto del día) cae en el rango? Cruce de medianoche: la parte de después de las 0:00
    corresponde al día siguiente al que figura en `days`."""
    a, b = minutes(r["start"]), minutes(r["end"])
    if b > a:
        return weekday in r["days"] and a <= minute < b
    return (weekday in r["days"] and minute >= a) or ((weekday - 1) % 7 in r["days"] and minute < b)


def select(data, weekday, minute):
    """Devuelve (perfil, "horario" | "defecto")."""
    hits = {}
    for i, p in enumerate(data["presets"]):
        for r in p.get("schedule", []):
            if in_range(r, weekday, minute):
                key = (_range_len(r), -int(p.get("priority") or 0), i)
                if p["id"] not in hits or key < hits[p["id"]][0]:
                    hits[p["id"]] = (key, p)
    beaten = {o for _, p in hits.values() for o in p.get("over", []) if o in hits}
    live = [h for pid, h in hits.items() if pid not in beaten] or list(hits.values())  # un ciclo no deja a nadie afuera
    if live:
        return min(live, key=lambda h: h[0])[1], "horario"
    by_id = {p["id"]: p for p in data["presets"]}
    return by_id.get(data.get("default")) or data["presets"][0], "defecto"


def _slug(name, taken):
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:24] or "perfil"
    s, n = base, 2
    while s in taken:
        s, n = f"{base}-{n}", n + 1
    return s


def _tags(v, label):
    if not isinstance(v, list):
        raise PresetError(f"{label}: lista inválida.")
    out = []
    for x in v[:12]:
        x = " ".join(str(x).split())[:80]
        if x and x.lower() not in (y.lower() for y in out):
            out.append(x)
    return out


def validate(data):
    if not isinstance(data, dict) or not isinstance(data.get("presets"), list):
        raise PresetError("Perfiles inválidos.")
    if not 1 <= len(data["presets"]) <= MAX_PRESETS:
        raise PresetError(f"Tiene que haber entre 1 y {MAX_PRESETS} perfiles.")
    out, ids = [], set()
    for p in data["presets"]:
        if not isinstance(p, dict):
            raise PresetError("Perfil inválido.")
        name = " ".join(str(p.get("name") or "").split())[:30]
        if not name:
            raise PresetError("Cada perfil necesita un nombre.")
        pid = str(p.get("id") or "")
        if not re.fullmatch(r"[a-z0-9-]{1,30}", pid) or pid in ids:
            pid = _slug(name, ids)
        ids.add(pid)
        if p.get("intent") not in INTENTS:
            raise PresetError(f"{name}: intención inválida.")
        sched = p.get("schedule") or []
        if not isinstance(sched, list) or len(sched) > MAX_RANGES:
            raise PresetError(f"{name}: horario inválido.")
        ranges = []
        for r in sched:
            days = sorted({int(d) for d in (r.get("days") or []) if str(d).isdigit() and 0 <= int(d) <= 6}) if isinstance(r, dict) else []
            if not days or not HHMM.match(str(r.get("start"))) or not HHMM.match(str(r.get("end"))):
                raise PresetError(f"{name}: cada horario necesita días y horas (HH:MM).")
            if r["start"] == r["end"] or minutes(r["start"]) >= 1440:
                raise PresetError(f"{name}: el horario no puede empezar y terminar a la misma hora.")
            ranges.append({"days": days, "start": r["start"], "end": r["end"]})
        disc = p.get("discovery")
        if disc not in (None, "nada", "algo", "mucho"):
            raise PresetError(f"{name}: novedad inválida.")
        prio = p.get("priority") or 0
        if not isinstance(prio, int) or isinstance(prio, bool) or not 0 <= prio <= 9:
            raise PresetError(f"{name}: prioridad entre 0 y 9.")
        out.append({"id": pid, "name": name, "intent": p["intent"], "schedule": ranges, "priority": prio, "discovery": disc,
                    "favor": _tags(p.get("favor") or [], "Estilos a favorecer"), "avoid": _tags(p.get("avoid") or [], "Estilos a evitar"),
                    "examples": _tags(p.get("examples") or [], "Referencias"),
                    "instrumental": bool(p.get("instrumental")), "prompt": " ".join(str(p.get("prompt") or "").split())[:240],
                    "note": " ".join(str(p.get("note") or "").split())[:200]})
    for p, raw in zip(out, data["presets"]):
        over = raw.get("over") if isinstance(raw.get("over"), list) else []
        p["over"] = [o for o in dict.fromkeys(str(x) for x in over) if o in ids and o != p["id"]]
    default = data.get("default") if data.get("default") in ids else out[0]["id"]
    return {"version": 1, "default": default, "presets": out}


def load(path):
    try:
        return validate(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return json.loads(json.dumps(DEFAULTS))


def save(path, data):
    clean = validate(data)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=1), encoding="utf-8")
    osenv.secure(tmp, 0o600)
    tmp.replace(p)
    return clean


def find(data, pid):
    return next((p for p in data["presets"] if p["id"] == pid), None)
