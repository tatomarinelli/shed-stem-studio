"""Motor local de Shed Stem Studio (mínimo): solo loopback, solo lectura, con lista de orígenes permitidos.

Uso: python3 engine/server.py [puerto]   (por defecto 8770)
Todo lo que viene de afuera (ruta, parámetros, cabeceras) se trata como dato.
"""
import json
import os
import osenv
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analysis  # noqa: E402
import backends  # noqa: E402
import art  # noqa: E402
import catalog  # noqa: E402
import destinations  # noqa: E402
import envsetup  # noqa: E402
import hardware  # noqa: E402
import library  # noqa: E402
import llmserver  # noqa: E402
import services  # noqa: E402
import firstrun  # noqa: E402
import settings  # noqa: E402
import sources  # noqa: E402
import models  # noqa: E402
import recs  # noqa: E402
import resources  # noqa: E402
import stems  # noqa: E402
import tidal_source as tidal  # noqa: E402
import webui  # noqa: E402

ALLOWED_ORIGINS = {"http://127.0.0.1:5173", "http://localhost:5173"}
ALLOWED_ORIGINS |= {o.strip().rstrip("/") for o in os.environ.get("STEMSHED_ORIGINS", "").split(",") if o.strip()}  # p. ej. el sitio publicado
HOST = os.environ.get("STEMSHED_HOST", "127.0.0.1")  # en Docker: 0.0.0.0 dentro del contenedor; el puerto se publica solo en loopback
ID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")
STEM_ID = r"(\d{1,12}|L[0-9a-f]{12})"


resources.configure(paths_fn=lambda: {k: v for k, v in settings.effective().items() if k in ("dataDir", "separationEnvDir", "separationModelsDir", "ollamaModelsDir")},
                    jobs_fn=services.active_jobs)


def apply_settings():
    s = settings.effective()
    stems.configure(s["dataDir"], s["separationEnvDir"], s["separationModelsDir"])
    analysis.configure(s["dataDir"], s["separationEnvDir"])
    return models.configure(s["ollamaModelsDir"], s["llmUrl"])


class Handler(BaseHTTPRequestHandler):
    server_version = "ShedStemStudioEngine/0.0.1"

    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        origin = self.headers.get("Origin")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.end_headers()
        self.wfile.write(body)

    def _static(self, path):
        """La interfaz construida, si hay una. True si respondió."""
        ui = webui.root()
        f = webui.resolve(ui, urllib.parse.unquote(path)) if ui else None
        if not f:
            return False
        mime, headers = webui.headers_for(f)
        body = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)
        return True

    def _range_headers(self, mime, length, start, end, total):
        partial = self.headers.get("Range") is not None
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", mime)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        origin = self.headers.get("Origin")
        if origin in ALLOWED_ORIGINS:  # el sitio publicado carga los stems desde otro origen
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _play_file(self, path):
        """Archivo local con soporte de rangos."""
        import mimetypes

        total = os.path.getsize(path)
        start, end = 0, total - 1
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else end
            else:  # sufijo: últimos N bytes
                start = max(0, total - int(m.group(2)))
            end = min(end, total - 1)
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{total}")
                self.end_headers()
                return
        self._range_headers(mimetypes.guess_type(str(path))[0] or "application/octet-stream", end - start + 1, start, end, total)
        with open(path, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(65536, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)

    def _play_tidal(self, track_id):
        """Intermediario con TIDAL: reenvía el rango pedido y no guarda nada."""
        src = tidal.stream_source(track_id)
        req = urllib.request.Request(src["url"], headers={"Range": self.headers["Range"]} if self.headers.get("Range") else {})
        try:
            up = urllib.request.urlopen(req, timeout=30)
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.end_headers()
            return
        with up:
            self.send_response(up.status)
            self.send_header("Content-Type", src["mime"])
            self.send_header("Accept-Ranges", "bytes")
            for h in ("Content-Length", "Content-Range"):
                if up.headers.get(h):
                    self.send_header(h, up.headers[h])
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            while True:
                chunk = up.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def do_GET(self):
        origin = self.headers.get("Origin")
        if origin is not None and origin not in ALLOWED_ORIGINS:
            return self._send(403, {"error": "origin", "message": "Origen no permitido"})
        url = urllib.parse.urlparse(self.path)
        path = url.path
        try:
            if path == "/engine/settings":
                return self._send(200, {"settings": settings.load(), "effective": settings.effective()})
            if path == "/engine/fs":
                return self._send(200, settings.list_dirs(urllib.parse.parse_qs(url.query).get("path", ["/"])[0]))
            if path == "/engine/library":
                return self._send(200, library.report())
            if path == "/engine/status":
                return self._send(200, {"engine": "ok", "tidal": tidal.status()})
            m = re.fullmatch(rf"/engine/stems/{STEM_ID}/status", path)
            if m:
                return self._send(200, stems.job_status(m.group(1)))
            m = re.fullmatch(r"/engine/play/(\d{1,12}|L[0-9a-f]{12})", path)
            if m:
                tid = m.group(1)
                if tid.startswith("L"):
                    file = library.path_for(tid)
                    if not file or not os.path.isfile(file):
                        return self._send(404, {"error": "not_found", "message": "Ese archivo ya no está en la biblioteca."})
                    return self._play_file(file)
                return self._play_tidal(tid)
            m = re.fullmatch(rf"/engine/analysis/{STEM_ID}/status", path)
            if m:
                return self._send(200, analysis.job_status(m.group(1)))
            m = re.fullmatch(rf"/engine/analysis/{STEM_ID}", path)
            if m:
                r = analysis.get(m.group(1))
                return self._send(200, r) if r else self._send(404, {"error": "no_analysis", "message": "Todavía no se analizó este tema."})
            if path == "/engine/stems/jobs":
                return self._send(200, stems.jobs_report())
            if path == "/engine/stems/list":
                return self._send(200, stems.list_separated())
            if path == "/engine/tracks":
                return self._send(200, stems.tracks_index())
            m = re.fullmatch(rf"/engine/files/{STEM_ID}/(manifest\.json|[a-z]+\.flac)", path)
            if m:
                f = stems.stem_file(m.group(1), m.group(2))
                if not f:
                    return self._send(404, {"error": "not_found", "message": "No existe ese archivo."})
                return self._play_file(f)
            if path == "/engine/music":
                q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
                return self._send(200, catalog.query(
                    kind="tracks" if q.get("kind") == "tracks" else "albums", q=q.get("q", "")[:100], source=q.get("source", "")[:10],
                    artist=q.get("artist", "")[:160], genre=q.get("genre", "")[:60],
                    limit=min(int(q.get("limit", 60)), 200), offset=max(int(q.get("offset", 0)), 0)))
            if path == "/engine/music/album":
                d = catalog.album_detail(urllib.parse.parse_qs(url.query).get("key", [""])[0][:300])
                return self._send(200 if d else 404, d or {"error": "not_found", "message": "No encontré ese disco."})
            if path == "/engine/pick":
                q = urllib.parse.parse_qs(url.query)
                return self._send(200, sources.pick({k: q[k][0] for k in ("local", "tidal") if k in q and q[k][0]}))
            m = re.fullmatch(r"/engine/albumart/(\d{1,12})", path)
            if m:
                try:
                    data = tidal.album_art(m.group(1))
                except Exception:
                    return self._send(404, {"error": "no_art", "message": "Sin arte"})
                self.send_response(200)
                self.send_header("Content-Type", art.content_type(data))
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "public, max-age=31536000, immutable")
                self.end_headers()
                self.wfile.write(data)
                return
            if path == "/engine/sources":
                return self._send(200, sources.status())
            if path == "/engine/album":
                q = urllib.parse.parse_qs(url.query)
                artist, album = q.get("artist", [""])[0][:160], q.get("album", [""])[0][:200]
                if not artist or not album:
                    return self._send(400, {"error": "params", "message": "Faltan artista y disco."})
                return self._send(200, sources.resolve_album(artist, album))
            if path == "/engine/resolve":
                q = urllib.parse.parse_qs(url.query)
                artist, title, album = (q.get(k, [""])[0][:200] for k in ("artist", "title", "album"))
                if not artist or not title:
                    return self._send(400, {"error": "params", "message": "Faltan artista y título."})
                return self._send(200, sources.resolve_track(artist, title, album))
            if path == "/engine/destinations":
                return self._send(200, {"destinations": destinations.listing(), "dryRun": destinations.DRY})
            if path == "/engine/recs/status":
                return self._send(200, recs.status())
            m = re.fullmatch(r"/engine/cover/([0-9a-f-]{36})", path) or re.fullmatch(rf"/engine/art/{STEM_ID}", path)
            if m:
                data = recs.cover(m.group(1)) if path.startswith("/engine/cover/") else art.for_track(m.group(1))
                if data is None:
                    return self._send(404, {"error": "no_art", "message": "Sin arte"})
                self.send_response(200)
                self.send_header("Content-Type", art.content_type(data))
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "public, max-age=31536000, immutable")  # el navegador lo guarda
                self.end_headers()
                self.wfile.write(data)
                return
            if path == "/engine/storage":
                return self._send(200, models.report())
            if path == "/engine/setup/status":
                return self._send(200, firstrun.status())
            if path == "/engine/recs/profile/suggested":
                return self._send(200, recs.suggested_profile(refresh=urllib.parse.parse_qs(url.query).get("refresh") == ["1"]))
            if path == "/engine/resources":  # cada pedido cuenta como una suscripción al muestreador
                try:
                    since = int(urllib.parse.parse_qs(url.query).get("since", [""])[0])
                except ValueError:
                    since = None
                return self._send(200, resources.SAMPLER.snapshot(since))
            if path == "/engine/services":
                return self._send(200, services.report())
            if path == "/engine/env/status":
                return self._send(200, envsetup.status())
            if path == "/engine/llm/status":
                return self._send(200, llmserver.status())
            if path == "/engine/backends":
                return self._send(200, backends.report(hardware._gpus()))
            if path == "/engine/models/separation/status":
                return self._send(200, stems.sep_download_status())
            m = re.fullmatch(r"/engine/models/([A-Za-z0-9._:/-]{1,100})/status", urllib.parse.unquote(path))
            if m:
                return self._send(200, models.pull_status(m.group(1)))
            if path == "/engine/hardware":
                return self._send(200, hardware.report(stems.ROOT, [stems.ENV]))
            if path == "/engine/tidal/login/status":
                return self._send(200, tidal.login_status())
            if path == "/engine/tidal/library":
                return self._send(200, tidal.library())
            m = re.fullmatch(r"/engine/tidal/playlists/([^/]+)", path)
            if m and ID_RE.match(m.group(1)):
                return self._send(200, tidal.playlist_tracks(m.group(1)))
            if not path.startswith("/engine/") and self._static(path):
                return
            return self._send(404, {"error": "not_found", "message": "Ruta desconocida"})
        except (stems.StemsError, analysis.AnalysisError, envsetup.EnvError, llmserver.LlmServerError) as e:
            return self._send(409, {"error": "stems", "message": str(e)})
        except tidal.SourceError as e:
            return self._send(409, {"error": e.code, "message": e.message})
        except Exception as e:  # una falla de TIDAL no debe tumbar el motor
            return self._send(502, {"error": "tidal_error", "message": f"TIDAL respondió con un error: {type(e).__name__}"})

    def do_POST(self):
        # Acciones con efecto: el origen es obligatorio y debe estar en la lista.
        if self.headers.get("Origin") not in ALLOWED_ORIGINS:
            return self._send(403, {"error": "origin", "message": "Origen no permitido"})
        path = self.path.split("?")[0]
        try:
            if path == "/engine/tidal/login/start":
                return self._send(200, tidal.login_start(renew="renew=1" in self.path.partition("?")[2].split("&")))
            if path == "/engine/tidal/login/cancel":
                return self._send(200, tidal.login_cancel())
            m = re.fullmatch(rf"/engine/analysis/{STEM_ID}/start", path)
            if m:
                size = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(size) or b"{}") if 0 < size <= 1024 else {}
                return self._send(200, analysis.start(m.group(1), force=bool(body.get("force"))))
            m = re.fullmatch(rf"/engine/stems/{STEM_ID}/delete", path)
            if m:
                return self._send(200, stems.delete_separated(m.group(1)))
            m = re.fullmatch(rf"/engine/stems/{STEM_ID}/separate", path)
            if m:
                is_local = m.group(1).startswith("L")
                return self._send(200, stems.start(None if is_local else tidal.session(), m.group(1)))
            if path in ("/engine/setup/skip", "/engine/setup/unskip", "/engine/setup/finish", "/engine/setup/reset"):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                if path.endswith("finish"):
                    firstrun.finish()
                elif path.endswith("reset"):
                    firstrun.reset()
                else:
                    firstrun.skip(str(body.get("step", "")), on=path.endswith("/skip"))
                return self._send(200, firstrun.status())
            if path == "/engine/shutdown":
                if json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}").get("confirm") is not True:
                    return self._send(400, {"error": "confirm", "message": "Falta la confirmación."})
                res = services.shutdown()
                if not res["ok"]:
                    return self._send(409, {"error": "busy", "message": "Hay trabajo en curso. Esperá a que termine.", "jobs": res["jobs"]})
                return self._send(200, res)
            if path == "/engine/open-folder":
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                return self._send(200, services.open_folder(str(body.get("key", ""))))
            if path == "/engine/env/install":
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                choice = body.get("backend")
                if choice is not None and not (isinstance(choice, str) and ID_RE.match(choice)):
                    return self._send(400, {"error": "bad_request", "message": "Motor de separación inválido."})
                return self._send(200, envsetup.start(choice))
            if path == "/engine/llm/install":
                return self._send(200, llmserver.install_start())
            if path == "/engine/models/separation/download":
                return self._send(200, stems.sep_download_start())
            m = re.fullmatch(r"/engine/models/([A-Za-z0-9._:/-]{1,100})/pull", urllib.parse.unquote(path))
            if m:
                return self._send(200, models.pull_start(m.group(1)))
            if path == "/engine/save":
                # ESCRIBE en las cuentas del usuario: solo con confirmación explícita de la interfaz.
                size = int(self.headers.get("Content-Length", 0))
                if size > 65536:
                    return self._send(413, {"error": "too_large", "message": "Pedido demasiado grande"})
                body = json.loads(self.rfile.read(size) or b"{}")
                if not isinstance(body, dict) or body.get("confirm") is not True:
                    return self._send(400, {"error": "confirm", "message": "Falta confirmar qué se guarda y dónde."})
                res = destinations.save(body.get("kind"), body.get("items"), body.get("destinations"), body.get("name"),
                                        recs.MEM_DIR / "saved.jsonl")
                return self._send(200, {"results": res, "dryRun": destinations.DRY})
            if path in ("/engine/recs/generate", "/engine/recs/reaction", "/engine/recs/profile", "/engine/recs/schedule", "/engine/recs/presets"):
                size = int(self.headers.get("Content-Length", 0))
                if size > 8192:
                    return self._send(413, {"error": "too_large", "message": "Pedido demasiado grande"})
                body = json.loads(self.rfile.read(size) or b"{}")
                if not isinstance(body, dict):
                    return self._send(400, {"error": "params", "message": "Pedido inválido"})
                if path == "/engine/recs/generate":
                    return self._send(200, recs.start(body.get("kind", "daily"), body))
                if path == "/engine/recs/reaction":
                    return self._send(200, {"reactions": recs.set_reaction(body.get("key"), body.get("reaction"))})
                if path == "/engine/recs/profile":
                    return self._send(200, {"profile": recs.save_profile(body)})
                if path == "/engine/recs/presets":
                    return self._send(200, {"presets": recs.save_presets(body)})
                patch = {k: v for k, v in (("recsAuto", body.get("auto")), ("recsCadenceHours", body.get("cadenceHours"))) if v is not None}
                settings.save(patch)
                return self._send(200, {"schedule": recs.schedule_info()})
            if path == "/engine/library/rescan":
                library.scan()
                return self._send(200, {"ok": True})
            if path == "/engine/music/refresh":
                library.scan()
                catalog.refresh_tidal()
                catalog.enrich_genres()
                return self._send(200, {"ok": True})
            if path == "/engine/settings":
                size = int(self.headers.get("Content-Length", 0))
                if size > 16384:
                    return self._send(413, {"error": "too_large", "message": "Pedido demasiado grande"})
                saved = settings.save(json.loads(self.rfile.read(size) or b"{}"))
                needs_restart = apply_settings()
                library.scan()
                return self._send(200, {"settings": saved, "effective": settings.effective(saved), "needsRestart": needs_restart})
            if path == "/engine/tidal/logout":
                tidal.logout()
                return self._send(200, {"ok": True})
            return self._send(404, {"error": "not_found", "message": "Ruta desconocida"})
        except settings.SettingsError as e:
            return self._send(400, {"error": "settings", "message": str(e)})
        except (stems.StemsError, analysis.AnalysisError, envsetup.EnvError, llmserver.LlmServerError, services.OpenError, ValueError) as e:
            return self._send(409, {"error": "stems", "message": str(e)})
        except tidal.SourceError as e:
            return self._send(409, {"error": e.code, "message": e.message})
        except Exception as e:
            return self._send(502, {"error": "tidal_error", "message": f"No se pudo completar la acción: {type(e).__name__}"})

    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            pass  # el navegador cortó la descarga (por ejemplo al saltar en el tema): no es un error

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8770
    osenv.kill_children_on_exit()  # Windows: los procesos hijos mueren con el motor
    osenv.ensure_ffmpeg_on_path()  # audio-separator lo necesita; en Windows lo instala winget fuera del PATH de este proceso
    apply_settings()
    models.ensure_ollama()
    catalog.load_state()
    library.scan()
    recs.ensure_ready()
    recs.genresim.configure(settings.effective()["dataDir"], models.OLLAMA)
    try:
        recs.import_seed()
    except Exception as e:  # una semilla rota no impide arrancar
        print(f"No se pudo importar la semilla del perfil: {type(e).__name__}", flush=True)
    if port == 8770 or os.environ.get("STEMSHED_SCHEDULER") == "1":  # la tarea automática solo corre en el motor principal (la cáscara de escritorio lo pide si usa otro puerto)
        recs.start_scheduler()
    print(f"Motor de Shed Stem Studio en http://{HOST}:{port}", flush=True)
    httpd = ThreadingHTTPServer((HOST, port), Handler)
    services.bind(httpd, HOST, port, ALLOWED_ORIGINS)
    httpd.serve_forever()
