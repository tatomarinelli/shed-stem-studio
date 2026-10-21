"""Utilidades compartidas de la evaluación de modelos (solo librería estándar)."""
import json
import re
import subprocess
import time
import unicodedata
import urllib.request

OLLAMA = "http://127.0.0.1:11500"   # instancia propia; nunca el servicio del sistema (11434)
UA = "ShedStemStudio/0.0.1 (prototipo local)"


def norm(text):
    t = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def chat(model, messages, temperature=0.2, seed=None, num_predict=400, fmt=None, keep_alive="10m",
         retries=3, timeout=300, think=False):
    """Devuelve dict con content, seconds, eval_count, tok_s, load_s. Reintenta ante timeouts/errores."""
    opts = {"temperature": temperature, "num_predict": num_predict}
    if seed is not None:
        opts["seed"] = seed
    body = {"model": model, "stream": False, "messages": messages, "options": opts, "keep_alive": keep_alive}
    if think is not None and model.startswith("qwen3"):
        body["think"] = think          # Qwen3 razona por defecto; lo apagamos para medir respuesta directa
    if fmt:
        body["format"] = fmt
    last = None
    for attempt in range(retries):
        try:
            t0 = time.time()
            req = urllib.request.Request(OLLAMA + "/api/chat", json.dumps(body).encode(),
                                         {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.load(r)
            sec = time.time() - t0
            ec = d.get("eval_count") or 0
            ed = (d.get("eval_duration") or 0) / 1e9
            return {"content": d["message"]["content"], "seconds": round(sec, 2), "eval_count": ec,
                    "tok_s": round(ec / ed, 1) if ed else None,
                    "load_s": round((d.get("load_duration") or 0) / 1e9, 2),
                    "prompt_tokens": d.get("prompt_eval_count")}
        except Exception as e:   # noqa: BLE001
            last = e
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"fallo tras {retries} intentos: {last!r}")


def vram():
    """VRAM total en uso (nvidia-smi, MiB) y la que Ollama dice tener cargada para el modelo (bytes de /api/ps)."""
    out = {"nvidia_used_mib": None, "ollama_ps": []}
    try:
        out["nvidia_used_mib"] = int(subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10).stdout.strip().splitlines()[0])
    except Exception:   # noqa: BLE001
        pass
    try:
        with urllib.request.urlopen(OLLAMA + "/api/ps", timeout=10) as r:
            out["ollama_ps"] = [{"model": m["name"], "size_gb": round(m["size"] / 1e9, 2),
                                 "size_vram_gb": round(m.get("size_vram", 0) / 1e9, 2)}
                                for m in json.load(r).get("models", [])]
    except Exception:   # noqa: BLE001
        pass
    return out


def unload(model):
    """Descarga el modelo de la VRAM (keep_alive 0) para medir de a uno."""
    body = {"model": model, "keep_alive": 0, "messages": []}
    try:
        req = urllib.request.Request(OLLAMA + "/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=60).read()
    except Exception:   # noqa: BLE001
        pass
