#!/usr/bin/env python3
"""Mide al agente planificador contra las reglas: ¿entiende de un pedido escrito (30 pedidos etiquetados a mano en `plan_cases.json`) más que las reglas, y sin inventar?

Uso:  python3 plan_bench.py --url http://127.0.0.1:11601 --model gemma3:4b,gemma3:12b,qwen3:8b [--out resultados.json] [--rules-only]

Por campo (época, ánimo, instrumental, idioma, país, "lo fundamental", género, referencias) cuenta aciertos (TP), inventos o errores (FP) y faltantes (FN) y muestra
precisión y recall de: REGLAS (intent.py, genregate.detect y dos regex nuevas de época e instrumental), MODELO crudo (ya validado contra los vocabularios cerrados)
y REGLAS+MODELO (las reglas primero; el modelo solo llena donde ellas no vieron nada: así se integra en recs). También: segundos por pedido, JSON inválido y cuántos
valores descartó la validación. Los pedidos no tocan MusicBrainz: solo el modelo.
"""
import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
FIELDS = ("era", "mood", "instrumental", "language", "countries", "canon", "genres", "refs")


def key_set(field, v):
    """Valor -> conjunto comparable."""
    import genregate
    import intent

    if v in (None, [], False, ""):
        return set()
    if field == "genres":
        return {genregate.canon(x) for x in v}
    if field == "refs":
        return {intent._norm(x) for x in v}
    if field == "countries":
        return set(v)
    return {v if not isinstance(v, (list, tuple)) else tuple(v)}


def score_case(field, exp, pred, case):
    """(tp, fp, fn) de un campo en un pedido."""
    if field == "era":
        if pred is None:
            return (0, 0, 1) if exp else (0, 0, 0)
        if not exp:
            return 0, 1, 0
        tol = case.get("eraTol", 0)
        ok = abs(pred[0] - exp[0]) <= tol and abs(pred[1] - exp[1]) <= tol
        return (1, 0, 0) if ok else (0, 1, 1)
    if field == "mood":
        if pred is None:
            return (0, 0, 1) if exp else (0, 0, 0)
        return (1, 0, 0) if exp and pred in exp else (0, 1, 1 if exp else 0)
    if field in ("instrumental", "language"):
        if pred is None:
            return (0, 0, 1) if exp is not None else (0, 0, 0)
        return (1, 0, 0) if exp == pred else (0, 1, 1 if exp is not None else 0)
    if field == "canon":
        return (1, 0, 0) if exp and pred else (0, 1, 0) if pred else (0, 0, 1) if exp else (0, 0, 0)
    e, p = key_set(field, exp), key_set(field, pred)
    if field == "refs":  # una referencia vale si coincide o una contiene a la otra ("Charly García" ~ "charly garcia")
        hit = {x for x in p if any(x == y or x in y or y in x for y in e)}
        return len(hit), len(p) - len(hit), len([y for y in e if not any(x == y or x in y or y in x for x in p)])
    return len(e & p), len(p - e), len(e - p)


def pack(preds, cases):
    """{campo: {tp, fp, fn, precision, recall}}"""
    out = {}
    for f in FIELDS:
        tp = fp = fn = 0
        for case, pred in zip(cases, preds):
            exp = {"era": case["era"], "mood": case["mood"], "instrumental": case["instrumental"], "language": case["language"], "countries": case["countries"],
                   "canon": case["canon"], "genres": case["genres"], "refs": case["refs"]}[f]
            a, b, c = score_case(f, exp, pred.get(f), case)
            tp, fp, fn = tp + a, fp + b, fn + c
        out[f] = {"tp": tp, "fp": fp, "fn": fn, "precision": round(tp / (tp + fp), 2) if tp + fp else None, "recall": round(tp / (tp + fn), 2) if tp + fn else None}
    return out


def from_rules(text):
    import planner

    r = planner.rules_view(text)
    return {"era": r["era"], "instrumental": r["instrumental"], "countries": r["countries"], "canon": r["canon"], "genres": r["genres"]}


def from_plan(plan):
    return {"era": (plan["from"], plan["to"]) if plan["from"] is not None else None, "mood": plan["mood"], "instrumental": plan["instrumental"], "language": plan["language"],
            "countries": plan["countries"], "canon": plan["canon"], "genres": plan["genres"], "refs": plan["refs"]}


def fill_gaps(rules, model):
    """Las reglas primero; el modelo solo llena el campo si las reglas no vieron nada."""
    out = dict(model)
    for k, v in rules.items():
        if v not in (None, [], False):
            out[k] = v
    return out


def table(title, res):
    print(f"\n{title}")
    print(f"  {'campo':<13}{'TP':>4}{'FP':>4}{'FN':>4}{'precisión':>11}{'recall':>8}")
    for f in FIELDS:
        m = res[f]
        p = "-" if m["precision"] is None else f"{m['precision']:.2f}"
        r = "-" if m["recall"] is None else f"{m['recall']:.2f}"
        print(f"  {f:<13}{m['tp']:>4}{m['fp']:>4}{m['fn']:>4}{p:>11}{r:>8}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:11601")
    ap.add_argument("--model", default="gemma3:4b")
    ap.add_argument("--out", default="")
    ap.add_argument("--rules-only", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    os.environ.update(STEMSHED_MEMORY_DIR=tempfile.mkdtemp(prefix="plan-bench-"), STEMSHED_NO_SCHEDULER="1")
    spec = json.loads((HERE / "plan_cases.json").read_text())
    cases, prof = spec["cases"], spec["profile"]
    rules = [from_rules(c["text"]) for c in cases]
    result = {"cases": len(cases), "rules": pack(rules, cases)}
    table("REGLAS (intent + genregate.detect + regex de época e instrumental)", result["rules"])
    if args.rules_only:
        return
    import models
    import planner
    import recs

    models.configure(models.OLLAMA_MODELS, args.url)
    for model in [m.strip() for m in args.model.split(",") if m.strip()]:
        preds, secs, errors, dropped, briefs, rows = [], [], 0, 0, [], []
        for case in cases:
            t0 = time.time()
            try:
                plan, drop, _ = planner.run(lambda m, s, u, sc, t: recs._chat_json(m, s, u, sc, t, tries=1, num_predict=recs.PLAN_PREDICT), model, case["text"], prof)
            except Exception as e:
                errors += 1
                preds.append({})
                rows.append({"text": case["text"], "error": f"{type(e).__name__}: {e}"})
                print(f"  {model}: error {type(e).__name__} en «{case['text'][:40]}»", flush=True)
                continue
            secs.append(time.time() - t0)
            dropped += len(drop)
            briefs.append(len(plan["brief"]))
            preds.append(from_plan(plan))
            rows.append({"text": case["text"], "plan": plan, "dropped": drop, "seconds": round(time.time() - t0, 2)})
        raw, merged = pack(preds, cases), pack([fill_gaps(r, p) for r, p in zip(rules, preds)], cases)
        result[model] = {"raw": raw, "merged": merged, "errors": errors, "droppedByValidation": dropped, "secPerRequest": round(sum(secs) / len(secs), 2) if secs else None,
                         "maxSec": round(max(secs), 2) if secs else None, "briefChars": {"mean": round(sum(briefs) / len(briefs)) if briefs else None, "max": max(briefs, default=None),
                                                                                         "empty": sum(1 for b in briefs if b == 0)}, "rows": rows}
        table(f"MODELO {model} (crudo, ya validado)", raw)
        table(f"REGLAS + {model} (el modelo llena donde las reglas no vieron)", merged)
        print(f"  errores {errors} · descartado por la validación {dropped} · {result[model]['secPerRequest']} s por pedido (máx {result[model]['maxSec']}) · brief {result[model]['briefChars']}", flush=True)
        if args.verbose:
            for case, pred in zip(cases, preds):
                for f in FIELDS:
                    exp = {"era": case["era"], "mood": case["mood"], "instrumental": case["instrumental"], "language": case["language"], "countries": case["countries"],
                           "canon": case["canon"], "genres": case["genres"], "refs": case["refs"]}[f]
                    a, b, c = score_case(f, exp, pred.get(f), case)
                    if b or c:
                        print(f"    {f:<12} esperado {exp!s:<28} dio {pred.get(f)!s:<28} «{case['text'][:50]}»")
    if args.out:
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
