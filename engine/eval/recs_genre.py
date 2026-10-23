#!/usr/bin/env python3
"""Mide si los pedidos por género devuelven discos del género pedido, con un modelo local y MusicBrainz reales.

Uso:  python3 recs_genre.py --url http://127.0.0.1:11600 [--model mistral-nemo] [--genres dub,bossa\\ nova] [--runs 1]
                            [--loose] [--type album] [--out ARCHIVO.json]

Aislamiento: perfil SINTÉTICO (no toca ni copia tus datos), memoria en una carpeta temporal, sin fuentes de TIDAL, sin guardar
resultados y sin contexto de Wikipedia. Consulta MusicBrainz de verdad (1 consulta por segundo): mantené los sets chicos.

Criterios ("funcional"): 0 discos fuera de género entre los mostrados (con --strict), todos existen en MusicBrainz, un disco por
artista, al menos 3 de 4 con mbid verificado, y los segundos por corrida. No mide "mejor que TIDAL/YouTube": solo adherencia y costo.
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

DEFAULT = ["dub", "bossa nova", "post-rock", "modal jazz", "afrobeat", "shoegaze", "bebop", "ambient"]
PROFILE = {"instrument": "guitarra", "level": "intermedio", "improve": ["oido"], "loves": ["jazz", "funk", "reggae"], "avoids": [],
           "essentials": ["Miles Davis", "Bob Marley"], "ownArtists": [], "discovery": "algo", "listening": "discos"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:11600")
    ap.add_argument("--model", default="", help="uno solo; o varios separados por coma para compararlos (deben estar instalados: acá no se baja nada)")
    ap.add_argument("--genres", default=",".join(DEFAULT))
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--loose", action="store_true", help="género flexible (no estricto)")
    ap.add_argument("--type", default="")
    ap.add_argument("--prompts", default="", help="pedidos SIN género, separados por |  (p. ej. 'estudiar:|sorprenderme:|libre:algo tranquilo')")
    ap.add_argument("--method", default="artistas", choices=("artistas", "discos"), help="cómo genera: el modelo propone artistas o discos")
    ap.add_argument("--classifier", default="off", choices=("off", "llm", "kev"), help="verificador complementario para los discos que la barrera deja cercanos")
    ap.add_argument("--kev-url", default="http://127.0.0.1:8009")
    ap.add_argument("--reviewer", default="off", help="agente revisor: off | same | nombre de un modelo")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="recs-genre-"))
    os.environ.update(STEMSHED_MEMORY_DIR=str(tmp), STEMSHED_NO_SCHEDULER="1", STEMSHED_SAVE_DRYRUN="1")
    import genregate
    import models
    import recs

    models.configure(models.OLLAMA_MODELS, args.url)
    recs.ARTISTS_FIRST = args.method == "artistas"
    real_load = recs.settings.load
    recs.settings.load = lambda: {**real_load(), "classifier": args.classifier, "classifierUrl": args.kev_url, "recsReviewer": args.reviewer}
    recs.albumctx.get = lambda *a, **k: None
    recs.profile_mod.save(recs.PROFILE, dict(PROFILE))
    tags = models.ollama_tags()
    if tags is None:
        sys.exit(f"No responde un servidor de modelos en {args.url}")
    installed = [m["name"] for m in tags]
    chosen = [m.strip() for m in args.model.split(",") if m.strip()] or [recs.pick_chat_model(tags, "")]
    missing = [m for m in chosen if m not in installed]
    if missing:
        sys.exit(f"No están instalados: {', '.join(missing)}. Instalados: {', '.join(installed)}. Bajalos desde Ajustes.")
    wants = [g.strip() for g in args.genres.split(",") if g.strip()] if not args.prompts else []
    free = [x.strip() for x in args.prompts.split("|") if x.strip()]
    out_path = Path(args.out) if args.out else tmp / "result.json"
    print(f"modelos={chosen} generos={wants} corridas={args.runs} estricto={not args.loose} carpeta={tmp}", flush=True)

    jobs = [(g, {"genres": [g], "strict": not args.loose}) for g in wants]
    for x in free:  # "modo:texto"
        mode, _, text = x.partition(":")
        jobs.append((x, {k: v for k, v in (("mode", mode.strip() or None), ("prompt", text.strip())) if v}))
    rows = []

    def one(model, g, req, n):
        t0 = time.time()
        if args.type:
            req = {**req, "type": args.type}
        row = {"model": model, "genre": g, "run": n}
        try:
            res = recs.run(model, "request", recs.clean_request(req), sources=[], save=False)
            picks = [p for p in [res["pick"]] + (res["alternatives"] or []) if p]
            seconds = round(time.time() - t0, 1)
            # Chequeo independiente de la barrera: géneros del ARTISTA en MusicBrainz (otra consulta, otro dato).
            indep = []
            for p in picks:
                if not req.get("genres"):
                    indep.append("n/a")
                    continue
                ag = recs.mb_artist_genres(p["artist"])
                indep.append(genregate.judge([g], p["genres"], ag)["status"] if (p["genres"] or ag) else "unknown")
            st = res["stats"]
            row.update(shown=[{"artist": p["artist"], "album": p["album"], "year": p["year"], "genres": p["genres"],
                               "gate": (p.get("genre") or {}).get("status"), "review": ((p.get("trail") or {}).get("review") or {}).get("fit")} for p in picks], independent=indep,
                       seconds=seconds, rounds=st["rounds"], proposed=st["proposed"], verified=st["verified"],
                       discardedBy=st["discardedBy"], modelSeconds=st["modelSeconds"], verifySeconds=st.get("verifySeconds"),
                       tokens=st["promptTokens"], vramGB=vram_gb())
        except Exception as e:
            row.update(error=f"{type(e).__name__}: {e}", seconds=round(time.time() - t0, 1))
        rows.append(row)
        if row.get("error"):
            print(f"{model} | {g} #{n}: ERROR {row['error']} ({row['seconds']} s)", flush=True)
        else:
            shown = "; ".join(f"{a['artist']} - {a['album']} [{', '.join(a['genres'][:2]) or '-'}|{a['gate']}{'|rev:' + a['review'] if a.get('review') else ''}]" for a in row["shown"])
            print(f"{model} | {g} #{n}: {len(row['shown'])} discos en {row['seconds']} s, {row['rounds']} rondas, {row['proposed']} propuestos, "
                  f"descartes {row['discardedBy']}, VRAM {row['vramGB']} GB\n    {shown}", flush=True)
        out_path.write_text(json.dumps({"models": chosen, "rows": rows, "summary": by_model(rows)}, ensure_ascii=False, indent=1))

    for model in chosen:
        for g, req in jobs:
            for n in range(args.runs):
                one(model, g, req, n)
    print(json.dumps(by_model(rows), ensure_ascii=False, indent=1))
    log = recs.classify.log_read(recs.CLASSIFIER_LOG)
    if log:
        print(f"\nveredictos del clasificador ({len(log)}):")
        for e in log:
            print(f"  {e['value']}: {e['mbid'][:8]} gate={e['gate']} -> {e['to'] or 'sin cambio'}  p={e['p']}")
    print("resultado:", out_path)


def by_model(rows):
    models_ = list(dict.fromkeys(r["model"] for r in rows))
    return {m: summarize([r for r in rows if r["model"] == m]) for m in models_}


def vram_gb():
    """VRAM en uso ahora (GB, nvidia-smi); None si no hay GPU NVIDIA. Con el modelo ya cargado es lo que ocupa (más lo de otros procesos)."""
    import subprocess

    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5).stdout
        return round(int(out.split()[0]) / 1024, 1)
    except Exception:
        return None


def summarize(rows):
    ok = [r for r in rows if not r.get("error")]
    shown = [a for r in ok for a in r["shown"]]
    return {
        "runs": len(rows), "errors": len(rows) - len(ok), "albums": len(shown),
        "offGenreShown": sum(1 for a in shown if a["gate"] not in ("match", "weak", None)),
        "weakShown": sum(1 for a in shown if a["gate"] == "weak"),
        "independentOff": sum(1 for r in ok for s in r["independent"] if s == "off"),
        "runsWith4": sum(1 for r in ok if len(r["shown"]) >= 4), "runsWith3plus": sum(1 for r in ok if len(r["shown"]) >= 3),
        "emptyRuns": sum(1 for r in ok if not r["shown"]),
        "secondsPerRun": round(sum(r["seconds"] for r in ok) / len(ok), 1) if ok else None,
        "vramGB": max((r["vramGB"] for r in ok if r.get("vramGB")), default=None),
        "discardedBy": {k: sum(r["discardedBy"].get(k, 0) for r in ok) for k in sorted({k for r in ok for k in r["discardedBy"]})},
    }


if __name__ == "__main__":
    main()
