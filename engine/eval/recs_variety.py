#!/usr/bin/env python3
"""Mide la variedad de las recomendaciones por perfil, en un entorno aislado.

Uso:  python3 recs_variety.py --runs 3 [--presets trabajo,descubrir] [--out ARCHIVO.json] [--context]

Aislamiento: copia la memoria real (solo lectura) a una carpeta temporal y apunta `STEMSHED_MEMORY_DIR` ahí; no copia la sesión de
TIDAL, no guarda resultados (save=False) y desactiva la tarea automática. Usa las fuentes en caché (sin red de TIDAL).
Por defecto no pide el contexto de Wikipedia (no afecta la variedad y gasta tiempo); `--context` lo activa.

Mide, sobre los discos que se le muestran al usuario (el recomendado + 3 alternativas): familia dominante, familias distintas,
tasa de verificación en MusicBrainz, repetidos entre corridas, violaciones de "evitar" y tiempo.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

REAL = Path.home() / ".config/stemshed"
COPY = ("profile.json", "presets.json", "taste.json", "events.jsonl", "sources.json", "memory.md", "reactions.json")

# Familia = primer género del disco (MusicBrainz los ordena por votos) que cae en alguna de estas listas.
FAMILIES = [
    ("reggae/dub", ("reggae", "dub", "ska", "dancehall", "roots")),
    ("jazz", ("jazz", "bop", "swing", "big band", "bossa")),
    ("funk/soul/r&b", ("funk", "soul", "r&b", "rhythm and blues", "disco", "groove")),
    ("hip hop", ("hip hop", "rap", "trip hop")),
    ("electrónica", ("electronic", "house", "techno", "ambient", "downtempo", "idm", "electro", "synth", "broken beat", "trance")),
    ("rock/indie", ("rock", "punk", "grunge", "metal", "indie", "alternative", "psychedelic", "shoegaze", "new wave", "surf")),
    ("folk/acústico", ("folk", "acoustic", "singer-songwriter", "country", "bluegrass", "blues")),
    ("latino/mundo", ("latin", "samba", "tango", "cumbia", "salsa", "afro", "world", "ethio", "tropic", "mpb", "bolero")),
    ("pop", ("pop",)),
    ("clásica", ("classical", "orchestral", "baroque", "opera")),
]


def family_of(genres):
    for g in genres or []:
        low = g.lower()
        for name, keys in FAMILIES:
            if any(k in low for k in keys):
                return name
    return "sin familia"


def all_families(genres):
    out = set()
    for g in genres or []:
        low = g.lower()
        for name, keys in FAMILIES:
            if any(k in low for k in keys):
                out.add(name)
    return out


def setup(tmp):
    for name in COPY:
        src = REAL / name
        if src.exists():
            shutil.copy2(src, tmp / name)
    os.environ["STEMSHED_MEMORY_DIR"] = str(tmp)
    os.environ["STEMSHED_NO_SCHEDULER"] = "1"
    os.environ["STEMSHED_SAVE_DRYRUN"] = "1"


def summarize(rows):
    """rows: [{preset, run, shown:[{artist, album, genres}], stats, seconds, violations}]"""
    out = {"byPreset": {}, "overall": {}}
    every = []
    for pid in dict.fromkeys(r["preset"] for r in rows):
        rs = [r for r in rows if r["preset"] == pid and not r.get("error")]
        shown = [a for r in rs for a in r["shown"]]
        fams = [family_of(a["genres"]) for a in shown]
        per_run_top = []
        per_run_distinct = []
        for r in rs:
            f = [family_of(a["genres"]) for a in r["shown"]]
            if f:
                per_run_top.append(max(f.count(x) for x in set(f)) / len(f))
                per_run_distinct.append(len(set(f)))
        keys = [(a["artist"], a["album"]) for a in shown]
        out["byPreset"][pid] = {
            "runs": len(rs), "errors": sum(1 for r in rows if r["preset"] == pid and r.get("error")),
            "albums": len(shown), "uniqueAlbums": len(set(keys)),
            "topFamilyShare": round(sum(per_run_top) / len(per_run_top), 2) if per_run_top else None,
            "distinctFamilies": round(sum(per_run_distinct) / len(per_run_distinct), 2) if per_run_distinct else None,
            "families": {f: fams.count(f) for f in sorted(set(fams), key=lambda x: -fams.count(x))},
            "verifiedRate": round(sum(r["stats"]["verifiedRate"] for r in rs) / len(rs), 2) if rs else None,
            "avoidViolations": sum(r["violations"] for r in rs),
            "secondsPerRun": round(sum(r["seconds"] for r in rs) / len(rs), 1) if rs else None,
            "noPick": sum(1 for r in rs if not r["shown"]),
        }
        every += shown
    fams = [family_of(a["genres"]) for a in every]
    ok = [r for r in rows if not r.get("error")]
    out["overall"] = {
        "albums": len(every), "uniqueAlbums": len({(a["artist"], a["album"]) for a in every}),
        "families": {f: fams.count(f) for f in sorted(set(fams), key=lambda x: -fams.count(x))},
        "topFamilyShare": round(max(fams.count(f) for f in set(fams)) / len(fams), 2) if fams else None,
        "verifiedRate": round(sum(r["stats"]["verifiedRate"] for r in ok) / len(ok), 2) if ok else None,
        "avoidViolations": sum(r["violations"] for r in ok),
    }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--presets", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--context", action="store_true", help="pedir también el contexto de Wikipedia")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="recs-variety-"))
    setup(tmp)
    import recs  # después de fijar las variables de entorno

    if not args.context:
        recs.albumctx.get = lambda *a, **k: None
    model = recs.choose_model()
    sources = recs.cached_sources()
    data = recs.load_presets()
    ids = [p["id"] for p in data["presets"]]
    if args.presets:
        want = args.presets.split(",")
        ids = [i for i in ids if i in want]
    prof_avoid = {p["id"]: [a for a in p.get("avoid", []) if len(recs.norm(a).split()) <= 3] for p in data["presets"]}
    out_path = Path(args.out) if args.out else tmp / "result.json"
    print(f"modelo={model} fuentes={len(sources)} perfiles={ids} corridas={args.runs} carpeta={tmp}", flush=True)

    rows = []
    for pid in ids:
        for n in range(args.runs):
            t0 = time.time()
            row = {"preset": pid, "run": n}
            try:
                res = recs.run(model, "daily", {"presetId": pid}, sources=sources, save=False)
                picks = [p for p in [res["pick"]] + (res["alternatives"] or []) if p]
                avoid = [recs.norm(a) for a in prof_avoid[pid]] + [recs.norm(a) for a in recs.profile_mod.load(recs.PROFILE).get("avoids", [])
                                                                    if len(recs.norm(a).split()) <= 3]
                viol = sum(1 for p in picks if any(a and any(a in recs.norm(g) for g in p["genres"]) for a in avoid))
                row.update(shown=[{"artist": p["artist"], "album": p["album"], "genres": p["genres"]} for p in picks],
                           stats=res["stats"], seconds=round(time.time() - t0, 1), violations=viol,
                           tokens=res["stats"]["promptTokens"])
            except Exception as e:
                row.update(error=f"{type(e).__name__}: {e}", seconds=round(time.time() - t0, 1))
            rows.append(row)
            shown = ", ".join(f"{a['artist']} - {a['album']} [{family_of(a['genres'])}]" for a in row.get("shown", []))
            print(f"{pid} #{n}: {row.get('error') or shown} ({row['seconds']} s)", flush=True)
            out_path.write_text(json.dumps({"model": model, "rows": rows, "summary": summarize(rows)}, ensure_ascii=False, indent=1))
    print(json.dumps(summarize(rows), ensure_ascii=False, indent=1))
    print("resultado:", out_path)


if __name__ == "__main__":
    main()
