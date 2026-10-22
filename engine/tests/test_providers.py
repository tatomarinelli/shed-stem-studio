"""Spotify y YouTube Music: PKCE, OAuth con state, renovación de tokens, lectura de biblioteca y almacenamiento cifrado.
Todo con respuestas simuladas: cualquier pedido de red no previsto hace fallar la prueba. Las dos plataformas se simulan
con osenv.WINDOWS / _dpapi / secret-tool, así que corren igual en Linux y en Windows."""
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["STEMSHED_NO_SCHEDULER"] = "1"
import osenv  # noqa: E402
import providers  # noqa: E402
from perms import assert_private  # noqa: E402
from providers import ProviderError  # noqa: E402


class Resp:
    def __init__(self, body):
        self.body = json.dumps(body).encode()

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def http_error(code, body=None, headers=None):
    return urllib.error.HTTPError("https://x", code, "err", headers or {}, io.BytesIO(json.dumps(body or {}).encode()))


class Net:
    """Red falsa: `routes` mapea un prefijo de URL a una respuesta, una excepción o una función. Todo lo demás falla."""

    def __init__(self):
        self.routes, self.calls = [], []

    def add(self, prefix, result):
        self.routes.append((prefix, result))

    def __call__(self, req, timeout=None):
        url = req.full_url
        self.calls.append((req.get_method(), url, req.data, dict(req.header_items())))
        for prefix, result in self.routes:
            if url.startswith(prefix):
                if callable(result):
                    result = result(req)
                if isinstance(result, BaseException):
                    raise result
                return Resp(result)
        raise AssertionError(f"Pedido de red no previsto: {url}")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patches = [mock.patch.object(osenv, "config_dir", lambda: Path(self.tmp.name) / "cfg"),
                   mock.patch.object(osenv, "keyring_available", lambda: False)]  # Linux sin llavero: archivo 600
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.net = Net()
        p = mock.patch.object(providers, "_urlopen", self.net)
        p.start()
        self.addCleanup(p.stop)
        providers._pending.clear()
        self.sp = providers.get("spotify")
        self.yt = providers.get("ytmusic")

    def connect(self, p, expires_in=3600, **extra):
        p.tokens_store.save({"access_token": "AT", "refresh_token": "RT", "expires_at": time.time() + expires_in, **extra})


class Pkce(Base):
    def test_vector_del_rfc_7636(self):
        self.assertEqual(providers.pkce_challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"), "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")

    def test_el_verificador_cumple_el_largo(self):
        v, c = providers.pkce_pair()
        self.assertTrue(43 <= len(v) <= 128)
        self.assertEqual(c, providers.pkce_challenge(v))


class Auth(Base):
    def test_sin_client_id_no_se_puede_conectar(self):
        with self.assertRaises(ProviderError) as cm:
            self.sp.auth_start(8770)
        self.assertEqual(cm.exception.code, "no_app")

    def test_url_de_autorizacion_de_spotify(self):
        self.sp.set_app("abcdef1234567890")
        out = self.sp.auth_start(8770)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(out["url"]).query)
        self.assertEqual(out["redirectUri"], "http://127.0.0.1:8770/engine/oauth/callback")
        self.assertEqual(q["redirect_uri"], [out["redirectUri"]])
        self.assertEqual(q["code_challenge_method"], ["S256"])
        self.assertEqual(q["response_type"], ["code"])
        self.assertEqual(set(q["scope"][0].split()), {"user-library-read", "playlist-read-private", "playlist-read-collaborative"})
        self.assertNotIn("client_secret", out["url"])

    def test_solo_permisos_de_lectura(self):
        for p in (self.sp, self.yt):
            self.assertFalse(p.capabilities["write"])
            self.assertFalse(p.capabilities["audio"])
            self.assertTrue(all("read" in s for s in p.scopes), p.scopes)

    def test_youtube_pide_client_secret_y_refresh_token(self):
        self.yt.set_app("abcdef1234567890.apps.googleusercontent.com")
        self.assertFalse(self.yt.configured())
        self.yt.set_app("abcdef1234567890.apps.googleusercontent.com", "GOCSPX-secret")
        self.assertTrue(self.yt.configured())
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.yt.auth_start(8770)["url"]).query)
        self.assertEqual((q["access_type"], q["prompt"]), (["offline"], ["consent"]))

    def test_client_id_invalido(self):
        with self.assertRaises(ProviderError):
            self.sp.set_app("<script>")

    def _start(self):
        self.sp.set_app("abcdef1234567890")
        url = self.sp.auth_start(8770)["url"]
        return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["state"][0]

    def test_callback_correcto_guarda_tokens_cifrados(self):
        state = self._start()
        self.net.add("https://accounts.spotify.com/api/token", lambda r: {"access_token": "AT", "refresh_token": "RT", "expires_in": 3600})
        ok, msg = providers.handle_callback({"state": [state], "code": ["CODE"]})
        self.assertTrue(ok, msg)
        form = urllib.parse.parse_qs(self.net.calls[0][2].decode())
        self.assertEqual(form["grant_type"], ["authorization_code"])
        self.assertIn("code_verifier", form)
        self.assertNotIn("client_secret", form)
        self.assertTrue(self.sp.connected())
        assert_private(self, self.sp.tokens_store.path)
        self.assertEqual(self.sp.tokens_store.protection(), "file-600")

    def test_state_malo_vencido_o_repetido(self):
        state = self._start()
        self.assertFalse(providers.handle_callback({"state": ["otro"], "code": ["C"]})[0])
        self.assertFalse(providers.handle_callback({"code": ["C"]})[0])
        providers._pending[state]["exp"] = time.time() - 1
        self.assertFalse(providers.handle_callback({"state": [state], "code": ["C"]})[0])
        state = self._start()
        self.net.add("https://accounts.spotify.com/api/token", {"access_token": "AT", "refresh_token": "RT", "expires_in": 60})
        self.assertTrue(providers.handle_callback({"state": [state], "code": ["C"]})[0])
        self.assertFalse(providers.handle_callback({"state": [state], "code": ["C"]})[0])  # un state sirve una vez

    def test_usuario_rechaza_el_permiso(self):
        state = self._start()
        ok, msg = providers.handle_callback({"state": [state], "error": ["access_denied"]})
        self.assertFalse(ok)
        self.assertEqual(self.net.calls, [])
        self.assertFalse(self.sp.connected())

    def test_la_pagina_de_vuelta_escapa_todo(self):
        page = providers.callback_page(False, "<script>alert(1)</script>").decode()
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)

    def test_respuesta_sin_refresh_token(self):
        state = self._start()
        self.net.add("https://accounts.spotify.com/api/token", {"access_token": "AT", "expires_in": 60})
        ok, _ = providers.handle_callback({"state": [state], "code": ["C"]})
        self.assertFalse(ok)
        self.assertFalse(self.sp.connected())

    def test_logout_borra_lo_local_y_no_usa_la_red(self):
        self.connect(self.sp)
        self.sp.logout()
        self.assertFalse(self.sp.connected())
        self.assertFalse(self.sp.tokens_store.path.exists())
        self.assertEqual(self.net.calls, [])


class Tokens(Base):
    def setUp(self):
        super().setUp()
        self.sp.set_app("abcdef1234567890")

    def test_renueva_el_vencido_y_conserva_el_refresh_si_no_rota(self):
        self.connect(self.sp, expires_in=-10, user="yo")
        self.net.add("https://accounts.spotify.com/api/token", {"access_token": "AT2", "expires_in": 3600})
        self.assertEqual(self.sp.access_token(), "AT2")
        t = self.sp.tokens_store.load()
        self.assertEqual((t["refresh_token"], t["user"]), ("RT", "yo"))

    def test_renovaciones_en_paralelo_hacen_un_solo_pedido(self):
        self.connect(self.sp, expires_in=-10)
        self.net.add("https://accounts.spotify.com/api/token", lambda r: (time.sleep(0.05), {"access_token": "AT2", "refresh_token": "RT2", "expires_in": 3600})[1])
        out = []
        ts = [threading.Thread(target=lambda: out.append(self.sp.access_token())) for _ in range(5)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(out, ["AT2"] * 5)
        self.assertEqual(len([c for c in self.net.calls if "token" in c[1]]), 1)
        self.assertEqual(self.sp.tokens_store.load()["refresh_token"], "RT2")

    def test_refresh_revocado_pide_reconectar(self):
        self.connect(self.sp, expires_in=-10)
        self.net.add("https://accounts.spotify.com/api/token", http_error(400, {"error": "invalid_grant"}))
        with self.assertRaises(ProviderError) as cm:
            self.sp.access_token()
        self.assertEqual(cm.exception.code, "reauth")

    def test_un_401_renueva_una_vez_y_reintenta(self):
        self.connect(self.sp)
        seen = []

        def api(req):
            seen.append(req.get_header("Authorization"))
            return http_error(401) if req.get_header("Authorization") == "Bearer AT" else {"id": "yo"}
        self.net.add("https://api.spotify.com/v1/me", api)
        self.net.add("https://accounts.spotify.com/api/token", {"access_token": "AT2", "expires_in": 3600})
        self.assertEqual(self.sp.api("https://api.spotify.com/v1/me"), {"id": "yo"})
        self.assertEqual(seen, ["Bearer AT", "Bearer AT2"])

    def test_limite_de_pedidos_y_403(self):
        self.connect(self.sp)
        self.net.add("https://api.spotify.com/v1/a", http_error(429, headers={"Retry-After": "7"}))
        self.net.add("https://api.spotify.com/v1/b", http_error(403, {"error": "forbidden"}))
        with self.assertRaises(ProviderError) as cm:
            self.sp.api("https://api.spotify.com/v1/a")
        self.assertIn("7", cm.exception.message)
        with self.assertRaises(ProviderError) as cm:
            self.sp.api("https://api.spotify.com/v1/b")
        self.assertEqual(cm.exception.code, "forbidden")

    def test_sin_red(self):
        self.connect(self.sp)
        self.net.add("https://api.spotify.com/v1/a", urllib.error.URLError("sin dns"))
        with self.assertRaises(ProviderError) as cm:
            self.sp.api("https://api.spotify.com/v1/a")
        self.assertEqual(cm.exception.code, "network")

    def test_no_sale_a_otro_host(self):
        self.connect(self.sp)
        for url in ("https://evil.example/v1/me", "http://api.spotify.com/v1/me", "https://api.spotify.com.evil.example/v1"):
            with self.assertRaises(ProviderError):
                self.sp.api(url)
        self.assertEqual(self.net.calls, [])


def sp_track(i, name="Tema", isrc="USX1", **kw):
    return {"id": f"track{i:08d}", "type": "track", "name": name, "duration_ms": 215000, "artists": [{"name": "Ana"}, {"name": "Beto"}],
            "album": {"name": "Disco"}, "external_ids": {"isrc": isrc}, "external_urls": {"spotify": f"https://open.spotify.com/track/{i}"}, **kw}


class SpotifyLibrary(Base):
    def setUp(self):
        super().setUp()
        self.sp.set_app("abcdef1234567890")
        self.connect(self.sp, user="yo")

    def test_biblioteca_ordenada_por_fecha_de_guardado(self):
        album = lambda i, d: {"added_at": d, "album": {"id": f"alb{i:09d}", "name": f"A{i}", "artists": [{"name": "Ana"}], "release_date": "1999-05-01",
                                                          "total_tracks": 9, "external_ids": {"upc": "123"}}}
        self.net.add("https://api.spotify.com/v1/me/albums", {"items": [album(1, "2024-01-01T00:00:00Z"), album(2, "2025-06-01T00:00:00Z")], "next": None})
        # dos páginas de temas: la segunda por `next` (mismo host)
        self.net.add("https://api.spotify.com/v1/me/tracks?offset=50", {"items": [{"added_at": "2026-03-01T00:00:00Z", "track": sp_track(3)}], "next": None})
        self.net.add("https://api.spotify.com/v1/me/tracks", {"items": [{"added_at": "2023-01-01T00:00:00Z", "track": sp_track(1)},
                                                                       {"added_at": "2025-01-01T00:00:00Z", "track": {"id": "ep", "type": "episode"}}],
                                                              "next": "https://api.spotify.com/v1/me/tracks?offset=50"})
        self.net.add("https://api.spotify.com/v1/me/playlists", {"items": [
            {"id": "plMia000001", "name": "Mía", "owner": {"id": "yo"}, "items": {"total": 5}},
            {"id": "plColab0001", "name": "Colab", "owner": {"id": "otro"}, "collaborative": True, "tracks": {"total": 2}},
            {"id": "plAjena0001", "name": "Ajena", "owner": {"id": "otro"}, "tracks": {"total": 40}}], "next": None})
        lib = self.sp.library()
        self.assertEqual([a["title"] for a in lib["albums"]], ["A2", "A1"])
        self.assertEqual((lib["albums"][0]["year"], lib["albums"][0]["upc"]), (1999, "123"))
        self.assertEqual([t["id"] for t in lib["tracks"]], ["track00000003", "track00000001"])  # el episodio se descarta
        t = lib["tracks"][0]
        self.assertEqual((t["artist"], t["album"], t["duration"], t["isrc"], t["source"]), ("Ana", "Disco", 215, "USX1", "spotify"))
        self.assertEqual([(p["name"], p["own"], p["readable"], p["tracks"]) for p in lib["playlists"]],
                         [("Mía", True, True, 5), ("Colab", False, True, 2), ("Ajena", False, False, 40)])

    def test_next_hacia_otro_host_se_rechaza(self):
        self.net.add("https://api.spotify.com/v1/me/albums", {"items": [], "next": "https://evil.example/steal"})
        with self.assertRaises(ProviderError):
            self.sp._pages("https://api.spotify.com/v1/me/albums", 100)
        self.assertEqual(len(self.net.calls), 1)

    def test_temas_de_playlist_con_las_dos_formas_de_la_api(self):
        self.net.add("https://api.spotify.com/v1/playlists/plMia000001/items", {"items": [
            {"added_at": "2024-01-01T00:00:00Z", "item": sp_track(1)},          # forma nueva
            {"added_at": "2025-01-01T00:00:00Z", "track": sp_track(2)},         # forma vieja
            {"added_at": "2025-02-01T00:00:00Z", "item": None}], "next": None})
        tr = self.sp.playlist_tracks("plMia000001")["tracks"]
        self.assertEqual([t["id"] for t in tr], ["track00000002", "track00000001"])

    def test_playlist_ajena_explica_por_que_no(self):
        self.net.add("https://api.spotify.com/v1/playlists/plAjena0001/items", http_error(403))
        with self.assertRaises(ProviderError) as cm:
            self.sp.playlist_tracks("plAjena0001")
        self.assertEqual(cm.exception.code, "not_readable")

    def test_id_de_playlist_invalido(self):
        with self.assertRaises(ProviderError):
            self.sp.playlist_tracks("../me")


class YouTubeLibrary(Base):
    def setUp(self):
        super().setUp()
        self.yt.set_app("abcdef1234567890.apps.googleusercontent.com", "GOCSPX-secret")
        self.connect(self.yt)

    def test_me_gusta_solo_musica_en_orden_de_guardado(self):
        self.net.add("https://www.googleapis.com/youtube/v3/channels", {"items": [{"contentDetails": {"relatedPlaylists": {"likes": "LLxxxxxxxxxx"}}}]})
        self.net.add("https://www.googleapis.com/youtube/v3/playlistItems", {"items": [
            {"snippet": {"publishedAt": "2026-02-01T00:00:00Z"}, "contentDetails": {"videoId": "vid_musica_1"}},
            {"snippet": {"publishedAt": "2026-01-01T00:00:00Z"}, "contentDetails": {"videoId": "vid_gatitos_"}}]})
        self.net.add("https://www.googleapis.com/youtube/v3/videos", {"items": [
            {"id": "vid_musica_1", "snippet": {"title": "Tema", "channelTitle": "Ana - Topic", "categoryId": "10"}, "contentDetails": {"duration": "PT1H2M3S"}},
            {"id": "vid_gatitos_", "snippet": {"title": "Gatitos", "channelTitle": "Canal", "categoryId": "15"}, "contentDetails": {"duration": "PT30S"}}]})
        self.net.add("https://www.googleapis.com/youtube/v3/playlists", {"items": [
            {"id": "PLviejaaaaaa", "snippet": {"title": "Vieja", "publishedAt": "2020-01-01T00:00:00Z"}, "contentDetails": {"itemCount": 3}},
            {"id": "PLnuevaaaaaa", "snippet": {"title": "Nueva", "publishedAt": "2026-01-01T00:00:00Z"}, "contentDetails": {"itemCount": 8}}]})
        lib = self.yt.library()
        self.assertEqual(lib["albums"], [])
        self.assertEqual(lib["skipped"], 1)
        self.assertEqual([(t["title"], t["artist"], t["duration"], t["addedAt"]) for t in lib["tracks"]], [("Tema", "Ana", 3723, "2026-02-01T00:00:00Z")])
        self.assertEqual([p["name"] for p in lib["playlists"]], ["Nueva", "Vieja"])
        self.assertFalse(self.yt.capabilities["albums"])

    def test_cuota_agotada(self):
        self.net.add("https://www.googleapis.com/youtube/v3/channels", http_error(403, {"error": {"message": "quota exceeded", "errors": [{"reason": "quotaExceeded"}]}}))
        with self.assertRaises(ProviderError) as cm:
            self.yt.library()
        self.assertEqual(cm.exception.code, "quota")

    def test_la_duracion_iso(self):
        import ytmusic_source as y
        self.assertEqual([y._seconds(x) for x in ("PT45S", "PT3M", "PT1H", "P1D", None)], [45, 180, 3600, None, None])


class Storage(unittest.TestCase):
    """osenv.write_protected en las tres variantes, simuladas."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.f = Path(self.tmp.name) / "sub" / "x-session.json"

    def test_windows_dpapi_no_deja_texto_plano_ni_temporales(self):
        with mock.patch.object(osenv, "WINDOWS", True), mock.patch.object(osenv, "_dpapi", side_effect=lambda d, protect: d[::-1]):
            self.assertEqual(osenv.write_protected(self.f, b'{"t": "secreto"}'), "dpapi")
            self.assertNotIn(b"secreto", self.f.read_bytes())
            self.assertEqual(osenv.read_protected(self.f), b'{"t": "secreto"}')
            self.assertEqual(osenv.protection_of(self.f), "dpapi")
        self.assertEqual(sorted(p.name for p in self.f.parent.iterdir()), ["x-session.json"])

    def test_linux_con_llavero_el_secreto_no_toca_el_disco(self):
        vault = {}

        def fake(args, data=None):
            acct = args[args.index("account") + 1]
            if args[0] == "store":
                vault[acct] = data
            elif args[0] == "clear":
                vault.pop(acct, None)
            elif args[0] == "lookup":
                return mock.Mock(returncode=0 if acct in vault else 1, stdout=vault.get(acct, b""))
            return mock.Mock(returncode=0, stdout=b"")
        with mock.patch.object(osenv, "WINDOWS", False), mock.patch.object(osenv, "keyring_available", lambda: True), \
                mock.patch.object(osenv, "_run_secret_tool", fake):
            self.assertEqual(osenv.write_protected(self.f, b'{"t": "secreto"}'), "keyring")
            self.assertNotIn(b"secreto", self.f.read_bytes())
            self.assertEqual(osenv.read_protected(self.f), b'{"t": "secreto"}')
            osenv.delete_protected(self.f)
            self.assertEqual(vault, {})
            self.assertFalse(self.f.exists())

    def test_linux_sin_llavero_cae_a_archivo_600(self):
        with mock.patch.object(osenv, "WINDOWS", False), mock.patch.object(osenv, "keyring_available", lambda: False):
            self.assertEqual(osenv.write_protected(self.f, b"{}"), "file-600")
        assert_private(self, self.f) if not osenv.WINDOWS else None
        self.assertEqual(osenv.protection_of(self.f), "file-600")

    def test_llavero_que_falla_al_guardar_cae_a_archivo(self):
        with mock.patch.object(osenv, "WINDOWS", False), mock.patch.object(osenv, "keyring_available", lambda: True), \
                mock.patch.object(osenv, "_run_secret_tool", lambda a, d=None: mock.Mock(returncode=1, stdout=b"")):
            self.assertEqual(osenv.write_protected(self.f, b"{}"), "file-600")

    def test_archivo_del_llavero_no_se_abre_en_windows(self):
        self.f.parent.mkdir(parents=True)
        self.f.write_bytes(osenv._KEYRING_MAGIC)
        with mock.patch.object(osenv, "WINDOWS", True), self.assertRaises(OSError):
            osenv.read_protected(self.f)

    def test_en_windows_los_tokens_de_un_proveedor_quedan_cifrados(self):
        cfg = Path(self.tmp.name) / "cfg"
        with mock.patch.object(osenv, "config_dir", lambda: cfg), mock.patch.object(osenv, "WINDOWS", True), \
                mock.patch.object(osenv, "_dpapi", side_effect=lambda d, protect: d[::-1]):
            sp = providers.get("spotify")
            sp.set_app("abcdef1234567890")
            sp.tokens_store.save({"access_token": "AT-secreto", "refresh_token": "RT-secreto", "expires_at": time.time() + 99})
            for name in ("providers-apps.json", "spotify-session.json"):
                self.assertTrue((cfg / name).read_bytes().startswith(osenv._DPAPI_MAGIC))
            self.assertNotIn(b"secreto", (cfg / "spotify-session.json").read_bytes())
            self.assertEqual(sp.status()["protection"], "dpapi")
            sp.logout()


class Server(Base):
    def test_rutas_http(self):
        import server
        with mock.patch.object(server.services, "_server", {"port": 0, "host": "", "origins": [], "httpd": None}):
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            port = httpd.server_address[1]
            server.services._server["port"] = port
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{port}"
            origin = {"Origin": "http://127.0.0.1:5173"}

            def call(path, method="GET", body=None, headers=None):
                req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None),
                                             method=method, headers=headers or {})
                try:
                    with urllib.request.urlopen(req) as r:  # noqa: S310  (es el servidor de la prueba; providers._urlopen es el simulado)
                        return r.status, r.headers, r.read()
                except urllib.error.HTTPError as e:
                    return e.code, e.headers, e.read()
            try:
                code, _, body = call("/engine/providers")
                self.assertEqual(code, 200)
                st = {p["id"]: p for p in json.loads(body)["providers"]}
                self.assertEqual(set(st), {"spotify", "ytmusic", "tidal"})
                self.assertEqual(st["spotify"]["redirectUri"], f"http://127.0.0.1:{port}/engine/oauth/callback")
                self.assertFalse(st["spotify"]["connected"])
                self.assertEqual(call("/engine/providers/spotify/app", "POST", {"clientId": "abcdef1234567890"})[0], 403)  # sin Origin
                self.assertEqual(call("/engine/providers/spotify/auth/start", "POST", {}, origin)[0], 409)  # falta el Client ID
                code, _, body = call("/engine/providers/spotify/app", "POST", {"clientId": "abcdef1234567890"}, origin)
                self.assertEqual((code, json.loads(body)["configured"]), (200, True))
                self.assertNotIn(b"abcdef1234567890", body)
                code, _, body = call("/engine/providers/spotify/auth/start", "POST", {}, origin)
                self.assertEqual(code, 200)
                self.assertIn("code_challenge_method=S256", json.loads(body)["url"])
                self.assertEqual(call("/engine/providers/spotify/library")[0], 401)  # no hay sesión
                self.assertEqual(call("/engine/providers/otro/library")[0], 404)
                code, headers, body = call("/engine/oauth/callback?error=%3Cscript%3E&state=zzz")
                self.assertEqual(code, 400)
                self.assertNotIn(b"<script>", body)
                self.assertEqual(headers["Referrer-Policy"], "no-referrer")
                self.assertEqual(self.net.calls, [])
            finally:
                httpd.shutdown()
                httpd.server_close()


if __name__ == "__main__":
    unittest.main()
