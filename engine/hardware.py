"""Detección de hardware y recomendación de modelos (solo lectura)."""
import os
import shutil
import subprocess
from pathlib import Path

# Catálogo de modelos locales candidatos. `gb` es el peso de la descarga; None = tamaño por confirmar.
# Nada se descarga solo: la interfaz recomienda y el usuario confirma. Hay que probar cada uno con un cuestionario musical.
CATALOG = [
    {"id": "mistral-nemo", "label": "Mistral Nemo 12B", "module": "recomendaciones", "gb": 7.1,
     "note": "General, multilingüe. Tamaño según una guía de terceros; falta probar cuánto sabe de música."},
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
    return out


def report(data_root, extra_paths=()):
    gpus = _gpus()
    disks = _disks(["/", str(Path.home()), str(data_root), *extra_paths])
    return {"gpus": gpus, "ram": _ram(), "cpu": _cpu(), "disks": disks,
            "models": recommend(gpus, disks, str(data_root))}
