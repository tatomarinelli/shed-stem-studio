"""Mapa de conocimiento: red de artistas, géneros y discos favoritos, con los recomendados afuera.

Vista derivada: se arma desde datos que ya existen (catálogo, pesos de gusto, reacciones, recomendaciones vigentes) y se puede borrar
sin perder nada. `build` es una función pura: recibe datos y `now`, devuelve nodos y aristas. Sin red ni disco.

Layout radial: la distancia al centro es el peso (centro = lo que más pesa), el ángulo agrupa por género principal y los recomendados
van en un anillo exterior. Todo `why` sale de una plantilla con datos del propio grafo, nunca de texto de un modelo.
"""
import hashlib
import math
import threading
import time

import genregate
import memory

# Parámetros ajustables (ver docs/mapa-grafo-plan.md). Todo `build` los toma de acá salvo que se pasen otros.
PARAMS = {
    "albumBase": 1.0,         # peso de un disco favorito en el día que se guardó
    "halfLifeDays": 180.0,    # decaimiento del peso de un favorito
    "undatedDays": 90,        # favoritos sin fecha de alta pesan como si fueran de hace tanto
    "reaction": {"loved": 1.5, "liked": 0.75, "heard": 0.25, "disliked": -0.5, "no": 0.0},
    "genresPerAlbum": 3,      # géneros que se conectan por disco
    "similarPerAlbum": 3,     # vecinos parecidos por disco
    "relatedPerArtist": 4,    # artistas parecidos que se unen a cada artista
    "similarMin": 0.34,       # parecido mínimo (Jaccard de géneros) para unir dos discos
    "sameArtistSim": 0.8,     # parecido de dos discos del mismo artista
    "recLinks": 2,            # discos propios con los que se une un recomendado
    "rMin": 0.08, "rMax": 0.85, "rRec": 1.0,   # radios normalizados: centro, borde de la red, anillo de recomendados
    "gamma": 0.55,            # <1 reparte por área: el centro no queda vacío (0,5 = densidad pareja)
    "petalMin": 0.034, "petalStep": 0.011, "petalMax": 0.11,   # flor: radio de los discos alrededor de su artista
    "repelIters": 40,         # relajación para que las flores no se pisen
    "commMin": 5,             # comunidades con menos nodos van a "sueltos"
    "bridges": 6, "gaps": 8,
    "recGap": 0.42,           # separación angular mínima entre recomendados (radianes)
}
KINDS = ("artist", "genre", "album", "rec")


def _h(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def album_id(artist, title):
    return "d:" + _h(f"{memory.norm(artist)}|{memory.norm(title)}")


def artist_id(name):
    return "a:" + memory.norm(name)


def genre_id(name):
    return "g:" + genregate.canon(name)


def rec_id(artist, title):
    return "r:" + _h(f"{memory.norm(artist)}|{memory.norm(title)}")


def _date(ts):
    return memory.iso(ts)[:10]


def _album_weight(a, reaction, now, p):
    ts = a.get("savedAt") or now - p["undatedDays"] * 86400
    w = memory.decay(p["albumBase"], min(ts, now), now, p["halfLifeDays"])
    if reaction:
        w += p["reaction"].get(reaction["action"], 0.0)
    return max(0.0, w), ts, bool(a.get("savedAt"))


def _jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _sector_key(genres, weights):
    """Género principal de un disco: el de más peso entre los suyos; sin géneros, ''."""
    best = ""
    for g in genres:
        if not best or (weights.get(g, 0.0), g) > (weights.get(best, 0.0), best):
            best = g
    return best


def build(albums, weights, reactions=(), recommended=(), own=(), now=0.0, params=None, artist_genres=None):
    """albums: discos del catálogo [{key, title, artist, year?, genres, sources, savedAt?, links?}].
    weights: salida de memory.weights ({"artists": [{name, w}], "genres": [{name, w}]}).
    reactions: [{artist, album, action, at}] vigentes. recommended: [{artist, album, mbid?, genres, reason?, score?}].
    own: artistas propios normalizados (nunca entran). artist_genres: {artista normalizado: [géneros]} de respaldo para discos sin géneros. Devuelve {"nodes": [...], "edges": [...], "stats": {...}}."""
    p = {**PARAMS, **(params or {})}
    own = set(own)
    react = {(memory.norm(r["artist"]), memory.norm(r["album"])): r for r in reactions}
    wa = {memory.norm(x["name"]): x["w"] for x in weights.get("artists", [])}
    wg = {genregate.canon(x["name"]): x["w"] for x in weights.get("genres", [])}

    nodes, edges = {}, []

    def node(nid, type_, label, w=0.0, **extra):
        n = nodes.get(nid)
        if n is None:
            n = nodes[nid] = {"id": nid, "type": type_, "label": label, "w": 0.0, **extra}
        n["w"] = max(n["w"], w)
        return n

    def edge(a, b, type_, w, why, evidence, at=None):
        edges.append({"from": a, "to": b, "type": type_, "w": round(w, 3), "at": at, "evidence": evidence, "why": why})

    own_albums = []
    genre_sets = {}
    for a in albums:
        if not a.get("artist") or not a.get("title") or memory.norm(a["artist"]) in own:
            continue
        r = react.get((memory.norm(a["artist"]), memory.norm(a["title"])))
        w, ts, dated = _album_weight(a, r, now, p)
        did, aid = album_id(a["artist"], a["title"]), artist_id(a["artist"])
        src = list(a.get("sources", []))
        node(did, "album", a["title"], w, artist=a["artist"], year=a.get("year"), sources=src, links=a.get("links", {}), artUrl=a.get("artUrl"),
             saved=_date(ts) if dated else None, key=a.get("key"), **({"reaction": r["action"]} if r else {}))
        node(aid, "artist", a["artist"], wa.get(memory.norm(a["artist"]), 0.0))
        edge(did, aid, "by", 1.0, f"\"{a['title']}\" es de {a['artist']}.", [{"kind": "catalog", "sources": src}])
        gs, inferred = [], False
        for g in (a.get("genres") or [])[:p["genresPerAlbum"]]:
            c = genregate.canon(g)
            if c and c not in gs:
                gs.append(c)
        if not gs:  # sin géneros propios: los del artista (MusicBrainz, de la caché local), marcados como heredados
            for g in (artist_genres or {}).get(memory.norm(a["artist"]), [])[:p["genresPerAlbum"]]:
                c = genregate.canon(g)
                if c and c not in gs:
                    gs.append(c)
            inferred = bool(gs)
        nodes[did]["genresFrom"] = "artist" if inferred else ("album" if gs else "none")
        genre_sets[did] = set(gs)
        for pos, c in enumerate(gs):
            node(genre_id(c), "genre", c, wg.get(c, 0.0))
            if inferred:
                edge(did, genre_id(c), "has-genre", 0.6 / (1 + pos), f"\"{c}\" es un género de {a['artist']}; \"{a['title']}\" no tiene géneros propios.",
                     [{"kind": "musicbrainz-artist", "artist": a["artist"], "inherited": True}])
            else:
                edge(did, genre_id(c), "has-genre", 1.0 / (1 + pos), f"\"{c}\" figura entre los géneros de \"{a['title']}\".",
                     [{"kind": "catalog", "field": "genres", "album": a["title"]}])
        own_albums.append((did, aid, a, gs))

    # artistas y géneros sin peso propio pesan lo que suman sus discos
    for field, prefix in (("artist", "a:"), ("genre", "g:")):
        for n in nodes.values():
            if n["type"] == field and n["w"] == 0.0:
                nbrs = [nodes[e["from"]]["w"] for e in edges if e["to"] == n["id"] and e["from"] in nodes and e["type"] in ("by", "has-genre")]
                n["w"] = sum(nbrs)

    # jerarquía de géneros
    for n in [n for n in nodes.values() if n["type"] == "genre"]:
        for parent in sorted(genregate.PARENTS.get(n["id"][2:], ())):
            if "g:" + parent in nodes:
                edge(n["id"], "g:" + parent, "subgenre-of", 1.0, f"\"{n['label']}\" es un subgénero de \"{parent}\" (regla propia).",
                     [{"kind": "rule", "source": "genregate.PARENTS"}])

    # artistas: sus géneros (los de sus discos) y los artistas con los que comparten géneros
    a_genres, a_albums = {}, {}
    for did, aid, a, gs in own_albums:
        a_albums[aid] = a_albums.get(aid, 0) + 1
        for c in gs:
            a_genres.setdefault(aid, {})[c] = a_genres.setdefault(aid, {}).get(c, 0) + 1
    for aid in sorted(a_genres):
        for c, k in sorted(a_genres[aid].items(), key=lambda kv: (-kv[1], kv[0])):
            discos = "disco" if k == 1 else "discos"
            edge(aid, genre_id(c), "has-genre", k / a_albums[aid], f"\"{c}\" figura en {k} {discos} de {nodes[aid]['label']}.",
                 [{"kind": "catalog", "field": "genres", "artist": nodes[aid]["label"], "albums": k}])
    a_sets = {aid: set(v) for aid, v in a_genres.items()}
    rel_pairs = set()
    for aid in sorted(a_sets):
        cand = []
        for other in sorted(a_sets):
            if other != aid:
                sim = _jaccard(a_sets[aid], a_sets[other])
                if sim >= p["similarMin"]:
                    cand.append((sim, other))
        for sim, other in sorted(cand, key=lambda x: (-x[0], x[1]))[:p["relatedPerArtist"]]:
            pair = tuple(sorted((aid, other)))
            if pair in rel_pairs:
                continue
            rel_pairs.add(pair)
            shared = sorted(a_sets[aid] & a_sets[other])
            edge(aid, other, "related", sim, f"{nodes[aid]['label']} y {nodes[other]['label']} comparten {', '.join(shared)}.",
                 [{"kind": "derived", "formula": "Jaccard de géneros", "shared": shared, "value": round(sim, 3)}])

    # discos parecidos: mismo artista o géneros en común
    by_genre, by_artist = {}, {}
    for did, aid, a, gs in own_albums:
        by_artist.setdefault(aid, []).append(did)
        for g in gs:
            by_genre.setdefault(g, []).append(did)
    seen_pairs = set()
    for did, aid, a, gs in own_albums:
        cand = {}
        for other in by_artist[aid]:
            if other != did:
                cand[other] = (p["sameArtistSim"], "artist")
        for g in gs:
            for other in by_genre[g]:
                if other != did and other not in cand:
                    s = _jaccard(genre_sets[did], genre_sets[other])
                    if s >= p["similarMin"]:
                        cand[other] = (s, "genres")
        top = sorted(cand.items(), key=lambda kv: (-kv[1][0], kv[0]))[:p["similarPerAlbum"]]
        for other, (s, how) in top:
            pair = tuple(sorted((did, other)))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            o = nodes[other]
            if how == "artist":
                why = f"\"{a['title']}\" y \"{o['label']}\" son del mismo artista, {a['artist']}."
                ev = [{"kind": "derived", "formula": "mismo artista", "artist": a["artist"]}]
            else:
                shared = sorted(genre_sets[did] & genre_sets[other])
                why = f"\"{a['title']}\" y \"{o['label']}\" comparten {', '.join(shared)}."
                ev = [{"kind": "derived", "formula": "Jaccard de géneros", "shared": shared, "value": round(s, 3)}]
            edge(did, other, "similar", s, why, ev)
            edges[-1]["scope"] = "same-artist" if how == "artist" else "other-artist"

    # recomendados: afuera de la red, unidos a lo propio más parecido
    recs_out = []
    for r in recommended:
        if not r.get("artist") or not r.get("album") or memory.norm(r["artist"]) in own:
            continue
        rid = rec_id(r["artist"], r["album"])
        if rid in nodes or album_id(r["artist"], r["album"]) in nodes:
            continue  # ya es tuyo: no es una recomendación
        gs = []
        for g in (r.get("genres") or []):
            c = genregate.canon(g)
            if c and c not in gs:
                gs.append(c)
        rs = set(gs[:p["genresPerAlbum"]])
        node(rid, "rec", r["album"], float(r.get("score") or 0.0), artist=r["artist"], year=r.get("year"), mbid=r.get("mbid"),
             **({"reason": r["reason"]} if r.get("reason") else {}))
        cand = []
        for did, aid, a, ags in own_albums:
            s = _jaccard(rs, genre_sets[did])
            if memory.norm(a["artist"]) == memory.norm(r["artist"]):
                s = max(s, p["sameArtistSim"])
            if s > 0:
                cand.append((s, did))
        cand.sort(key=lambda x: (-x[0], x[1]))
        for s, did in cand[:p["recLinks"]]:
            shared = sorted(rs & genre_sets[did])
            why = f"Se parece a \"{nodes[did]['label']}\" (lo guardaste): comparten {', '.join(shared)}." if shared else \
                  f"Es del mismo artista que \"{nodes[did]['label']}\"."
            edge(rid, did, "similar-to", s, why, [{"kind": "derived", "formula": "Jaccard de géneros", "shared": shared, "value": round(s, 3)}])
        recs_out.append(rid)

    _layout(nodes, edges, p)
    comms = _communities(nodes, edges, p)
    bridges = _bridges(nodes, edges, comms, p)
    gaps = _gaps(nodes, edges, p)
    return {"nodes": sorted(nodes.values(), key=lambda n: n["id"]), "edges": edges, "communities": comms, "bridges": bridges, "gaps": gaps,
            "stats": {**{k: sum(1 for n in nodes.values() if n["type"] == k) for k in KINDS}, "edges": len(edges), "communities": len(comms)}}


def _layout(nodes, edges, p):
    """Posición radial: radio por peso (el que más pesa, al centro), ángulo por género principal. Determinístico."""
    g_w = {n["id"][2:]: n["w"] for n in nodes.values() if n["type"] == "genre"}
    gens = {}
    for e in edges:
        if e["type"] == "has-genre":
            gens.setdefault(e["from"], []).append(e["to"][2:])
    sector = {}
    for nid, n in nodes.items():
        if n["type"] == "album":
            sector[nid] = _sector_key(gens.get(nid, []), g_w)
        elif n["type"] == "genre":
            sector[nid] = nid[2:]
    for e in edges:  # artistas: el género principal de sus discos; recomendados: el de su vecino más cercano
        if e["type"] == "by" and e["to"] in nodes:
            sector.setdefault("art:" + e["to"], []).append(sector.get(e["from"], ""))
    for nid, n in nodes.items():
        if n["type"] == "artist":
            c = [x for x in sector.get("art:" + nid, []) if x]
            sector[nid] = max(sorted(set(c)), key=c.count) if c else ""
    for e in sorted((e for e in edges if e["type"] == "similar-to"), key=lambda e: -e["w"]):
        sector.setdefault(e["from"], sector.get(e["to"], ""))
    for nid, n in nodes.items():
        if n["type"] == "rec":
            sector.setdefault(nid, "")
    # el género sin padre pasa a su padre, para que dub y reggae queden en el mismo sector
    def root(g):
        seen = set()
        while g and g not in seen and genregate.PARENTS.get(g):
            seen.add(g)
            g = sorted(genregate.PARENTS[g], key=lambda x: (-g_w.get(x, 0.0), x))[0]
        return g
    groups = {}
    for nid in nodes:
        k = root(sector.get(nid, ""))
        groups.setdefault(k, []).append(nid)
        nodes[nid]["group"] = k
    _place(nodes, edges, groups, p)
    recs = sorted((n for n in nodes.values() if n["type"] == "rec"), key=lambda n: (n["angle"], n["id"]))
    gap = min(p["recGap"], 2 * math.pi / max(1, len(recs)))
    prev = None
    for n in recs:  # que no se apilen en el anillo
        ang = n["angle"] if prev is None else max(n["angle"], prev + gap)
        prev = ang
        n["angle"], n["x"], n["y"] = round(ang, 4), round(p["rRec"] * math.cos(ang), 4), round(p["rRec"] * math.sin(ang), 4)
    for n in nodes.values():
        n["w"] = round(n["w"], 3)
        n["radius"] = round(math.hypot(n["x"], n["y"]), 4)
        n["angle"] = round(math.atan2(n["y"], n["x"]) % (2 * math.pi), 4)


def _place(nodes, edges, groups, p):
    """Posiciones. Artistas y géneros van en el radar (radio = ranking de peso, ángulo = sector); cada artista es el centro de una
    "flor" con sus discos como pétalos; los recomendados quedan en el anillo exterior. Determinístico."""
    owner = {e["from"]: e["to"] for e in edges if e["type"] == "by"}
    for nid, n in nodes.items():  # el disco hereda el sector de su artista: la flor no se parte
        if n["type"] == "album" and owner.get(nid) in nodes:
            n["group"] = nodes[owner[nid]]["group"]
    petals = {}
    for nid, n in nodes.items():
        if n["type"] == "album" and nid in owner:
            petals.setdefault(owner[nid], []).append(nid)
    hubs = [n for n in nodes.values() if n["type"] in ("artist", "genre")]
    reach = {}
    for n in hubs:
        k = len(petals.get(n["id"], ()))
        reach[n["id"]] = min(p["petalMax"], p["petalMin"] + p["petalStep"] * max(0, k - 1)) if k else 0.0
    ranked = sorted(hubs, key=lambda n: (-n["w"], n["id"]))
    rank = {n["id"]: i / max(1, len(ranked) - 1) for i, n in enumerate(ranked)}
    total = max(1, len(hubs) + sum(1 for n in nodes.values() if n["type"] == "rec"))
    pos, start = {}, 0.0
    for k in sorted(groups, key=lambda k: (-len(groups[k]), k)):
        ids = sorted((i for i in groups[k] if nodes[i]["type"] in ("artist", "genre", "rec")), key=lambda i: (nodes[i]["type"], i))
        if not ids:
            continue
        span = 2 * math.pi * len(ids) / total
        for i, nid in enumerate(ids):
            ang = start + span * (i + 0.5) / len(ids)
            n = nodes[nid]
            r = p["rRec"] if n["type"] == "rec" else p["rMin"] + rank[nid] ** p["gamma"] * (p["rMax"] - p["rMin"])
            pos[nid] = [r * math.cos(ang), r * math.sin(ang)]
        start += span
    home = {i: list(v) for i, v in pos.items()}
    movable = [n["id"] for n in hubs]
    rad = {i: reach[i] + 0.014 for i in movable}
    cell = 0.25
    for _ in range(p["repelIters"]):  # las flores no se pisan: empuje entre vecinos y un tirón suave a su sitio
        grid = {}
        for i in movable:
            grid.setdefault((int(pos[i][0] // cell), int(pos[i][1] // cell)), []).append(i)
        push = {i: [0.0, 0.0] for i in movable}
        for (cx, cy), cur in grid.items():
            near = [j for dx in (-1, 0, 1) for dy in (-1, 0, 1) for j in grid.get((cx + dx, cy + dy), ())]
            for a in cur:
                for b in near:
                    if a >= b:
                        continue
                    dx, dy = pos[a][0] - pos[b][0], pos[a][1] - pos[b][1]
                    d = math.hypot(dx, dy) or 1e-6
                    gap = rad[a] + rad[b] - d
                    if gap > 0:
                        ux, uy = (dx / d, dy / d) if d > 1e-5 else (math.cos(len(a) + len(b)), math.sin(len(a) + len(b)))
                        push[a][0] += ux * gap * 0.5; push[a][1] += uy * gap * 0.5
                        push[b][0] -= ux * gap * 0.5; push[b][1] -= uy * gap * 0.5
        for i in movable:
            x = pos[i][0] + push[i][0] + (home[i][0] - pos[i][0]) * 0.04
            y = pos[i][1] + push[i][1] + (home[i][1] - pos[i][1]) * 0.04
            r = math.hypot(x, y)
            if r > p["rMax"]:
                x, y = x * p["rMax"] / r, y * p["rMax"] / r
            pos[i] = [x, y]
    for nid, (x, y) in pos.items():
        nodes[nid]["x"], nodes[nid]["y"] = round(x, 4), round(y, 4)
        if nodes[nid]["type"] == "rec":
            nodes[nid]["angle"] = math.atan2(y, x) % (2 * math.pi)
    for aid, kids in petals.items():  # pétalos: parejos alrededor del artista, con una fase propia para no alinear todas las flores
        cx, cy = nodes[aid]["x"], nodes[aid]["y"]
        phase = int(_h(aid)[:4], 16) / 65535 * 2 * math.pi
        for k, did in enumerate(sorted(kids)):
            a = phase + 2 * math.pi * k / len(kids)
            nodes[did]["x"], nodes[did]["y"] = round(cx + reach[aid] * math.cos(a), 4), round(cy + reach[aid] * math.sin(a), 4)
    for n in nodes.values():
        n.setdefault("x", 0.0), n.setdefault("y", 0.0)
        n.setdefault("angle", 0.0)


# comunidades: Louvain (modularidad) determinístico sobre artistas, géneros y discos
LINK_W = {"by": 1.5, "has-genre": 1.0, "similar": 1.0, "subgenre-of": 0.6, "related": 0.6}


def _louvain(adj):
    """adj: {nodo: {vecino: peso}} simétrico. Devuelve {nodo: comunidad}. Orden fijo: mismo grafo, mismo resultado."""
    member = {i: [i] for i in adj}
    level = {i: dict(v) for i, v in adj.items()}
    for _ in range(6):
        comm = {i: i for i in level}
        deg = {i: sum(v.values()) for i, v in level.items()}
        m2 = sum(deg.values())
        if not m2:
            break
        tot = dict(deg)
        moved_any = False
        for _pass in range(20):
            moved = False
            for i in sorted(level):
                ci = comm[i]
                links = {}
                for j, w in level[i].items():
                    if j != i:
                        links[comm[j]] = links.get(comm[j], 0.0) + w
                tot[ci] -= deg[i]
                best, gain = ci, links.get(ci, 0.0) - tot[ci] * deg[i] / m2
                for c in sorted(links):
                    g = links[c] - tot[c] * deg[i] / m2
                    if g > gain + 1e-12:
                        best, gain = c, g
                tot[best] += deg[i]
                if best != ci:
                    comm[i], moved = best, True
            moved_any = moved_any or moved
            if not moved:
                break
        if not moved_any:
            break
        groups = {}
        for i, c in comm.items():
            groups.setdefault(c, []).extend(member[i])
        member = {c: sorted(v) for c, v in groups.items()}
        agg = {c: {} for c in member}
        for i, nb in level.items():
            for j, w in nb.items():
                ci, cj = comm[i], comm[j]
                agg[ci][cj] = agg[ci].get(cj, 0.0) + w
        level = agg
    return {x: c for c, v in member.items() for x in v}


def _adjacency(nodes, edges):
    adj = {i: {} for i, n in nodes.items() if n["type"] != "rec"}
    for e in edges:
        w = LINK_W.get(e["type"])
        if w and e["from"] in adj and e["to"] in adj:
            v = w * max(e["w"], 0.05)
            adj[e["from"]][e["to"]] = adj[e["from"]].get(e["to"], 0.0) + v
            adj[e["to"]][e["from"]] = adj[e["to"]].get(e["from"], 0.0) + v
    return adj


def _communities(nodes, edges, p):
    """Agrupa y nombra con sus géneros de más peso (dato, no invento). Devuelve la lista y marca `community` en cada nodo (-1 = suelto)."""
    adj = _adjacency(nodes, edges)
    raw = _louvain(adj)
    by = {}
    for nid, c in raw.items():
        by.setdefault(c, []).append(nid)
    big = sorted((v for v in by.values() if len(v) >= p["commMin"]), key=lambda v: (-len(v), v[0]))
    out, label = [], {}
    for idx, ids in enumerate(big):
        gen = sorted((nodes[i] for i in ids if nodes[i]["type"] == "genre"), key=lambda n: (-n["w"], n["id"]))
        art = sorted((nodes[i] for i in ids if nodes[i]["type"] == "artist"), key=lambda n: (-n["w"], n["id"]))
        name = " + ".join(n["label"] for n in gen[:2]) or (art[0]["label"] + (" y afines" if len(art) > 1 else "") if art else f"Grupo {idx + 1}")
        out.append({"id": idx, "name": name, "size": len(ids), "albums": sum(1 for i in ids if nodes[i]["type"] == "album"),
                    "genres": [n["label"] for n in gen[:3]], "artists": [n["label"] for n in art[:3]]})
        for i in ids:
            label[i] = idx
    for nid, n in nodes.items():
        n["community"] = label.get(nid, -1)
    for nid, n in nodes.items():  # una recomendación toma la comunidad del disco tuyo al que más se parece
        if n["type"] == "rec":
            best = max((e for e in edges if e["from"] == nid and e["type"] == "similar-to"), key=lambda e: (e["w"], e["to"]), default=None)
            n["community"] = nodes[best["to"]]["community"] if best else -1
    return out


def _bridges(nodes, edges, comms, p):
    """Géneros y artistas cuyos vínculos se reparten entre varias comunidades: los puentes."""
    names = {c["id"]: c["name"] for c in comms}
    adj = _adjacency(nodes, edges)
    found = []
    for nid, nb in adj.items():
        n = nodes[nid]
        if n["type"] not in ("artist", "genre") or n["community"] < 0:
            continue
        share = {}
        for j, w in nb.items():
            c = nodes[j]["community"]
            if c >= 0:
                share[c] = share.get(c, 0.0) + w
        tot = sum(share.values())
        if tot <= 0 or len(share) < 2:
            continue
        frac = {c: v / tot for c, v in share.items()}
        top = sorted(frac, key=lambda c: (-frac[c], c))[:2]
        if frac[top[1]] < 0.2:
            continue
        count = {c: sum(1 for j in nb if nodes[j]["community"] == c) for c in top}
        if sum(1 for j in nb if nodes[j]["community"] >= 0) < 4:
            continue  # con tan pocos vínculos no hay puente que valga
        if n["type"] == "genre" and min(count.values()) < 2:
            continue  # un género con un solo vínculo de cada lado es casualidad
        mix = 1 - sum(v * v for v in frac.values())
        found.append({"id": nid, "label": n["label"], "type": n["type"], "score": round(mix * math.sqrt(max(n["w"], 0.0)), 3),
                      "communities": top, "why": f"\"{n['label']}\" une \"{names[top[0]]}\" ({count[top[0]]} vínculos) con \"{names[top[1]]}\" ({count[top[1]]} vínculos).",
                      "evidence": [{"kind": "derived", "formula": "reparto de vínculos entre comunidades", "shares": {str(c): round(frac[c], 3) for c in top}}]})
    return sorted(found, key=lambda b: (-b["score"], b["id"]))[:p["bridges"]]


def _gaps(nodes, edges, p):
    """Géneros vecinos de lo que ya tenés (padre, hijo o hermano en la tabla propia) y de los que no hay ningún disco."""
    have = {}
    for e in edges:
        if e["type"] == "has-genre" and e["from"].startswith("d:") and nodes[e["from"]].get("genresFrom") != "artist":
            have.setdefault(e["to"][2:], set()).add(e["from"])
    owned = {g for g, ds in have.items() if ds}
    weight = {n["id"][2:]: n["w"] for n in nodes.values() if n["type"] == "genre"}
    refused = {g for g, ds in have.items() for d in ds if nodes[d].get("reaction") in ("disliked", "no")}
    children = {}
    for c, ps in genregate.PARENTS.items():
        for q in ps:
            children.setdefault(q, set()).add(c)
    cand = {}
    for g in sorted(owned):
        rel = [(q, "padre") for q in sorted(genregate.PARENTS.get(g, ()))] + [(c, "subgénero") for c in sorted(children.get(g, ()))]
        for q in sorted(genregate.PARENTS.get(g, ())):
            rel += [(h, "hermano") for h in sorted(children.get(q, ())) if h != g]
        for target, how in rel:
            if target in owned or target in refused:
                continue
            cand.setdefault(target, []).append((g, how))
    out = []
    for target, near in cand.items():
        near = sorted(set(near), key=lambda x: (-weight.get(x[0], 0.0), x[0]))
        score = sum(weight.get(g, 0.0) for g, _ in near)
        g, how = near[0]
        rel = {"padre": "es el género padre de", "subgénero": "es un subgénero de", "hermano": "es un género hermano de"}[how]
        out.append({"genre": target, "near": [g for g, _ in near[:3]], "score": round(score, 3),
                    "why": f"\"{target}\" {rel} \"{g}\" (lo tenés en {len(have[g])} discos) y no tenés discos de {target}.",
                    "evidence": [{"kind": "rule", "source": "genregate.PARENTS", "near": [g for g, _ in near[:3]]}]})
    picked, per = [], {}
    for x in sorted(out, key=lambda x: (-x["score"], x["genre"])):  # que no sean todos hijos del mismo género
        if per.get(x["near"][0], 0) < 2:
            per[x["near"][0]] = per.get(x["near"][0], 0) + 1
            picked.append(x)
    return picked[:p["gaps"]]


def current(now=None):
    """El mapa con los datos reales de la máquina: catálogo, pesos de gusto, reacciones y recomendaciones vigentes."""
    import catalog
    import recs

    now = now or time.time()
    snap = recs.snapshot(now)
    last = recs._read_json(recs.LAST, {}) or {}
    picks = []
    for key in ("daily", "request"):
        r = last.get(key) or {}
        picks += [x for x in [r.get("pick"), *(r.get("alternatives") or [])] if x]
    albums = [{**a, "savedAt": catalog._ts(a.get("savedAt"))} for a in catalog.snapshot()["albums"]]
    return build(albums, snap["weights"], snap["history"], picks, recs.own_artists(), now, artist_genres=_cached_artist_genres(recs))


def context(names, data=None):
    """Todo lo que el mapa sabe de las comunidades elegidas (por nombre): para que el recomendador lea la red. Solo datos del grafo, nada inventado.
    Devuelve None si ninguna existe. `artists` va completo (de más a menos peso), cada uno con sus géneros."""
    g = data or current()
    zones = [c for c in g["communities"] if c["name"] in set(names)]
    if not zones:
        return None
    ids = {c["id"] for c in zones}
    nodes = {n["id"]: n for n in g["nodes"]}
    inside = {i for i, n in nodes.items() if n["community"] in ids and n["type"] != "rec"}
    a_gen = {}
    for e in g["edges"]:
        if e["type"] == "has-genre" and e["from"].startswith("a:") and e["from"] in inside:
            a_gen.setdefault(e["from"], []).append((e["w"], e["to"]))
    artists = []
    for i in sorted((i for i in inside if nodes[i]["type"] == "artist"), key=lambda i: (-nodes[i]["w"], i)):
        gs = [nodes[t]["label"] for _, t in sorted(a_gen.get(i, []), key=lambda x: (-x[0], x[1]))[:3]]
        artists.append({"name": nodes[i]["label"], "genres": gs})
    genres = [nodes[i]["label"] for i in sorted((i for i in inside if nodes[i]["type"] == "genre"), key=lambda i: (-nodes[i]["w"], i))][:8]
    albums = [f"{nodes[i]['artist']} - {nodes[i]['label']}" for i in sorted((i for i in inside if nodes[i]["type"] == "album"), key=lambda i: (-nodes[i]["w"], i))][:12]
    by_genre = {}
    for a in artists:
        for gn in a["genres"]:
            by_genre.setdefault(gn, []).append(a["name"])
    gset = set(genres)
    return {"zones": [{"name": c["name"], "size": c["size"], "albums": c["albums"], "genres": c["genres"]} for c in zones],
            "genres": genres, "artists": artists, "albums": albums, "byGenre": {k: v[:3] for k, v in by_genre.items()},
            "gaps": [x["genre"] for x in g["gaps"] if gset & set(x["near"])][:5],
            "bridges": [b["label"] for b in g["bridges"] if ids & set(b["communities"])][:5]}


_enrich = {"running": False, "done": 0, "total": 0}
_enrich_lock = threading.Lock()


def enrich_status():
    return dict(_enrich)


def enrich_start():
    """Busca en MusicBrainz los géneros de los artistas cuyos discos no tienen (a pedido; 1 consulta por segundo y con caché)."""
    import catalog
    import recs

    with _enrich_lock:
        if _enrich["running"]:
            return enrich_status()
        _enrich.update(running=True, done=0, total=0)

    def work():
        try:
            own = set(recs.own_artists())
            have = _cached_artist_genres(recs)
            todo = {}
            for a in catalog.snapshot()["albums"]:
                n = memory.norm(a.get("artist") or "")
                if n and n not in own and not a.get("genres") and n not in have:
                    todo.setdefault(n, a["artist"])
            _enrich["total"] = len(todo)
            for n, name in sorted(todo.items()):
                while catalog._pause.is_set():  # una recomendación en curso usa MusicBrainz primero
                    time.sleep(0.5)
                recs.mb_artist_genres(name)
                _enrich["done"] += 1
        finally:
            _enrich["running"] = False

    threading.Thread(target=work, daemon=True).start()
    return enrich_status()


def _cached_artist_genres(recs):
    """Géneros de artistas que ya están en las cachés de MusicBrainz de la máquina. Solo lee: no consulta la red."""
    out = {}
    for k, v in (recs._read_json(recs._genre_cache_file(), {}) or {}).items():
        if k.startswith("artist:") and isinstance(v, dict) and v.get("genres"):
            out[k[7:]] = v["genres"]
    for k, v in (recs._read_json(recs._artist_cache_file(), {}) or {}).items():
        data = v.get("data") if isinstance(v, dict) else None
        gs = data.get("genres") if isinstance(data, dict) else None
        if k.startswith("artist:") and gs:
            out.setdefault(k[7:], gs)
    return out
