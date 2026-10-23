"""Cuánto tarda una búsqueda y cómo cambia cada variable. Se mide en cada corrida real y se estima con la mediana de las últimas;
sin historial alcanza se usan valores de referencia (medidos con mistral-nemo en una RTX 5080) y se avisa que son estimados.

Funciones puras sobre una lista de corridas; el archivo (<dataDir>/recs/timings.json) lo lee y escribe recs.py.
"""
import statistics

KEEP = 30
MIN_RUNS = 2
# Referencia (segundos): modelo local, MusicBrainz (artistas + discos, caché fría) y contexto de Wikipedia por disco.
DEFAULT = {"model": 4.0, "musicbrainz": 22.0, "context": 12.0, "extraRound": 18.0}


def entry(result):
    """Lo que se guarda de una corrida terminada (sin cancelar)."""
    st = result["stats"]
    if st.get("cancelled"):
        return None
    return {"method": st.get("method"), "genre": bool(st.get("genres")), "rounds": st.get("rounds"), "proposed": st.get("proposed"),
            "model": st.get("modelSeconds"), "musicbrainz": max(0.0, (st.get("verifySeconds") or 0) - 0.0), "context": st.get("contextSeconds") or 0.0,
            "total": st.get("seconds"), "contextMode": "now" if st.get("contextSeconds") else "demand"}


def add(runs, e):
    return ([*runs, e] if e else list(runs))[-KEEP:]


def _med(values, default):
    vals = [v for v in values if isinstance(v, (int, float))]
    return round(statistics.median(vals), 1) if vals else default


def estimate(runs, genre=False, context="demand"):
    """{total, parts: {model, musicbrainz, context}, basis}. `genre` = pedido con género (más rondas); `context` = 'now' o 'demand'."""
    same = [r for r in runs if r.get("genre") == genre and r.get("method") == "artistas"]
    measured = len(same) >= MIN_RUNS
    pool = same if measured else []
    model = _med([r["model"] for r in pool], DEFAULT["model"])
    # verifySeconds ya incluye lo que tardó el modelo en esa ronda: se separa para no sumarlo dos veces.
    mb = _med([max(0.0, r["musicbrainz"] - r["model"]) for r in pool], DEFAULT["musicbrainz"])
    ctx_runs = [r["context"] for r in runs if r.get("context")]
    ctx = _med(ctx_runs, DEFAULT["context"]) if context == "now" else 0.0
    parts = {"model": model, "musicbrainz": mb, "context": ctx}
    return {"total": round(sum(parts.values())), "parts": parts,
            "basis": f"medido en {len(same)} búsquedas tuyas" if measured else "estimado (todavía sin historial propio)"}
