import { player } from './player.svelte';
import { stemlist } from './stemlist.svelte';

export interface Job { state: 'idle' | 'running' | 'done' | 'error'; stage?: string; percent?: number; message?: string }
/** Una separación según el motor: sirve aunque la haya empezado otra pantalla o la página se haya recargado. */
export interface ActiveJob { id: string; title: string; artist: string; state: 'running' | 'done' | 'error'; stage?: string; percent: number; message: string }

const STAGE_LABEL: Record<string, string> = { download: 'Bajando el tema', model: 'Preparando el modelo', separate: 'Separando', measure: 'Midiendo' };

class Separation {
  jobs = $state<Record<string, Job>>({});
  /** Lo que el motor está separando (o terminó hace menos de un minuto), con título y artista. */
  active = $state<ActiveJob[]>([]);
  #watchers = 0;
  #timer = 0;
  #running = new Set<string>();

  get processing() { return this.active.filter(j => j.state === 'running'); }
  get failed() { return this.active.filter(j => j.state === 'error'); }
  stageLabel(stage?: string) { return STAGE_LABEL[stage ?? ''] ?? 'Trabajando'; }

  /** Sondea al motor mientras haya alguna pantalla mirando (más seguido si hay algo en curso). */
  watch(on: boolean) {
    this.#watchers = Math.max(0, this.#watchers + (on ? 1 : -1));
    window.clearTimeout(this.#timer);
    if (this.#watchers > 0) void this.#poll();
  }

  async #poll() {
    try {
      const list: ActiveJob[] = await (await fetch('/engine/stems/jobs')).json();
      const now = new Set(list.filter(j => j.state === 'running').map(j => j.id));
      const finished = [...this.#running].some(id => !now.has(id) && list.some(j => j.id === id && j.state === 'done'));
      this.#running = now;
      this.active = list;
      if (finished) { await player.init(); await stemlist.load(); }  // terminó: aparece en la lista de descargados
    } catch { /* motor apagado: el resto de la interfaz lo informa */ }
    if (this.#watchers > 0) this.#timer = window.setTimeout(() => void this.#poll(), this.#running.size ? 1200 : 4000);
  }

  label(id: string) {
    const j = this.jobs[id];
    if (!j || j.state !== 'running') return '';
    return `${STAGE_LABEL[j.stage ?? ''] ?? 'Trabajando'}${j.percent ? ` ${j.percent} %` : '…'}`;
  }

  get busy() { return Object.values(this.jobs).some(j => j.state === 'running'); }

  async start(id: string) {
    this.jobs[id] = { state: 'running', stage: 'download', percent: 0 };
    const res = await fetch(`/engine/stems/${id}/separate`, { method: 'POST' });
    const body = await res.json();
    if (!res.ok) { this.jobs[id] = { state: 'error', message: body.message ?? 'No se pudo empezar la separación.' }; return; }
    if (body.state === 'done') { await this.#finish(id); return; }
    const timer = window.setInterval(async () => {
      try {
        const st: Job = await (await fetch(`/engine/stems/${id}/status`)).json();
        this.jobs[id] = st;
        if (st.state === 'running') return;
        window.clearInterval(timer);
        if (st.state === 'done') await this.#finish(id);
      } catch {
        window.clearInterval(timer);
        this.jobs[id] = { state: 'error', message: 'Se perdió la conexión con el motor.' };
      }
    }, 1500);
  }

  async #finish(id: string) {
    this.jobs[id] = { state: 'done' };
    await player.init(); // vuelve a leer la lista de temas separados
    await stemlist.load();
  }
}

export const separation = new Separation();
