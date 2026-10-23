"""Diversidad de lo que se muestra: de los discos ya verificados y puntuados se eligen los que se muestran con MMR (relevancia máxima marginal).

El primero es siempre el de mayor puntaje. Cada siguiente maximiza  lam * puntaje - (1 - lam) * parecido con lo ya elegido,  así no salen tres discos
casi iguales (medido: pedir "bebop" mostró 3 discos "jazz, hard bop"). El parecido es de géneros (sin contar el género pedido, que todos comparten)
y de década. Funciones puras. `lam = 1` desactiva la diversidad.
"""


def _decade(v):
    return v["year"] // 10 if isinstance(v.get("year"), int) else None


def similarity(a, b, ignore=()):
    """0-1: 0,7 por géneros en común (Jaccard, sin los de `ignore`) + 0,3 por la misma década."""
    ga = {g for g in (a.get("genres") or [])[:4] if g not in ignore}
    gb = {g for g in (b.get("genres") or [])[:4] if g not in ignore}
    jac = len(ga & gb) / len(ga | gb) if ga | gb else 0.0
    da, db = _decade(a), _decade(b)
    return round(0.7 * jac + 0.3 * (1.0 if da is not None and da == db else 0.0), 4)


def diversify(items, k=4, lam=0.7, ignore=(), tier=lambda v: 0):
    """Los `k` que se muestran, en orden. `tier(v)` menor va antes (p. ej. los del género exacto antes que los "cercanos"): un nivel no se
    mezcla con el siguiente hasta agotarse. Devuelve (elegidos, resto); cada elegido lleva `diversity` = su mayor parecido con los anteriores."""
    pool = sorted(items, key=lambda v: -v["score"])
    chosen = []
    while pool and len(chosen) < k:
        level = min(tier(v) for v in pool)
        cand = [v for v in pool if tier(v) == level]
        penalty = lambda v: max((similarity(v, c, ignore) for c in chosen), default=0.0)
        best = max(cand, key=lambda v: (lam * v["score"] - (1 - lam) * penalty(v), v["score"]))
        pool.remove(best)
        chosen.append({**best, "diversity": round(penalty(best), 2)})
    return chosen, pool


def spread(items, ignore=()):
    """Variedad media de un conjunto: 1 - parecido medio entre pares (0 = todos iguales, 1 = todos distintos)."""
    pairs = [(a, b) for i, a in enumerate(items) for b in items[i + 1:]]
    return round(1 - sum(similarity(a, b, ignore) for a, b in pairs) / len(pairs), 3) if pairs else None
