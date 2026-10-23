#!/usr/bin/env python3
"""Mide al agente revisor: ¿distingue lo que encaja con el modo 'concentrarme' de lo que claramente no? 32 discos etiquetados (`review_cases.json`).

Uso:  python3 review_bench.py --url http://127.0.0.1:11601 --model gemma3:4b,qwen3:8b [--genres] [--batch 8]

Veredicto 'si' = encaja; 'dudoso' y 'no' cuentan como "no encaja". Mide exactitud, cuántos de los que NO encajan baja (recall) y cuántos de los
que encajan deja pasar. `--genres` le pasa los géneros (como los tendría de MusicBrainz); sin eso solo ve artista, disco y año.
"""
import argparse
import json
import os
import random
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:11601")
    ap.add_argument("--model", default="gemma3:4b")
    ap.add_argument("--genres", action="store_true")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    os.environ.update(STEMSHED_MEMORY_DIR=tempfile.mkdtemp(prefix="review-bench-"), STEMSHED_NO_SCHEDULER="1")
    import models
    import recs
    import reviewer

    models.configure(models.OLLAMA_MODELS, args.url)
    spec = json.loads((HERE / "review_cases.json").read_text())
    cases = spec["cases"][:]
    random.Random(args.seed).shuffle(cases)
    result = {}
    for model in [m.strip() for m in args.model.split(",") if m.strip()]:
        rows, secs, errors = [], [], 0
        for i in range(0, len(cases), args.batch):
            chunk = cases[i:i + args.batch]
            items = [{"n": k + 1, "artist": c["artist"], "album": c["album"], "year": c["year"], "genres": c["genres"] if args.genres else []} for k, c in enumerate(chunk)]
            t0 = time.time()
            try:
                verdicts, _ = reviewer.review(lambda m, s, u, sc, t: recs._chat_json(m, s, u, sc, t, num_predict=400), model, {}, spec["mode"], [], items)
            except Exception as e:
                errors += 1
                print(f"  {model}: error {type(e).__name__} {e}", flush=True)
                continue
            secs.append(time.time() - t0)
            for k, c in enumerate(chunk):
                v = verdicts.get(k + 1)
                rows.append({**c, "fit": v["fit"] if v else None, "issue": v["issue"] if v else None})
        answered = [r for r in rows if r["fit"]]
        pred_yes = lambda r: r["fit"] == "si"
        acc = sum(pred_yes(r) == (r["label"] == "yes") for r in answered) / len(answered) if answered else None
        no = [r for r in answered if r["label"] == "no"]
        yes = [r for r in answered if r["label"] == "yes"]
        m = {"answered": len(answered), "of": len(cases), "errors": errors, "accuracy": round(acc, 3) if acc is not None else None,
             "lowersTheBad": round(sum(not pred_yes(r) for r in no) / len(no), 3) if no else None,
             "keepsTheGood": round(sum(pred_yes(r) for r in yes) / len(yes), 3) if yes else None,
             "secPerBatch": round(sum(secs) / len(secs), 2) if secs else None}
        result[model] = {"metrics": m, "rows": rows}
        print(f"{model:<14} {'con géneros' if args.genres else 'sin géneros'}: {json.dumps(m)}", flush=True)
        for r in answered:
            if pred_yes(r) != (r["label"] == "yes"):
                print(f"    falla: {r['label']:<3} → {r['fit']:<6} {r['issue']:<12} {r['artist']} - {r['album']}", flush=True)
    if args.out:
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
