#!/usr/bin/env python3
"""Sirve esta carpeta en http://127.0.0.1:8899 con los encabezados de aislamiento (COOP/COEP) que necesita el reproductor.
Uso:  python serve-check.py      y abrir http://127.0.0.1:8899/webview-check.html (en Edge y dentro de una ventana WebView2)."""
import http.server
import socketserver
import sys
from pathlib import Path

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
ROOT = Path(__file__).resolve().parent


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(ROOT), **k)

    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *a):
        pass


with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), Handler) as srv:
    print(f"Sirviendo en http://127.0.0.1:{PORT}/webview-check.html  (Ctrl+C para cortar)")
    srv.serve_forever()
