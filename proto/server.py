"""Servidor del prototipo: COOP/COEP (hilos y SharedArrayBuffer), stems de la caché en solo lectura y /report para volcar mediciones."""
import http.server, json, os, re, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = '/mnt/plexdata/tidal-stems/cache'
STEM_RE = re.compile(r'^/stems/(\d+)/(manifest\.json|peaks\.json|[a-z]+\.flac)$')

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def end_headers(self):
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def translate_path(self, path):
        m = STEM_RE.match(path.split('?')[0])
        if m:
            return os.path.join(CACHE, m.group(1), 'roformer', m.group(2))
        return super().translate_path(path)

    def do_POST(self):
        m = re.match(r'^/report/([\w.-]+)$', self.path)
        if not m:
            self.send_error(404); return
        body = self.rfile.read(int(self.headers.get('content-length', 0)))
        with open(os.path.join(ROOT, 'results', m.group(1) + '.json'), 'wb') as f:
            f.write(body)
        self.send_response(200); self.end_headers()

    def log_message(self, *a):
        pass

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    http.server.ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()
