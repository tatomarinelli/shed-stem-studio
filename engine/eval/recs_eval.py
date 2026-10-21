#!/usr/bin/env python3
"""Evalúa un modelo como proponedor de discos: existencia (MusicBrainz), afinidad de género, formato JSON, latencia, VRAM.

Uso:  python3 recs_eval.py --model gemma3:12b --runs 3
Lee (solo lectura) el campo `prompt` de ~/.config/stemshed/recs-last.json.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import common  # noqa: E402
import mb  # noqa: E402

LAST = Path.home() / ".config/stemshed/recs-last.json"
PROFILE = ("Músico que estudia su instrumento y quiere mejorar teoría y oído. "
           "Prefiere discos enteros y sacar temas de oído. Quiere discos que le enseñen algo y lo saquen un poco de su zona.")
SYSTEM = ("Sos un curador de música. " + PROFILE + " Respondé SOLO con JSON válido de esta forma: "
          '{"discos":[{"artista":"","disco":"","anio":0,"motivo":""}]}. '
          "Proponé 6 discos completos reales que probablemente no escuchó. 'anio' es el año de lanzamiento o null si no estás seguro. "
          "'motivo' es una sola frase en español rioplatense que mencione únicamente artistas o discos de la lista de gustos del usuario; "
          "NO afirmes datos del disco (músicos, modos, fechas, historia). Si no estás seguro de que un disco existe, no lo incluyas.")
AFFINE = ("jazz", "soul", "funk", "r&b", "rhythm and blues", "fusion", "bop")


def known_albums(prompt):
    m = re.search(r"Discos favoritos: (.*)", prompt)
    out = set()
    for part in (m.group(1).split(";") if m else []):
        if " - " in part:
            a, b = part.split(" - ", 1)
            out.add((common.norm(a), common.norm(b)))
    return out


def parse(content):
    try:
        data = json.loads(content)
    except Exception:   # noqa: BLE001
        return False, []
    items = data.get("discos") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return False, []
    out = []
    for it in items:
        if isinstance(it, dict) and it.get("artista") and it.get("disco"):
            y = it.get("anio")
            out.append({"artist": str(it["artista"]), "album": str(it["disco"]), "year": y if isinstance(y, int) else None,
                        "reason": str(it.get("motivo", ""))})
    return True, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--out")
    a = ap.parse_args()
    prompt = json.loads(LAST.read_text())["prompt"]
    known = known_albums(prompt)
    runs = []
    for r in range(a.runs):
        res = common.chat(a.model, [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
                          temperature=0.7, seed=100 + r, num_predict=900, fmt="json")
        v = common.vram()
        valid, items = parse(res["content"])
        for it in items:
            it["known"] = (common.norm(it["artist"]), common.norm(it["album"])) in known
            exists, year_ok, g = mb.match(it["artist"], it["album"], it["year"])
            lenient = mb.match_lenient(it["artist"], it["album"])
            it.update({"exists_lenient": bool(lenient), "mb_lenient": lenient, "exists": exists, "year_ok": year_ok, "mb": g, "genres": [], "affine": None})
            if exists:
                it["genres"] = mb.genres(g["mbid"])
                it["affine"] = any(any(k in x for k in AFFINE) for x in it["genres"]) if it["genres"] else None
        runs.append({"run": r + 1, "raw": res["content"], "json_valid": valid, "n_items": len(items), "items": items,
                     "seconds": res["seconds"], "load_s": res["load_s"], "tok_s": res["tok_s"], "eval_count": res["eval_count"],
                     "vram": v})
        print(f"[{a.model}] run{r+1}: valid={valid} items={len(items)} exist={sum(i['exists'] for i in items)} "
              f"tok/s={res['tok_s']} {res['seconds']}s", flush=True)
    allitems = [i for x in runs for i in x["items"]]
    n = len(allitems)
    ex = [i for i in allitems if i["exists"]]
    withg = [i for i in ex if i["genres"]]
    summary = {"candidates": n, "json_valid_runs": sum(x["json_valid"] for x in runs), "runs": a.runs,
               "exist_pct": round(100 * len(ex) / n, 1) if n else None,
               "exist_lenient_pct": round(100 * sum(i["exists_lenient"] for i in allitems) / n, 1) if n else None,
               "exist_year_ok_pct": round(100 * sum(i["exists"] and i["year_ok"] for i in allitems) / n, 1) if n else None,
               "with_genres": len(withg), "affine_pct_of_existing_with_genres": round(100 * sum(bool(i["affine"]) for i in withg) / len(withg), 1) if withg else None,
               "affine_pct_of_all": round(100 * sum(bool(i["affine"]) for i in allitems) / n, 1) if n else None,
               "already_known": sum(i["known"] for i in allitems),
               "unique_albums": len({(common.norm(i["artist"]), common.norm(i["album"])) for i in allitems}),
               "seconds_mean": round(sum(x["seconds"] for x in runs) / len(runs), 1),
               "tok_s_mean": round(sum(x["tok_s"] or 0 for x in runs) / len(runs), 1)}
    out = a.out or str(Path(__file__).resolve().parents[2] / "docs/agent-notes/model-eval-raw" / f"recs-{a.model.replace(':', '_')}.json")
    Path(out).write_text(json.dumps({"model": a.model, "system": SYSTEM, "summary": summary, "runs": runs}, ensure_ascii=False, indent=1))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
