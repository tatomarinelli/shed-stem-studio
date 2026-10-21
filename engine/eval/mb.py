"""Cliente mínimo de MusicBrainz (<=1 consulta/s, User-Agent propio, caché en disco). Lógica copiada de engine/recs.py (verify/mb_search)."""
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import common

MB = "https://musicbrainz.org/ws/2/release-group"
CACHE = Path(__file__).resolve().parents[2] / "docs/agent-notes/model-eval-raw/mb-cache.json"
_last = [0.0]
_cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}


def _get(url):
    key = url
    if key in _cache:
        return _cache[key]
    wait = 1.1 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    for attempt in range(4):
        try:
            _last[0] = time.time()
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": common.UA}), timeout=30) as r:
                data = json.load(r)
            _cache[key] = data
            CACHE.write_text(json.dumps(_cache, ensure_ascii=False))
            return data
        except Exception:   # noqa: BLE001
            time.sleep(3 * (attempt + 1))
    raise RuntimeError("MusicBrainz no respondió")


def search(artist, album):
    q = f'releasegroup:"{album}" AND artist:"{artist}"'
    return _get(f"{MB}?query={urllib.parse.quote(q)}&fmt=json&limit=5").get("release-groups", [])


def match(artist, album, year=None):
    """(existe, existe_con_año_ok, grupo|None) con el mismo criterio que recs.verify."""
    for g in search(artist, album):
        credit = " ".join(a.get("name", "") for a in g.get("artist-credit", []) if isinstance(a, dict))
        if g.get("score", 0) < 90 or common.norm(g.get("title", "")) != common.norm(album) or common.norm(artist) not in common.norm(credit):
            continue
        y = int(g["first-release-date"][:4]) if g.get("first-release-date", "")[:4].isdigit() else None
        return True, not (year and y and abs(year - y) > 1), {"mbid": g["id"], "year": y, "title": g["title"], "artist": credit.strip()}
    return False, False, None


def match_lenient(artist, album):
    """Criterio más laxo sobre los mismos resultados: título igual o contenido, y algún token del artista (>=4 letras) en el crédito."""
    toks = [t for t in common.norm(artist).split() if len(t) >= 4]
    na = common.norm(album)
    for g in search(artist, album):
        credit = common.norm(" ".join(a.get("name", "") for a in g.get("artist-credit", []) if isinstance(a, dict)))
        nt = common.norm(g.get("title", ""))
        if g.get("score", 0) >= 70 and (nt == na or (len(na) > 6 and (na in nt or nt in na))) and any(t in credit for t in toks):
            return {"mbid": g["id"], "year": g.get("first-release-date", "")[:4], "title": g["title"], "artist": credit}
    return None


def genres(mbid):
    d = _get(f"{MB}/{mbid}?inc=genres+tags&fmt=json")
    return sorted({g["name"].lower() for g in d.get("genres", [])})
