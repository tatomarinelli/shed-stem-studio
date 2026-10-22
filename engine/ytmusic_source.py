"""YouTube Music por la YouTube Data API v3 oficial (OAuth de Google con PKCE, solo lectura).

Límites reales de la API oficial (ver docs/fuentes-spotify-youtube.md): no expone los álbumes guardados ni la biblioteca de
YouTube Music como tal. Sí da tus playlists y la lista de "Me gusta" (videos); se filtran los de categoría Música.
El usuario crea su proyecto en Google Cloud, activa la YouTube Data API y carga Client ID y Client Secret (cliente de
escritorio) en Ajustes; se guardan cifrados. El audio no se obtiene.
"""
import re

import providers
import ytmusic_unofficial as unofficial
from providers import ProviderError, norm_track

API = "https://www.googleapis.com/youtube/v3"
CAPS = {"likes": 500, "playlists": 200, "playlistTracks": 500}
MUSIC_CATEGORY = "10"
ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,64}$")
DURATION = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")


class YouTubeMusicProvider(providers.Provider):
    id, label = "ytmusic", "YouTube Music"
    capabilities = {"audio": False, "albums": False, "playlists": True, "savedTracks": True, "write": False}
    api_host = "www.googleapis.com"
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url = "https://oauth2.googleapis.com/token"
    scopes = ("https://www.googleapis.com/auth/youtube.readonly",)
    needs_secret = True
    note = "La API oficial no da los álbumes guardados: solo playlists y Me gusta (música). No entrega audio."

    # La cuenta cuenta como conectada si tiene la API oficial o la biblioteca completa (no oficial), o las dos.
    def _official(self):
        return super().configured() and super().connected()

    def configured(self):
        return super().configured() or unofficial.connected()

    def connected(self):
        return self._official() or unofficial.connected()

    def logout(self):
        super().logout()
        unofficial.clear()

    def status(self, port=8770):
        out = super().status(port)
        out["connected"] = out["configured"] and self.connected()
        out["capabilities"] = {**self.capabilities, "albums": unofficial.connected()}
        out["unofficial"] = {"installed": unofficial.installed(), "connected": unofficial.connected(), "install": unofficial.install_state(),
                             "protection": unofficial.protection(), "pairing": unofficial.pairing(),
                             "extension": unofficial.EXT_DIR.is_dir(), "browser": (unofficial.find_browser() or [None])[0]}
        out["official"] = {"configured": super().configured(), "connected": self._official()}
        return out

    def extra_auth_params(self):
        return {"access_type": "offline", "prompt": "consent"}  # sin esto Google no entrega refresh token

    def friendly(self, e):
        if e.code == "api_error" and e.status == 403:
            if "quota" in e.message.lower():
                return ProviderError("quota", "Se agotó la cuota diaria de la API de YouTube. Probá mañana.", 403)
            return ProviderError("forbidden", "Google rechazó el pedido. Revisá que la YouTube Data API esté activada en tu proyecto y que tu cuenta figure como usuario de prueba.", 403)
        return e

    def _pages(self, path, cap, params):
        out, token = [], None
        while len(out) < cap:
            body = self.api(f"{API}/{path}", {"maxResults": 50, **params, **({"pageToken": token} if token else {})})
            out += body.get("items") or []
            token = body.get("nextPageToken")
            if not token:
                break
        return out[:cap]

    def _music_items(self, playlist_id, cap):
        """Temas de una playlist: se dejan solo los videos de categoría Música (1 unidad de cuota cada 50). Conserva el orden de la lista."""
        items = self._pages("playlistItems", cap, {"part": "snippet,contentDetails", "playlistId": playlist_id})
        ids = [i["contentDetails"]["videoId"] for i in items if (i.get("contentDetails") or {}).get("videoId")]
        info = {}
        for k in range(0, len(ids), 50):
            for v in self.api(f"{API}/videos", {"part": "snippet,contentDetails", "id": ",".join(ids[k:k + 50])}).get("items") or []:
                info[v["id"]] = v
        out, skipped = [], 0
        for i in items:
            vid = (i.get("contentDetails") or {}).get("videoId")
            v = info.get(vid)
            if not v or (v.get("snippet") or {}).get("categoryId") != MUSIC_CATEGORY:
                skipped += 1
                continue
            sn = v["snippet"]
            out.append(norm_track("ytmusic", vid, sn.get("title"), _artist(sn.get("channelTitle", "")), "", _seconds(v.get("contentDetails", {}).get("duration")),
                                  "", (i.get("snippet") or {}).get("publishedAt"), f"https://music.youtube.com/watch?v={vid}"))
        return out, skipped

    def library(self):
        """Biblioteca completa (no oficial) si está conectada; la API oficial aporta lo que la otra no trae (Me gusta) y es el respaldo."""
        full, official, note = None, None, ""
        if unofficial.connected():
            try:
                full = unofficial.library()
            except ProviderError as e:
                if not self._official():
                    raise
                note = e.message  # se sigue con la API oficial y se avisa
        if self._official():
            official = self._official_library()
        if not full:
            return {**official, "note": note} if official else {"albums": [], "tracks": [], "playlists": []}
        if not official:
            return full
        seen = {t["id"] for t in full["tracks"]}
        pl = {p["id"] for p in full["playlists"]}
        return {"albums": full["albums"], "tracks": full["tracks"] + [t for t in official["tracks"] if t["id"] not in seen],
                "playlists": full["playlists"] + [p for p in official["playlists"] if p["id"] not in pl]}

    def _official_library(self):
        ch = self.api(f"{API}/channels", {"part": "contentDetails", "mine": "true"}).get("items") or []
        likes = ((ch[0].get("contentDetails") or {}).get("relatedPlaylists") or {}).get("likes") if ch else None
        tracks, skipped = self._music_items(likes, CAPS["likes"]) if likes else ([], 0)
        playlists = [{"id": p["id"], "source": "ytmusic", "name": (p.get("snippet") or {}).get("title", ""), "tracks": (p.get("contentDetails") or {}).get("itemCount"),
                      "own": True, "readable": True, "addedAt": (p.get("snippet") or {}).get("publishedAt"), "url": f"https://music.youtube.com/playlist?list={p['id']}"}
                     for p in self._pages("playlists", CAPS["playlists"], {"part": "snippet,contentDetails", "mine": "true"})]
        return {"albums": [], "tracks": tracks, "skipped": skipped, "playlists": providers.newest_first(playlists)}

    def album_tracks(self, album_id):
        return unofficial.album_tracks(album_id)

    def playlist_tracks(self, playlist_id):
        if not ID_RE.match(str(playlist_id)):
            raise ProviderError("bad_id", "Playlist inválida.", 400)
        tracks, skipped = self._music_items(playlist_id, CAPS["playlistTracks"])
        return {"tracks": tracks, "skipped": skipped}


def _artist(channel):
    """Los temas oficiales de YouTube Music salen de un canal "Artista - Topic"."""
    return re.sub(r"\s+-\s+Topic$", "", channel or "")


def _seconds(iso):
    m = DURATION.match(iso or "")
    if not m:
        return None
    h, mi, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + s
