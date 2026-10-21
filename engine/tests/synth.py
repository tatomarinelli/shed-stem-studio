"""Temas sintéticos con verdad conocida para probar analyze.py: acordes (síntesis aditiva), bajo, melodía y batería,
escritos como stems FLAC + manifest.json igual que la caché real. Solo numpy + soundfile (venv de separación).
"""
import json
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 22050
NOTE = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
        "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
QUAL = {"": (0, 4, 7), "m": (0, 3, 7), "7": (0, 4, 7, 10), "maj7": (0, 4, 7, 11), "m7": (0, 3, 7, 10),
        "m7b5": (0, 3, 6, 10), "dim": (0, 3, 6), "sus4": (0, 5, 7)}


def parse(label):
    root = label[:2] if len(label) > 1 and label[1] in "#b" else label[:1]
    return NOTE[root], label[len(root):]


def transpose_label(label, semis):
    root, q = parse(label)
    return SHARP_NAMES[(root + semis) % 12] + q


SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def tone(f, dur, partials=8, decay=3.0, bright=1.0, rng=None):
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for h in range(1, partials + 1):
        if f * h > SR / 2 - 500:
            break
        y += (bright / h) * np.sin(2 * np.pi * f * h * t + (rng.uniform(0, 6.28) if rng is not None else 0))
    env = np.exp(-decay * t) * np.minimum(1, t / 0.005)
    return y * env


def add(buf, start, y):
    i = int(start * SR)
    if i >= len(buf):
        return
    j = min(len(buf), i + len(y))
    buf[i:j] += y[: j - i]


def beat_times(bpm, n_beats, bpm_end=None):
    """Tiempos de pulso; con bpm_end el tempo cambia linealmente (accelerando/ritardando)."""
    times, t = [], 0.5
    for k in range(n_beats):
        times.append(t)
        b = bpm if bpm_end is None else bpm + (bpm_end - bpm) * k / max(1, n_beats - 1)
        t += 60.0 / b
    return np.array(times)


def make_song(folder, progression, bpm, beats_per_chord=4, repeats=4, bpm_end=None, swing=False,
              melody_scale=None, tonic=None, seed=0, walking=False, title="synth", transpose=0, silent=()):
    """progression: lista de etiquetas ("Dm7", "G7"...). Devuelve la verdad (acordes con tiempos, beats, downbeats).
    transpose: semitonos (la verdad devuelta ya viene transpuesta). silent: stems que se escriben mudos y marcados
    silent en el manifest (como un tema sin batería o sin bajo)."""
    if transpose:
        progression = [transpose_label(c, transpose) for c in progression]
        if tonic is not None:
            tonic = (tonic + transpose) % 12
    rng = np.random.default_rng(seed)
    labels = [c for _ in range(repeats) for c in progression]
    n_beats = len(labels) * beats_per_chord
    beats = beat_times(bpm, n_beats + 1, bpm_end)
    dur = beats[-1] + 1.5
    n = int(dur * SR)
    gtr, bass, drums, other = (np.zeros(n) for _ in range(4))
    truth = []
    for ci, lab in enumerate(labels):
        b0 = ci * beats_per_chord
        start, end = beats[b0], beats[b0 + beats_per_chord]
        truth.append({"start": float(start), "end": float(end), "label": lab})
        root, q = parse(lab)
        notes = [48 + ((root + iv) % 12) + (12 if (root + iv) % 12 < 4 else 0) for iv in QUAL[q]]
        for k in range(beats_per_chord):          # guitarra: un rasguido por pulso (comping)
            if k % 2 == 1 and rng.random() < 0.3:
                continue
            t0 = beats[b0 + k]
            for m in notes:
                add(gtr, t0 + rng.uniform(0, 0.015), 0.12 * tone(hz(m), beats[b0 + k + 1] - t0 + 0.05, decay=2.0, rng=rng))
        for k in range(beats_per_chord):          # bajo: fundamental en 1 y 3 (o caminando)
            t0 = beats[b0 + k]
            if walking:
                iv = [0, QUAL[q][1], QUAL[q][2], QUAL[q][1]][k % 4]
            elif k % 2 == 0:
                iv = 0 if k % 4 == 0 else QUAL[q][2] if rng.random() < 0.3 else 0
            else:
                continue
            m = 24 + ((root + iv) % 12) + (12 if (root + iv) % 12 < 4 else 0)
            span = beats[b0 + k + 1] - t0 if walking else beats[min(b0 + k + 2, len(beats) - 1)] - t0
            add(bass, t0, 0.35 * tone(hz(m), span, partials=5, decay=1.2, rng=rng))
        if melody_scale is not None:              # melodía: notas de la escala, más de acorde en los tiempos fuertes
            for k in range(beats_per_chord):
                t0 = beats[b0 + k]
                pool = [(root + iv) % 12 for iv in QUAL[q]] if k % 2 == 0 else [(tonic + iv) % 12 for iv in melody_scale]
                pc = int(rng.choice(pool))
                add(other, t0, 0.10 * tone(hz(72 + pc), beats[b0 + k + 1] - t0, partials=4, decay=1.5, rng=rng))
    for k in range(n_beats):                      # batería: bombo 1 y 3, redoblante 2 y 4, hi-hat en corcheas
        t0, t1 = beats[k], beats[k + 1]
        if k % 4 in (0, 2):
            tt = np.arange(int(0.25 * SR)) / SR
            add(drums, t0, 0.8 * np.sin(2 * np.pi * (50 + 80 * np.exp(-tt * 30)) * tt) * np.exp(-tt * 12))
        else:
            sn = rng.normal(0, 1, int(0.15 * SR)) * np.exp(-np.arange(int(0.15 * SR)) / SR * 25)
            add(drums, t0, 0.35 * sn)
        off = (t1 - t0) * (2 / 3 if swing else 0.5)
        for tt in (t0, t0 + off):
            hh = rng.normal(0, 1, int(0.04 * SR))
            hh = np.diff(hh, prepend=0) * np.exp(-np.arange(len(hh)) / SR * 120)
            add(drums, tt, 0.12 * hh)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    stems = {"guitar": gtr, "bass": bass, "drums": drums, "other": other}
    meta = []
    for name, y in stems.items():
        y = np.clip(y, -1, 1).astype(np.float32) * (0.0 if name in silent else 1.0)
        sf.write(folder / f"{name}.flac", y, SR)
        rms = 20 * np.log10(np.sqrt(np.mean(y ** 2)) + 1e-12)
        meta.append({"name": name, "file": f"{name}.flac", "rms_db": round(float(rms), 1), "silent": bool(rms < -60)})
    (folder / "manifest.json").write_text(json.dumps({"track_id": "synth", "title": title, "artist": "synth",
                                                      "duration": dur, "stems": meta}))
    return {"chords": truth, "beats": beats[:-1].tolist(), "downbeats": beats[:-1:4].tolist(), "duration": dur}


def chord_accuracy(truth, est, step=0.05, root_only=False):
    """Fracción del tiempo con acorde correcto (raíz+calidad, o solo raíz). Se compara contra la verdad por intervalos."""
    def at(segs, t):
        for s in segs:
            if s["start"] <= t < s["end"]:
                return s
        return None

    ok = tot = 0
    t = truth[0]["start"]
    while t < truth[-1]["end"]:
        tr, es = at(truth, t), at(est, t)
        if tr:
            tot += 1
            if es and es.get("root") is not None:
                r1, q1 = parse(tr["label"])
                r2 = NOTE[es["root"]]
                q2 = "" if es["quality"] == "maj" else es["quality"]
                ok += (r1 == r2) if root_only else (r1 == r2 and q1 == q2)
        t += step
    return ok / max(1, tot)


def beat_f1(ref, est, tol=0.07):
    ref, est = np.asarray(ref), np.asarray(est)
    if not len(ref) or not len(est):
        return 0.0
    hit = sum(np.min(np.abs(est - r)) <= tol for r in ref)
    p, r = hit / len(est), hit / len(ref)
    return 0 if p + r == 0 else 2 * p * r / (p + r)
