"""La interfaz servida por el motor: tipos, aislamiento de origen y que no se pueda salir de la carpeta."""
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["STEMSHED_NO_SCHEDULER"] = "1"
import webui  # noqa: E402


class WebUi(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "dist"
        (self.root / "assets").mkdir(parents=True)
        (self.root / "index.html").write_text("<h1>hola</h1>", encoding="utf-8")
        (self.root / "assets" / "app-abc.js").write_text("1", encoding="utf-8")
        (self.root / "rubberband.wasm").write_bytes(b"\0asm")
        (Path(self._tmp.name) / "secreto.txt").write_text("no", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_resolve_dentro_y_fuera(self):
        self.assertEqual(webui.resolve(self.root, "/"), self.root.resolve() / "index.html")
        self.assertIsNotNone(webui.resolve(self.root, "/assets/app-abc.js"))
        self.assertIsNone(webui.resolve(self.root, "/nada.html"))
        self.assertIsNone(webui.resolve(self.root, "/../secreto.txt"))
        self.assertIsNone(webui.resolve(self.root, r"/..\secreto.txt"))
        self.assertIsNone(webui.resolve(self.root, "/assets"))  # una carpeta no es un archivo

    def test_cabeceras(self):
        mime, h = webui.headers_for(self.root / "rubberband.wasm")
        self.assertEqual(mime, "application/wasm")
        self.assertEqual((h["Cross-Origin-Opener-Policy"], h["Cross-Origin-Embedder-Policy"]), ("same-origin", "require-corp"))
        self.assertEqual(h["Cache-Control"], "no-store")
        self.assertIn("immutable", webui.headers_for(self.root / "assets" / "app-abc.js")[1]["Cache-Control"])
        self.assertEqual(webui.headers_for(self.root / "assets" / "app-abc.js")[0], "text/javascript")

    def test_root_sin_compilacion(self):
        with mock.patch.dict(os.environ, {"STEMSHED_UI": str(self.root)}):
            self.assertEqual(webui.root(), self.root)
        with mock.patch.dict(os.environ, {"STEMSHED_UI": str(Path(self._tmp.name) / "vacio")}):
            self.assertIsNone(webui.root())

    def test_servidor_real(self):
        import server  # noqa: E402
        with mock.patch.dict(os.environ, {"STEMSHED_UI": str(self.root)}):
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{httpd.server_address[1]}"
            try:
                r = urllib.request.urlopen(base + "/")
                self.assertEqual(r.read(), b"<h1>hola</h1>")
                self.assertEqual(r.headers["Cross-Origin-Embedder-Policy"], "require-corp")
                self.assertEqual(urllib.request.urlopen(base + "/rubberband.wasm").headers["Content-Type"], "application/wasm")
                for bad in ("/nada", "/%2e%2e/secreto.txt", "/engine/no-existe"):
                    with self.assertRaises(urllib.error.HTTPError) as cm:
                        urllib.request.urlopen(base + bad)
                    cm.exception.close()
                    self.assertEqual(cm.exception.code, 404, bad)
            finally:
                httpd.shutdown()
                httpd.server_close()


if __name__ == "__main__":
    unittest.main()
