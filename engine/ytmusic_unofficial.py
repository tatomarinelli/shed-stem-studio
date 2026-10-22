"""Biblioteca completa de YouTube Music con `ytmusicapi` (librería NO oficial; ver docs/fuentes-spotify-youtube.md).

A diferencia de la YouTube Data API, esta lee lo que el usuario ve en music.youtube.com: álbumes guardados, temas de su
biblioteca (con álbum) y playlists. Es opcional, solo lectura y se elige desde Fuentes:
- La librería no viene incluida: se instala a pedido en una carpeta propia (`pylibs`, junto a la configuración), nunca sola.
- El login es una vez: el usuario pega los encabezados de una petición a music.youtube.com con su sesión abierta
  (el método "browser" de ytmusicapi). Se guardan cifrados (osenv.write_protected). Si Google invalida la sesión,
  la lectura falla con un mensaje claro y se pegan de nuevo.
- YouTube puede cambiar su interfaz interna y romper la librería hasta que salga una versión nueva: por eso es un complemento
  y la API oficial sigue siendo la base.
"""
import hmac
import io
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path

import jobs
import osenv
import providers
from providers import ProviderError, Store, norm_track

LIMITS = {"albums": 2000, "songs": 5000, "playlists": 200}
HEADERS_MAX = 30000
STORE = Store("ytmusic-headers.json")
_install = {}
_lock = threading.Lock()


def pylibs():
    return osenv.config_dir() / "pylibs"


def _lib():
    """El módulo ytmusicapi o None. Mira primero en la carpeta propia."""
    p = str(pylibs())
    if pylibs().is_dir() and p not in sys.path:
        sys.path.append(p)
    try:
        import ytmusicapi
        return ytmusicapi
    except ImportError:
        return None


def installed():
    return _lib() is not None


def install_state():
    return jobs.public(_install) if _install else {"state": "idle"}


def install():
    """Instala ytmusicapi con pip en `pylibs`. Solo corre porque el usuario lo pidió desde Fuentes."""
    with _lock:
        if installed() or _install.get("state") == "running":
            return
        jobs.start(_install, state="running", step="Instalando ytmusicapi")

    def work():
        try:
            pylibs().mkdir(parents=True, exist_ok=True)
            proc = subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--target", str(pylibs()), "ytmusicapi"],
                                  capture_output=True, text=True, timeout=300, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if proc.returncode or not installed():
                tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-1:] or [""]
                jobs.update(_install, state="error", error=f"No se pudo instalar ytmusicapi. {tail[0][:200]}")
            else:
                jobs.update(_install, state="done")
        except Exception as e:
            jobs.update(_install, state="error", error=f"No se pudo instalar ytmusicapi ({type(e).__name__}).")

    threading.Thread(target=work, daemon=True).start()


# ------------------------------------------------------------------ emparejar con la extensión del navegador
# La extensión (engine/ytmusic_extension) ve los encabezados de la petición a music.youtube.com y los manda al motor SOLO
# si el usuario tocó "Conectar" en Fuentes: ese botón crea un token de un solo uso (10 minutos) que viaja en la dirección que
# abre. Sin token vigente el motor ignora lo que llegue.
PAIR_TTL = 600
EXT_DIR = Path(__file__).resolve().parent / "ytmusic_extension"
_pair = {}


def pair_start(port, launch=False):
    """Crea el token. Con `launch`, abre un navegador Chromium propio de la app (perfil aparte, extensión ya cargada) en
    YouTube Music: el usuario inicia sesión ahí una vez y no instala nada. Sin navegador compatible, `launched` es False
    y la interfaz abre la dirección en el navegador de siempre (hace falta la extensión cargada a mano)."""
    with _lock:
        _pair.update(token=secrets.token_urlsafe(24), exp=time.time() + PAIR_TTL)
        url = f"https://music.youtube.com/#stemshed={_pair['token']}&port={int(port)}"
    browser = launch_browser(url) if launch else None
    return {"url": url, "expiresIn": PAIR_TTL, "launched": bool(browser), "browser": browser}


def find_browser():
    """Un navegador de la familia Chromium instalado: (nombre, ruta) o None."""
    import shutil
    if osenv.WINDOWS:
        roots = [os.environ.get(k) for k in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
        rel = {"Edge": r"Microsoft\Edge\Application\msedge.exe", "Chrome": r"Google\Chrome\Application\chrome.exe", "Brave": r"BraveSoftware\Brave-Browser\Application\brave.exe"}
        for name, r in rel.items():
            for root in filter(None, roots):
                if (Path(root) / r).is_file():
                    return name, str(Path(root) / r)
        return None
    for name, exe in (("Chromium", "chromium"), ("Chromium", "chromium-browser"), ("Chrome", "google-chrome-stable"), ("Chrome", "google-chrome"),
                      ("Brave", "brave"), ("Edge", "microsoft-edge-stable"), ("Edge", "microsoft-edge")):
        path = shutil.which(exe)
        if path:
            return name, path
    return None


def browser_command(exe, url):
    return [exe, f"--user-data-dir={osenv.config_dir() / 'browser-profile'}", f"--load-extension={EXT_DIR}",
            "--disable-features=DisableLoadExtensionCommandLineSwitch", "--no-first-run", "--no-default-browser-check", url]


def launch_browser(url):
    found = find_browser() if EXT_DIR.is_dir() else None
    if not found:
        return None
    name, exe = found
    flags = {"creationflags": getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)} if osenv.WINDOWS else {"start_new_session": True}
    try:
        subprocess.Popen(browser_command(exe, url), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)
    except OSError:
        return None
    return name


def pairing():
    return bool(_pair.get("token")) and _pair.get("exp", 0) > time.time()


def pair_cancel():
    with _lock:
        _pair.clear()


def pair_receive(token, headers):
    """La extensión entrega los encabezados (dict nombre -> valor). Un token sirve una vez; un intento fallido no lo gasta."""
    with _lock:
        ok = pairing() and isinstance(token, str) and hmac.compare_digest(token, _pair["token"])
    if not ok:
        raise ProviderError("pair_invalid", "El emparejamiento venció o no es válido. Tocá Conectar de nuevo en Fuentes.", 403)
    if not isinstance(headers, dict) or not 0 < len(headers) < 80 or not all(isinstance(k, str) and isinstance(v, str) for k, v in headers.items()):
        raise ProviderError("bad_headers", "Encabezados inválidos.", 400)
    save_headers("\n".join(f"{k}: {v}" for k, v in headers.items() if "\n" not in k + v))
    pair_cancel()


def extension_zip():
    """La extensión empaquetada, lista para cargar en el navegador; None si la carpeta no está."""
    if not EXT_DIR.is_dir():
        return None
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(EXT_DIR.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(EXT_DIR).as_posix())
    return buf.getvalue()


# ------------------------------------------------------------------ sesión
def connected():
    return bool(STORE.load())


def protection():
    return STORE.protection() if connected() else None


def clear():
    STORE.delete()


def _client(headers):
    lib = _lib()
    if not lib:
        raise ProviderError("not_installed", "Falta instalar ytmusicapi.", 409)
    try:
        return lib.YTMusic(auth=headers)
    except Exception as e:
        raise ProviderError("bad_headers", f"Los encabezados no sirven: {str(e)[:160]}", 400)


def save_headers(raw):
    """Valida los encabezados pegados (con una lectura real de 1 disco) y los guarda cifrados."""
    raw = str(raw or "").strip()
    if not raw or len(raw) > HEADERS_MAX:
        raise ProviderError("bad_headers", "Pegá los encabezados de la petición completos.", 400)
    lib = _lib()
    if not lib:
        raise ProviderError("not_installed", "Primero instalá ytmusicapi.", 409)
    try:
        from ytmusicapi.setup import setup
        headers = json.loads(setup(headers_raw=raw))
    except Exception:
        raise ProviderError("bad_headers", "No pude leer esos encabezados. Copiá la petición entera desde las herramientas del navegador.", 400)
    if "SAPISIDHASH" not in headers.get("authorization", ""):
        raise ProviderError("bad_headers", "Falta el encabezado Authorization: copiá una petición POST a /youtubei/v1/browse con tu sesión abierta.", 400)
    try:
        _client(headers).get_library_albums(limit=1)
    except ProviderError:
        raise
    except Exception as e:
        raise _friendly(e)
    STORE.save(headers)


def _friendly(e):
    text = f"{type(e).__name__} {e}".lower()
    if any(k in text for k in ("401", "403", "sign in", "authentication", "login", "cookie")):
        return ProviderError("reauth", "La sesión de YouTube Music venció. Pegá los encabezados de nuevo.", 401)
    if any(k in text for k in ("connection", "timeout", "resolve", "network")):
        return ProviderError("network", "No hay conexión con YouTube Music.", 502)
    return ProviderError("api_error", f"YouTube Music respondió algo inesperado ({type(e).__name__}). Puede que la librería necesite actualizarse.", 502)


# ------------------------------------------------------------------ lectura
def library():
    headers = STORE.load()
    if not headers:
        raise ProviderError("no_session", "Todavía no conectaste la biblioteca completa de YouTube Music.", 401)
    yt = _client(headers)
    try:
        albums = yt.get_library_albums(limit=LIMITS["albums"], order="recently_added")
        songs = yt.get_library_songs(limit=LIMITS["songs"], order="recently_added")
        lists = yt.get_library_playlists(limit=LIMITS["playlists"])
    except ProviderError:
        raise
    except Exception as e:
        raise _friendly(e)
    return {"albums": [a for a in map(_album, albums or []) if a], "tracks": [t for t in map(_track, songs or []) if t],
            "playlists": [p for p in map(_playlist, lists or []) if p]}


def _artist(item):
    names = [a.get("name", "") for a in item.get("artists") or [] if isinstance(a, dict)]
    return names[0] if names else ""


def _album(a):
    if not isinstance(a, dict) or not a.get("browseId") or not a.get("title"):
        return None
    year = str(a.get("year") or "")
    return {"id": a["browseId"], "source": "ytmusic", "title": a["title"], "artist": _artist(a), "year": int(year) if year.isdigit() else None,
            "thumb": _thumb(a.get("thumbnails")), "addedAt": None, "url": f"https://music.youtube.com/browse/{a['browseId']}"}  # la lista viene de lo último guardado a lo más viejo


def _track(t):
    if not isinstance(t, dict) or not t.get("videoId") or not t.get("title"):
        return None
    album = t.get("album") if isinstance(t.get("album"), dict) else {}
    return norm_track("ytmusic", t["videoId"], t["title"], _artist(t), album.get("name", ""), t.get("duration_seconds"), "", None,
                      f"https://music.youtube.com/watch?v={t['videoId']}")


def _thumb(thumbs):
    ts = [t for t in thumbs or [] if isinstance(t, dict) and t.get("url")]
    return min(ts, key=lambda t: abs((t.get("width") or 300) - 300))["url"] if ts else ""


def album_tracks(browse_id):
    """Temas de un disco de YouTube Music (para abrirlo en Música aunque no esté en TIDAL ni en tus archivos)."""
    headers = STORE.load()
    if not headers:
        raise ProviderError("no_session", "Todavía no conectaste la biblioteca completa de YouTube Music.", 401)
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,64}", str(browse_id)):
        raise ProviderError("bad_id", "Disco inválido.", 400)
    try:
        alb = _client(headers).get_album(browse_id)
    except ProviderError:
        raise
    except Exception as e:
        raise _friendly(e)
    name = alb.get("title", "") if isinstance(alb, dict) else ""
    out = []
    for t in (alb.get("tracks") or []) if isinstance(alb, dict) else []:
        if isinstance(t, dict) and t.get("videoId") and t.get("title"):
            out.append(norm_track("ytmusic", t["videoId"], t["title"], _artist(t) or _artist(alb), name, t.get("duration_seconds"), "", None,
                                  f"https://music.youtube.com/watch?v={t['videoId']}"))
    return {"tracks": out}


def _playlist(p):
    if not isinstance(p, dict) or not p.get("playlistId"):
        return None
    return {"id": p["playlistId"], "source": "ytmusic", "name": p.get("title", ""), "tracks": p.get("count"), "own": True, "readable": True,
            "addedAt": None, "url": f"https://music.youtube.com/playlist?list={p['playlistId']}"}
