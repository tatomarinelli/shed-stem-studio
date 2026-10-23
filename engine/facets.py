"""Memoria segmentada: lo que la app sabe del usuario, separado por tema y generado SOLO con datos.

La fuente de verdad sigue siendo events.jsonl + taste.json + profile.json (ver memory.py). De ahí se derivan estas "facetas", cada una
en JSON (para el motor y para la vista de mapa) y en Markdown (para leerla):

  identity      quién es: instrumento, nivel, banda propia (declarado por él)
  taste         qué pesa hoy: artistas, géneros y décadas, con de dónde sale cada peso
  avoid         qué evita: estilos declarados, discos descartados
  habits        cómo usa la app: pedidos por perfil, qué reacciona
  learning      qué quiere mejorar y estudiar
  observations  hipótesis con evidencia (ids de discos): se muestran para que las confirme o rechace; nunca texto inventado
  graph         nodos y relaciones (artistas, géneros, discos, observaciones) para el mapa visual

Reglas: reacciones por ítem, nunca por género (una observación negativa se MUESTRA pero no cambia pesos ni se pasa sola al modelo; solo
si el usuario la confirma pasa a "evitar"). La banda propia (`ownArtists`) nunca aparece como gusto ni en el grafo.
Funciones puras (sin red ni reloj): reciben `now`.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import genregate
import memory

FACETS = ("identity", "taste", "avoid", "habits", "learning", "observations", "graph")
STATES = ("proposed", "confirmed", "rejected")
POSITIVE = ("loved", "liked")
NEGATIVE = ("disliked", "no")
MIN_EVIDENCE = 3          # reacciones mínimas a un género para armar una observación
GRAPH_ARTISTS, GRAPH_GENRES, GRAPH_ALBUMS = 25, 25, 40


def genres_by_mbid(taste, events=()):
    """mbid -> géneros del disco: los ya plegados en taste.known y los de las reacciones recientes (todavía en events.jsonl)."""
    out = {m: list(v.get("genres") or []) for m, v in taste.get("known", {}).items()}
    for m, e in memory.latest_reactions(events).items():
        if e.get("action") in memory.REACTIONS:
            out[m] = list(e.get("genres") or [])
    return out


def _oid(kind, key):
    return kind + ":" + hashlib.sha1(memory.norm(key).encode()).hexdigest()[:8]


# ---------------------------------------------------------------- observaciones (reglas determinísticas)
def observations(history, taste, states=None, events=()):
    """Hipótesis con evidencia. history: [{mbid, artist, album, action, at, known?}]; los géneros de cada disco salen de taste y events."""
    states = states or {}
    items = {h["mbid"]: h for h in history}
    gmap = genres_by_mbid(taste, events)
    genres = {}
    for mbid, h in items.items():
        for g in gmap.get(mbid, [])[:3]:
            genres.setdefault(genregate.canon(g), []).append(mbid)
    out = []

    def add(kind, key, text, confidence, evidence, effect):
        oid = _oid(kind, key)
        out.append({"id": oid, "kind": kind, "key": key, "text": text, "confidence": round(confidence, 2), "evidence": evidence[:8],
                    "effect": effect, "status": states.get(oid, "proposed")})

    for g, mbids in sorted(genres.items()):
        acts = [items[m]["action"] for m in mbids]
        pos, neg = sum(a in POSITIVE for a in acts), sum(a in NEGATIVE for a in acts)
        n = pos + neg
        if n < MIN_EVIDENCE:
            continue
        if pos / n >= 0.75:
            add("genre-pos", g, f"Te gustan los discos de {g}: {pos} de {n} que clasificaste.", min(0.95, n / 6), mbids,
                "Ya cuenta en tus gustos (por cada disco); esto solo lo resume.")
        elif neg / n >= 0.75:
            add("genre-neg", g, f"Seguís descartando discos de {g}: {neg} de {n}.", min(0.95, n / 6), mbids,
                "No cambia nada solo. Si lo confirmás, pasa a lo que evitás.")
    by_artist = {}
    for h in history:
        if h["action"] == "loved":
            by_artist.setdefault(memory.norm(h["artist"]), []).append(h)
    for hs in by_artist.values():
        if len(hs) >= 2:
            add("artist-pos", hs[0]["artist"], f"Te encantaron {len(hs)} discos de {hs[0]['artist']}.", min(0.95, len(hs) / 4),
                [h["mbid"] for h in hs], "Ya cuenta en tus gustos.")
    recent = [h for h in history if h["action"] != "clear"][:8]
    knowns = [h for h in recent if h.get("known")]
    if len(recent) >= 6 and len(knowns) / len(recent) >= 0.5:
        add("known-high", "recent", f"Ya conocías {len(knowns)} de los últimos {len(recent)} discos que clasificaste: quizás convenga más descubrimiento.",
            0.6, [h["mbid"] for h in knowns], "Podés subir el descubrimiento en tu perfil.")
    return out


# ---------------------------------------------------------------- facetas
def derive(snap, now, states=None, presets=None, focus=None):
    """snap: lo que devuelve recs.snapshot (taste, events, profile, sources, weights, history). Devuelve {faceta: dato}."""
    prof, w, taste, events, hist = snap["profile"], snap["weights"], snap["taste"], snap["events"], snap["history"]
    own = {memory.norm(a) for a in prof.get("ownArtists", [])}
    top = lambda items, n: [{"name": x["name"], "w": x["w"], "from": x.get("from", [])} for x in items if memory.norm(x["name"]) not in own][:n]
    obs = observations(hist, taste, states, events)
    confirmed_neg = [o for o in obs if o["kind"] == "genre-neg" and o["status"] == "confirmed"]
    identity = {"instrument": prof.get("instrument"), "level": prof.get("level"), "ownArtists": prof.get("ownArtists", []),
                "listening": prof.get("listening"), "pace": prof.get("pace"), "discovery": prof.get("discovery"), "notes": prof.get("notes")}
    taste_f = {"artists": top(w["artists"], 20), "genres": top(w["genres"], 15), "decades": top(w.get("decades", []), 5),
               "sources": {"favorites": len(snap.get("sources", [])), "reactions": len(hist)}}
    avoid = {"styles": list(prof.get("avoids", [])),
             "confirmedFromObservations": [o["text"] for o in confirmed_neg],
             "confirmedStyles": [o["key"] for o in confirmed_neg],  # solo lo que el usuario confirmó pasa a filtrar
             "discarded": [{"mbid": h["mbid"], "artist": h["artist"], "album": h["album"], "action": h["action"]} for h in hist if h["action"] in NEGATIVE][:30]}
    shown = [e for e in events if e.get("type") == "shown"]
    habits = {"shownByPreset": _count(e.get("preset") for e in shown), "shownByKind": _count(e.get("kind") for e in shown),
              "reactionsByPreset": _count(h.get("preset") for h in hist), "reactions": _count(h["action"] for h in hist),
              "knownRate": round(sum(1 for h in hist if h.get("known")) / len(hist), 2) if hist else None,
              "presets": [p["name"] for p in (presets or {}).get("presets", [])]}
    learning = {"improve": prof.get("improve", []), "focus": [(focus or {}).get(x, x) for x in prof.get("improve", [])],
                "instrument": prof.get("instrument"), "level": prof.get("level"), "notes": prof.get("notes")}
    f = {"identity": identity, "taste": taste_f, "avoid": avoid, "habits": habits, "learning": learning,
         "observations": {"items": obs, "generatedAt": memory.iso(now)}}
    f["graph"] = graph(f, hist, genres_by_mbid(taste, events), obs, own)
    return f


def _count(values):
    out = {}
    for v in values:
        if v:
            out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def graph(f, hist, gmap, obs, own=()):
    """Nodos y aristas para el mapa. id: a:artista, g:género, d:disco (mbid), o:observación. Pesos ya con decaimiento."""
    nodes, edges, seen = [], [], set()

    def node(nid, type_, label, w=None, **extra):
        if nid not in seen:
            seen.add(nid)
            nodes.append({"id": nid, "type": type_, "label": label, **({"w": round(w, 3)} if w is not None else {}), **extra})

    for a in f["taste"]["artists"][:GRAPH_ARTISTS]:
        node("a:" + memory.norm(a["name"]), "artist", a["name"], a["w"])
    for g in f["taste"]["genres"][:GRAPH_GENRES]:
        node("g:" + genregate.canon(g["name"]), "genre", g["name"], g["w"])
    for h in hist[:GRAPH_ALBUMS]:
        if memory.norm(h["artist"]) in own:
            continue
        d = "d:" + h["mbid"]
        node(d, "album", h["album"], None, action=h["action"], known=bool(h.get("known")))
        node("a:" + memory.norm(h["artist"]), "artist", h["artist"], 0.0)
        edges.append({"from": d, "to": "a:" + memory.norm(h["artist"]), "type": "by"})
        for g in gmap.get(h["mbid"], [])[:3]:
            gid = "g:" + genregate.canon(g)
            node(gid, "genre", g, 0.0)
            edges.append({"from": d, "to": gid, "type": "has-genre"})
    for g in [n for n in nodes if n["type"] == "genre"]:  # jerarquía de géneros: dub -> reggae
        for parent in genregate.PARENTS.get(g["id"][2:], ()):
            if "g:" + parent in seen:
                edges.append({"from": g["id"], "to": "g:" + parent, "type": "subgenre-of"})
    for o in obs:
        node("o:" + o["id"], "observation", o["text"], o["confidence"], status=o["status"])
        for m in o["evidence"]:
            if "d:" + m in seen:
                edges.append({"from": "o:" + o["id"], "to": "d:" + m, "type": "evidence"})
    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------- Markdown legible
TITLES = {"identity": "Quién sos", "taste": "Qué te gusta hoy", "avoid": "Qué evitás", "habits": "Cómo usás la app",
          "learning": "Qué querés aprender", "observations": "Lo que creo saber de vos"}


def _names(items, n=10):
    return ", ".join(f"{i['name']} ({i['w']:.1f})" for i in items[:n]) or "(sin datos todavía)"


def render_md(name, data):
    out = [f"# {TITLES[name]}", "Generado con tus datos; se regenera solo. No lo edites acá.", ""]
    if name == "identity":
        out += [f"- {k}: {v}" for k, v in data.items() if v not in (None, "", [])]
    elif name == "taste":
        out += [f"- Artistas: {_names(data['artists'])}", f"- Géneros: {_names(data['genres'])}", f"- Décadas: {_names(data['decades'], 5)}",
                f"- Base: {data['sources']['favorites']} favoritos, {data['sources']['reactions']} reacciones"]
    elif name == "avoid":
        out += [f"- Estilos que evitás: {', '.join(data['styles']) or '(ninguno)'}"]
        out += [f"- Confirmaste: {t}" for t in data["confirmedFromObservations"]]
        out += [f"- Descartaste: {d['artist']} - {d['album']}" for d in data["discarded"][:10]]
    elif name == "habits":
        out += [f"- Mostrados por perfil: {data['shownByPreset'] or '(sin datos)'}", f"- Reacciones: {data['reactions'] or '(sin datos)'}",
                f"- Ya conocías: {int((data['knownRate'] or 0) * 100)} % de lo que clasificaste"]
    elif name == "learning":
        out += [f"- Querés mejorar: {', '.join(data['focus']) or '(sin definir)'}", f"- Instrumento: {data['instrument']} ({data['level']})"]
    elif name == "observations":
        for o in data["items"]:
            out.append(f"- [{o['status']}] {o['text']} (confianza {o['confidence']}; {len(o['evidence'])} discos de evidencia)")
        if not data["items"]:
            out.append("(todavía no hay suficientes reacciones para sacar conclusiones)")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- archivos
def write_all(folder, facets, write):
    """Escribe <folder>/memory/<faceta>.json y .md. `write(path, text)` es el escritor atómico de memory.Store."""
    base = Path(folder) / "memory"
    for name in FACETS:
        write(base / f"{name}.json", json.dumps(facets[name], ensure_ascii=False, indent=1))
        if name in TITLES:
            write(base / f"{name}.md", render_md(name, facets[name]))


def load_states(folder):
    try:
        data = json.loads((Path(folder) / "memory" / "observation-states.json").read_text(encoding="utf-8"))
        return {k: v for k, v in data.items() if v in STATES}
    except (OSError, ValueError, AttributeError):
        return {}


def set_state(folder, write, oid, status):
    if status not in STATES:
        raise ValueError("Estado inválido.")
    states = load_states(folder)
    states[oid] = status
    write(Path(folder) / "memory" / "observation-states.json", json.dumps(states, ensure_ascii=False, indent=1))
    return states
