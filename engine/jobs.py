"""Estado de las tareas largas (descargas, instalaciones): un diccionario por tarea que la interfaz consulta.

`updated` (epoch) cambia solo cuando avanzó algo de verdad (hecho, paso, porcentaje o estado), no en cada vuelta del vigía:
si deja de cambiar mientras la tarea figura "running", la interfaz avisa "sin novedades hace N s". Es una señal medida, no inventada.
"""
import time

WATCH = ("done", "step", "percent", "state")


def update(job, **fields):
    changed = any(job.get(k) != fields[k] for k in WATCH if k in fields)
    job.update(fields)
    if changed or "updated" not in job:
        job["updated"] = time.time()
    return job


def start(job, **fields):
    """Arranca una tarea: borra lo de la vez anterior y marca la hora de inicio."""
    job.clear()
    now = time.time()
    job.update(startedAt=now, updated=now)
    job.update(fields)
    return job


def public(job):
    """Copia para la interfaz, sin los campos internos (los que empiezan con _)."""
    return {k: v for k, v in job.items() if not k.startswith("_")}


def rate(job, done, now=None, min_dt=1.0):
    """Velocidad medida entre dos muestras de `done` (bytes). Queda en `rate`; con muy poco tiempo entre muestras no hace nada."""
    now = now if now is not None else time.time()
    last = job.get("_t")
    if last is None:
        job["_t"], job["_b"] = now, done
        return
    if now - last >= min_dt:
        job["rate"] = max(0, int((done - job["_b"]) / (now - last)))
        job["_t"], job["_b"] = now, done
