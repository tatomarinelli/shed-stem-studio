// Análisis musical del tema cargado: tonalidad, tempo con pulsos y progresión de acordes (lo calcula el motor).
export interface Chord { start: number; end: number; root: string | null; quality: string | null; label: string; bass: string | null; confidence: number }
export interface Analysis {
  version: number; trackId: string; durationSec: number;
  key: { tonic: string; mode: string; label: string; confidence: number; blues: boolean; alternatives: { tonic: string; mode: string; score: number }[]; majorMinor?: { label: string } };
  tempo: { bpm: number; confidence: number; beats: number[]; downbeats: number[]; timeSignature: string; stable: boolean; alternatives: { bpm: number; relation: string }[]; downbeatConfidence?: number };
  chords: Chord[]; notes: string[];
}

class AnalysisStore {
  state = $state<'none' | 'checking' | 'running' | 'ready' | 'error'>('none');
  data = $state<Analysis | null>(null);
  stage = $state('');
  percent = $state(0);
  message = $state('');
  showGrid = $state(true);
  showChords = $state(true);
  #id = '';
  #timer = 0;

  /** Trae el análisis guardado de un tema, si existe. */
  async load(id: string) {
    this.#id = id; window.clearTimeout(this.#timer);
    this.data = null; this.message = ''; this.state = 'checking';
    try {
      const res = await fetch(`/engine/analysis/${id}`);
      if (id !== this.#id) return;
      if (res.ok) { this.data = await res.json(); this.state = 'ready'; return; }
      // sin análisis guardado: ¿hay uno corriendo?
      const st = await (await fetch(`/engine/analysis/${id}/status`)).json();
      if (id !== this.#id) return;
      if (st.state === 'running') { this.state = 'running'; this.#poll(id); } else this.state = 'none';
    } catch {
      if (id === this.#id) { this.state = 'none'; this.message = 'No pude hablar con el motor.'; }
    }
  }

  async start(force = false) {
    const id = this.#id; if (!id) return;
    this.message = ''; this.state = 'running'; this.stage = ''; this.percent = 0;
    try {
      const res = await fetch(`/engine/analysis/${id}/start`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ force }) });
      const body = await res.json();
      if (!res.ok) { this.state = 'error'; this.message = body.message ?? 'No se pudo analizar.'; return; }
      if (body.state === 'done') { await this.load(id); return; }
      this.#poll(id);
    } catch { this.state = 'error'; this.message = 'No pude hablar con el motor.'; }
  }

  #poll(id: string) {
    this.#timer = window.setTimeout(async () => {
      if (id !== this.#id) return;
      try {
        const st = await (await fetch(`/engine/analysis/${id}/status`)).json();
        if (id !== this.#id) return;
        this.stage = st.stage ?? ''; this.percent = st.percent ?? 0;
        if (st.state === 'running') return this.#poll(id);
        if (st.state === 'error') { this.state = 'error'; this.message = st.message ?? 'Falló el análisis.'; return; }
        await this.load(id);
      } catch { this.state = 'error'; this.message = 'Se perdió la conexión con el motor.'; }
    }, 1200);
  }

  /** Acorde que suena en un instante (búsqueda binaria; los acordes cubren el tema entero). */
  chordAt(t: number): Chord | null {
    const c = this.data?.chords; if (!c?.length) return null;
    let lo = 0, hi = c.length - 1;
    while (lo < hi) { const m = (lo + hi + 1) >> 1; if (c[m].start <= t) lo = m; else hi = m - 1; }
    return c[lo];
  }
}

export const analysis = new AnalysisStore();
