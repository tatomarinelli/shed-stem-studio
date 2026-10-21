// Estado de la música unificada (todas las fuentes): lo muestran Fuentes (conexiones) y Música (catálogo).
export interface MusicStatus {
  tidal: { fetchedAt: number; refreshing: boolean; error: string; albums: number; tracks: number };
  local: { scanning: boolean; scanned: number; total: number };
  genres: { running: boolean; done: number; total: number };
}

class MusicStore {
  status = $state<MusicStatus | null>(null);
  sources = $state({ local: 0, tidal: 0 });
  /** Se incrementa cada vez que el catálogo cambió (para que Música vuelva a pedir). */
  version = $state(0);
  #timer = 0;
  #busy = false;

  get working() {
    const s = this.status;
    return !!s && (s.tidal.refreshing || s.local.scanning || s.genres.running);
  }

  async loadStatus() {
    try {
      const r = await (await fetch('/engine/music?kind=albums&limit=1')).json();
      const was = this.working;
      this.status = r.status;
      this.sources = r.facets.sources;
      if (was && !this.working) this.version++;
    } catch { /* el motor no responde: se deja el último estado */ }
    window.clearTimeout(this.#timer);
    if (this.working) this.#timer = window.setTimeout(() => this.loadStatus(), 2000);
  }

  async refresh(): Promise<boolean> {
    if (this.#busy) return false;
    this.#busy = true;
    try {
      const res = await fetch('/engine/music/refresh', { method: 'POST' });
      await this.loadStatus();
      return res.ok;
    } catch { return false; } finally { this.#busy = false; }
  }
}

export const music = new MusicStore();
