"""Recomendación "artistas primero": el modelo propone ARTISTAS (los conoce mucho mejor que los títulos exactos) y los discos salen de
la lista real del artista en MusicBrainz. Así no hay discos inventados (antes ~60 % de lo propuesto no existía y cada inexistente
costaba dos consultas de 1,1 s) y los géneros del artista y del disco ya vienen en las mismas respuestas.

Recibe `mb_get` (la función con espaciado global de recs) y una caché (dict) para poder probarse sin red.
"""
import re
import time
import urllib.parse

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

ARTIST = "https://musicbrainz.org/ws/2/artist"
RELEASE_GROUP = "https://musicbrainz.org/ws/2/release-group"
TTL = 30 * 86400
ALBUMS_PER_ARTIST = 6


def _norm(text):
    import memory

    return memory.norm(text)


def _genres(items):
    """[(nombre, votos)] de más a menos votado; sirve para 'tags' y 'genres' de MusicBrainz."""
    return [(g["name"].lower(), g.get("count", 0)) for g in sorted(items or [], key=lambda x: -x.get("count", 0)) if g.get("name")]


def resolve(name, mb_get, cache, now=None, need_origin=False):
    """{mbid, name, genres: [nombre...], votes: {nombre: votos}} del artista con ese nombre exacto; None si MusicBrainz no lo tiene."""
    now = now or time.time()
    key = "artist:" + _norm(name)
    hit = cache.get(key)
    fresh = hit and now - hit["at"] < TTL and (not hit.get("data") or UUID.match(str(hit["data"].get("mbid"))))  # un id que no es de MusicBrainz = caché dañada: se vuelve a pedir
    if fresh and not (need_origin and hit.get("data") and "country" not in hit["data"]):  # lo guardado antes de tener el país se pide de nuevo solo si hace falta
        return hit.get("data")
    q = urllib.parse.quote(f'artist:"{name}"')
    found = mb_get(f"{ARTIST}?query={q}&fmt=json&limit=5").get("artists", [])
    same = [a for a in found if a.get("score", 0) >= 90 and _norm(a.get("name", "")) == _norm(name)]
    # Hay artistas homónimos: el que más tags tiene es casi siempre el conocido.
    best = max(same, key=lambda a: (sum(t.get("count", 0) for t in a.get("tags", [])), a.get("score", 0)), default=None)
    data = None
    if best:
        gs = _genres(best.get("genres") or best.get("tags"))
        data = {"mbid": best["id"], "name": best["name"], "genres": [g for g, _ in gs][:8], "votes": dict(gs[:8]),
                "country": best.get("country"), "area": (best.get("area") or {}).get("name"), "beginArea": (best.get("begin-area") or {}).get("name")}
    cache[key] = {"at": now, "data": data}
    return data


def albums_of(artist, mb_get, cache, now=None, kind="album"):
    """Release-groups del artista: [{mbid, title, year, primary, secondary, genres, votes}]. Hasta 100 (los más relevantes de MusicBrainz)."""
    now = now or time.time()
    key = f"rg:{kind}:{artist['mbid']}"
    hit = cache.get(key)
    if hit and now - hit["at"] < TTL and all(UUID.match(str(a.get("mbid"))) for a in hit["data"]):
        return hit["data"]
    url = f"{RELEASE_GROUP}?artist={artist['mbid']}&type={kind}&inc=genres&limit=100&fmt=json"
    out = []
    for g in mb_get(url).get("release-groups", []):
        gs = _genres(g.get("genres"))
        date = g.get("first-release-date") or ""
        out.append({"mbid": g["id"], "title": g.get("title", ""), "year": int(date[:4]) if date[:4].isdigit() else None,
                    "primary": g.get("primary-type"), "secondary": g.get("secondary-types") or [],
                    "genres": [x for x, _ in gs][:6], "votes": sum(c for _, c in gs)})
    cache[key] = {"at": now, "data": out}
    return out


def pick_candidates(albums, keep, limit=ALBUMS_PER_ARTIST):
    """Los `limit` discos más prometedores del artista. `keep(album) -> (ok, rank)`: ok filtra (tipo, ya conocido, género) y rank
    ordena (mayor primero); a igual rank, más votos de género (señal de que MusicBrainz lo tiene bien descripto) y luego el más antiguo."""
    scored = []
    for a in albums:
        ok, rank = keep(a)
        if ok:
            scored.append((rank, a["votes"], -(a["year"] or 9999), a))
    scored.sort(key=lambda t: t[:3], reverse=True)
    seen, out = set(), []
    for *_, a in scored:  # versiones repetidas del mismo título (reediciones) cuentan una vez
        t = re.sub(r"[^a-z0-9]+", "", a["title"].lower())
        if t not in seen:
            seen.add(t)
            out.append(a)
        if len(out) == limit:
            break
    return out
