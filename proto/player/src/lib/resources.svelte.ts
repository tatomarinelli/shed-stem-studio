// Monitor de recursos: estado y sondeo de GET /engine/resources.
// Se sondea cada 1 s solo mientras alguien lo mira (panel abierto o barra del menú con un trabajo activo) y la pestaña está visible.
// Cada pedido trae solo el historial nuevo (?since=); el motor apaga su muestreador solo cuando dejan de llegar pedidos.

export interface ResGpu {
  index: number; name: string; vendor: 'nvidia' | 'amd'; utilPercent: number | null; memUsedBytes: number | null; memTotalBytes: number | null;
  tempC: number | null; powerW: number | null; unverified?: boolean;
}
export interface ResDisk { path: string; keys: string[]; totalBytes: number; freeBytes: number; usedPercent: number | null }
export interface ResProcess { pid: number; role: string; name: string; inApp: boolean; cpuPercent: number | null; rssBytes: number | null; gpuMemBytes: number | null }
export interface ResHistory { t: number[]; cpu: (number | null)[]; ram: (number | null)[]; gpuUtil: (number | null)[]; gpuMem: (number | null)[] }
export interface ResSnapshot {
  now: number; intervalMs: number; platform: string;
  cpu: { percent: number | null; cores: number | null } | null;
  ram: { totalBytes: number; usedBytes: number; availableBytes: number; percent: number | null } | null;
  gpus: ResGpu[]; disks: ResDisk[]; processes: ResProcess[]; jobs: { kind: string; label: string; percent?: number; step?: string }[]; errors: string[];
  history: ResHistory;
}

export const WINDOW_MS = 300_000;
const EMPTY = (): ResHistory => ({ t: [], cpu: [], ram: [], gpuUtil: [], gpuMem: [] });
const KEYS = ['cpu', 'ram', 'gpuUtil', 'gpuMem'] as const;

const GIB = 1024 ** 3;
export const gb = (b: number | null | undefined, digits = 1) => (b == null ? '—' : `${(b / GIB).toLocaleString('es', { minimumFractionDigits: digits, maximumFractionDigits: digits })} GB`);
export const mb = (b: number | null | undefined) => (b == null ? '—' : b >= GIB ? gb(b) : `${Math.round(b / 1048576).toLocaleString('es')} MB`);
export const pct = (v: number | null | undefined) => (v == null ? '—' : `${Math.round(v)} %`);

class Resources {
  data = $state<ResSnapshot | null>(null);
  hist = $state<ResHistory>(EMPTY());
  /** El motor no responde (o está apagado). */
  offline = $state(false);
  #watchers = 0;
  #timer = 0;
  #since = 0;
  #busy = false;

  constructor() {
    document.addEventListener('visibilitychange', () => this.#sync());
  }

  /** Empieza a mirar. Devuelve la función que deja de mirar (se puede llamar más de una vez sin descontar de más). */
  watch(): () => void {
    this.#watchers++;
    this.#sync();
    let done = false;
    return () => {
      if (done) return;
      done = true;
      this.#watchers--;
      this.#sync();
    };
  }

  #sync() {
    window.clearInterval(this.#timer);
    this.#timer = 0;
    if (this.#watchers > 0 && document.visibilityState === 'visible') {
      void this.#poll();
      this.#timer = window.setInterval(() => void this.#poll(), 1000);
    } else if (this.#watchers === 0) {
      this.data = null; // sin nadie mirando, lo que quedó ya es viejo
    }
  }

  async #poll() {
    if (this.#busy) return;
    this.#busy = true;
    try {
      const res = await fetch(`/engine/resources${this.#since ? `?since=${this.#since}` : ''}`);
      if (!res.ok) throw new Error(String(res.status));
      const d: ResSnapshot = await res.json();
      this.#merge(d.history, d.now);
      this.data = d;
      this.offline = false;
    } catch {
      this.offline = true;
    } finally {
      this.#busy = false;
    }
  }

  #merge(add: ResHistory, now: number) {
    const h = this.hist;
    const cut = now - WINDOW_MS;
    let from = 0;
    while (from < h.t.length && h.t[from] < cut) from++;
    const next = EMPTY();
    next.t = h.t.slice(from).concat(add.t);
    for (const k of KEYS) next[k] = h[k].slice(from).concat(add[k]);
    this.hist = next;
    if (next.t.length) this.#since = next.t[next.t.length - 1];
  }
}

export const resources = new Resources();
