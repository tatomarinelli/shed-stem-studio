"""Detección de hardware y recomendación de modelos (solo lectura)."""
import os
import osenv
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
PARTIAL_MAX = 1.5        # con Vulkan, un modelo hasta 1,5 veces la VRAM corre repartido entre placa y CPU (Mistral Nemo 12B en 8 GB: 82 % en placa, 19,8 tok/s contra 6,5 en CPU). Solo medido con Vulkan: con CUDA no cambia nada
SEPARATION_GB = 3.0      # VRAM de la separación con BS-Roformer-SW: pico medido de 2,7 GiB (clip de 90 s, 2026-10-21) + margen


def _nvidia_gpus():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    gpus = []
    for line in out.strip().splitlines():
        name, total, used = [x.strip() for x in line.split(",")]
        gpus.append({"name": name, "vendor": "nvidia", "accel": "cuda", "llmAccel": "cuda", "integrated": False,
                     "vramGB": round(int(total) / 1024, 1), "usedGB": round(int(used) / 1024, 1)})
    return gpus


def _gpus():
    """NVIDIA con nvidia-smi (aceleración CUDA); en Windows también AMD e Intel por DXGI.
    `accel` = separación: solo CUDA está verificada, las demás placas quedan en None (se asume CPU).
    `llmAccel` = modelos de recomendación con Ollama: CUDA en NVIDIA y Vulkan en AMD/Intel dedicadas (medido en una RX 6700S:
    88,8 tok/s contra 20,9 en CPU con llama3.2:3b); Ollama descarta las integradas."""
    gpus = _nvidia_gpus()
    for a in osenv.gpu_adapters():
        if a["vendor"] == "nvidia" and gpus:
            continue  # ya la dio nvidia-smi, con la VRAM usada
        llm = "cuda" if a["vendor"] == "nvidia" else ("vulkan" if a["vendor"] in ("amd", "intel") and not a["integrated"] else None)
        gpus.append({"name": a["name"], "vendor": a["vendor"], "accel": "cuda" if a["vendor"] == "nvidia" else None, "llmAccel": llm, "integrated": a["integrated"],
                     "vramGB": round(a["vramBytes"] / 1024**3, 1), "usedGB": None})
    return sorted(gpus, key=lambda g: (g["accel"] is None, g["integrated"], -g["vramGB"]))


def _ram():
    if osenv.WINDOWS:
        mem = osenv.ram_bytes()
        if mem:
            return {"totalGB": round(mem[0] / 1024 ** 3, 1), "availableGB": round(mem[1] / 1024 ** 3, 1)}
        return {"totalGB": 0, "availableGB": 0}
    info = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        k, v = line.split(":", 1)
        info[k] = int(v.split()[0]) / 1024 / 1024  # kB -> GB
    return {"totalGB": round(info["MemTotal"], 1), "availableGB": round(info["MemAvailable"], 1)}


def _cpu():
    if osenv.WINDOWS:
        return {"name": osenv.cpu_name(), "threads": os.cpu_count()}
    name = ""
    for line in Path("/proc/cpuinfo").read_text().splitlines():
        if line.startswith("model name"):
            name = line.split(":", 1)[1].strip()
            break
    return {"name": name, "threads": os.cpu_count()}


def _usage(path):
    """Espacio del disco donde está (o estaría) la ruta: sube hasta la primera carpeta que existe. None si no hay ninguna."""
    p = Path(path)
    for q in (p, *p.parents):
        if q.exists():
            return shutil.disk_usage(q)
    return None


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
    usable = [g for g in gpus if g.get("llmAccel", "cuda")]  # los modelos de recomendación usan la placa por CUDA o Vulkan; sin la clave (llamadas viejas) se asume CUDA
    best = max(usable, key=lambda g: g["vramGB"], default=None)
    partial_ok = bool(best) and best.get("llmAccel") == "vulkan"
    sep_gpu = any(g.get("accel", "cuda") for g in gpus)  # si la separación va por CPU no compite por la VRAM
    free_vram = max((g["vramGB"] for g in usable), default=0)
    free_disk = next((d["freeGB"] for d in disks if d["path"] == target_disk), None)
    if free_disk is None:  # la carpeta de datos todavía no existe: vale el disco donde se va a crear
        u = _usage(target_disk)
        free_disk = round(u.free / 1e9) if u else 0
    out = []
    for m in CATALOG:
        need = (m["gb"] or 0) + VRAM_HEADROOM_GB
        reasons = []
        if not gpus:
            reasons.append("No se detectó una GPU: correría en CPU, mucho más lento.")
        elif not usable:
            reasons.append(f"Con {gpus[0]['name']} no hay aceleración para estos modelos: correría en CPU, mucho más lento.")
        elif need > free_vram and not (partial_ok and (m["gb"] or 0) <= PARTIAL_MAX * free_vram):
            reasons.append(f"Necesita unos {need:.0f} GB de VRAM y la GPU tiene {free_vram:.0f} GB.")
        if m["gb"] and m["gb"] * 1.2 > free_disk:
            reasons.append(f"Necesita unos {m['gb']:.0f} GB de disco y en {target_disk} quedan {free_disk} GB.")
        partial = partial_ok and need > free_vram and not reasons
        out.append({**m, "fits": not reasons, "reasons": reasons, "partial": partial,
                    "withSeparation": bool(usable) and (not sep_gpu or (m["gb"] or 0) + SEPARATION_GB + VRAM_HEADROOM_GB <= free_vram)})
    best = max((m for m in out if m["fits"] and m.get("tested")), key=lambda m: m.get("quiz") or 0, default=None)
    for m in out:
        m["recommended"] = m is best
        if m["fits"] and not m.get("tested"):
            m["reasons"] = m["reasons"] + ["Cabe en tu GPU, pero todavía no se midió cuánto sabe de música."]
    return out


def report(data_root, extra_paths=()):
    gpus = _gpus()
    disks = _disks([Path.home().anchor or "/", str(Path.home()), str(data_root), *extra_paths])
    return {"gpus": gpus, "ram": _ram(), "cpu": _cpu(), "disks": disks,
            "models": recommend(gpus, disks, str(data_root))}
