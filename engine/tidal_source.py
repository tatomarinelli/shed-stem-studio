"""Fuente TIDAL (vía tidalapi, no oficial): login propio y lectura de favoritos y playlists.

Adaptado de tidalrecs/sources.py (código propio del cliente de TIDAL para Linux). El motor hace su propio
login por código de dispositivo y guarda la sesión en la carpeta de Shed Stem Studio del usuario; no depende del
cliente de TIDAL ni lee su sesión. Solo lectura sobre TIDAL: nunca escribe en la cuenta.
"""
import os
import osenv
import threading
import time
from pathlib import Path

CONFIG_DIR = osenv.config_dir()
TIDAL_SESSION = CONFIG_DIR / "tidal-session.json"
CACHE_SECONDS = 3600  # búsquedas por artista/título
LONG_SECONDS = 24 * 3600  # biblioteca, playlists y discos: solo cambian cuando el usuario toca Actualizar (clear_cache)
EXPIRED_RETRY = 60  # con la sesión vencida no se vuelve a consultar a TIDAL en cada sondeo
PAGE = 50          # tamaño de página que TIDAL acepta en todos los listados
MAX_ITEMS = 20000  # tope de seguridad contra un servidor que repita páginas para siempre


class SourceError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


_lock = threading.Lock()
_start_lock = threading.Lock()
_session = None
_expired = {"at": 0.0, "error": None}
_cache = {}
_login = {"state": "idle", "message": ""}  # idle | pending | done | expired | error
_attempt = None  # el único intento de login vigente (o None)


def _get_session():
    global _session
    if _session is not None:
        return _session
    if _expired["error"] and time.time() - _expired["at"] < EXPIRED_RETRY:
        raise _expired["error"]
    try:
        import tidalapi
    except ImportError:
        raise SourceError("no_tidalapi", "Falta la librería tidalapi en el Python del motor (pip install tidalapi).")
    if not TIDAL_SESSION.exists():
        raise SourceError("no_session", "Todavía no conectaste TIDAL. Tocá Conectar TIDAL para iniciar sesión.")
    session = tidalapi.Session()
    if not _load_session(session) or not session.check_login():
        _expired.update(at=time.time(), error=SourceError("session_expired", "La sesión de TIDAL venció. Tocá Conectar TIDAL para iniciar sesión de nuevo."))
        raise _expired["error"]
    _expired["error"] = None
    _session = session
    return session


def _load_session(session):
    """tidalapi lee de un archivo: si el nuestro está cifrado (Windows, DPAPI) se descifra a un temporal que se borra enseguida."""
    try:
        raw = osenv.read_protected(TIDAL_SESSION)
    except OSError:
        return False
    if not TIDAL_SESSION.read_bytes().startswith(osenv._DPAPI_MAGIC):
        return session.load_session_from_file(TIDAL_SESSION)
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
        return session.load_session_from_file(Path(tmp))
    finally:
        Path(tmp).unlink(missing_ok=True)


def _cached(key, fn, ttl=CACHE_SECONDS):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    value = fn()
    _cache[key] = (time.time(), value)
    return value


def paged(fetch, key=lambda x: x.id, page=PAGE, limit=MAX_ITEMS):
    """Trae un listado completo de a páginas: fetch(limit, offset) -> lista. Corta con una página vacía, o sin
    ítems nuevos (si el servidor ignora el offset no se repite para siempre). No confía en que la página venga llena:
    TIDAL puede devolver menos que lo pedido y todavía quedar más."""
    out, seen, offset = [], set(), 0
    while len(out) < limit:
        batch = fetch(page, offset)
        new = [x for x in batch if key(x) not in seen]
        if not new:
            break
        seen.update(key(x) for x in new)
        out.extend(new)
        offset += len(batch)
    return out


def _saved(x):
    d = getattr(x, "user_date_added", None)
    return d.isoformat() if d else None


def clear_cache():
    _cache.clear()


def album_by_id(album_id):
    """Los temas de un disco de TIDAL por su id (sin búsqueda)."""
    def build():
        album = _get_session().album(int(album_id))
        return {"id": str(album.id), "title": album.name, "artist": album.artist.name if album.artist else "",
                "tracks": [_track(t) for t in album.tracks()]}
    with _lock:
        return _cached(f"albumid:{album_id}", build, LONG_SECONDS)


_covers_filled = {"done": False}
_fill_lock = threading.Lock()
_covers = {}  # id de disco -> código de portada que trae el listado de favoritos


def remember_covers(albums):
    """Guarda los códigos de portada del listado (también desde el snapshot en disco). Sirven aunque el disco ya no se pueda pedir por id."""
    _covers.update({str(a["id"]): a["cover"] for a in albums if a.get("cover")})


def cover_url(cover, size=320):
    return f"https://resources.tidal.com/images/{str(cover).replace('-', '/')}/{size}x{size}.jpg"


def album_art(album_id):
    import urllib.request

    cover = _covers.get(str(album_id))
    if not cover:
        with _fill_lock:  # los pedidos en paralelo esperan a que termine la carga en vez de fallar
            if not _covers_filled["done"]:
                # Snapshot viejo (sin códigos de portada): una sola vez se completa desde el listado de favoritos, que además queda en caché.
                try:
                    library()
                except Exception:
                    pass
                _covers_filled["done"] = True
        cover = _covers.get(str(album_id))
    # Con el código del listado no hace falta pedir el disco: hay discos que TIDAL ya no entrega por id pero siguen en favoritos.
    url = cover_url(cover) if cover else _get_session().album(int(album_id)).image(320)
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "ShedStemStudio/0.0.1"}), timeout=20) as r:
        return r.read()


def _track(t):
    artist = getattr(t, "artist", None)
    album = getattr(t, "album", None)
    return {"id": str(t.id), "title": t.name, "artist": artist.name if artist else "",
            "album": album.name if album else "", "duration": getattr(t, "duration", None)}


def status():
    with _lock:
        try:
            _get_session()
            return {"connected": True}
        except SourceError as e:
            out = {"connected": False, "code": e.code, "message": e.message}
            if _login["state"] == "pending":
                out["login"] = _login_view()  # la interfaz retoma el código vigente si se recarga o se vuelve a montar
            return out


def _own_playlists(session):
    """Las playlists propias, todas (el endpoint tiene tope por página)."""
    uid = session.user.id

    def fetch(limit, offset):
        return session.request.map_request(f"users/{uid}/playlists", params={"limit": limit, "offset": offset},
                                           parse=session.user.playlist.parse_factory)
    return paged(fetch)


def library():
    """Favoritos completos, del más reciente al más viejo (orden de guardado): se pagina hasta el final, sin tope fijo."""
    def build():
        from tidalapi.types import AlbumOrder, ArtistOrder, ItemOrder, OrderDirection
        session = _get_session()
        fav = session.user.favorites
        desc = OrderDirection.Descending
        playlists = []
        for p in _own_playlists(session):
            creator = getattr(p, "creator", None)
            playlists.append({"id": str(p.id), "name": p.name, "tracks": getattr(p, "num_tracks", None),
                              "own": bool(creator and getattr(creator, "id", None) == session.user.id)})
        albums = paged(lambda n, o: fav.albums(limit=n, offset=o, order=AlbumOrder.DateAdded, order_direction=desc))
        tracks = paged(lambda n, o: fav.tracks(limit=n, offset=o, order=ItemOrder.Date, order_direction=desc))
        artists = paged(lambda n, o: fav.artists(limit=n, offset=o, order=ArtistOrder.DateAdded, order_direction=desc))
        return {
            "tracks": [{**_track(t), "savedAt": _saved(t)} for t in tracks],
            "albums": [{"id": str(a.id), "title": a.name, "artist": a.artist.name if a.artist else "",
                        "year": getattr(a, "year", None), "tracks": getattr(a, "num_tracks", None), "savedAt": _saved(a),
                        "cover": getattr(a, "cover", None)}
                       for a in albums],
            "artists": [a.name for a in artists],
            "playlists": playlists,
        }
    with _lock:
        lib = _cached("library", build, LONG_SECONDS)
    remember_covers(lib["albums"])
    return lib


def playlist_tracks(playlist_id):
    def build():
        pl = _get_session().playlist(playlist_id)
        return {"tracks": [_track(t) for t in paged(lambda n, o: pl.tracks(limit=n, offset=o))]}
    with _lock:
        return _cached("pl:" + playlist_id, build, LONG_SECONDS)


MIN_REUSE_SECONDS = 20  # si al código vigente le quedan menos, mejor pedir otro


def _login_view():
    """Estado público del intento en curso (siempre con el código vigente y cuándo vence)."""
    view = {"state": _login["state"], "message": _login["message"]}
    if _attempt and _login["state"] == "pending":
        view.update(code=_attempt["code"], url=_attempt["url"], expiresAt=_attempt["expiresAt"],
                    expiresIn=max(0, round(_attempt["expiresAt"] - time.time())), attempt=_attempt["id"])
    return view


def _finish(attempt, **state):
    """Cierra un intento; un intento viejo (reemplazado o cancelado) no toca el estado."""
    with _lock:
        if _attempt is not attempt:
            return
        _login.update(**state)


def _wait_login(attempt, session):
    """Un solo hilo por intento: sondea cada `interval` hasta autorizar, vencer o que lo reemplacen."""
    global _session
    cancel = attempt["cancel"]
    try:
        while not cancel.is_set():
            if time.time() >= attempt["expiresAt"]:
                return _finish(attempt, state="expired", message="El código venció. Pedí uno nuevo.")
            try:
                result = session._check_link_login(attempt["link"], False)  # una sola consulta; TimeoutError = todavía no
            except TimeoutError:
                cancel.wait(0.5)  # tidalapi ya espera `interval` dentro de la consulta
                continue
            if cancel.is_set():
                return
            session.process_auth_token(result, is_pkce_token=False)
            if not session.check_login():
                raise RuntimeError("login incompleto")
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            osenv.secure(CONFIG_DIR, 0o700)
            session.save_session_to_file(TIDAL_SESSION)
            osenv.secure(TIDAL_SESSION, 0o600)
            osenv.protect_file(TIDAL_SESSION)
            with _lock:
                if _attempt is not attempt:
                    return
                _session = None
                _expired["error"] = None
                _cache.clear()
                _login.update(state="done", message="")
            return
    except Exception as e:
        _finish(attempt, state="error", message=f"No se pudo iniciar sesión: {type(e).__name__}")


def login_start(renew=False):
    """Inicia (o retoma) el login por código de dispositivo. Hay un solo intento a la vez.

    Si ya hay uno vigente y no se pide `renew`, devuelve ese mismo código; con `renew` (o si está por vencer)
    cancela el anterior y pide uno nuevo."""
    import tidalapi

    global _attempt
    with _start_lock:  # los pedidos de código se serializan; la red no se hace con _lock tomado
        with _lock:
            cur = _attempt
            if cur and _login["state"] == "pending" and not renew and cur["expiresAt"] - time.time() > MIN_REUSE_SECONDS:
                return _login_view()
        session = tidalapi.Session()
        link = session.get_link_login()
        with _lock:
            cur = _attempt
            if cur:
                cur["cancel"].set()
            attempt = _new_attempt(cur, link)
            _attempt = attempt
            _login.update(state="pending", message="")
            view = _login_view()
    threading.Thread(target=_wait_login, args=(attempt, session), daemon=True).start()
    return view


def _new_attempt(cur, link):
    url = link.verification_uri_complete
    return {"id": (cur["id"] + 1) if cur else 1, "link": link, "cancel": threading.Event(), "code": link.user_code,
            "url": url if url.startswith("http") else "https://" + url,
            "expiresAt": time.time() + float(link.expires_in), "interval": float(link.interval)}


def login_status():
    with _lock:
        return _login_view()


def login_cancel():
    global _attempt
    with _lock:
        if _attempt:
            _attempt["cancel"].set()
        _attempt = None
        _login.update(state="idle", message="")
        return _login_view()


def logout():
    global _session, _attempt
    with _lock:
        if _attempt:
            _attempt["cancel"].set()
        _attempt = None
        _session = None
        _expired["error"] = None
        _cache.clear()
        _login.update(state="idle", message="")
        TIDAL_SESSION.unlink(missing_ok=True)


def session():
    """Sesión cargada para otros módulos del motor (la separación la usa para bajar el audio)."""
    with _lock:
        return _get_session()


def _norm(text):
    import re
    import unicodedata

    t = unicodedata.normalize("NFD", str(text).lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in t if not unicodedata.combining(c))).strip()


def album_tracks(artist, album):
    """Busca un disco en TIDAL por artista y título (coincidencia normalizada) y devuelve sus temas. None si no lo encuentra."""
    def build():
        import tidalapi

        session = _get_session()
        found = session.search(f"{artist} {album}", models=[tidalapi.album.Album], limit=10).get("albums", [])
        want_t, want_a = _norm(album), _norm(artist)
        for a in found:
            a_artist = a.artist.name if getattr(a, "artist", None) else ""
            if _norm(a.name) == want_t and want_a in _norm(a_artist):
                return {"album": {"id": str(a.id), "title": a.name, "artist": a_artist, "year": getattr(a, "year", None)},
                        "tracks": [_track(t) for t in a.tracks()]}
        return {"album": None, "tracks": []}
    with _lock:
        return _cached(f"album:{_norm(artist)}:{_norm(album)}", build)


_stream_cache = {}


def stream_source(track_id):
    """URL directa y tipo de contenido para escuchar un tema sin guardarlo. Prefiere lossless; si el stream no es
    simple (DASH o cifrado) cae a 320 kbps. La URL es de TIDAL (nunca viene del cliente) y vence: se cachea poco."""
    track_id = str(int(track_id))
    hit = _stream_cache.get(track_id)
    if hit and time.time() - hit[0] < 240:
        return hit[1]
    import tidalapi

    with _lock:
        session = _get_session()
        for quality in (tidalapi.Quality.high_lossless, tidalapi.Quality.low_320k):
            session.config.quality = quality
            manifest = session.track(int(track_id)).get_stream().get_stream_manifest()
            if manifest.is_bts and manifest.encryption_type in (None, "", "NONE"):
                value = {"url": manifest.get_urls()[0], "mime": manifest.mime_type or "audio/flac"}
                _stream_cache[track_id] = (time.time(), value)
                return value
    raise SourceError("stream", "TIDAL no entregó un stream que se pueda escuchar directamente. Probá separar el tema.")


def find_track(artist, title, album=""):
    """Un tema de TIDAL que coincida con la referencia. None si no hay."""
    def build():
        import tidalapi

        session = _get_session()
        wt, wa, wb = _norm(title), _norm(artist), _norm(album)
        best = None
        for t in session.search(f"{artist} {title}", models=[tidalapi.media.Track], limit=10).get("tracks", []):
            ta = t.artist.name if getattr(t, "artist", None) else ""
            if _norm(t.name) == wt and wa in _norm(ta):
                if wb and getattr(t, "album", None) and _norm(t.album.name) == wb:
                    return _track(t)
                best = best or _track(t)
        return best
    with _lock:
        return _cached(f"track:{_norm(artist)}:{_norm(title)}:{_norm(album)}", build)
