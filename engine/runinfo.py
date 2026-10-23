"""Con qué variables corre una búsqueda: lo que se entendió del pedido, del perfil y de los gustos, en forma estructurada y corta (no el texto del prompt).

Es lo que muestra la pantalla Agentes arriba de las tarjetas: quién sos según el perfil, qué pediste, qué perfil de sugerencia está activo, cuánto pesan los gustos frente
a lo nuevo, qué gustos pesan, qué se excluye y con qué parámetros trabajan los agentes. Función pura: recibe lo ya calculado por `recs`.
"""
import intent
import planner as planner_mod

SHORT = 80   # un texto escrito por el usuario se muestra recortado: lo que importa es que hubo texto, no el 1:1


def _top(items, n):
    return [{"name": x["name"], "w": round(x["w"], 1)} for x in items[:n]]


def _planner_view(req, info):
    """Cómo entendió el pedido el planificador. Todo es opinión del modelo salvo lo que traen las reglas (marcado con `source`); el brief nunca se presenta como hecho."""
    info = info or {}
    pl, era = req.get("plan") or {}, req.get("era")
    if not info.get("enabled"):
        return {"enabled": False}
    return {"enabled": True, "model": info.get("model"), "ran": bool(info.get("ran")), "ok": bool(info.get("ok")), "seconds": info.get("seconds") or 0,
            "era": {"from": era["from"], "to": era["to"], "source": era["source"], "strict": era["strict"]} if era else None,
            "mood": planner_mod.MOODS.get(pl.get("mood")), "instrumental": pl.get("instrumental"), "language": planner_mod.LANGS.get(pl.get("language")),
            "refs": pl.get("refs") or [], "genres": pl.get("genres") or [], "brief": pl.get("brief") or None,
            "added": info.get("added") or [], "dropped": len(info.get("dropped") or [])}


def describe(*, kind, request, prof, preset, pdata, mode, alpha, plan, ctx_text, weights, focus_labels, favorites, reactions, excluded, shown_recently,
             avoid, own_artists, half_life_days, engine, planner=None):
    req = request or {}
    text = (req.get("prompt") or "").strip()
    seed = req.get("seed")
    explicit_mode = req.get("mode")
    genres = req.get("genres") or []
    filled = bool(prof.get("instrument") or prof.get("improve") or prof.get("loves"))
    uses_focus = filled and bool(prof.get("improve")) and mode in (None, "estudiar") and plan["useGoals"]   # solo en modo estudiar o sin modo, y si el tipo de pedido las usa
    return {
        "kind": kind,
        "request": {"genres": genres, "strict": bool(req.get("strict")) if (genres or req.get("countries")) else None, "genresDetected": bool(req.get("genresDetected")),
                    "type": req.get("type"), "mode": mode, "modeFrom": "pedido" if explicit_mode else ("perfil" if mode else None),
                    "countries": req.get("countries") or [], "countryNames": [intent.country_name(c) for c in req.get("countries") or []], "countriesDetected": bool(req.get("countriesDetected")), "canon": bool(req.get("canon")),
                    "era": ({"from": req["era"]["from"], "to": req["era"]["to"], "source": req["era"]["source"], "strict": bool(req["era"].get("strict"))} if req.get("era") else None),
                    "hasText": bool(text), "text": (text[:SHORT] + "…") if len(text) > SHORT else text or None,
                    "seed": " - ".join(x for x in (seed.get("artist"), seed.get("album") or seed.get("title")) if x) if seed else None},
        "profile": {"filled": filled, "instrument": prof.get("instrument") or None, "level": prof.get("level") or None,
                    "focus": [focus_labels.get(x, x) for x in prof.get("improve", [])] if uses_focus else [], "focusSkipped": bool(prof.get("improve")) and not uses_focus,
                    "loves": prof.get("loves", []), "avoids": avoid, "discovery": pdata.get("discovery") or prof.get("discovery"),
                    "listening": prof.get("listening"), "ownArtists": own_artists},
        "preset": {"name": preset.get("name"), "how": preset.get("how"), "intent": pdata.get("intent"), "instrumental": bool(pdata.get("instrumental")),
                   "favor": pdata.get("favor", []), "hasPrompt": bool(pdata.get("prompt"))},
        "plan": {"kind": plan["kind"], "label": plan["label"], "useInstrument": plan["useInstrument"], "useGoals": plan["useGoals"], "useTaste": plan["useTaste"],
                 "requestPct": round(plan["requestWeight"] * 100), "why": plan["why"]},
        "scoring": {"tastePct": round(alpha * 100), "genreWeightPct": 75 if genres else None,
                    "textWeightPct": 65 if (text or seed) and not genres and not req.get("countries") else None},
        "taste": {"artists": _top(weights.get("artists", []), 6), "genres": _top(weights.get("genres", []), 6), "decades": _top(weights.get("decades", []), 3),
                  "favorites": favorites, "reactions": reactions, "halfLifeDays": round(half_life_days)},
        "exclusions": {"known": excluded, "shownRecently": shown_recently},
        "context": ctx_text or None,
        "planner": _planner_view(req, planner),
        "engine": engine,
    }
