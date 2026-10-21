import { player } from './player.svelte';
import { stemlist } from './stemlist.svelte';

export interface Job { state: 'idle' | 'running' | 'done' | 'error'; stage?: string; percent?: number; message?: string }

const STAGE_LABEL: Record<string, string> = { download: 'Bajando el tema', model: 'Preparando el modelo', separate: 'Separando', measure: 'Midiendo' };

class Separation {
  jobs = $state<Record<string, Job>>({});

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
