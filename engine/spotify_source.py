"""Spotify por la Web API oficial: OAuth con PKCE (sin secreto), solo lectura.

El usuario registra su propia app en developer.spotify.com y carga el Client ID en Ajustes (se guarda cifrado, nunca en el
repo). Desde marzo de 2026 las apps nuevas en modo desarrollo exigen Premium en la cuenta dueña y admiten 5 usuarios; la
lectura de los temas de una playlist solo anda en las propias o colaborativas (`/playlists/{id}/items`).
El audio no se obtiene: Spotify solo entrega metadatos (ver docs/fuentes-spotify-youtube.md).
"""
import re

import providers
from providers import ProviderError, norm_track, newest_first

API = "https://api.spotify.com/v1"
PAGE = 50
CAPS = {"albums": 500, "tracks": 500, "playlists": 200, "playlistTracks": 500}  # tope por lista: una biblioteca enorme no cuelga el motor
ID_RE = re.compile(r"^[A-Za-z0-9]{10,40}$")


class SpotifyProvider(providers.Provider):
    id, label = "spotify", "Spotify"
    capabilities = {"audio": False, "albums": True, "playlists": True, "savedTracks": True, "write": False}
    api_host = "api.spotify.com"
    auth_url = "https://accounts.spotify.com/authorize"
    token_url = "https://accounts.spotify.com/api/token"
    scopes = ("user-library-read", "playlist-read-private", "playlist-read-collaborative")  # solo lectura
    note = "Solo metadatos: Spotify no entrega el audio. El tema se busca en tus archivos."

    def friendly(self, e):
        if e.code == "api_error" and e.status == 403:
            return ProviderError("forbidden", "Spotify rechazó el pedido. En modo desarrollo hace falta que tu usuario esté agregado en el panel de la app y que la cuenta dueña tenga Premium.", 403)
        return e

    def _pages(self, url, cap, params=None):
        """Sigue `next` solo si apunta al mismo host de la API (viene de la red: es un dato)."""
        out = []
        params = {"limit": PAGE, **(params or {})}
        while url and len(out) < cap:
            body = self.api(url, params)
            params = None  # `next` ya trae todos los parámetros
            out += body.get("items") or []
            url = body.get("next")
        return out[:cap]

    def _me(self):
        t = self.tokens_store.load() or {}
        if not t.get("user"):
            user = self.api(API + "/me").get("id", "")
            with self.lock:
                t = self.tokens_store.load() or {}  # el token pudo renovarse mientras tanto
                t["user"] = user
                self.tokens_store.save(t)
        return t["user"]

    def library(self):
        me = self._me()
        albums = [_album(i.get("album") or {}, i.get("added_at")) for i in self._pages(API + "/me/albums", CAPS["albums"])]
        tracks = [_track(i.get("track") or {}, i.get("added_at")) for i in self._pages(API + "/me/tracks", CAPS["tracks"])]
        playlists = []
        for p in self._pages(API + "/me/playlists", CAPS["playlists"]):
            if not p or not p.get("id"):
                continue
            own = (p.get("owner") or {}).get("id") == me
            readable = own or bool(p.get("collaborative"))
            count = (p.get("items") or p.get("tracks") or {}).get("total")
            playlists.append({"id": p["id"], "source": "spotify", "name": p.get("name", ""), "tracks": count, "own": own,
                              "readable": readable, "addedAt": None, "url": (p.get("external_urls") or {}).get("spotify", "")})
        return {"albums": newest_first([a for a in albums if a["id"]]), "tracks": newest_first([t for t in tracks if t["id"]]), "playlists": playlists}

    def playlist_tracks(self, playlist_id):
        if not ID_RE.match(str(playlist_id)):
            raise ProviderError("bad_id", "Playlist inválida.", 400)
        try:
            items = self._pages(f"{API}/playlists/{playlist_id}/items", CAPS["playlistTracks"])
        except ProviderError as e:
            if e.status in (403, 404):
                raise ProviderError("not_readable", "Spotify solo deja leer los temas de tus playlists o las colaborativas.", 403)
            raise
        tracks = [_track(i.get("item") or i.get("track") or {}, i.get("added_at")) for i in items]  # `item` desde 2026; `track` antes
        return {"tracks": newest_first([t for t in tracks if t["id"]])}


def _track(t, added_at):
    if t.get("type", "track") != "track" or not t.get("id"):  # episodios y temas locales no tienen id usable
        return {"id": ""}
    artists = [a.get("name", "") for a in t.get("artists") or []]
    return norm_track("spotify", t["id"], t.get("name"), artists[0] if artists else "", (t.get("album") or {}).get("name"),
                      round(t["duration_ms"] / 1000) if t.get("duration_ms") else None, (t.get("external_ids") or {}).get("isrc"),
                      added_at, (t.get("external_urls") or {}).get("spotify", ""), artists=artists)


def _album(a, added_at):
    artists = [x.get("name", "") for x in a.get("artists") or []]
    year = (a.get("release_date") or "")[:4]
    return {"id": a.get("id", ""), "source": "spotify", "title": a.get("name", ""), "artist": artists[0] if artists else "",
            "artists": artists, "year": int(year) if year.isdigit() else None, "tracks": a.get("total_tracks"),
            "upc": (a.get("external_ids") or {}).get("upc", ""), "addedAt": added_at, "url": (a.get("external_urls") or {}).get("spotify", "")}
