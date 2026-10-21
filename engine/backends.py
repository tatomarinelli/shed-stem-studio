"""Motores de separación (backends): cuál conviene según el hardware y cuáles se pueden instalar hoy.

El asistente muestra la recomendación; el usuario confirma con un clic y recién ahí se descarga algo (envsetup).
Solo es "instalable" lo que existe de verdad: un archivo de requisitos probado. Lo demás se muestra como "Próximamente",
con el motivo, y nunca se ofrece instalar. Análisis completo y evidencia: docs/backends-separacion.md.
"""
import re
from pathlib import Path

import osenv

HERE = Path(__file__).parent

# `verified`: dónde se probó de punta a punta (instalar, separar un tema). Windows: nada todavía.
CATALOG = [
    {"id": "cuda", "label": "Placa NVIDIA (CUDA)", "approxGb": 8, "installable": True,
     "requirements": {"windows": "requirements-env.win-nvidia.txt", "other": "requirements-env.txt"},
     "verified": {"other": True, "windows": False}, "requires": "Requiere NVIDIA",
     "about": "Separa en la placa de video. Es lo más rápido."},
    {"id": "cpu", "label": "Procesador (CPU)", "approxGb": 1.1, "installable": True,
     "requirements": {"windows": "requirements-env.win-cpu.txt", "other": "requirements-env.txt"},
     "verified": {"other": False, "windows": False},
     "about": "Funciona en cualquier equipo, pero separar un tema tarda mucho más (unos 16 s por trozo en un Ryzen 9 6900HS: ≈ 19 min para 5 min de música, estimado)."},
    {"id": "directml", "label": "DirectML (AMD, Intel y NVIDIA en Windows)", "approxGb": None, "installable": False, "windowsOnly": True,
     "about": "Usa cualquier placa compatible con DirectX 12 sin controladores especiales. Falta convertir el modelo a ONNX "
              "(existe para Demucs; no para BS-Roformer) y escribir ese camino de separación."},
    {"id": "rocm", "label": "AMD (ROCm)", "approxGb": None, "installable": False, "requires": "Requiere AMD",
     "about": "En Windows, PyTorch oficial con ROCm figura solo para placas AMD recientes (RX 7000 y 9000, según fuentes de terceros)."},
]
RECENT_AMD = re.compile(r"\bRX\s*(7|9)\d{3}\b", re.I)


def _key():
    return "windows" if osenv.WINDOWS else "other"


def by_id(backend_id):
    return next((b for b in CATALOG if b["id"] == backend_id), None)


def requirements_for(backend_id):
    """Archivo de requisitos del motor, o None si no se puede instalar."""
    b = by_id(backend_id)
    if not b or not b["installable"]:
        return None
    return HERE / b["requirements"][_key()]


def compatible(backend_id, gpus):
    """¿Este equipo puede usar ese motor? CUDA necesita una NVIDIA; ROCm, una AMD dedicada; el resto, cualquiera."""
    if backend_id == "cuda":
        return any(g.get("vendor") == "nvidia" for g in gpus)
    if backend_id == "rocm":
        return any(g.get("vendor") == "amd" and not g.get("integrated") for g in gpus)
    return True


def recommended_id(gpus):
    """NVIDIA con CUDA -> cuda; todo lo demás -> cpu (hasta que haya un camino acelerado verificado)."""
    return "cuda" if any(g.get("accel") == "cuda" for g in gpus) else "cpu"


def _why(b, gpus):
    """Texto específico de este equipo para una opción que todavía no se ofrece."""
    non_nv = [g for g in gpus if g.get("vendor") in ("amd", "intel")]
    names = ", ".join(g["name"] for g in non_nv if not g.get("integrated")) or ", ".join(g["name"] for g in non_nv)
    if b["id"] == "directml" and non_nv:
        return f"Podría usar {names}. Próximamente: todavía no se puede instalar."
    if b["id"] == "rocm" and any(g.get("vendor") == "amd" for g in gpus):
        amd = [g["name"] for g in gpus if g.get("vendor") == "amd" and not g.get("integrated")]
        recent = any(RECENT_AMD.search(n) for n in amd)
        return (f"{amd[0]} parece de una generación reciente: podría servir, sin verificar y todavía sin camino de instalación." if recent and amd
                else f"{(amd or ['Tu placa AMD'])[0]} no figura entre las placas con PyTorch oficial para Windows.")
    return b["about"]


def report(gpus):
    """Lo que devuelve GET /engine/backends: opciones, cuál se recomienda y por qué."""
    rec = recommended_id(gpus)
    gpu = next((g for g in gpus if not g.get("integrated")), gpus[0] if gpus else None)
    options = []
    for b in CATALOG:
        if b.get("windowsOnly") and not osenv.WINDOWS:
            continue
        verified = b.get("verified", {}).get(_key(), False)
        options.append({"id": b["id"], "label": b["label"], "approxGb": b["approxGb"], "installable": b["installable"],
                        "compatible": compatible(b["id"], gpus), "requires": b.get("requires"),
                        "recommended": b["id"] == rec, "verified": verified,
                        "note": _why(b, gpus) if not b["installable"] else b["about"]})
    reason = f"Detectado: {gpu['name']}" if gpu else "Sin placa de video"
    return {"recommended": rec, "reason": reason, "gpu": gpu["name"] if gpu else None, "options": options}
