"""Portadas de Spotify y YouTube Music: el motor las baja de a una desde los servidores de imágenes del servicio y las
guarda en disco, así la interfaz no carga nada de terceros. Solo https y solo esos dominios; tamaño y tipo acotados."""
import hashlib
import urllib.parse
import urllib.request
from pathlib import Path

import settings

# Dominios de imágenes de cada servicio. Se acepta el dominio y sus subdominios (YouTube Music sirve de yt3, lh3, lh4… .googleusercontent.com).
HOSTS = ("scdn.co", "spotifycdn.com", "ytimg.com", "ggpht.com", "googleusercontent.com")
MAX_BYTES = 1_500_000
TIMEOUT = 15
_urlopen = urllib.request.urlopen  # las pruebas lo reemplazan


def allowed(url):
    p = urllib.parse.urlparse(str(url))
    host = p.hostname or ""
    return p.scheme == "https" and any(host == h or host.endswith("." + h) for h in HOSTS) and not p.username and len(str(url)) < 600


def url_for(thumb):
    """Dirección del motor para una portada externa (None si no es de un dominio permitido)."""
    return "/engine/extart?" + urllib.parse.urlencode({"u": thumb}) if thumb and allowed(thumb) else None


def _cache_dir():
    return Path(settings.effective()["dataDir"]) / "catalog" / "art"


def fetch(url):
    """(bytes, content-type) de la portada, de la caché o de la red; None si no se puede."""
    if not allowed(url):
        return None
    f = _cache_dir() / (hashlib.sha1(url.encode()).hexdigest() + ".img")
    try:
        data = f.read_bytes()
        return data[1:], {1: "image/jpeg", 2: "image/png", 3: "image/webp"}.get(data[0], "image/jpeg")
    except OSError:
        pass
    try:
        with _urlopen(urllib.request.Request(url, headers={"User-Agent": "ShedStemStudio"}), timeout=TIMEOUT) as r:
            ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            body = r.read(MAX_BYTES + 1)
    except Exception:
        return None
    if ctype not in ("image/jpeg", "image/png", "image/webp") or not body or len(body) > MAX_BYTES:
        return None
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(bytes([{"image/jpeg": 1, "image/png": 2, "image/webp": 3}[ctype]]) + body)
    except OSError:
        pass
    return body, ctype


def cached_cover(key, produce):
    """Bytes de una portada guardada en disco con esa clave; si no está, `produce()` la pide una vez y la guarda."""
    f = _cache_dir() / f"{hashlib.sha1(key.encode()).hexdigest()}.cover"
    try:
        return f.read_bytes()
    except OSError:
        pass
    data = produce()
    if data and len(data) <= MAX_BYTES:
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
        except OSError:
            pass
    return data
