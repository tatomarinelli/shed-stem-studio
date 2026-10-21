#!/usr/bin/env python3
"""Verifica la interfaz con un Chromium SIN ventana (headless) y clics reales por CDP.

Uso:
  uicheck.py URL [--wait S] [--click "texto del botón o selector CSS"]... [--text "selector CSS"] [--eval "js"] [--shot ruta.png]

Los pasos se ejecutan en el orden dado. --click acepta texto visible de un botón/enlace o un selector CSS (si empieza con . # [ ).
--text imprime el texto visible de ese selector (por defecto body). Siempre imprime errores de consola/excepciones.
Ejemplo: uicheck.py "http://127.0.0.1:5173/#/musica" --wait 3 --click "Temas" --text main
"""
import argparse, base64, json, os, shutil, socket, struct, subprocess, sys, tempfile, time, urllib.request


class WS:
    def __init__(self, url):
        host, port = url.split('/')[2].split(':'); path = '/' + url.split('/', 3)[3]
        self.s = socket.create_connection((host, int(port)), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.send(f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n".encode())
        self.s.recv(4096); self.i = 0; self.events = []

    def _send(self, o):
        d = json.dumps(o).encode(); m = os.urandom(4); n = len(d)
        h = bytes([0x81]) + (bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack('>H', n) if n < 65536 else bytes([0x80 | 127]) + struct.pack('>Q', n)) + m
        self.s.sendall(h + bytes(b ^ m[i % 4] for i, b in enumerate(d)))

    def _recv(self):
        def rd(n):
            b = b''
            while len(b) < n: b += self.s.recv(n - len(b))
            return b
        h = rd(2); n = h[1] & 127
        if n == 126: n = struct.unpack('>H', rd(2))[0]
        elif n == 127: n = struct.unpack('>Q', rd(8))[0]
        return json.loads(rd(n))

    def call(self, method, params=None):
        self.i += 1; self._send({'id': self.i, 'method': method, 'params': params or {}})
        while True:
            r = self._recv()
            if r.get('id') == self.i: return r.get('result', r.get('error'))
            if r.get('method'): self.events.append(r)

    def ev(self, js):
        r = self.call('Runtime.evaluate', {'expression': js, 'returnByValue': True, 'awaitPromise': True})
        return r.get('result', {}).get('value') if 'result' in r else r


CLICK = """(t)=>{const css=/^[.#\\[]/.test(t);let el;if(css)el=document.querySelector(t);else{const all=[...document.querySelectorAll('button,a,summary,[role=tab],label')];
el=all.find(e=>e.textContent.trim()===t)||all.find(e=>e.textContent.trim().includes(t));}
if(!el)return 'NO ENCONTRADO: '+t;el.click();return 'clic en: '+(el.textContent||el.tagName).trim().slice(0,60)}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('url'); ap.add_argument('--wait', type=float, default=2)
    ap.add_argument('--click', action='append', default=[]); ap.add_argument('--text', action='append', default=[])
    ap.add_argument('--eval', action='append', default=[]); ap.add_argument('--shot')
    ap.add_argument('--size', help='ancho x alto de la ventana, por ejemplo 390x800 (celular)')
    ap.add_argument('--steps-wait', type=float, default=1.2, help='espera tras cada clic')
    a = ap.parse_args()
    prof = tempfile.mkdtemp(prefix='uicheck-'); port = 9400 + os.getpid() % 500
    exe = shutil.which('chromium') or 'chromium'
    proc = subprocess.Popen([exe, '--headless=new', '--no-sandbox', f'--user-data-dir={prof}', f'--remote-debugging-port={port}',
                             '--autoplay-policy=no-user-gesture-required', '--window-size=1400,1000', 'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try: tabs = json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/json')); break
            except Exception: time.sleep(0.2)
        ws = WS([t for t in tabs if t['type'] == 'page'][0]['webSocketDebuggerUrl'])
        ws.call('Runtime.enable'); ws.call('Page.enable')
        if a.size:
            w, h = (int(x) for x in a.size.lower().split('x')); ws.call('Emulation.setDeviceMetricsOverride', {'width': w, 'height': h, 'deviceScaleFactor': 1, 'mobile': w < 700})
        ws.call('Page.navigate', {'url': a.url}); time.sleep(a.wait)
        for t in a.click:
            print('>', ws.ev(f"({CLICK})({json.dumps(t)})")); time.sleep(a.steps_wait)
        for js in a.eval:
            print('= ', json.dumps(ws.ev(js), ensure_ascii=False)[:2000]); time.sleep(a.steps_wait)
        for sel in (a.text or ['body']):
            print(f'--- texto de {sel} ---'); print((ws.ev(f"(document.querySelector({json.dumps(sel)})||{{}}).innerText||''") or '').strip()[:6000])
        if a.shot:
            open(a.shot, 'wb').write(base64.b64decode(ws.call('Page.captureScreenshot', {'format': 'png'})['data'])); print('captura:', a.shot)
        errs = [e for e in ws.events if e['method'] in ('Runtime.exceptionThrown',) or (e['method'] == 'Runtime.consoleAPICalled' and e['params']['type'] == 'error')]
        for e in errs[:10]:
            p = e['params']; print('ERROR CONSOLA:', json.dumps(p.get('exceptionDetails', {}).get('exception', {}).get('description') or [x.get('value') for x in p.get('args', [])], ensure_ascii=False)[:300])
        print('errores de consola:', len(errs))
    finally:
        proc.terminate(); shutil.rmtree(prof, ignore_errors=True)


main()
