"""Detección de hardware y recomendación de modelos (solo lectura)."""
import os
import shutil
import subprocess
from pathlib import Path

# Catálogo de modelos locales candidatos. `gb` es el peso de la descarga (tamaño según ollama.com/library).
# Nada se descarga solo: la interfaz recomienda y el usuario confirma.
# `quiz` = aciertos del cuestionario musical (engine/eval/quiz.py, 46 respuestas); None = sin medir.
# Solo se marca "recomendado" un modelo que cabe en la GPU Y fue medido (el de mejor `quiz`).
# Ningún modelo probado es fiable como fuente de datos: proponen candidatos y siempre se verifica (docs/model-comparison.md).
CATALOG = [
    {"id": "mistral-nemo", "label": "Mistral Nemo 12B", "module": "recomendaciones", "gb": 7.1,
     "license": "Apache 2.0", "tested": True, "quiz": 36, "quizTotal": 46,
     "note": "Medido: 36/46 del cuestionario, 77 % de candidatos reales, ~106 tok/s. Inventa datos: solo para proponer y verificar."},
    {"id": "gemma3:12b", "label": "Gemma 3 12B", "module": "recomendaciones", "gb": 8.2,
     "license": "Gemma Terms of Use (restricciones de uso)", "tested": True, "quiz": 34, "quizTotal": 46,
     "note": "Medido: 34/46, 78 % de candidatos reales, propone más jazz/soul/funk pero repite. Solo para proponer y verificar."},
    {"id": "gemma3:27b", "label": "Gemma 3 27B", "module": "recomendaciones", "gb": 17.0,
     "license": "Gemma Terms of Use (restricciones de uso)", "tested": False, "quiz": None, "quizTotal": 46,
     "note": "Sin medir: probablemente sepa más por tamaño, pero no está comprobado (en las pruebas más parámetros no garantizaron más acierto)."},
    {"id": "qwen3:30b", "label": "Qwen3 30B (MoE)", "module": "recomendaciones", "gb": 19.0,
     "license": "Apache 2.0", "tested": False, "quiz": None, "quizTotal": 46,
     "note": "Sin medir. Qwen3 14B salió peor que Mistral Nemo en el cuestionario musical."},
]
VRAM_HEADROOM_GB = 2.0   # activaciones y contexto
SEPARATION_GB = 8.0      # VRAM que usa la separación con RoFormer (estimada): no coexiste con un modelo grande


def _gpus():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    gpus = []
    for line in out.strip().splitlines():
        name, total, used = [x.strip() for x in line.split(",")]
        gpus.append({"name": name, "vramGB": round(int(total) / 1024, 1), "usedGB": round(int(used) / 1024, 1)})
    return gpus


def _ram():
    info = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        k, v = line.split(":", 1)
        info[k] = int(v.split()[0]) / 1024 / 1024  # kB -> GB
    return {"totalGB": round(info["MemTotal"], 1), "availableGB": round(info["MemAvailable"], 1)}


def _cpu():
    name = ""
    for line in Path("/proc/cpuinfo").read_text().splitlines():
        if line.startswith("model name"):
            name = line.split(":", 1)[1].strip()
            break
    return {"name": name, "threads": os.cpu_count()}


def _disks(paths):
    seen, out = set(), []
    for p in paths:
        p = Path(p)
        if not p.exists():
            continue
        usage = shutil.disk_usage(p)
        key = (usage.total, usage.free)
        if key in seen:
            continue
        seen.add(key)
        out.append({"path": str(p), "totalGB": round(usage.total / 1e9), "freeGB": round(usage.free / 1e9),
                    "usedPct": round(100 * (1 - usage.free / usage.total))})
    return out


def recommend(gpus, disks, target_disk):
    free_vram = max((g["vramGB"] for g in gpus), default=0)
    free_disk = next((d["freeGB"] for d in disks if d["path"] == target_disk), 0)
    out = []
    for m in CATALOG:
        need = (m["gb"] or 0) + VRAM_HEADROOM_GB
        reasons = []
        if not gpus:
            reasons.append("No se detectó una GPU: correría en CPU, mucho más lento.")
        elif need > free_vram:
            reasons.append(f"Necesita unos {need:.0f} GB de VRAM y la GPU tiene {free_vram:.0f} GB.")
        if m["gb"] and m["gb"] * 1.2 > free_disk:
            reasons.append(f"Necesita unos {m['gb']:.0f} GB de disco y en {target_disk} quedan {free_disk} GB.")
        out.append({**m, "fits": not reasons, "reasons": reasons,
                    "withSeparation": bool(gpus) and (m["gb"] or 0) + SEPARATION_GB + VRAM_HEADROOM_GB <= free_vram})
    best = max((m for m in out if m["fits"] and m.get("tested")), key=lambda m: m.get("quiz") or 0, default=None)
    for m in out:
        m["recommended"] = m is best
        if m["fits"] and not m.get("tested"):
            m["reasons"] = m["reasons"] + ["Cabe en tu GPU, pero todavía no se midió cuánto sabe de música."]
    return out


def report(data_root, extra_paths=()):
    gpus = _gpus()
    disks = _disks(["/", str(Path.home()), str(data_root), *extra_paths])
    return {"gpus": gpus, "ram": _ram(), "cpu": _cpu(), "disks": disks,
            "models": recommend(gpus, disks, str(data_root))}
