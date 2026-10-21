export interface ModelInfo { label: string; where: string; path: string; present: boolean; bytes: number }
export interface StorageItem { label: string; path: string; bytes: number; writable: boolean }
export interface StorageReport {
  env: { present: boolean; path: string; approxGb: number; step?: string };
  separation: ModelInfo[];
  separationInUse: string;
  recommendations: { provider: string; running: boolean; path: string; inUse: string | null; models: ModelInfo[] };
  storage: StorageItem[];
}
export interface Gpu { name: string; vramGB: number; usedGB: number }
export interface Disk { path: string; totalGB: number; freeGB: number; usedPct: number }
export interface Candidate { id: string; label: string; module: string; gb: number | null; note: string; fits: boolean; reasons: string[]; withSeparation: boolean }
export interface HardwareReport {
  gpus: Gpu[]; ram: { totalGB: number; availableGB: number }; cpu: { name: string; threads: number }; disks: Disk[]; models: Candidate[];
}
export interface Config { audioSources: string[]; dataDir: string; ollamaModelsDir: string; separationModelsDir: string; separationEnvDir: string; musicFolders: string[]; llmUrl: string; llmModel: string }
export interface AudioSource { id: 'local' | 'tidal'; label: string; enabled: boolean; available: boolean; detail: string }
export interface Pull { state: 'idle' | 'running' | 'done' | 'error'; percent?: number; message?: string; done?: number; total?: number; rate?: number; step?: string; approx?: boolean }
export interface Job { kind: string; label: string; percent?: number; step?: string }
export interface Services {
  engine: { host: string; port: number; pid: number; uptimeSec: number; docker: boolean; origins: string[]; hostPaths: Record<string, { path: string; var: string }> };
  llm: { url: string; running: boolean; own: boolean; loaded: { name: string; bytes: number }[]; installed: number };
  tidal: { connected: boolean };
  scheduler: { auto: boolean; cadenceHours: number };
  jobs: Job[];
}

class Settings {
  state = $state<'loading' | 'ready' | 'no_engine'>('loading');
  storage = $state<StorageReport | null>(null);
  hardware = $state<HardwareReport | null>(null);
  pulls = $state<Record<string, Pull>>({});
  sepPull = $state<Pull>({ state: 'idle' });
  services = $state<Services | null>(null);
  shutdownMessage = $state('');
  #svcTimer = 0;

  async loadServices() {
    try {
      const res = await fetch('/engine/services');
      if (res.ok) this.services = await res.json();
    } catch { /* motor apagado: el estado general lo informa */ }
  }

  #watchers = 0;

  /** Varias pantallas pueden mirar los servicios a la vez; el sondeo se apaga cuando no queda nadie. */
  watchServices(on: boolean) {
    this.#watchers = Math.max(0, this.#watchers + (on ? 1 : -1));
    window.clearInterval(this.#svcTimer);
    if (this.#watchers === 0) return;
    void this.loadServices();
    this.#svcTimer = window.setInterval(() => void this.loadServices(), 4000);
  }

  /** Retoma el estado de las descargas que siguen en el motor (por ejemplo, tras recargar la página). */
  async syncJobs(pullIds: string[] = []) {
    try {
      const [e, s] = await Promise.all([fetch('/engine/env/status'), fetch('/engine/models/separation/status')]);
      const env: Pull = await e.json(), sep: Pull = await s.json();
      if (env.state !== 'idle' && this.envPull.state !== 'running') this.envPull = env;
      else if (env.state === 'running') this.envPull = env;
      if (sep.state !== 'idle' && this.sepPull.state !== 'running') this.sepPull = sep;
      else if (sep.state === 'running') this.sepPull = sep;
      for (const id of pullIds) {
        const st: Pull = await (await fetch(`/engine/models/${encodeURIComponent(id)}/status`)).json();
        if (st.state !== 'idle') this.pulls[id] = st;
      }
    } catch { /* motor apagado: lo informa el estado general */ }
  }

  /** Abre una carpeta de Ajustes en el explorador del sistema. Devuelve el motivo si no se pudo. */
  async openFolder(key: 'dataDir' | 'separationEnvDir' | 'separationModelsDir' | 'ollamaModelsDir'): Promise<string> {
    try {
      const res = await fetch('/engine/open-folder', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key }) });
      return res.ok ? '' : (await res.json()).message ?? 'No se pudo abrir la carpeta.';
    } catch { return 'No pude hablar con el motor.'; }
  }

  async shutdown() {
    this.shutdownMessage = '';
    try {
      const res = await fetch('/engine/shutdown', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"confirm":true}' });
      const body = await res.json();
      if (!res.ok) { this.shutdownMessage = body.message ?? 'No se pudo apagar.'; await this.loadServices(); return; }
      this.watchServices(false);
      this.services = null;
      this.state = 'no_engine';
    } catch {
      this.shutdownMessage = 'No pude hablar con el motor.';
    }
  }
  error = $state('');
  sources = $state<AudioSource[]>([]);
  config = $state<Config | null>(null);
  effective = $state<Config | null>(null);
  saveMessage = $state<{ ok: boolean; text: string } | null>(null);
  #timer = 0;

  async load() {
    try {
      const [s, h, c, a] = await Promise.all([fetch('/engine/storage'), fetch('/engine/hardware'), fetch('/engine/settings'), fetch('/engine/sources')]);
      if (!s.ok || !h.ok || !c.ok || !a.ok) throw new Error('El motor respondió con un error.');
      this.storage = await s.json();
      this.hardware = await h.json();
      this.sources = await a.json();
      const cfg = await c.json();
      this.config = cfg.settings;
      this.effective = cfg.effective;
      this.state = 'ready';
    } catch {
      this.state = 'no_engine';
    }
  }

  /** Guarda un cambio de ajustes. Devuelve true si el motor lo aceptó; si no, deja el motivo en saveMessage. */
  async save(patch: Partial<Config>): Promise<boolean> {
    this.saveMessage = null;
    try {
      const res = await fetch('/engine/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch) });
      const body = await res.json();
      if (!res.ok) { this.saveMessage = { ok: false, text: body.message ?? 'No se pudo guardar.' }; return false; }
      this.saveMessage = { ok: true, text: body.needsRestart ? 'Guardado. Reiniciá Ollama para que use la carpeta nueva.' : 'Guardado.' };
      await this.load();
      return true;
    } catch {
      this.saveMessage = { ok: false, text: 'No pude hablar con el motor.' };
      return false;
    }
  }

  #sepTimer = 0;
  #envTimer = 0;
  envPull = $state<Pull>({ state: 'idle' });

  async installEnv() {
    this.envPull = { state: 'running', percent: 0 };
    const res = await fetch('/engine/env/install', { method: 'POST' });
    const body = await res.json();
    if (!res.ok) { this.envPull = { state: 'error', message: body.message }; return; }
    window.clearInterval(this.#envTimer);
    this.#envTimer = window.setInterval(async () => {
      this.envPull = await (await fetch('/engine/env/status')).json();
      if (this.envPull.state === 'running') return;
      window.clearInterval(this.#envTimer);
      await this.load();
    }, 2000);
  }

  async pullSeparation() {
    this.sepPull = { state: 'running', percent: 0 };
    const res = await fetch('/engine/models/separation/download', { method: 'POST' });
    const body = await res.json();
    if (!res.ok) { this.sepPull = { state: 'error', message: body.message }; return; }
    window.clearInterval(this.#sepTimer);
    this.#sepTimer = window.setInterval(async () => {
      this.sepPull = await (await fetch('/engine/models/separation/status')).json();
      if (this.sepPull.state === 'running') return;
      window.clearInterval(this.#sepTimer);
      await this.load();
    }, 1500);
  }

  async pull(id: string) {
    this.error = '';
    this.pulls[id] = { state: 'running', percent: 0 };
    const res = await fetch(`/engine/models/${encodeURIComponent(id)}/pull`, { method: 'POST' });
    const body = await res.json();
    if (!res.ok) { this.pulls[id] = { state: 'error', message: body.message }; return; }
    window.clearInterval(this.#timer);
    this.#timer = window.setInterval(async () => {
      const st: Pull = await (await fetch(`/engine/models/${encodeURIComponent(id)}/status`)).json();
      this.pulls[id] = st;
      if (st.state === 'running') return;
      window.clearInterval(this.#timer);
      await this.load();
    }, 1500);
  }
}

export const settings = new Settings();
