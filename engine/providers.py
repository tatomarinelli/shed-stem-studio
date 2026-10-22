"""Proveedores de música (Spotify, YouTube Music, TIDAL) detrás de una interfaz común.

Cada proveedor responde lo mismo: `status()`, `library()` (álbumes, temas guardados y playlists, los más nuevos
primero según la fecha en que el usuario los guardó), `playlist_tracks(id)` y, para los que usan OAuth, el alta y la baja de
la cuenta. Un tema es siempre una REFERENCIA (artista, título, disco, ISRC): el audio de Spotify y YouTube Music NO se
obtiene (DRM y términos), así que `capabilities.audio` es False y ninguno entra en `audioSources`; "Enviar al estudio"
busca el tema en los archivos locales (`sources.resolve_track`).

Reglas (CLAUDE.md): solo lectura (los permisos que se piden son de lectura, así que ni siquiera hay forma de escribir),
sin secretos en el repo, tokens guardados con `osenv.write_protected` (DPAPI en Windows, llavero en Linux, o archivo
600 si no hay llavero), y todo lo que viene de la red se trata como dato.
"""
import base64
import hashlib
import json
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import osenv

TIMEOUT = 20
OAUTH_TTL = 600  # segundos que vale un intento de autorización
_urlopen = urllib.request.urlopen  # las pruebas lo reemplazan: ninguna prueba toca la red


class ProviderError(Exception):
    def __init__(self, code, message, status=409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


# ------------------------------------------------------------------ HTTP
def http_json(method, url, headers=None, form=None, params=None):
    """Pide JSON y mapea los errores comunes a ProviderError con mensajes para el usuario."""
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Accept": "application/json", "User-Agent": "ShedStemStudio/0.0.4", **(headers or {})})
    try:
        with _urlopen(req, timeout=TIMEOUT) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        detail = _error_body(e)
        if e.code == 401:
            raise ProviderError("unauthorized", "La cuenta rechazó el acceso.", 401)
        if e.code == 429:
            wait = (e.headers.get("Retry-After") if e.headers else None) or "unos"
            raise ProviderError("rate_limited", f"Demasiados pedidos. Esperá {wait} segundos y probá de nuevo.", 429)
        raise ProviderError("api_error", detail or f"El servicio respondió {e.code}.", e.code)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ProviderError("network", f"No hay conexión con el servicio ({type(e).__name__}).", 502)
    try:
        return json.loads(body or b"{}")
    except ValueError:
        raise ProviderError("bad_response", "El servicio devolvió algo que no se entiende.", 502)


def _error_body(e):
    try:
        b = json.loads(e.read() or b"{}")
    except Exception:
        return ""
    err = b.get("error")
    if isinstance(err, dict):  # Google: {"error": {"message", "errors": [{"reason"}]}}
        reason = (err.get("errors") or [{}])[0].get("reason", "")
        return f"{reason}: {err.get('message', '')}"[:200]
    return f"{err or ''} {b.get('error_description') or ''}".strip()[:200]


# ------------------------------------------------------------------ PKCE y estado de OAuth
def pkce_pair():
    verifier = secrets.token_urlsafe(64)  # 86 caracteres, dentro de los 43-128 del RFC 7636
    return verifier, pkce_challenge(verifier)


def pkce_challenge(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode()


_pending = {}  # state -> {provider, verifier, redirect, exp}
_pending_lock = threading.Lock()


def redirect_uri(port):
    """Siempre con la IP literal (Spotify no acepta `localhost`) y el puerto en que escucha el motor."""
    return f"http://127.0.0.1:{int(port)}/engine/oauth/callback"


def take_pending(state):
    """Un `state` sirve una sola vez y vence: devuelve el intento o None."""
    with _pending_lock:
        now = time.time()
        for k in [k for k, v in _pending.items() if v["exp"] < now]:
            del _pending[k]
        return _pending.pop(state, None) if isinstance(state, str) else None


# ------------------------------------------------------------------ almacenes cifrados
class Store:
    """Un JSON guardado con el almacén de la plataforma (osenv.write_protected)."""

    def __init__(self, filename):
        self.filename = filename

    @property
    def path(self):
        return osenv.config_dir() / self.filename

    def load(self):
        try:
            return json.loads(osenv.read_protected(self.path))
        except (OSError, ValueError):
            return None

    def save(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        osenv.secure(self.path.parent, 0o700)
        return osenv.write_protected(self.path, json.dumps(data).encode())

    def delete(self):
        osenv.delete_protected(self.path)

    def protection(self):
        return osenv.protection_of(self.path)


# ------------------------------------------------------------------ interfaz común
def norm_track(source, tid, title, artist, album="", duration=None, isrc="", added_at=None, url="", **extra):
    return {"id": str(tid), "source": source, "title": title or "", "artist": artist or "", "album": album or "",
            "duration": duration, "isrc": isrc or "", "addedAt": added_at, "url": url, **extra}


def newest_first(items):
    """Orden por fecha de guardado (ISO 8601, ordena como texto); lo que no tiene fecha queda al final en su orden."""
    return sorted(items, key=lambda x: x.get("addedAt") or "", reverse=True)


class Provider:
    id = ""
    label = ""
    capabilities = {"audio": False, "albums": True, "playlists": True, "savedTracks": True, "write": False}
    api_host = ""
    auth_url = token_url = ""
    scopes = ()
    needs_secret = False  # Google pide client_secret aunque el cliente de escritorio no lo pueda guardar en secreto

    def __init__(self):
        self.tokens_store = Store(f"{self.id}-session.json")
        self.lock = threading.RLock()

    # -- app del usuario (Client ID propio; nunca va en el repo)
    def app(self):
        return (Store("providers-apps.json").load() or {}).get(self.id) or {}

    def set_app(self, client_id, client_secret=""):
        client_id, client_secret = str(client_id).strip(), str(client_secret or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9._~-]{10,200}", client_id):
            raise ProviderError("bad_client_id", "El Client ID no parece válido.", 400)
        if client_secret and not re.fullmatch(r"[\x21-\x7e]{6,200}", client_secret):
            raise ProviderError("bad_client_secret", "El Client Secret no parece válido.", 400)
        store = Store("providers-apps.json")
        apps = store.load() or {}
        apps[self.id] = {"clientId": client_id, **({"clientSecret": client_secret} if client_secret else {})}
        store.save(apps)

    def configured(self):
        a = self.app()
        return bool(a.get("clientId")) and (not self.needs_secret or bool(a.get("clientSecret")))

    # -- autorización
    def auth_start(self, port):
        if not self.configured():
            raise ProviderError("no_app", f"Primero cargá el Client ID de tu app de {self.label}.")
        verifier, challenge = pkce_pair()
        state = secrets.token_urlsafe(24)
        redirect = redirect_uri(port)
        with _pending_lock:
            _pending[state] = {"provider": self.id, "verifier": verifier, "redirect": redirect, "exp": time.time() + OAUTH_TTL}
        q = {"client_id": self.app()["clientId"], "response_type": "code", "redirect_uri": redirect, "scope": " ".join(self.scopes),
             "state": state, "code_challenge_method": "S256", "code_challenge": challenge, **self.extra_auth_params()}
        return {"url": self.auth_url + "?" + urllib.parse.urlencode(q), "redirectUri": redirect}

    def extra_auth_params(self):
        return {}

    def auth_callback(self, pending, code):
        a = self.app()
        form = {"grant_type": "authorization_code", "code": code, "redirect_uri": pending["redirect"],
                "client_id": a["clientId"], "code_verifier": pending["verifier"]}
        if a.get("clientSecret"):
            form["client_secret"] = a["clientSecret"]
        with self.lock:
            tok = self._token_request(form)
            if not tok.get("refresh_token"):
                raise ProviderError("no_refresh", "La cuenta no entregó permiso para renovar la sesión. Probá conectar de nuevo.")
            self._save_tokens(tok, {})

    def _token_request(self, form):
        try:
            tok = http_json("POST", self.token_url, form=form)
        except ProviderError as e:
            if e.status in (400, 401) and e.code != "network":
                raise ProviderError("reauth", f"La sesión de {self.label} venció o se revocó. Conectala de nuevo.", 401)
            raise
        if not tok.get("access_token"):
            raise ProviderError("bad_response", "El servicio no entregó un token.", 502)
        return tok

    def _save_tokens(self, tok, old):
        self.tokens_store.save({**old, "access_token": tok["access_token"], "refresh_token": tok.get("refresh_token") or old.get("refresh_token", ""),
                                "expires_at": time.time() + float(tok.get("expires_in", 3600)), "scope": tok.get("scope", old.get("scope", ""))})

    def access_token(self, force_from=None):
        """Token vigente. La renovación va con candado: dos pedidos a la vez no renuevan dos veces (los refresh tokens pueden rotar)."""
        with self.lock:
            t = self.tokens_store.load()
            if not t or not t.get("refresh_token"):
                raise ProviderError("no_session", f"Todavía no conectaste {self.label}.", 401)
            fresh = t["expires_at"] - 60 > time.time() and t["access_token"] != force_from
            if fresh:
                return t["access_token"]
            a = self.app()
            form = {"grant_type": "refresh_token", "refresh_token": t["refresh_token"], "client_id": a.get("clientId", "")}
            if a.get("clientSecret"):
                form["client_secret"] = a["clientSecret"]
            tok = self._token_request(form)
            self._save_tokens(tok, t)
            return tok["access_token"]

    def connected(self):
        t = self.tokens_store.load()
        return bool(t and t.get("refresh_token"))

    def logout(self):
        """Borra la sesión local. No llama a la red ni toca nada de la cuenta externa (se revoca desde la web del servicio)."""
        self.tokens_store.delete()

    # -- pedidos a la API
    def api(self, url, params=None):
        host = urllib.parse.urlparse(url)
        if host.scheme != "https" or host.hostname != self.api_host:
            raise ProviderError("bad_url", "Dirección fuera del servicio.", 502)
        token = self.access_token()
        try:
            return http_json("GET", url, {"Authorization": f"Bearer {token}"}, params=params)
        except ProviderError as e:
            if e.code != "unauthorized":
                raise self.friendly(e)
        token = self.access_token(force_from=token)  # un 401: se renueva una vez y se reintenta
        try:
            return http_json("GET", url, {"Authorization": f"Bearer {token}"}, params=params)
        except ProviderError as e:
            raise self.friendly(e)

    def friendly(self, e):
        return e

    def status(self, port=8770):
        connected = self.connected() if self.configured() else False
        return {"id": self.id, "label": self.label, "configured": self.configured(), "connected": connected,
                "needsSecret": self.needs_secret, "capabilities": self.capabilities,
                "protection": self.tokens_store.protection() if connected else None, "redirectUri": redirect_uri(port),
                "note": self.note}

    note = ""

    def library(self):
        raise NotImplementedError

    def playlist_tracks(self, playlist_id):
        raise NotImplementedError


# ------------------------------------------------------------------ TIDAL (adaptador; su login sigue en tidal_source)
class TidalProvider(Provider):
    id, label = "tidal", "TIDAL"
    capabilities = {"audio": True, "albums": True, "playlists": True, "savedTracks": True, "write": False}
    note = "Vía no oficial (tidalapi). Su inicio de sesión es el de siempre."

    def configured(self):
        return True

    def connected(self):
        import tidal_source
        return tidal_source.status().get("connected", False)

    def logout(self):
        import tidal_source
        tidal_source.logout()

    def status(self, port=8770):
        out = super().status(port)
        out["managedBy"] = "tidal"
        return out

    def library(self):
        import tidal_source
        lib = tidal_source.library()
        return {"albums": [{**a, "source": "tidal", "addedAt": None} for a in lib["albums"]],  # fecha de guardado: pendiente (tidalapi admite order=DATE)
                "tracks": [{**t, "source": "tidal", "isrc": "", "addedAt": None, "url": ""} for t in lib["tracks"]],
                "playlists": [{**p, "source": "tidal", "readable": True, "addedAt": None} for p in lib["playlists"]]}

    def playlist_tracks(self, playlist_id):
        import tidal_source
        return {"tracks": [{**t, "source": "tidal", "isrc": "", "addedAt": None, "url": ""} for t in tidal_source.playlist_tracks(playlist_id)["tracks"]]}


def handle_callback(query):
    """Vuelta del navegador desde el servicio. `query` es el dict de parse_qs (datos no confiables). Devuelve (ok, mensaje)."""
    first = lambda k: (query.get(k) or [""])[0]
    pending = take_pending(first("state"))
    if not pending:
        return False, "Este enlace ya se usó o venció. Volvé a Ajustes y tocá Conectar de nuevo."
    if first("error"):
        return False, "No diste permiso o la cuenta lo rechazó."
    code = first("code")
    if not code or len(code) > 2048:
        return False, "La respuesta del servicio no trae código."
    try:
        get(pending["provider"]).auth_callback(pending, code)
    except ProviderError as e:
        return False, e.message
    return True, "Listo, cuenta conectada."


def callback_page(ok, message):
    """HTML mínimo para la pestaña que abrió el servicio. Todo lo que se muestra se escapa."""
    import html
    title = "Conectado" if ok else "No se pudo conectar"
    return ("<!doctype html><meta charset=utf-8><meta name=referrer content=no-referrer><title>Shed Stem Studio</title>"
            "<body style='font-family:system-ui;background:#16130f;color:#eee;display:grid;place-items:center;height:100vh;margin:0'>"
            f"<main style='text-align:center'><h1>{html.escape(title)}</h1><p>{html.escape(message)}</p>"
            "<p style='color:#999'>Podés cerrar esta pestaña y volver a Shed Stem Studio.</p></main>").encode()


# ------------------------------------------------------------------ registro
_registry = {}


def register(provider):
    _registry[provider.id] = provider
    return provider


def get(provider_id):
    load_all()
    if provider_id not in _registry:
        raise ProviderError("unknown_provider", "Proveedor desconocido.", 404)
    return _registry[provider_id]


def all_providers():
    load_all()
    return list(_registry.values())


def load_all():
    if _registry:
        return
    import spotify_source
    import ytmusic_source
    register(spotify_source.SpotifyProvider())
    register(ytmusic_source.YouTubeMusicProvider())
    register(TidalProvider())

