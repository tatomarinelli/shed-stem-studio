import { toast } from './toast.svelte';

export interface DlJob {
  state: 'idle' | 'running' | 'done' | 'error' | 'cancelled';
  percent?: number; step?: string; message?: string; cancelling?: boolean;
  file?: string; dir?: string; name?: string; tagged?: boolean; note?: string;
}
interface Item { file: string; dir: string; title: string; artist: string; quality?: string }
export interface Quality { id: string; label: string; hint: string; kind: 'orig' | 'aac' | 'mp3'; kbps: number | null; available: boolean; reason: string }
export interface Options { dir: string; free: number; ffmpeg: boolean; mp3: boolean; qualities: Quality[]; ipod: { label: string; hint: string; qualities: string[] } }
/** Un tema elegido: el motor busca su audio con `ids` (o `id`); `seconds` solo sirve para estimar el peso. */
export interface Pick { id?: string; ids?: { local?: string; tidal?: string }; artist?: string; title?: string; album?: string; seconds?: number }
export interface Estimate { items: { bytes: number | null; exact: boolean; why: string }[]; bytes: number; unknown: number; approx: boolean; free: number; enough: boolean; dir: string }
export interface BatchItem { id: string | null; title: string; artist: string; state: 'pending' | 'running' | 'done' | 'already' | 'error' | 'cancelled'; message: string }
export interface Batch {
  state: 'running' | 'done' | 'cancelled' | 'error'; total: number; done: number; current: string | null; quality: string; summary: string; dir: string; startedAt: number;
  items: BatchItem[]; currentJob?: { id: string; title: string; artist: string; percent: number; step: string };
}
const PREFS = 'stemshed.download';

/** Descarga de temas a archivos (carpeta `downloadDir` de Ajustes) y "abrir en carpeta". Solo se dispara con un clic. */
class Downloads {
  dir = $state('');
  items = $state<Record<string, Item>>({});
  jobs = $state<Record<string, DlJob>>({});
  options = $state<Options | null>(null);
  quality = $state('original');
  ipod = $state(false);
  folders = $state(false);
  batch = $state<Batch | null>(null);
  #timer = 0;
  #btimer = 0;
  #dismissed = 0;
  #loaded = false;

  constructor() {
    try {
      const p = JSON.parse(localStorage.getItem(PREFS) ?? 'null');
      if (p && typeof p.quality === 'string') { this.quality = p.quality; this.ipod = !!p.ipod; this.folders = !!p.folders; }
    } catch { /* sin almacenamiento: quedan los valores por defecto */ }
  }

  #save() { try { localStorage.setItem(PREFS, JSON.stringify({ quality: this.quality, ipod: this.ipod, folders: this.folders })); } catch { /* sin almacenamiento */ } }
  /** Calidad que se usa de verdad (el perfil iPod solo admite MP3 128 o 192). */
  get q() { return this.ipod && !(this.options?.ipod.qualities ?? ['mp3_128', 'mp3_192']).includes(this.quality) ? 'mp3_128' : this.quality; }
  get key() { return this.q + (this.ipod ? ':ipod' : ''); }
  get qualityLabel() { return this.options?.qualities.find(x => x.id === this.q)?.label ?? this.q; }
  setQuality(q: string) { this.quality = q; this.#save(); }
  setIpod(on: boolean) { this.ipod = on; if (on) this.quality = this.q; this.#save(); }
  setFolders(on: boolean) { this.folders = on; this.#save(); }

  async loadOptions() {
    try { this.options = await (await fetch('/engine/download/options')).json(); } catch { /* motor apagado */ }
  }


  /** Lee la lista una sola vez (muchas filas lo piden a la vez). */
  ensure() { if (!this.#loaded) { this.#loaded = true; void this.load(); void this.loadOptions(); } }

  async load() {
    try {
      const r = await (await fetch('/engine/downloads')).json();
      this.dir = r.dir; this.items = r.items;
      const b: Batch | null = r.batch;
      if (b && b.state === 'running' && b.startedAt !== this.#dismissed) { this.batch = b; this.#pollBatch(); }   // un lote ya terminado no reaparece al recargar
      for (const j of r.jobs as (DlJob & { id: string })[]) if (j.state === 'running' && !this.jobs[j.id]) { this.jobs[j.id] = j; this.#poll(); }
    } catch { /* motor apagado: el resto de la interfaz lo informa */ }
  }

  /** Estado de un tema: en curso, con error, o ya descargado. */
  of(id?: string): DlJob | undefined {
    if (!id) return undefined;
    const j = this.jobs[id];
    if (j && j.state !== 'done') return j;
    const it = this.items[`${id}|${this.key}`];
    return it ? { state: 'done', file: it.file, dir: it.dir } : j;
  }

  get busy() { return Object.values(this.jobs).some(j => j.state === 'running'); }

  async start(id: string) {
    this.jobs[id] = { state: 'running', percent: 0, step: 'Preparando' };
    try {
      const res = await fetch(`/engine/download/${id}/start`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ quality: this.q, profile: this.ipod ? 'ipod' : undefined }) });
      const body = await res.json();
      if (!res.ok) { this.#fail(id, body.message ?? 'No se pudo empezar la descarga.'); return; }
      if (body.already) { delete this.jobs[id]; await this.load(); toast.show(`Ya estaba descargado en ${body.dir}.`); return; }
      this.jobs[id] = body;
      this.#poll();
    } catch { this.#fail(id, 'No pude hablar con el motor.'); }
  }

  #fail(id: string, message: string) {
    this.jobs[id] = { state: 'error', message };
    toast.show(message, 'warn');
  }

  async cancel(id: string) {
    const j = this.jobs[id];
    if (j) this.jobs[id] = { ...j, cancelling: true };
    try { await fetch(`/engine/download/${id}/cancel`, { method: 'POST' }); } catch { /* el sondeo muestra el estado real */ }
  }

  /** Muestra el archivo (por id de tema) o una carpeta conocida (por ruta) en el administrador de archivos. */
  async reveal(arg: { id?: string; path?: string; original?: boolean }) {
    try {
      const res = await fetch('/engine/reveal', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(arg.id ? { quality: this.key, ...arg } : arg) });
      if (!res.ok) toast.show((await res.json()).message ?? 'No se pudo abrir la carpeta.', 'warn');
    } catch { toast.show('No pude hablar con el motor.', 'warn'); }
  }

  async #post<T>(url: string, body: object): Promise<{ ok: boolean; data: T & { message?: string } }> {
    const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    return { ok: res.ok, data: await res.json() };
  }

  /** Peso estimado de una selección con la calidad elegida (null si el motor no contesta). */
  async estimate(picks: Pick[]): Promise<Estimate | null> {
    try {
      const r = await this.#post<Estimate>('/engine/download/estimate', { items: picks, quality: this.q, profile: this.ipod ? 'ipod' : undefined });
      return r.ok ? r.data : null;
    } catch { return null; }
  }

  /** Baja la selección en serie (solo al apretar el botón). Devuelve el motivo si no pudo empezar. */
  async startBatch(picks: Pick[]): Promise<string> {
    try {
      const r = await this.#post<Batch>('/engine/download/batch/start', { items: picks, quality: this.q, profile: this.ipod ? 'ipod' : undefined, folders: this.folders });
      if (!r.ok) return r.data.message ?? 'No se pudo empezar la descarga.';
      this.batch = r.data;
      this.#pollBatch();
      return '';
    } catch { return 'No pude hablar con el motor.'; }
  }

  async cancelBatch(mode: 'all' | 'current') {
    try { await this.#post('/engine/download/batch/cancel', { mode }); } catch { /* el sondeo muestra el estado real */ }
  }

  dismissBatch() { if (this.batch) this.#dismissed = this.batch.startedAt; this.batch = null; }

  #pollBatch() {
    if (this.#btimer) return;
    let last = -1;
    this.#btimer = window.setInterval(async () => {
      try {
        const b: Batch | null = (await (await fetch('/engine/download/batch/status')).json()).batch;
        if (b && b.startedAt !== this.#dismissed) this.batch = b;
        if (b && b.done !== last) { last = b.done; await this.load(); }
        if (!b || b.state !== 'running') { window.clearInterval(this.#btimer); this.#btimer = 0; await this.load(); }
      } catch { window.clearInterval(this.#btimer); this.#btimer = 0; }
    }, 1000);
  }

  #poll() {
    if (this.#timer) return;
    this.#timer = window.setInterval(async () => {
      const running = Object.entries(this.jobs).filter(([, j]) => j.state === 'running').map(([id]) => id);
      if (!running.length) { window.clearInterval(this.#timer); this.#timer = 0; return; }
      for (const id of running) {
        try {
          const st: DlJob = await (await fetch(`/engine/download/${id}/status?q=${encodeURIComponent(this.key)}`)).json();
          if (st.state === 'running') { this.jobs[id] = st; continue; }
          if (st.state === 'done') {
            this.jobs[id] = st;
            await this.load();
            toast.show(`Descargado: ${st.name ?? 'listo'}${st.dir ? ` · en ${st.dir}` : ''}${st.tagged === false ? ' (sin etiquetas)' : ''}`);
          } else if (st.state === 'cancelled') delete this.jobs[id];
          else if (st.state === 'error') this.#fail(id, st.message || 'Falló la descarga.');
          else delete this.jobs[id];
        } catch { this.#fail(id, 'Se perdió la conexión con el motor.'); }
      }
    }, 1000);
  }
}

export const downloads = new Downloads();
