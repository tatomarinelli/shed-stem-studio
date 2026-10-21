import { loadTrack, type LoadedTrack, type TrackInfo } from './stems';
import { preview } from './preview.svelte';
import { view } from './view.svelte';

export type EngineName = 'rb-fast' | 'rb-finer' | 'st';
export const ENGINES: { id: EngineName; label: string }[] = [
  { id: 'rb-fast', label: 'Rubber Band (rápido)' },
  { id: 'rb-finer', label: 'Rubber Band (fino, más CPU)' },
  { id: 'st', label: 'SoundTouch' },
];

export const STEM_LABELS: Record<string, string> = {
  guitar: 'Guitarra', bass: 'Bajo', drums: 'Batería', piano: 'Piano', vocals: 'Voz', other: 'Otros',
};

export const STEM_COLORS: Record<string, string> = {
  guitar: '#f0a43c', bass: '#4fa3d9', drums: '#e8694f', piano: '#b48be6', vocals: '#f1a7c4', other: '#7cc7a3',
};

export interface Section { id: string; name: string; start: number; end: number }

export interface StemState { name: string; gain: number; mute: boolean; solo: boolean; peaks: Uint8Array }

class Player {
  tracks = $state<TrackInfo[]>([]);
  status = $state<'idle' | 'loading' | 'ready' | 'error'>('idle');
  error = $state('');
  progress = $state({ done: 0, total: 0, name: '' });
  track = $state<TrackInfo | null>(null);
  stems = $state<StemState[]>([]);
  playing = $state(false);
  position = $state(0); // segundos, interpolado
  duration = $state(0);
  speed = $state(1);
  engine = $state<EngineName>('rb-fast');
  loopA = $state<number | null>(null);
  loopB = $state<number | null>(null);
  loopOn = $state(false);
  underruns = $state(0);
  sections = $state<Section[]>([]);
  selectedSection = $state('');
  clickOn = $state(false);
  clickGain = $state(0.5);
  hasBeats = $state(false);
  #beats: { frames: Float64Array; down: Uint8Array } | null = null;
  loopSectionId = $state(''); // si el loop es el de una sección, cuál: los cambios de esa sección lo siguen
  metrics = $state({ heapMB: 0, flacMB: 0, loadMs: 0, f32MB: 0, baseLatencyMs: 0, outLatencyMs: 0, engineReady: false });

  #ctx: AudioContext | null = null;
  #node: AudioWorkletNode | null = null;
  #data: LoadedTrack | null = null;
  #wasm: WebAssembly.Module | null = null;
  #lastPos = 0;   // posición (s) en el instante #lastAudioT
  #lastAudioT = 0; // reloj de AUDIO del contexto, no el de pared: así el cabezal no se desfasa si la pestaña se traba
  #raf = 0;

  async init() {
    this.tracks = await (await fetch('/engine/tracks')).json();
    this.#tick();
  }

  get sr() { return this.#data?.sampleRate ?? 44100; }
  get loopActive() { return this.loopOn && this.loopA != null && this.loopB != null && this.loopB > this.loopA; }

  async load(id: string) {
    this.#teardown();
    this.status = 'loading';
    this.error = '';
    try {
      this.#ctx = new AudioContext({ sampleRate: 44100, latencyHint: 'playback' });
      await this.#ctx.audioWorklet.addModule('/worklet.js');
      this.#wasm ??= await WebAssembly.compile(await (await fetch('/rubberband.wasm')).arrayBuffer());
      this.#data = await loadTrack(id, this.#ctx, (done, total, name) => (this.progress = { done, total, name }));
      this.track = this.tracks.find(t => t.id === id) ?? null;
      this.stems = this.#data.stems.map(s => ({ name: s.name, gain: 1, mute: false, solo: false, peaks: s.peaks }));
      this.duration = this.#data.length / this.sr;
      this.position = 0; this.#lastPos = 0; this.#lastAudioT = this.#ctx?.currentTime ?? 0;
      this.loopA = this.loopB = null; this.loopOn = false;
      view.reset(this.duration);
      this.sections = this.#loadSections(id); this.selectedSection = ''; this.loopSectionId = '';
      this.metrics.flacMB = this.#data.flacBytes / 1e6;
      this.metrics.loadMs = this.#data.loadMs;
      this.metrics.f32MB = (this.#data.stems.length * this.#data.length * 8) / 1e6;
      this.#makeNode(0);
      this.status = 'ready';
    } catch (e) {
      this.status = 'error';
      this.error = String(e);
    }
  }

  /** Descarga el tema cargado (por ejemplo, si se borró). */
  unload() {
    this.#teardown();
    this.#beats = null; this.hasBeats = false; this.clickOn = false;
    this.sections = []; this.selectedSection = ''; this.loopSectionId = '';
    this.track = null; this.stems = []; this.status = 'idle'; this.duration = 0; this.position = 0;
  }

  #teardown() {
    this.#node?.disconnect();
    this.#node = null;
    void this.#ctx?.close();
    this.#ctx = null;
    this.#data = null;
    this.playing = false;
    this.metrics.engineReady = false;
  }

  #effectiveGains(): number[] {
    const anySolo = this.stems.some(s => s.solo);
    return this.stems.map(s => (s.mute || (anySolo && !s.solo) ? 0 : s.gain));
  }

  #makeNode(startFrame: number) {
    const ctx = this.#ctx!, d = this.#data!;
    this.#node?.disconnect();
    this.metrics.engineReady = false;
    const node = new AudioWorkletNode(ctx, 'stem-engine', {
      numberOfInputs: 0, outputChannelCount: [2],
      processorOptions: {
        stems: d.stems.map(s => ({ L: s.L, R: s.R })), length: d.length, engine: this.engine, wasmModule: this.#wasm,
        speed: this.speed, pos: startFrame, gains: this.#effectiveGains(), autoplay: this.playing,
        beats: this.#beats, clickOn: this.clickOn, clickGain: this.clickGain,
        loop: this.loopActive ? { a: Math.round(this.loopA! * this.sr), b: Math.round(this.loopB! * this.sr) } : null,
      },
    });
    node.port.onmessage = e => {
      const m = e.data;
      if (m.type === 'ready') this.metrics.engineReady = true;
      else if (m.type === 'pos') { this.#lastPos = m.pos / this.sr; this.#lastAudioT = m.t; this.underruns = m.underruns; }
      else if (m.type === 'ended') { this.playing = false; this.position = this.duration; }
    };
    node.connect(ctx.destination);
    this.#node = node;
    this.#lastPos = startFrame / this.sr;
    this.#lastAudioT = ctx.currentTime;
    this.underruns = 0;
    this.metrics.baseLatencyMs = ctx.baseLatency * 1000;
    this.metrics.outLatencyMs = ('outputLatency' in ctx ? ctx.outputLatency : 0) * 1000;
  }

  #post(m: object) { this.#node?.port.postMessage(m); }

  // ---- click: suena en los pulsos del análisis (en segundos de la fuente), después del estirador
  setBeats(beats: number[] | null, downbeats: number[] = []) {
    if (!beats?.length) { this.#beats = null; this.hasBeats = false; this.clickOn = false; this.#post({ type: 'beats', frames: null, down: null }); return; }
    const sr = this.sr, frames = new Float64Array(beats.map(t => t * sr));
    const down = new Uint8Array(beats.length);
    let j = 0;
    for (let i = 0; i < beats.length; i++) { while (j < downbeats.length && downbeats[j] < beats[i] - 0.03) j++; if (j < downbeats.length && Math.abs(downbeats[j] - beats[i]) <= 0.03) down[i] = 1; }
    this.#beats = { frames, down };
    this.hasBeats = true;
    this.#post({ type: 'beats', frames: frames.slice(), down: down.slice() });
  }
  toggleClick(on = !this.clickOn) { if (!this.hasBeats) return; this.clickOn = on; this.#post({ type: 'click', on, gain: this.clickGain }); }
  setClickGain(g: number) { this.clickGain = g; this.#post({ type: 'click', on: this.clickOn, gain: g }); }

  async play() {
    if (this.status !== 'ready') return;
    preview.stop(); // una sola cosa suena a la vez
    await this.#ctx!.resume();
    if (this.position >= this.duration - 0.05) this.seek(0);
    this.#lastPos = this.position;
    this.#lastAudioT = this.#ctx!.currentTime;
    this.playing = true;
    this.#post({ type: 'play' });
  }
  pause() { this.playing = false; this.#post({ type: 'pause' }); }
  toggle() { return this.playing ? this.pause() : this.play(); }

  seek(sec: number) {
    sec = Math.max(0, Math.min(this.duration, sec));
    this.position = this.#lastPos = sec;
    this.#lastAudioT = this.#ctx?.currentTime ?? 0;
    this.#post({ type: 'seek', frame: Math.round(sec * this.sr) });
  }

  setSpeed(v: number) {
    this.#rebase(); // la pendiente cambia: se ancla en la posición actual antes de cambiarla
    this.speed = v;
    this.#post({ type: 'speed', value: v });
  }

  setEngine(e: EngineName) {
    this.engine = e;
    if (this.status === 'ready') this.#makeNode(Math.round(this.position * this.sr));
  }

  #sendGains() { this.#effectiveGains().forEach((g, i) => this.#post({ type: 'gain', i, g })); }
  setGain(i: number, g: number) { this.stems[i].gain = g; this.#sendGains(); }
  toggleMute(i: number) { this.stems[i].mute = !this.stems[i].mute; this.#sendGains(); }
  toggleSolo(i: number) { this.stems[i].solo = !this.stems[i].solo; this.#sendGains(); }

  #sendLoop() {
    if (this.loopActive) this.#post({ type: 'loop', a: Math.round(this.loopA! * this.sr), b: Math.round(this.loopB! * this.sr) });
    else this.#post({ type: 'loop', a: null });
  }
  setLoopA(sec = this.position) { this.loopSectionId = ''; this.loopA = sec; if (this.loopB != null && this.loopB <= sec) this.loopB = null; this.#sendLoop(); }
  setLoopB(sec = this.position) {
    if (this.loopA == null || sec <= this.loopA) return;
    this.loopSectionId = '';
    this.loopB = sec; this.loopOn = true; this.#sendLoop();
  }
  toggleLoop() { if (this.loopA != null && this.loopB != null) { this.loopOn = !this.loopOn; this.#sendLoop(); } }
  clearLoop() { this.loopA = this.loopB = null; this.loopOn = false; this.loopSectionId = ''; this.#sendLoop(); }

  /** Posición que se está escuchando, extrapolada con el reloj de audio y con la vuelta del loop. */
  #estimate(): number {
    const ctx = this.#ctx;
    if (!ctx) return this.#lastPos;
    let est = this.#lastPos + Math.max(0, ctx.currentTime - this.#lastAudioT) * this.speed;
    if (this.loopActive && this.#lastPos < this.loopB! && est >= this.loopB!) {
      est = this.loopA! + ((est - this.loopA!) % (this.loopB! - this.loopA!));
    }
    // Lo que se oye va detrás de lo que se procesa: la latencia de salida del dispositivo.
    const lat = (('outputLatency' in ctx ? ctx.outputLatency : 0) || ctx.baseLatency || 0) * this.speed;
    let heard = est - lat;
    if (this.loopActive && heard < this.loopA! && est >= this.loopA!) heard += this.loopB! - this.loopA!;
    return Math.max(0, Math.min(this.duration, heard));
  }

  #rebase() { this.#lastPos = this.position; this.#lastAudioT = this.#ctx?.currentTime ?? 0; }

  // ---- secciones (A, B, C...): rangos con nombre sobre la línea de tiempo. Pueden dejar huecos; nunca se superponen.
  #sectionsKey(id: string) { return `stemshed.sections.${id}`; }
  #loadSections(id: string): Section[] {
    try {
      const raw = JSON.parse(localStorage.getItem(this.#sectionsKey(id)) ?? '[]') as Partial<Section & { t: number }>[];
      // Formato anterior: solo la marca de inicio; el fin era la marca siguiente.
      return raw.map((x, i) => ({ id: x.id!, name: x.name!, start: x.start ?? x.t!, end: x.end ?? raw[i + 1]?.start ?? raw[i + 1]?.t ?? this.duration }));
    } catch { return []; }
  }
  #saveSections() {
    if (!this.track) return;
    this.sections.sort((a, b) => a.start - b.start);
    try { localStorage.setItem(this.#sectionsKey(this.track.id), JSON.stringify(this.sections)); } catch { /* sin almacenamiento */ }
  }
  /** Sección donde está el cabezal (-1 si está en un hueco o antes de la primera). */
  get currentSection() {
    return this.sections.findIndex(s => this.position >= s.start - 0.05 && this.position < s.end);
  }
  addSection(t = this.position) {
    if (!this.track) return;
    const MIN = 0.5;
    const inside = this.sections.find(s => t > s.start + MIN && t < s.end - MIN);
    let created: Section;
    if (inside) {
      // Dentro de una sección: se parte en dos.
      created = { id: crypto.randomUUID(), name: '', start: t, end: inside.end };
      inside.end = t;
      if (this.loopSectionId === inside.id) this.#syncLoop(inside);
    } else {
      if (this.sections.some(s => t > s.start - MIN && t < s.end + MIN)) return; // pegada a un borde: no hace falta
      const next = this.sections.find(s => s.start > t);
      const end = next ? next.start : this.duration;
      if (end - t < MIN) return;
      created = { id: crypto.randomUUID(), name: '', start: t, end };
    }
    const used = new Set(this.sections.map(s => s.name));
    created.name = [...'ABCDEFGHIJKLMNOPQRSTUVWXYZ'].find(c => !used.has(c)) ?? `S${this.sections.length + 1}`;
    this.sections.push(created);
    this.selectedSection = created.id;
    this.#saveSections();
  }
  removeSection(id: string) {
    if (this.loopSectionId === id) this.clearLoop(); // el loop de una sección que ya no existe se apaga
    this.sections = this.sections.filter(s => s.id !== id);
    if (this.selectedSection === id) this.selectedSection = '';
    this.#saveSections();
  }
  renameSection(id: string, name: string) {
    const s = this.sections.find(x => x.id === id);
    if (s && name.trim()) { s.name = name.trim().slice(0, 12); this.#saveSections(); }
  }
  /** Mueve un borde. Si la sección vecina lo comparte, se mueven juntos; nunca se cruzan ni salen del tema. */
  setSectionEdge(id: string, edge: 'start' | 'end', t: number) {
    const MIN = 0.5, TOUCH = 0.05;
    const list = [...this.sections].sort((a, b) => a.start - b.start);
    const i = list.findIndex(s => s.id === id);
    if (i < 0) return;
    const s = list[i], prev = list[i - 1], next = list[i + 1];
    const touchPrev = !!prev && Math.abs(prev.end - s.start) < TOUCH, touchNext = !!next && Math.abs(s.end - next.start) < TOUCH;
    let moved: Section[];
    if (edge === 'start') {
      const lo = prev ? (touchPrev ? prev.start + MIN : prev.end) : 0;
      s.start = Math.max(lo, Math.min(t, s.end - MIN));
      if (touchPrev) prev.end = s.start;
      moved = touchPrev ? [s, prev] : [s];
    } else {
      const hi = next ? (touchNext ? next.end - MIN : next.start) : this.duration;
      s.end = Math.min(hi, Math.max(t, s.start + MIN));
      if (touchNext) next.start = s.end;
      moved = touchNext ? [s, next] : [s];
    }
    const linked = moved.find(m => m.id === this.loopSectionId);
    if (linked) this.#syncLoop(linked);
    this.#saveSections();
  }
  goSection(i: number) { const s = this.sections[i]; if (s) { this.selectedSection = s.id; this.seek(s.start); } }
  stepSection(dir: 1 | -1) {
    if (!this.sections.length) return;
    let cur = this.currentSection;
    if (cur < 0) cur = dir === 1 ? this.sections.filter(s => s.start <= this.position).length - 1 : this.sections.filter(s => s.start < this.position).length;
    // Hacia atrás, dentro de una sección ya avanzada, vuelve primero al comienzo de la propia sección.
    const backHere = dir === -1 && this.currentSection >= 0 && this.position - this.sections[cur].start > 1.5;
    const target = backHere ? cur : Math.max(0, Math.min(this.sections.length - 1, cur + dir));
    // Con un loop de sección activo, el loop acompaña el salto.
    if (this.loopSectionId && this.loopOn) this.#linkLoop(target); else this.goSection(target);
  }
  /** Repite una sección: fija el loop en sus límites y lo enlaza. De nuevo sobre la misma, lo apaga. */
  loopSection(i: number) {
    const s = this.sections[i];
    if (!s) return;
    if (this.loopSectionId === s.id && this.loopOn) { this.clearLoop(); return; }
    this.#linkLoop(i);
  }
  #linkLoop(i: number) {
    const s = this.sections[i];
    this.selectedSection = s.id; this.loopSectionId = s.id; this.loopOn = true;
    this.#syncLoop(s);
    this.seek(s.start);
  }
  #syncLoop(s: Section) { this.loopA = s.start; this.loopB = s.end; this.#sendLoop(); }

  #tick = () => {
    if (this.playing) this.position = this.#estimate();
    const mem = (performance as unknown as { memory?: { usedJSHeapSize: number } }).memory;
    if (mem) this.metrics.heapMB = mem.usedJSHeapSize / 1e6;
    this.#raf = requestAnimationFrame(this.#tick);
  };
}

export const player = new Player();
