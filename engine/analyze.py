"""Análisis musical de un tema separado en stems: tonalidad (con modo), tempo con grilla de pulsos y compases, y acordes.

Corre en el venv de separación (numpy, scipy, soundfile, soxr, librosa), solo con CPU:

    analyze.py <carpeta_stems> [--out archivo.json] [--track-id ID] [variantes...]

La carpeta tiene {guitar,bass,drums,piano,vocals,other}.flac y manifest.json. Escribe el resultado en JSON (formato
"version": 1, ver docs/analysis.md) por stdout o en --out, y el progreso en stderr como líneas "PROGRESS <etapa> <pct>".

Idea: los stems suman la mezcla, así que cada tarea usa lo que mejor la informa. El pulso sale de batería + bajo, la
armonía de guitarra + piano + otros (las voces fuera por defecto: meten melodía), y la fundamental de los acordes del
stem de bajo. Todo es estimación: los modos y los compases en especial.
"""
import os

# Límites de hilos y nada de GPU ANTES de importar numpy/numba (otros procesos usan la máquina).
for _var in ("NUMBA_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_var, "8")
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ.setdefault("NUMBA_CACHE_DIR", os.path.join(os.environ.get("STEMSHED_DATA", "/mnt/plexdata/stemshed"), "tmp", "numba"))

import argparse  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
import soxr  # noqa: E402

VERSION = 1
SR = 22050
HOP = 512                 # onsets / pulso (23 ms)
CHOP = 2048               # croma (93 ms)
STEMS = ("guitar", "bass", "drums", "piano", "vocals", "other")

SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
ES = {"C": "Do", "D": "Re", "E": "Mi", "F": "Fa", "G": "Sol", "A": "La", "B": "Si"}

# Modos: intervalos desde la tónica. "major"/"minor" son jónico/eólico, se nombran como mayor/menor.
MODES = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "minor": (0, 2, 3, 5, 7, 8, 10),
    "harmonicMinor": (0, 2, 3, 5, 7, 8, 11),
}
MODE_ES = {"major": "mayor", "minor": "menor", "dorian": "dórico", "phrygian": "frigio", "lydian": "lidio",
           "mixolydian": "mixolidio", "harmonicMinor": "menor armónico"}
MODE_HELP = {
    "major": "escala mayor (jónico)",
    "minor": "menor natural (eólico): 3ra, 6ta y 7ma menores",
    "dorian": "menor con 6ta mayor (dórico): suena menos triste que el menor natural",
    "phrygian": "menor con 2da menor (frigio)",
    "lydian": "mayor con 4ta aumentada (lidio)",
    "mixolydian": "mayor con 7ma menor (mixolidio): típico de blues, funk y rock",
    "harmonicMinor": "menor con 7ma mayor (menor armónico): el V es dominante",
}
# Desde qué grado de la escala mayor sale cada modo (para elegir bemoles o sostenidos según la armadura).
MODE_DEGREE = {"major": 0, "dorian": 2, "phrygian": 4, "lydian": 5, "mixolydian": 7, "minor": 9, "harmonicMinor": 9}
FLAT_MAJORS = {5, 10, 3, 8, 1, 6}  # F Bb Eb Ab Db Gb

# Calidades de acorde (intervalos) y sufijo.
QUALITIES = [
    ("", (0, 4, 7)), ("m", (0, 3, 7)), ("7", (0, 4, 7, 10)), ("maj7", (0, 4, 7, 11)), ("m7", (0, 3, 7, 10)),
    ("m7b5", (0, 3, 6, 10)), ("dim", (0, 3, 6)), ("sus4", (0, 5, 7)),
]
# Sesgo a lo simple: una tríada gana si la 7ma no tiene energía real.
QUALITY_PRIOR = {"": 0.03, "m": 0.03, "7": 0.0, "maj7": -0.01, "m7": 0.0, "m7b5": -0.03, "dim": -0.05, "sus4": -0.04}


BACKBEAT_MIN = 0.3   # alternancia mínima del redoblante para creerle al contratiempo
PARITY_MAX = 0.45     # por debajo, uno de cada dos pulsos es un contratiempo débil -> estamos al doble
CHG = float(os.environ.get("STEMSHED_CHG", "4.0"))         # costo (nats) de cambiar de acorde fuera del 1 y el 3
CHG_DOWN = float(os.environ.get("STEMSHED_CHG_DOWN", "0.25"))  # factor del costo en el 1 del compás
CHG_HALF = float(os.environ.get("STEMSHED_CHG_HALF", "0.5"))   # factor en el 3
BETA = float(os.environ.get("STEMSHED_BETA", "25"))
RARE_MODE_PENALTY = float(os.environ.get("STEMSHED_RARE", "0.05"))  # frigio, lidio y menor armónico: menos comunes
W_FIRST = float(os.environ.get("STEMSHED_WFIRST", "0.2"))  # peso de la fundamental del primer compás como tónica
SNARE_HZ = float(os.environ.get("STEMSHED_SNARE_HZ", "4000"))


def progress(stage, pct):
    print(f"PROGRESS {stage} {int(pct)}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------- carga

def load_mono(path, sr=SR, block=SR * 20):
    """Lee un FLAC por bloques, lo pasa a mono y lo remuestrea a `sr` sin cargar el estéreo entero en memoria."""
    out = []
    with sf.SoundFile(str(path)) as f:
        rs = soxr.ResampleStream(f.samplerate, sr, 1, dtype="float32", quality="HQ") if f.samplerate != sr else None
        while True:
            data = f.read(block, dtype="float32", always_2d=True)
            last = len(data) < block
            mono = data.mean(axis=1).astype(np.float32)
            out.append(rs.resample_chunk(mono, last=last) if rs else mono)
            if last:
                break
    return np.concatenate(out) if out else np.zeros(0, np.float32)


def read_manifest(folder):
    try:
        return json.loads((Path(folder) / "manifest.json").read_text())
    except (OSError, ValueError):
        return {}


def available_stems(folder, manifest):
    silent = {s["name"] for s in manifest.get("stems", []) if s.get("silent")}
    return {n: Path(folder) / f"{n}.flac" for n in STEMS if (Path(folder) / f"{n}.flac").exists() and n not in silent}


# ---------------------------------------------------------------- utilidades

def norm01(x):
    x = np.asarray(x, dtype=np.float64)
    hi = np.percentile(x, 99) if x.size else 0
    return np.clip(x / hi, 0, 1.5) if hi > 1e-9 else np.zeros_like(x)


def spell(pc, flats):
    return (FLAT if flats else SHARP)[pc % 12]


def spanish(name):
    base = ES[name[0]]
    if len(name) > 1:
        base += " bemol" if name[1] == "b" else " sostenido"
    return base


def key_uses_flats(tonic, mode):
    major_pc = (tonic - MODE_DEGREE.get(mode, 0)) % 12
    return major_pc in FLAT_MAJORS


def fold_chroma(C, freqs, tuning_hz_ratio=1.0):
    """CQT (magnitud) -> croma de 12 clases con compresión logarítmica."""
    midi = 69 + 12 * np.log2(freqs / (440.0 * tuning_hz_ratio))
    pcs = np.round(midi).astype(int) % 12
    E = np.log1p(30 * C / (C.max() + 1e-12))
    out = np.zeros((12, C.shape[1]))
    for pc in range(12):
        out[pc] = E[pcs == pc].sum(axis=0)
    return out


def harmonic_template(intervals, partials=6, decay=0.6):
    """Plantilla de acorde que cuenta los armónicos de cada nota (la 3ra armónica de la 3ra cae en la 7ma, etc.)."""
    t = np.zeros(12)
    for iv in intervals:
        for h in range(1, partials + 1):
            t[(iv + int(round(12 * np.log2(h)))) % 12] += decay ** (h - 1)
    return t / np.linalg.norm(t)


# ---------------------------------------------------------------- pulso

NFFT = 2048


def mel_chunked(y, librosa, n_mels=64, fmin=0.0, fmax=None, chunk_frames=2048):
    """Igual que librosa.feature.melspectrogram (center=True, relleno con ceros) pero por tramos de ~47 s: la STFT de
    un tema de 15 min entera pesa cientos de MB; así el pico de memoria queda acotado."""
    fb = librosa.filters.mel(sr=SR, n_fft=NFFT, n_mels=n_mels, fmin=fmin, fmax=fmax or SR / 2).astype(np.float32)
    ypad = np.pad(y.astype(np.float32, copy=False), (NFFT // 2, NFFT // 2))
    total = 1 + len(y) // HOP
    out = np.empty((n_mels, total), dtype=np.float32)
    win = np.hanning(NFFT + 1)[:-1].astype(np.float32)  # periódica, como scipy.signal.get_window("hann")
    for a in range(0, total, chunk_frames):
        b = min(total, a + chunk_frames)
        seg = ypad[a * HOP: (b - 1) * HOP + NFFT]
        if len(seg) < (b - a - 1) * HOP + NFFT:
            seg = np.pad(seg, (0, (b - a - 1) * HOP + NFFT - len(seg)))
        frames = np.lib.stride_tricks.sliding_window_view(seg, NFFT)[::HOP][: b - a]
        spec = np.abs(np.fft.rfft(frames * win, axis=1)).astype(np.float32) ** 2
        out[:, a:b] = fb @ spec.T
    return out


def onset_env(y, librosa, fmax=None, fmin=None):
    if y is None or not np.any(y):
        return None
    S = mel_chunked(y, librosa, n_mels=64, fmin=fmin or 0.0, fmax=fmax or SR / 2)
    return librosa.onset.onset_strength(S=librosa.power_to_db(S, ref=np.max), sr=SR, hop_length=HOP)


def per_frame_chunked(fn, env, size=6000, pad=800):
    """Aplica fn(tramo) -> (..., cuadros) por tramos con solapamiento y pega solo el centro de cada uno. Así los
    tempogramas de un tema largo no ocupan cientos de MB de una vez."""
    parts = []
    for a in range(0, len(env), size):
        lo, hi = max(0, a - pad), min(len(env), a + size + pad)
        r = fn(env[lo:hi])
        parts.append(r[..., a - lo: a - lo + min(size, len(env) - a)])
    return np.concatenate(parts, axis=-1)


def mean_chunked(fn, env, size=6000):
    total, n = None, 0
    for a in range(0, len(env), size):
        seg = env[a:a + size]
        if len(seg) < 200 and n:
            break
        r = fn(seg)
        total = r.sum(axis=-1) if total is None else total + r.sum(axis=-1)
        n += r.shape[-1]
    return total / max(1, n)


def tempo_candidates(env, librosa):
    """Autocorrelación del tempograma: puntaje por BPM (sin prior) para decidir octava."""
    ac = mean_chunked(lambda e: librosa.feature.tempogram(onset_envelope=e, sr=SR, hop_length=HOP, win_length=768), env)
    tg = None
    bpms = librosa.tempo_frequencies(len(ac), sr=SR, hop_length=HOP)
    ok = np.isfinite(bpms) & (bpms >= 30) & (bpms <= 300)
    bpms, ac = bpms[ok], ac[ok]
    # La autocorrelación favorece los múltiplos lentos (si algo se repite cada T, también cada 2T) y la DFT los
    # rápidos (armónicos 2f, 3f). El producto de las dos marca el pulso real (Peeters 2007).
    ft = mean_chunked(lambda e: np.abs(librosa.feature.fourier_tempogram(onset_envelope=e, sr=SR, hop_length=HOP,
                                                                          win_length=768)), env)
    fb = librosa.fourier_tempo_frequencies(sr=SR, hop_length=HOP, win_length=768)
    keep = fb > 0
    dft = np.interp(np.log2(bpms), np.log2(fb[keep]), ft[keep])
    ac_n = np.maximum(ac, 0) / (ac.max() + 1e-12)
    dft_n = dft / (dft.max() + 1e-12)
    return bpms, ac_n * dft_n, tg


def score_at(bpms, ac, bpm):
    if bpm < bpms.min() or bpm > bpms.max():
        return 0.0
    i = np.argmin(np.abs(np.log2(bpms / bpm)))
    lo, hi = max(0, i - 2), i + 3
    return float(ac[lo:hi].max())


def choose_tempo(bpms, ac):
    """Pico de la autocorrelación con un prior suave hacia 60-180 y 100 BPM; devuelve (bpm, alternativas, confianza)."""
    # prior plano en 60-180 (la octava se decide después con reglas musicales) y que cae fuera de ese rango
    lo, hi = np.log2(bpms / 60.0), np.log2(bpms / 180.0)
    prior = np.where(bpms < 60, np.exp(-0.5 * (lo / 0.5) ** 2), np.where(bpms > 180, np.exp(-0.5 * (hi / 0.5) ** 2), 1.0))
    weighted = ac * prior
    from scipy.signal import find_peaks
    peaks, _ = find_peaks(weighted)
    if not len(peaks):
        peaks = np.array([int(np.argmax(weighted))])
    best = peaks[np.argmax(weighted[peaks])]
    bpm = float(bpms[best])
    # entre el elegido y su doble/mitad, preferir el que quede en 60-180 si el puntaje crudo es comparable
    cands = []
    for f in (0.5, 1.0, 2.0, 2 / 3, 1.5):
        b = bpm * f
        if 30 <= b <= 300:
            cands.append({"bpm": round(b, 1), "score": round(score_at(bpms, ac, b), 4), "factor": f})
    raw = score_at(bpms, ac, bpm)
    others = [c["score"] for c in cands if c["factor"] != 1.0]
    rest = np.sort(ac[peaks])[::-1]
    second = rest[1] if len(rest) > 1 else 0
    conf = float(np.clip((raw - second * 0.8) / (raw + 1e-9), 0, 1)) if raw > 0 else 0.0
    return bpm, cands, conf, others


def band_accent(y, librosa, low_hz=150.0, high_hz=4000.0, split=False):
    """Acento por cuadro en escala lineal (no dB): flujo positivo de las bandas grave (bombo, bajo) y media
    (redoblante, rasguido), cada una normalizada. Los platillos y el hi-hat (agudos) quedan afuera a propósito."""
    if y is None or not np.any(y):
        return None
    S = mel_chunked(y, librosa, n_mels=64)
    f = librosa.mel_frequencies(n_mels=64, fmax=SR / 2)
    out = []
    for sel in (f < low_hz, (f >= low_hz) & (f < high_hz)):
        if not sel.any():
            continue
        band = np.sqrt(S[sel].sum(axis=0))
        flux = np.maximum(np.diff(band, prepend=band[0]), 0)
        out.append(norm01(flux))
    return out if split else np.max(out, axis=0)


def parity_contrast(accent, beats):
    """Con pulsos al doble del tempo real, uno de cada dos cae en un contratiempo débil: medir cuánto más débil es la
    paridad floja (0 = muy distinta -> estamos al doble; 1 = pareja -> tempo correcto)."""
    if accent is None or len(beats) < 8:
        return None
    fr = np.clip(np.round(np.asarray(beats) * SR / HOP).astype(int), 0, len(accent) - 1)
    a = np.array([accent[max(0, f - 2):f + 3].max() for f in fr])
    even, odd = a[0::2].mean(), a[1::2].mean()
    return float(min(even, odd) / (max(even, odd) + 1e-9))


def backbeat(snare, beats):
    """Cuánto parece un contratiempo (redoblante en 2 y 4) con estos pulsos: alternancia entre paridades por la
    similitud de las dos fases fuertes. Al doble del tempo el redoblante cae en una sola de cada 4 fases (similitud
    baja); a la mitad cae en todos los pulsos (alternancia baja)."""
    if snare is None or beats is None or len(beats) < 16:
        return 0.0
    fr = np.clip(np.round(np.asarray(beats) * SR / HOP).astype(int), 0, len(snare) - 1)
    a = np.array([snare[max(0, f - 2):f + 3].max() for f in fr])
    m = np.array([a[p::4].mean() for p in range(4)])
    even, odd = m[0] + m[2], m[1] + m[3]
    strong = (m[0], m[2]) if even > odd else (m[1], m[3])
    alt = 1 - min(even, odd) / (max(even, odd) + 1e-9)
    sim = min(strong) / (max(strong) + 1e-9)
    return float(alt * sim)


def drum_timbre(y, librosa):
    """Espectro mel (dB) de la batería por cuadro, para comparar el timbre de los golpes (bombo vs redoblante)."""
    S = librosa.power_to_db(mel_chunked(y, librosa, n_mels=40), ref=np.max)
    return np.maximum(S, -60.0) + 60.0


def alternation(timbre, beats):
    """Estructura de período 2 en el timbre de los golpes: en el tempo correcto de un groove bombo/redoblante, los
    pulsos pares se parecen entre sí, los impares entre sí, y pares e impares difieren. Al doble del tempo los pares
    son bombo y redoblante (distintos); a la mitad todos son iguales."""
    if timbre is None or beats is None or len(beats) < 16:
        return 0.0
    fr = np.clip(np.round(np.asarray(beats) * SR / HOP).astype(int), 0, timbre.shape[1] - 1)
    v = []
    for p in range(4):
        sel = fr[p::4]
        x = np.stack([timbre[:, max(0, f - 1):f + 3].max(axis=1) for f in sel]).mean(axis=0)
        x = x - x.mean()
        v.append(x / (np.linalg.norm(x) + 1e-9))
    sim = lambda a, b: float(v[a] @ v[b])  # noqa: E731
    return (sim(0, 2) + sim(1, 3) - sim(0, 1) - sim(2, 3) - sim(0, 3) - sim(1, 2)) / 2 


def alignment(env, beats):
    """Cuánto más fuerte es el ataque en los pulsos que en promedio (pulsos que caen en los golpes -> alto)."""
    if beats is None or not len(beats):
        return 0.0
    fr = np.clip(np.round(np.asarray(beats) * SR / HOP).astype(int), 0, len(env) - 1)
    return float(np.mean([env[max(0, f - 1):f + 2].max() for f in fr]) / (env.mean() + 1e-9))


def track_beats(env, bpm, librosa, local=None, tightness=100):
    kw = {"bpm": local} if local is not None else {"bpm": bpm}
    _, beats = librosa.beat.beat_track(onset_envelope=env, sr=SR, hop_length=HOP, tightness=tightness,
                                       trim=True, units="time", **kw)
    return np.asarray(beats, dtype=float)


def tempo_stats(beats, window=None):
    """BPM global (media de intervalos sanos) y variación por ventanas (~30 s; más cortas en temas cortos)."""
    if len(beats) < 8:
        return None, None, []
    if window is None:
        window = float(np.clip((beats[-1] - beats[0]) / 5, 8, 30))
    ibi = np.diff(beats)
    med = np.median(ibi)
    good = np.abs(ibi - med) < 0.25 * med
    local = []
    t0 = beats[0]
    while t0 < beats[-1]:
        sel = (beats[1:] >= t0) & (beats[1:] < t0 + window) & good
        if sel.sum() >= 6:
            local.append({"t": round(float(t0), 1), "bpm": round(float(60 / np.mean(ibi[sel])), 2)})
        t0 += window / 2
    bpm = float(60 / np.mean(ibi[good])) if good.any() else float(60 / med)
    vals = np.array([x["bpm"] for x in local]) if local else np.array([bpm])
    spread = float((np.percentile(vals, 90) - np.percentile(vals, 10)) / np.median(vals)) if len(vals) > 2 else 0.0
    return bpm, spread, local


def fit_grid(beats):
    """Pulsos ideales de tempo fijo (regresión) para comparar con los detectados."""
    k = np.arange(len(beats))
    a, b = np.polyfit(k, beats, 1)
    return a * k + b, a


# ---------------------------------------------------------------- croma por pulso

def beat_sync(feat, frame_times, edges, agg=np.median):
    out = np.zeros((feat.shape[0], len(edges) - 1))
    idx = np.searchsorted(frame_times, edges)
    for i in range(len(edges) - 1):
        a, b = idx[i], max(idx[i + 1], idx[i] + 1)
        out[:, i] = agg(feat[:, a:b], axis=1) if b <= feat.shape[1] else (feat[:, -1] if feat.shape[1] else 0)
    return out


def estimate_tuning(y, librosa, n_seg=4, seg_sec=30):
    """Afinación en semitonos (-0,5..0,5) respecto de La 440: mediana circular de varios tramos repartidos por el tema
    (una sola estimación al principio puede caer en una intro o en un tramo raro)."""
    n = len(y)
    seg = int(seg_sec * SR)
    starts = [0] if n <= seg else np.linspace(0, n - seg, n_seg).astype(int)
    vals = []
    for a in starts:
        part = y[a:a + seg]
        if np.sqrt(np.mean(part ** 2)) < 1e-4:
            continue
        try:
            # bins_per_octave=12 -> rango ±50 cents (con 36 se satura en ±17 cents)
            vals.append(float(librosa.estimate_tuning(y=part, sr=SR, bins_per_octave=12)))
        except Exception:
            continue
    if not vals:
        return 0.0
    ang = np.array(vals) * 2 * np.pi  # un semitono = vuelta completa: +0,49 y -0,49 son casi lo mismo
    mean = np.angle(np.mean(np.exp(1j * ang)))
    dev = np.angle(np.exp(1j * (ang - mean)))
    med = mean + np.median(dev)
    return float(((med / (2 * np.pi)) + 0.5) % 1.0 - 0.5)


def cqt_chroma(y, librosa, fmin, n_octaves, tuning):
    """`tuning` en semitonos (-0,5..0,5) respecto de La 440. Tres bins por semitono centrados en cada nota."""
    bpo = 36
    fmin = fmin * 2 ** (tuning / 12) * 2 ** (-1 / bpo)
    C = np.abs(librosa.cqt(y, sr=SR, hop_length=CHOP, fmin=fmin, n_bins=n_octaves * bpo, bins_per_octave=bpo))
    freqs = librosa.cqt_frequencies(n_bins=n_octaves * bpo, fmin=fmin, bins_per_octave=bpo)
    energy = C.sum(axis=0)
    return fold_chroma(C, freqs, 2 ** (tuning / 12)), energy


# ---------------------------------------------------------------- acordes

def chord_vocab():
    names, roots, quals, temps = [], [], [], []
    for r in range(12):
        for q, iv in QUALITIES:
            roots.append(r)
            quals.append(q)
            temps.append(np.roll(harmonic_template(iv), r))
    return np.array(roots), quals, np.array(temps)


def chord_emissions(treble, bass, roots, quals, temps, bass_w, key_bonus=None, bass_metric=None):
    """Puntaje por pulso y acorde: coseno con la plantilla + bonus si el bajo toca la fundamental."""
    T = treble / (np.linalg.norm(treble, axis=0, keepdims=True) + 1e-9)
    score = temps @ T  # (n_chords, n_beats)
    score += np.array([QUALITY_PRIOR[q] for q in quals])[:, None]
    if bass is not None and bass_w > 0:
        B = bass / (bass.sum(axis=0, keepdims=True) + 1e-9)
        if bass_metric is not None:  # el bajo caminante pasa por 3ras y 5tas: su nota pesa más en el 1 del compás
            B = B * bass_metric[None, :]
        score += bass_w * B[roots]
    if key_bonus is not None:
        score += key_bonus[:, None]
    return score


def viterbi(score, beta, change_cost, downbeat_mask):
    """Suavizado: cambiar de acorde cuesta, menos en el 1 (y algo menos en el 3) del compás."""
    n, m = score.shape
    logp = beta * score
    logp -= np.log(np.exp(logp - logp.max(axis=0)).sum(axis=0)) + logp.max(axis=0)
    dp = logp[:, 0].copy()
    back = np.zeros((n, m), dtype=np.int32)
    for t in range(1, m):
        cost = change_cost * (CHG_DOWN if downbeat_mask[t] == 1 else CHG_HALF if downbeat_mask[t] == 2 else 1.0)
        best_prev = int(np.argmax(dp))
        stay = dp
        jump = dp[best_prev] - cost
        take_jump = jump > stay
        back[:, t] = np.where(take_jump, best_prev, np.arange(n))
        dp = np.where(take_jump, jump, stay) + logp[:, t]
    path = np.zeros(m, dtype=np.int32)
    path[-1] = int(np.argmax(dp))
    for t in range(m - 1, 0, -1):
        path[t - 1] = back[path[t], t]
    post = np.exp(logp)
    return path, post


def segments_from_path(path, post, edges, roots, quals, bass, silent, flats, min_beats=1):
    segs = []
    i = 0
    while i < len(path):
        j = i
        while j + 1 < len(path) and path[j + 1] == path[i] and silent[j + 1] == silent[i]:
            j += 1
        c = path[i]
        seg = {"start": round(float(edges[i]), 3), "end": round(float(edges[j + 1]), 3)}
        if silent[i]:
            seg.update(root=None, quality=None, label="N", bass=None, confidence=0.0)
        else:
            root = int(roots[c])
            label = spell(root, flats) + quals[c]
            bass_name = None
            if bass is not None:
                bsum = bass[:, i:j + 1].sum(axis=1)
                bpc = int(np.argmax(bsum))
                share = bsum[bpc] / (bsum.sum() + 1e-9)
                tones = {(root + iv) % 12 for iv in dict(QUALITIES)[quals[c]]}
                if bpc != root and bpc in tones and share > 0.35:
                    bass_name = spell(bpc, flats)
                    label += "/" + bass_name
            seg.update(root=spell(root, flats), quality=quals[c] or "maj", label=label, bass=bass_name,
                       confidence=round(float(np.clip(post[c, i:j + 1].mean() * 3, 0, 1)), 2))
        segs.append(seg)
        i = j + 1
    # pegar segmentos idénticos separados por nada
    merged = []
    for s in segs:
        if merged and merged[-1]["label"] == s["label"]:
            merged[-1]["end"] = s["end"]
        else:
            merged.append(s)
    return merged


# ---------------------------------------------------------------- tonalidad

def key_profile(mode):
    p = np.zeros(12)
    for iv in MODES[mode]:
        p[iv] = 1.0
    p[0] += 0.6
    p[7] += 0.3 if 7 in MODES[mode] else 0
    p[MODES[mode][2]] += 0.2
    return p


def estimate_key(chroma_sum, root_hist, bass_hist, first_last, w_root=0.5, w_bass=0.5, w_first=W_FIRST, w_last=0.1):
    """Dos pasos en uno: el perfil del modo reconoce el conjunto de notas y la evidencia de tónica (fundamentales de
    los acordes, bajo, primer y último acorde) decide cuál de sus grados es el centro."""
    c = chroma_sum - chroma_sum.mean()
    c /= np.linalg.norm(c) + 1e-9
    tonic_ev = w_root * root_hist + w_bass * bass_hist
    if first_last:
        tonic_ev[first_last[0]] += w_first
        tonic_ev[first_last[1]] += w_last
    rows = []
    for mode in MODES:
        prof = key_profile(mode)
        for t in range(12):
            p = np.roll(prof, t)
            p = p - p.mean()
            corr = float(c @ (p / np.linalg.norm(p)))
            penalty = RARE_MODE_PENALTY if mode in ("phrygian", "lydian", "harmonicMinor") else 0.0
            rows.append((corr + tonic_ev[t] - penalty, t, mode, corr))
    rows.sort(reverse=True)
    return rows


# ---------------------------------------------------------------- análisis completo

def analyze(folder, track_id=None, beat_source="drums+bass", chord_bass=True, with_vocals=False, bass_w=0.25):
    import librosa  # noqa: E402  (después de fijar hilos)

    t_start = time.time()
    folder = Path(folder)
    manifest = read_manifest(folder)
    stems = available_stems(folder, manifest)
    notes = []
    if not stems:
        raise SystemExit("No hay stems con sonido en " + str(folder))
    progress("load", 0)

    sig = {}
    harm = None
    harm_names = [n for n in ("guitar", "piano", "other") if n in stems] + (["vocals"] if with_vocals and "vocals" in stems else [])
    if not harm_names and "vocals" in stems:
        harm_names = ["vocals"]
        notes.append("Sin instrumentos armónicos separados: la armonía sale de la voz.")
    for k, n in enumerate(harm_names):
        y = load_mono(stems[n])
        harm = y if harm is None else _add(harm, y)
        progress("load", 10 + 30 * (k + 1) / (len(harm_names) + 2))
    for n in ("bass", "drums"):
        if n in stems:
            sig[n] = load_mono(stems[n])
    progress("load", 45)
    length = max(len(x) for x in [harm, *sig.values()] if x is not None)
    duration = length / SR
    harm = _pad(harm, length)
    for n in list(sig):
        sig[n] = _pad(sig[n], length)

    # ---- pulso
    progress("tempo", 50)
    envs = {}
    if "drums" in sig:
        envs["drums"] = onset_env(sig["drums"], librosa)
        envs["kick"] = onset_env(sig["drums"], librosa, fmax=160)
    if "bass" in sig:
        envs["bass"] = onset_env(sig["bass"], librosa, fmax=800)
    envs["harm"] = onset_env(harm, librosa) if harm is not None else None
    parts = {"drums+bass": ["drums", "bass"], "drums": ["drums"], "bass": ["bass"],
             "all": ["drums", "bass", "harm"]}[beat_source]
    used = [p for p in parts if envs.get(p) is not None]
    if not used:
        used = [p for p in ("drums", "bass", "harm") if envs.get(p) is not None]
    n_env = min(len(envs[p]) for p in used)
    env = sum(norm01(envs[p][:n_env]) for p in used)
    bpms, ac, tg = tempo_candidates(env, librosa)
    bpm0, cands, t_conf, _ = choose_tempo(bpms, ac)
    # Octava (mitad/doble), con dos pruebas sobre el par (lento, rápido = 2 x lento):
    # 1) contratiempo del redoblante: en el tempo correcto el redoblante (banda media de la batería) cae en pulsos
    #    alternos (2 y 4). Al doble cae cada 4 pulsos; a la mitad, en todos.
    # 2) si no hay contratiempo claro (jazz con ride, bossa, sin batería): al doble, uno de cada dos pulsos es un
    #    contratiempo débil en las bandas grave y media.
    bands = band_accent(sig.get("drums"), librosa, high_hz=SNARE_HZ, split=True) if "drums" in sig else None
    if bands is not None:
        accent, snare = np.maximum(bands[0], bands[1]), bands[1]
    else:
        snare = None
        acc = [band_accent(sig.get("bass"), librosa) if "bass" in sig else None, band_accent(harm, librosa)]
        acc = [a for a in acc if a is not None]
        accent = np.max([a[:min(map(len, acc))] for a in acc], axis=0) if acc else None
    fast = bpm0
    while fast < 100:
        fast *= 2
    while fast >= 200:
        fast /= 2
    octave_info = {}
    if True:
        slow = fast / 2
        beats_fast = track_beats(env, fast, librosa)
        beats_slow = track_beats(env, slow, librosa) if slow >= 50 else None
        alt_f = backbeat(snare, beats_fast)
        alt_s = backbeat(snare, beats_slow)
        pc = parity_contrast(accent, beats_fast)
        timbre = drum_timbre(sig["drums"], librosa) if "drums" in sig else None
        tim_s, tim_f = alternation(timbre, beats_slow), alternation(timbre, beats_fast)
        if beats_slow is None:
            choice, rule, margin = fast, "límite", 0.5
        elif max(tim_s, tim_f) > 0 and abs(tim_s - tim_f) > 0.15:
            choice, rule, margin = (slow if tim_s > tim_f else fast), "timbre", min(1, abs(tim_s - tim_f) / 1.0)
        elif max(alt_f, alt_s) > BACKBEAT_MIN and abs(alt_s - alt_f) > 0.05:
            choice, rule, margin = (slow if alt_s > alt_f else fast), "contratiempo", min(1, abs(alt_s - alt_f) / 0.4)
        elif pc is not None:
            choice, rule, margin = (slow if pc < PARITY_MAX else fast), "paridad", min(1, abs(pc - PARITY_MAX) / 0.4)
        else:
            choice, rule, margin = bpm0, "prior", 0.0
        octave_info = {"slowBpm": round(slow, 1), "fastBpm": round(fast, 1), "rule": rule, "margin": round(margin, 2),
                       "timbreSlow": round(tim_s, 3), "timbreFast": round(tim_f, 3), "backbeatSlow": round(alt_s, 3),
                       "backbeatFast": round(alt_f, 3), "parityFast": None if pc is None else round(pc, 3)}
        # control: si el seguidor de pulsos no logra sostener el tempo elegido (se le escapa >4 %) o sus pulsos caen
        # bastante peor sobre los ataques que los de la otra octava, quedarse con la otra
        if beats_slow is not None:
            got = {fast: beats_fast, slow: beats_slow}
            other = slow if choice == fast else fast
            al_c, al_o = alignment(env, got[choice]), alignment(env, got[other])
            real = tempo_stats(got[choice])[0] or choice
            octave_info.update(alignChosen=round(al_c, 3), alignOther=round(al_o, 3), trackedBpm=round(real, 2))
            if abs(real - choice) / choice > 0.025 and al_c < al_o:
                choice = other
                octave_info["rule"] += "+control"
        bpm0 = choice
    beats = track_beats(env, bpm0, librosa)
    bpm, spread, local = tempo_stats(beats)
    stable = True
    if bpm is not None and spread is not None and spread > 0.03:
        # tempo que se mueve: seguir el tempo local (array de BPM por cuadro) en vez de una grilla rígida
        try:
            from scipy.stats import uniform  # noqa: F401
            loc = per_frame_chunked(lambda e: librosa.feature.tempo(onset_envelope=e, sr=SR, hop_length=HOP,
                                                                    aggregate=None, std_bpm=0.25, start_bpm=bpm,
                                                                    ac_size=12.0), env)
            loc = np.clip(loc, bpm / 1.4, bpm * 1.4)
            beats_v = track_beats(env, bpm, librosa, local=loc, tightness=60)
            b2, s2, l2 = tempo_stats(beats_v)
            if b2 is not None:
                beats, bpm, spread, local = beats_v, b2, s2, l2
        except Exception as e:  # versión de librosa sin tempo variable: quedarse con lo que hay
            notes.append(f"No pude seguir el tempo variable ({type(e).__name__}).")
    if bpm is None:
        bpm, spread, local = bpm0, 0.0, []
        notes.append("Muy pocos pulsos detectados: el tempo es poco confiable.")
    if spread is not None and spread > 0.03:
        stable = False
        notes.append(f"El tempo varía (entre ~{min(x['bpm'] for x in local):.0f} y ~{max(x['bpm'] for x in local):.0f} BPM): "
                     "los pulsos siguen la grabación, no una grilla fija.")
    # alternativas de octava en función del bpm final
    alts = [{"bpm": round(bpm * f, 2), "score": round(score_at(bpms, ac, bpm * f), 4), "relation": r}
            for f, r in ((0.5, "mitad"), (2.0, "doble")) if 30 <= bpm * f <= 300]
    main_score = score_at(bpms, ac, bpm)
    close = [a for a in alts if a["score"] > 0.8 * main_score]
    if close:
        notes.append("Ambigüedad de octava en el tempo: " + ", ".join(f"{a['relation']} ({a['bpm']:.0f} BPM)" for a in close)
                     + " también encaja.")
    if beat_source != "harm" and "drums" not in sig:
        notes.append("Sin batería separada: el pulso sale del bajo y la armonía.")

    # ---- croma
    progress("chroma", 60)
    edges = np.concatenate([[0.0], beats, [duration]]) if len(beats) else np.arange(0, duration + 0.5, 0.5)
    edges = np.unique(np.clip(edges, 0, duration))
    tuning = estimate_tuning(harm, librosa) if harm is not None else 0.0
    if abs(tuning) > 0.4:
        notes.append(f"La afinación de la grabación está a {tuning * 100:+.0f} cents de La 440, casi a mitad de camino "
                     "entre dos semitonos: la tónica y las fundamentales podrían estar corridas medio tono.")
    chroma_h, energy_h = cqt_chroma(harm, librosa, librosa.note_to_hz("C2"), 6, tuning)
    progress("chroma", 75)
    del harm
    frame_t = np.arange(chroma_h.shape[1]) * CHOP / SR
    treble = beat_sync(chroma_h, frame_t, edges)
    e_beat = beat_sync(energy_h[None, :], frame_t, edges, agg=np.mean)[0]
    bass_b = None
    if "bass" in sig:
        chroma_b, energy_b = cqt_chroma(sig["bass"], librosa, librosa.note_to_hz("E1"), 3, tuning)
        bass_b = beat_sync(chroma_b, np.arange(chroma_b.shape[1]) * CHOP / SR, edges)
        eb = beat_sync(energy_b[None, :], np.arange(chroma_b.shape[1]) * CHOP / SR, edges, agg=np.mean)[0]
        bass_b = bass_b * (eb > 0.02 * (np.percentile(eb, 95) + 1e-9))[None, :]
        # el croma del bajo: realzar la clase dominante (la fundamental) y quitar el piso
        bass_b = np.maximum(bass_b - bass_b.mean(axis=0, keepdims=True), 0) ** 2
    progress("chords", 80)

    # ---- compases (fase del 1)
    beat_idx = edges[1:-1]  # tiempos de pulso dentro de edges
    downbeats, phase, phase_conf = [], 0, 0.0
    if len(beats) >= 8:
        bf = librosa.time_to_frames(beats, sr=SR, hop_length=HOP)
        bf = np.clip(bf, 0, n_env - 1)

        def at(name):
            e = envs.get(name)
            if e is None:
                return np.zeros(len(bf))
            e = norm01(e[:n_env])
            return np.array([e[max(0, f - 2):f + 3].max() for f in bf])

        # cambio armónico al llegar a cada pulso (croma tratado + bajo)
        h = treble[:, 1:len(beats) + 1] if treble.shape[1] > len(beats) else treble[:, :len(beats)]
        hn = h / (np.linalg.norm(h, axis=0, keepdims=True) + 1e-9)
        change = np.r_[0, 1 - np.sum(hn[:, 1:] * hn[:, :-1], axis=0)]
        if bass_b is not None:
            bb = bass_b[:, 1:len(beats) + 1] if bass_b.shape[1] > len(beats) else bass_b[:, :len(beats)]
            bn = bb / (np.linalg.norm(bb, axis=0, keepdims=True) + 1e-9)
            change = change + 0.5 * np.r_[0, 1 - np.sum(bn[:, 1:] * bn[:, :-1], axis=0)]
        feat = 0.6 * at("kick") + 0.3 * at("bass") + 1.0 * norm01(change)
        scores = np.array([feat[p::4].mean() if len(feat[p::4]) else 0 for p in range(4)])
        phase = int(np.argmax(scores))
        srt = np.sort(scores)[::-1]
        phase_conf = float(np.clip((srt[0] - srt[1]) / (srt[0] + 1e-9) * 4, 0, 1))
        downbeats = beats[phase::4]
    notes.append("Compás asumido 4/4; el 1 de cada compás es una estimación"
                 + (" con poca seguridad." if phase_conf < 0.3 else "."))

    # ---- acordes (pasada 1 sin tonalidad)
    roots, quals, temps = chord_vocab()
    silent = e_beat < 0.03 * (np.percentile(e_beat, 95) + 1e-9)
    # posición métrica de cada segmento de croma: 1 = primer pulso de compás, 2 = tercer pulso
    metric = np.zeros(treble.shape[1], dtype=int)
    if len(beats):
        for k in range(len(beats)):
            seg = k + 1 if edges[0] == 0.0 and len(edges) - 1 > len(beats) else k
            if seg < len(metric):
                rel = (k - phase) % 4
                metric[seg] = 1 if rel == 0 else 2 if rel == 2 else 0
    bass_used = bass_b if chord_bass else None
    bmet = np.where(metric == 1, 1.0, np.where(metric == 2, 0.7, 0.4))
    sc = chord_emissions(treble, bass_used, roots, quals, temps, bass_w, bass_metric=bmet)
    path, post = viterbi(sc, beta=BETA, change_cost=CHG, downbeat_mask=metric)

    # ---- tonalidad
    progress("key", 90)
    dur = np.diff(edges)
    w = dur * (~silent)
    chroma_sum = (treble / (treble.sum(axis=0, keepdims=True) + 1e-9) * w).sum(axis=1)
    root_hist = np.zeros(12)
    for k, c in enumerate(path):
        if not silent[k]:
            root_hist[roots[c]] += w[k]
    root_hist /= root_hist.sum() + 1e-9
    bass_hist = np.zeros(12)
    if bass_b is not None:
        bh = (bass_b / (bass_b.sum(axis=0, keepdims=True) + 1e-9) * w).sum(axis=1)
        bass_hist = bh / (bh.sum() + 1e-9)
    voiced = [k for k in range(len(path)) if not silent[k]]
    first_last = _first_last_roots(path, silent, roots)
    rows = estimate_key(chroma_sum, root_hist, bass_hist if chord_bass else root_hist, first_last)
    best = rows[0]
    _, tonic, mode, _ = best
    flats = key_uses_flats(tonic, mode)

    # ---- acordes (pasada 2: leve preferencia por los diatónicos de la tonalidad hallada)
    scale = {(tonic + iv) % 12 for iv in MODES[mode]}
    bonus = np.array([0.02 if all((r + iv) % 12 in scale for iv in dict(QUALITIES)[q]) else 0.0
                      for r, q in zip(roots, quals)])
    sc = chord_emissions(treble, bass_used, roots, quals, temps, bass_w, key_bonus=bonus, bass_metric=bmet)
    path, post = viterbi(sc, beta=BETA, change_cost=CHG, downbeat_mask=metric)
    chords = segments_from_path(path, post, edges, roots, quals, bass_used, silent, flats)
    chords = [c for c in chords if c["end"] - c["start"] > 1e-3]

    # alternativas de tonalidad (distintas en tónica+modo), puntaje relativo
    shown = "minor" if mode == "harmonicMinor" else mode
    seen, alternatives = {(tonic, shown)}, [None]
    for s, t, m, _ in rows:
        m = "minor" if m == "harmonicMinor" else m
        if (t, m) in seen:
            continue
        seen.add((t, m))
        alternatives.append({"tonic": spell(t, key_uses_flats(t, m)), "mode": m, "score": round(float(s), 3)})
        if len(alternatives) == 4:
            break
    norm_mode = lambda m: "minor" if m == "harmonicMinor" else m  # noqa: E731
    margin = rows[0][0] - next(s for s, t, m, _ in rows if (t, norm_mode(m)) != (tonic, shown))
    tonic_margin = rows[0][0] - next(s for s, t, m, _ in rows if t != tonic)
    k_conf = float(np.clip(margin / 0.15, 0, 1) * 0.6 + np.clip(best[3], 0, 1) * 0.4)
    # mayor/menor clásico (relativos) para quien no piensa en modos
    mm = next((t, m) for _, t, m, _ in rows if m in ("major", "minor"))
    family = "minor" if 3 in MODES[mode] else "major"
    blues = _is_blues(chords, tonic, flats)
    tonic_name = spell(tonic, flats)
    variant = None
    if mode == "harmonicMinor":  # menor con V7: para el usuario es "menor"; el detalle va en variant y en notes
        variant, mode = "harmonicMinor", "minor"
        notes.append(f"{spanish(tonic_name)} menor con dominante (V7): la 7ma sube medio tono como en el menor armónico.")
    label = f"{spanish(tonic_name)} {MODE_ES[mode]}"
    if mode not in ("major", "minor"):
        notes.append(f"Modo estimado: {label} ({MODE_HELP[mode]}). Es una estimación; la alternativa tonal más simple es "
                     f"{spanish(spell(mm[0], key_uses_flats(*mm)))} {MODE_ES[mm[1]]}.")
    if blues:
        label = f"{spanish(tonic_name)} blues"
        notes.append(f"Parece un blues en {tonic_name}: el I y el IV dominan y suenan como dominantes (7). En el blues "
                     "se mezclan la 3ra mayor y la menor; el modo informado es solo el que mejor encaja con las notas.")
    progress("done", 100)
    return {
        "version": VERSION,
        "trackId": track_id or manifest.get("track_id") or folder.parent.name,
        "createdAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "durationSec": round(duration, 3),
        "title": manifest.get("title"), "artist": manifest.get("artist"),
        "key": {"tonic": tonic_name, "mode": mode, "family": family, "label": label,
                "majorMinor": {"tonic": spell(mm[0], key_uses_flats(*mm)), "mode": mm[1],
                               "label": f"{spanish(spell(mm[0], key_uses_flats(*mm)))} {MODE_ES[mm[1]]}"},
                "variant": variant, "blues": blues, "confidence": round(k_conf, 2),
                "tonicConfidence": round(float(np.clip(tonic_margin / 0.15, 0, 1) * 0.6 + np.clip(best[3], 0, 1) * 0.4), 2), "alternatives": alternatives[1:4],
                "tuningCents": round(tuning * 100, 1)},
        "tempo": {"bpm": round(float(bpm), 2),
                  "confidence": round(float((0.5 * t_conf + 0.5 * octave_info.get("margin", 0.0)) * (1.0 if stable else 0.7)), 2),
                  "beats": [round(float(b), 3) for b in beats], "downbeats": [round(float(b), 3) for b in downbeats],
                  "timeSignature": "4/4", "stable": bool(stable), "variation": round(float(spread or 0), 4),
                  "local": local, "alternatives": alts, "downbeatConfidence": round(phase_conf, 2),
                  "source": "+".join(used), "octave": octave_info},
        "chords": chords,
        "notes": notes,
        "stats": {"keyEvidence": {"chroma": [round(float(x), 3) for x in chroma_sum / (chroma_sum.sum() + 1e-9)],
                                  "rootHist": [round(float(x), 3) for x in root_hist],
                                  "bassHist": [round(float(x), 3) for x in bass_hist], "firstLast": first_last},
                  "elapsedSec": round(time.time() - t_start, 2), "stems": sorted(stems),
                  "harmonyFrom": harm_names, "variant": {"beatSource": beat_source, "chordBass": chord_bass,
                                                         "withVocals": with_vocals}},
    }


def _first_last_roots(path, silent, roots, window=4):
    """Fundamental que más pulsos ocupa en el primer y en el último compás con sonido (más robusto que "el primer
    acorde", que puede ser un error suelto de un pulso). Empates: la primera / la última en sonar."""
    voiced = [int(roots[path[k]]) for k in range(len(path)) if not silent[k]]
    if not voiced:
        return []
    head, tail = voiced[:window], voiced[-window:]
    first = max(dict.fromkeys(head), key=head.count)              # dict conserva el orden: gana la primera
    last = max(dict.fromkeys(reversed(tail)), key=tail.count)     # recorrido desde el final: gana la última
    return [first, last]


def _is_blues(chords, tonic, flats):
    tot = {}
    for c in chords:
        if c.get("root"):
            tot[(c["root"], c["quality"])] = tot.get((c["root"], c["quality"]), 0) + c["end"] - c["start"]
    total = sum(tot.values()) or 1
    I, IV = spell(tonic, flats), spell(tonic + 5, flats)
    share = lambda root, q=None: sum(v for (r, qq), v in tot.items() if r == root and (q is None or qq == q)) / total  # noqa: E731
    # blues: el I y el IV ocupan buena parte del tema y al menos uno de los dos suena como dominante (7)
    return bool(share(I) >= 0.3 and share(IV) >= 0.12 and share(IV, "7") >= 0.05
                and share(I, "7") + share(I, "m7") >= 0.08)


def _add(a, b):
    n = max(len(a), len(b))
    return _pad(a, n) + _pad(b, n)


def _pad(x, n):
    if x is None:
        return np.zeros(n, np.float32)
    return x if len(x) >= n else np.pad(x, (0, n - len(x)))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Tonalidad, tempo y acordes de un tema separado en stems.")
    ap.add_argument("folder")
    ap.add_argument("--out")
    ap.add_argument("--track-id")
    ap.add_argument("--beat-source", default="drums+bass", choices=["drums+bass", "drums", "bass", "all"])
    ap.add_argument("--no-chord-bass", action="store_true", help="variante: acordes sin el stem de bajo")
    ap.add_argument("--with-vocals", action="store_true", help="variante: sumar la voz a la armonía")
    a = ap.parse_args(argv)
    res = analyze(a.folder, a.track_id, a.beat_source, not a.no_chord_bass, a.with_vocals)
    text = json.dumps(res, ensure_ascii=False)
    if a.out:
        tmp = Path(a.out).with_suffix(".tmp")
        tmp.write_text(text)
        tmp.replace(a.out)
    else:
        print(text)


if __name__ == "__main__":
    main()
