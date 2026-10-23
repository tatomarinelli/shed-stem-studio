#!/usr/bin/env python3
"""Prueba de portadas al salir y volver a una pantalla (Chromium SIN ventana, vía uicheck.py). Falla si alguna portada queda cargada pero invisible.

Uso:  covercheck.py [URL] [--vueltas N]      (por defecto http://127.0.0.1:5173/#/recomendaciones y 12 idas y vueltas)

Por qué existe: con la imagen en la caché del navegador y la pantalla montándose de nuevo, el evento `load` se pierde y la portada quedaba con opacity 0 para siempre
(imagen bien, URL bien, nada en pantalla). Los tests del motor no lo ven. Mide, al terminar y 4 s después, cuántas portadas son visibles frente al total.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
JS = ('JSON.stringify((()=>{const i=[...document.querySelectorAll("main .cv img")];'
      'return {total:i.length,visibles:i.filter(x=>getComputedStyle(x).opacity==="1").length}})())')


def main():
    args = sys.argv[1:]
    laps = 12
    if "--vueltas" in args:
        k = args.index("--vueltas")
        laps = int(args[k + 1])
        del args[k:k + 2]
    url = args[0] if args else "http://127.0.0.1:5173/#/recomendaciones"
    steps = []
    for _ in range(laps):
        steps += ["--click", "Estudio", "--wait", "0.03", "--click", "Recomendaciones", "--wait", "0.03"]
    cmd = [sys.executable, os.path.join(HERE, "uicheck.py"), url, "--size", "1280x1500", "--wait", "3", *steps, "--wait", "1", "--eval", JS, "--wait", "4", "--eval", JS]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=240).stdout
    results = [json.loads(json.loads(m)) for m in re.findall(r'^=\s+(".*")\s*$', out, re.M)]
    if len(results) < 2:
        print("No pude leer el resultado de uicheck:\n" + out[-600:])
        return 2
    ok = True
    for label, r in zip(("al terminar", "4 s después"), results[-2:]):
        good = r["total"] > 0 and r["visibles"] == r["total"]
        ok &= good
        print(f"{label}: {r['visibles']} de {r['total']} portadas visibles {'OK' if good else 'FALLA'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
