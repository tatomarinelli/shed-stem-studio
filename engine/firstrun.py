"""Asistente de primer inicio: el estado de cada paso se calcula de lo que realmente está instalado y configurado.

No guarda estado propio salvo si el usuario ya cerró el asistente (`setup.done`) y qué pasos saltó (`setup.skipped`),
en los ajustes. Nada se instala ni se descarga desde acá: eso lo hacen los botones de cada paso.
"""
import envsetup
import library
import models
import recs
import settings
import stems
import tidal_source

STEPS = ("equipo", "carpetas", "separacion", "musica", "modelo", "perfil")
ESSENTIAL = ("separacion", "musica", "modelo", "perfil")
LABELS = {"equipo": "Tu equipo", "carpetas": "Dónde guardar", "separacion": "Separación en instrumentos", "musica": "Fuentes",
          "modelo": "Recomendaciones", "perfil": "Perfil de gustos"}


def _chat_models():
    tags = models.ollama_tags()
    return None if tags is None else [m for m in tags if "embed" not in m["name"].lower()]


def _step_state(done, running, error, skipped):
    if done:
        return "done"
    if running:
        return "running"
    if error:
        return "error"
    return "skipped" if skipped else "pending"


def status():
    s = settings.load()
    cfg = s.get("setup") or {}
    skipped = set(cfg.get("skipped") or [])
    sep_env, sep_model = envsetup.present(), stems.sep_model_present()
    folders = s.get("musicFolders") or []
    tracks = len(library._state["tracks"])
    try:
        tidal_ok = bool(tidal_source.status().get("connected"))
    except Exception:
        tidal_ok = False
    chat = _chat_models()
    pulling = any(p.get("state") == "running" for p in models._pulls.values())
    pull_error = any(p.get("state") == "error" for p in models._pulls.values())
    prof_done = recs.profile_mod.filled(recs.load_profile())

    steps = {
        "equipo": {"state": "done", "detail": {}},
        "carpetas": {"state": "done", "detail": {"dataDir": settings.effective(s)["dataDir"]}},
        "separacion": {"state": _step_state(sep_env and sep_model, envsetup._job["state"] == "running" or stems._dl["state"] == "running",
                                            envsetup._job["state"] == "error" or stems._dl["state"] == "error", "separacion" in skipped),
                       "detail": {"env": sep_env, "model": sep_model}},
        # Una carpeta vacía no cuenta (por ejemplo la que Docker monta por defecto): hace falta TIDAL o música encontrada.
        "musica": {"state": _step_state(tidal_ok or tracks > 0 or (bool(folders) and library._state["scanning"]), False, False, "musica" in skipped),
                   "detail": {"folders": len(folders), "tracks": tracks, "tidal": tidal_ok}},
        "modelo": {"state": _step_state(bool(chat), pulling, pull_error, "modelo" in skipped),
                   "detail": {"serverUp": chat is not None, "installed": [m["name"] for m in chat or []]}},
        "perfil": {"state": _step_state(prof_done, False, False, "perfil" in skipped), "detail": {}},
    }
    complete = all(steps[k]["state"] == "done" for k in ESSENTIAL)
    missing = [k for k in ESSENTIAL if steps[k]["state"] != "done"]
    return {"steps": [{"id": k, "label": LABELS[k], **steps[k]} for k in STEPS],
            "complete": complete, "missing": missing, "closed": bool(cfg.get("done")),
            # El asistente se abre solo la primera vez que falta algo esencial; después, solo un aviso discreto.
            "show": not cfg.get("done") and not complete,
            "notice": bool(cfg.get("done")) and not complete}


def _save(**changes):
    cur = dict(settings.load().get("setup") or {})
    cur.update(changes)
    settings.save({"setup": cur})


def skip(step, on=True):
    if step not in STEPS:
        raise settings.SettingsError("Ese paso no existe.")
    cur = set((settings.load().get("setup") or {}).get("skipped") or [])
    cur.add(step) if on else cur.discard(step)
    _save(skipped=sorted(cur))


def finish():
    _save(done=True)


def reset():
    _save(done=False, skipped=[])
