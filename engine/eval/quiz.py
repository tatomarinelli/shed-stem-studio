#!/usr/bin/env python3
"""Cuestionario de música verificable para comparar modelos locales.

Uso:  python3 quiz.py --model gemma3:12b --runs 2 [--out ruta.json]
Corrección automática por regex sobre el texto normalizado (minúsculas, sin tildes).
`all`: todas deben aparecer; `none`: ninguna debe aparecer (anti falso positivo).
Trampas (kind=trap): se aprueba si el modelo admite que no conoce; si no, cuenta como alucinación.
Las respuestas dudosas se marcan en `review` y las revisa una persona (ver docs/model-comparison.md).
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import common  # noqa: E402

SYSTEM = ("Sos un experto en música. Respondé en español, en una o dos oraciones, de forma directa. "
          "Si no conocés el dato o no estás seguro de que algo existe, decilo claramente en lugar de inventar.")

# Q(id, tema, pregunta, respuesta esperada, regex all, regex none)
Q = [
    ("kob_year", "jazz", "¿En qué año se publicó el disco Kind of Blue de Miles Davis?", "1959", [r"1959"], []),
    ("kob_bass", "jazz", "¿Quién tocó el contrabajo en Kind of Blue de Miles Davis?", "Paul Chambers", [r"chambers"], []),
    ("kob_drums", "jazz", "¿Quién tocó la batería en Kind of Blue de Miles Davis?", "Jimmy Cobb", [r"cobb"], []),
    ("cantaloupe", "jazz", "¿En qué disco de Herbie Hancock aparece el tema Cantaloupe Island?", "Empyrean Isles (1964)", [r"empyrean"], []),
    ("headhunters", "jazz", "¿Qué disco de Herbie Hancock de 1973 incluye el tema Chameleon?", "Head Hunters", [r"head ?hunters"], []),
    ("bitches", "jazz", "¿Cómo se llama el disco doble de Miles Davis de 1970 considerado piedra fundacional del jazz fusión?", "Bitches Brew", [r"bitches brew"], []),
    ("giant", "jazz", "¿En qué año se publicó Giant Steps de John Coltrane?", "1960 (grabado en 1959)", [r"1960"], []),
    ("lovesup", "jazz", "¿En qué año se publicó A Love Supreme de John Coltrane?", "1965", [r"1965"], []),
    ("midnightblue", "jazz", "¿Qué saxofonista tenor toca en el disco Midnight Blue de Kenny Burrell?", "Stanley Turrentine", [r"turrentine"], []),
    ("greenlabel", "jazz", "¿En qué sello grabó Grant Green sus discos más conocidos de los 60, como Idle Moments?", "Blue Note", [r"blue note"], []),
    ("smokin", "jazz", "¿Qué pianista lideraba el trío que acompaña a Wes Montgomery en Smokin' at the Half Note?", "Wynton Kelly", [r"wynton kelly|kelly"], []),
    ("brightsize", "jazz", "¿Qué bajista toca en Bright Size Life, el primer disco de Pat Metheny como líder?", "Jaco Pastorius", [r"jaco|pastorius"], []),
    ("vanguard", "jazz", "¿Quién fue el contrabajista del trío de Bill Evans en Sunday at the Village Vanguard (1961)?", "Scott LaFaro", [r"lafaro"], []),
    ("takefive", "jazz", "¿En qué compás está escrito Take Five del Dave Brubeck Quartet?", "5/4", [r"5 4|cinco cuartos|5 por 4"], []),
    ("badu_debut", "gusto", "¿Cómo se llama el primer disco de estudio de Erykah Badu, de 1997?", "Baduizm", [r"baduizm"], []),
    ("badu_2008", "gusto", "¿Cómo se llama el disco de Erykah Badu de 2008 que empieza con New Amerykah?", "New Amerykah Part One (4th World War)", [r"4th world war|part one|parte uno|part 1|\(?4th"], []),
    ("hendrix_debut", "gusto", "¿Cuál fue el primer disco de The Jimi Hendrix Experience, de 1967?", "Are You Experienced", [r"are you experienced"], []),
    ("fela_genre", "gusto", "¿Qué género musical creó o popularizó Fela Kuti?", "Afrobeat", [r"afrobeat|afro beat"], []),
    ("sowhat_mode", "teoria", "¿En qué modo está basada la melodía principal de So What de Miles Davis?", "Dórico", [r"dorico|dorian|dorio"], [r"re menor"]),
    ("lydian", "teoria", "¿Qué modo se obtiene tocando una escala mayor empezando desde su cuarto grado?", "Lidio", [r"lidio|lydian"], []),
    ("mixolydian", "teoria", "¿Qué modo es una escala mayor con la séptima menor (bemol)?", "Mixolidio", [r"mixolidio|mixolydian"], []),
    ("ddorian", "teoria", "¿Cuántas alteraciones (sostenidos o bemoles) tiene la escala de Re dórico?", "Ninguna (son las notas blancas Re Mi Fa Sol La Si Do)", [r"ningun|cero|\b0\b|sin alteraciones|no tiene"], []),
    ("iivi", "teoria", "¿Qué acordes con séptima forman la progresión II-V-I en Do mayor?", "Dm7 - G7 - Cmaj7", [r"(dm7|re ?m(enor)? ?(7|con septima|septima))", r"(g7|sol ?(7|dominante|con septima))", r"(cmaj7|c ?maj ?7|c ?m?7 ?mayor|do ?(maj|mayor) ?7|do mayor con septima mayor|c△)"], []),
    # Trampas: no existen; la respuesta correcta es admitir que no lo conoce.
    ("trap_shorter", "trampa", "¿Qué temas tiene el disco Midnight Orchids de Wayne Shorter?", "No existe", [], []),
    ("trap_burrell", "trampa", "¿En qué año salió el disco Saturn Rooftops de Kenny Burrell y quién lo acompaña?", "No existe", [], []),
    ("trap_badu", "trampa", "¿De qué trata el disco Copper Lungs de Erykah Badu?", "No existe", [], []),
    ("trap_green", "trampa", "¿Qué músicos graban con Grant Green en su disco Amber Staircase de 1967?", "No existe", [], []),
    ("trap_artist", "trampa", "Contame sobre el guitarrista de jazz Marcelo Vanterpool Quintana y su disco Calle Seis.", "No existe", [], []),
]

ADMIT = re.compile(r"no (lo |la |los )?(conozco|tengo (informacion|datos|registro|constancia)|encuentro|existe|figura|hay (informacion|registro|datos)|"
                   r"estoy (seguro|al tanto)|cuento con|puedo (confirmar|verificar|encontrar)|sabria|se de|sé de|poseo|dispongo|tengo conocimiento|recuerdo|aparece)|"
                   r"desconozco|ficticio|inventado|no sabria|no estoy seguro|no pude encontrar|sin (datos|informacion) (sobre|de)")


def grade(item, text):
    kind = item[1]
    n = common.norm(text)
    if kind == "trampa":
        admitted = bool(ADMIT.search(n))
        # Admite pero luego inventa detalles (años, nombres de temas entre comillas, lista numerada): lo revisa una persona.
        suspicious = admitted and (len(text) > 350 or bool(re.search(r"\b(19|20)\d\d\b", text)) or "\n1." in text or '"' in text)
        return ("ok" if admitted and not suspicious else "alucina" if not admitted else "revisar"), admitted
    for rx in item[5]:
        if re.search(rx, n):
            return "mal", None
    if all(re.search(rx, n) for rx in item[4]):
        return "ok", None
    return "mal", None


def run(model, runs, out):
    results = []
    base = common.vram()
    for r in range(runs):
        for it in Q:
            msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": it[2]}]
            try:
                res = common.chat(model, msgs, temperature=0.2, seed=r + 1, num_predict=300)
            except Exception as e:   # noqa: BLE001
                res = {"content": "", "error": str(e), "tok_s": None, "seconds": None}
            verdict, _ = grade(it, res["content"])
            results.append({"run": r + 1, "id": it[0], "topic": it[1], "question": it[2], "expected": it[3],
                            "answer": res["content"], "auto": verdict, "tok_s": res.get("tok_s"),
                            "seconds": res.get("seconds"), "error": res.get("error")})
            print(f"[{model}] run{r+1} {it[0]:14s} {verdict}", flush=True)
    summary = summarize(results)
    data = {"model": model, "temperature": 0.2, "runs": runs, "system": SYSTEM, "vram": common.vram(),
            "vram_before": base, "summary": summary, "results": results}
    Path(out).write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(json.dumps(summary, ensure_ascii=False))


def summarize(results):
    real = [x for x in results if x["topic"] != "trampa"]
    trap = [x for x in results if x["topic"] == "trampa"]
    toks = [x["tok_s"] for x in results if x.get("tok_s")]
    return {"real_total": len(real), "real_ok": sum(x["auto"] == "ok" for x in real),
            "real_mal": sum(x["auto"] == "mal" for x in real),
            "trap_total": len(trap), "trap_ok": sum(x["auto"] == "ok" for x in trap),
            "trap_alucina": sum(x["auto"] == "alucina" for x in trap),
            "trap_revisar": sum(x["auto"] == "revisar" for x in trap),
            "tok_s_mean": round(sum(toks) / len(toks), 1) if toks else None}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--out")
    a = ap.parse_args()
    out = a.out or str(Path(__file__).resolve().parents[2] / "docs/agent-notes/model-eval-raw" /
                       f"quiz-{a.model.replace(':', '_').replace('/', '_')}.json")
    run(a.model, a.runs, out)
