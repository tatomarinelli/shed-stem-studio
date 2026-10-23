#!/usr/bin/env python3
"""Compara verificadores de género de texto (¿la descripción del disco lo sostiene como del género X?) sobre casos ETIQUETADOS.

Uso:
  python3 clf_bench.py --fetch-only                       # baja y guarda las descripciones de Wikipedia (una vez)
  python3 clf_bench.py --backends llm,kev-noul,kev-choice --ollama http://127.0.0.1:11600 --kev http://127.0.0.1:8009

Casos: `clf_cases.json` (54, etiquetados a mano; revisalos). Evidencia = las primeras oraciones del artículo de Wikipedia, como en la app
(`albumctx.sentences`). Mide por backend: exactitud con umbral 0,5 y con el mejor umbral, AUROC, Brier, ECE, exactitud en los casos difíciles
(géneros vecinos) y latencia. No toca tus datos; la red es solo Wikipedia (no MusicBrainz) y los servidores locales.
"""
import argparse
import json
import math
import statistics
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
CASES = HERE / "clf_cases.json"
CACHE = Path("/mnt/plexdata/stemshed/eval/clf-extracts.json")
SENT, LIMIT = 2, 360   # cuánta descripción se le da (como el resumen de la app); --sent 0 = el extracto completo (hasta 2500 caracteres)


def fetch_extracts():
    import albumctx

    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    cases = json.loads(CASES.read_text())["cases"]
    for c in cases:
        key = f"{c['artist']}|{c['album']}"
        if key in cache and (cache[key]["found"] or not cache[key]["errors"]):
            continue  # un "no hay" solo se recuerda si Wikipedia contestó; un fallo de red/límite se vuelve a pedir
        for attempt in range(4):
            errors = []
            art = albumctx.find_article(c["artist"], c["album"], errors)
            if art or not errors:
                break
            time.sleep(8 * (attempt + 1))  # Wikipedia limita las ráfagas
        cache[key] = {"found": bool(art), "extract": (art or {}).get("extract", ""), "url": (art or {}).get("url", ""), "errors": errors}
        print(("ok  " if art else ("NO? " if errors else "NO  ")) + key, flush=True)
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
    return cache


def usable(cache):
    import albumctx

    out = []
    for c in json.loads(CASES.read_text())["cases"]:
        e = cache.get(f"{c['artist']}|{c['album']}")
        if e and e["found"] and e["extract"]:
            out.append({**c, "desc": albumctx.sentences(e["extract"], SENT, LIMIT) if SENT else e["extract"]})
    return out


def premise_of(c):
    import classify

    classify.DESC_MAX = max(classify.DESC_MAX, LIMIT if SENT else 2500)
    return classify.premise(c["artist"], c["album"], None, [], (), {"text": c["desc"], "source": "wikipedia"})[0]


def post(url, body, timeout=120):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def backend_llm(args):
    import classify
    import models

    models.configure(models.OLLAMA_MODELS, args.ollama)
    be = classify.LlmBackend(models.chat, args.model, guard=not args.no_guard)
    return lambda c: be.nli(premise_of(c), classify.hypothesis("genre", c["genre"]))["entailment"]


def backend_kev(args, kind):
    def call(c):
        g = c["genre"]
        if kind == "noul":
            q = {"type": "noul", "instructions": f'Does the description show that this album belongs to the genre "{g}"?'}
        else:
            q = {"type": "choice", "instructions": "Which genre does the description say this album belongs to?",
                 "criteria": {g: f"The album belongs to the genre {g}", "other": "The album belongs to a different genre"}}
        ans = post(args.kev.rstrip("/") + "/v1/systemone", {"state": premise_of(c), "model": "kev-latest", "questions": {"q": q}})["answers"]["q"]
        return ans["noul"] if kind == "noul" else ans["probabilities"][g]
    return call


def auroc(scores, labels):
    pos = [s for s, y in zip(scores, labels) if y]
    neg = [s for s, y in zip(scores, labels) if not y]
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def ece(scores, labels, bins=10):
    tot = 0.0
    for b in range(bins):
        idx = [i for i, s in enumerate(scores) if b / bins <= s < (b + 1) / bins or (b == bins - 1 and s == 1.0)]
        if idx:
            tot += len(idx) / len(scores) * abs(sum(labels[i] for i in idx) / len(idx) - sum(scores[i] for i in idx) / len(idx))
    return tot


def metrics(rows):
    ok = [r for r in rows if r["p"] is not None]
    s, y = [r["p"] for r in ok], [1 if r["label"] == "yes" else 0 for r in ok]
    acc = lambda thr, ids: (sum((s[i] >= thr) == bool(y[i]) for i in ids) / len(ids)) if ids else None
    allid = list(range(len(ok)))
    best = max(((acc(t / 20, allid), t / 20) for t in range(1, 20)), default=(None, None))
    hard = [i for i, r in enumerate(ok) if r.get("hard")]
    lat = [r["sec"] for r in ok]
    return {"n": len(ok), "errors": len(rows) - len(ok), "acc@0.5": round(acc(0.5, allid), 3), "acc@best": round(best[0], 3), "bestThr": best[1],
            "auroc": round(auroc(s, y), 3), "brier": round(sum((a - b) ** 2 for a, b in zip(s, y)) / len(y), 3), "ece": round(ece(s, y), 3),
            "hardAcc@0.5": round(acc(0.5, hard), 3) if hard else None, "p50Sec": round(statistics.median(lat), 2) if lat else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch-only", action="store_true")
    ap.add_argument("--backends", default="llm")
    ap.add_argument("--ollama", default="http://127.0.0.1:11600")
    ap.add_argument("--model", default="mistral-nemo:latest")
    ap.add_argument("--kev", default="http://127.0.0.1:8009")
    ap.add_argument("--sent", type=int, default=2, help="oraciones de evidencia (0 = extracto completo)")
    ap.add_argument("--limit", type=int, default=360, help="caracteres máximos de las oraciones")
    ap.add_argument("--no-guard", action="store_true", help="el backend llm sin la guarda de 'el género tiene que estar en la premisa'")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    global SENT, LIMIT
    SENT, LIMIT = args.sent, args.limit
    cache = fetch_extracts()
    if args.fetch_only:
        print(f"{sum(1 for e in cache.values() if e['found'])} de {len(cache)} con artículo")
        return
    cases = usable(cache)
    print(f"{len(cases)} casos con descripción ({sum(c['label'] == 'yes' for c in cases)} sí, {sum(c['label'] == 'no' for c in cases)} no)", flush=True)
    result = {}
    for name in [b.strip() for b in args.backends.split(",") if b.strip()]:
        fn = {"llm": lambda: backend_llm(args), "kev-noul": lambda: backend_kev(args, "noul"), "kev-choice": lambda: backend_kev(args, "choice")}[name]()
        rows = []
        for c in cases:
            t0 = time.time()
            try:
                p = float(fn(c))
            except Exception as e:
                p = None
                print(f"  {name}: error en {c['artist']} - {c['album']}: {type(e).__name__} {e}", flush=True)
            rows.append({"artist": c["artist"], "album": c["album"], "genre": c["genre"], "label": c["label"], "hard": c.get("hard", False),
                         "p": p, "sec": round(time.time() - t0, 3)})
        result[name] = {"metrics": metrics(rows), "rows": rows}
        print(name, json.dumps(result[name]["metrics"]), flush=True)
        bad = [r for r in rows if r["p"] is not None and (r["p"] >= 0.5) != (r["label"] == "yes")]
        for r in bad:
            print(f"    falla: {r['genre']:<10} {r['label']:<3} p={r['p']:.2f}  {r['artist']} - {r['album']}", flush=True)
    if args.out:
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
