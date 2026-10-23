export interface ModelInfo { label: string; where: string; path: string; present: boolean; bytes: number }
export interface StorageItem { label: string; path: string; bytes: number; writable: boolean }
export interface StorageReport {
  env: { present: boolean; path: string; approxGb: number; step?: string; backend?: string | null };
  separation: ModelInfo[];
  separationInUse: string;
  recommendations: { provider: string; running: boolean; path: string; inUse: string | null; models: ModelInfo[] };
  storage: StorageItem[];
}
export interface Gpu { name: string; vramGB: number; usedGB: number | null; vendor?: string; accel?: string | null; llmAccel?: string | null; integrated?: boolean }
export interface Disk { path: string; totalGB: number; freeGB: number; usedPct: number }
export interface Candidate { id: string; label: string; module: string; gb: number | null; note: string; fits: boolean; reasons: string[]; withSeparation: boolean; partial?: boolean }
export interface HardwareReport {
  gpus: Gpu[]; ram: { totalGB: number; availableGB: number }; cpu: { name: string; threads: number }; disks: Disk[]; models: Candidate[];
}
export interface BackendOption { group?: 'available' | 'incompatible' | 'soon'; id: string; label: string; approxGb: number | null; installable: boolean; compatible: boolean; requires: string | null; recommended: boolean; verified: boolean; note: string }
export interface BackendReport { recommended: string; reason: string; gpu: string | null; options: BackendOption[] }
export interface LlmServer {
  installed: boolean; running: boolean; canInstall: boolean; approxGb: number;
  accel: 'cuda' | 'vulkan' | 'cpu'; gpu: string | null; job: Pull;
}
export interface Config { llmProvider: 'ollama' | 'llamacpp'; audioSources: string[]; dataDir: string; ollamaModelsDir: string; separationModelsDir: string; separationEnvDir: string; downloadDir: string; musicFolders: string[]; llmUrl: string; llmModel: string; recsContext?: 'demand' | 'now'; classifier?: 'off' | 'llm' | 'kev'; classifierUrl?: string; recsReviewer?: string }
export interface AudioSource { id: 'local' | 'tidal'; label: string; enabled: boolean; available: boolean; detail: string }
export interface Pull {
  state: 'idle' | 'running' | 'done' | 'error' | 'cancelled'; percent?: number; message?: string; done?: number; total?: number; rate?: number;
  step?: string; approx?: boolean;
  /** Epoch (s) de cuando arrancó y de la última vez que avanzó algo de verdad; los pone el motor. */
  startedAt?: number; updated?: number;
  /** El motor está cortando la tarea; `cancelable: false` = ya no se puede cortar sin dejarla a medias. */
  cancelling?: boolean; cancelable?: boolean;
  /** Aviso de la interfaz (por ejemplo, por qué no se pudo cancelar). */
  notice?: string;
}
export interface DetectedServer { kind: 'ollama' | 'llamacpp' | 'openai'; port: number; url: string; version: string | null; models: string[]; current: boolean; own: boolean }
export interface DetectedGguf { path: string; name: string; bytes: number; folder: string }
export interface LlmDetect {
  servers: DetectedServer[]; binaries: { ollama: string | null; llamaServer: string | null };
  ollamaFolders: { path: string; models: number }[]; ggufs: DetectedGguf[];
  own: { running: boolean; port: number | null; model: string | null; job: Pull }; current: string; provider: 'ollama' | 'llamacpp';
}
export interface Job { kind: string; label: string; percent?: number; step?: string }
export interface Services {
  engine: { host: string; port: number; pid: number; uptimeSec: number; docker: boolean; origins: string[]; hostPaths: Record<string, { path: string; var: string }> };
  llm: { url: string; provider?: string; running: boolean; own: boolean; loaded: { name: string; bytes: number }[]; installed: number };
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

  /** Sondeos de tareas largas, uno por clave: cada tarea se mira hasta que deja de estar en curso (también tras recargar la página). */
  #timers = new Map<string, number>();

  #watch(key: string, tick: () => Promise<boolean>, ms: number, after?: () => Promise<void>) {
    if (this.#timers.has(key)) return; // ya se está siguiendo
    const id = window.setInterval(async () => {
      let running = false;
      try { running = await tick(); } catch { running = true; /* un tropiezo de red no corta el seguimiento */ }
      if (running) return;
      window.clearInterval(id);
      this.#timers.delete(key);
      if (after) await after();
    }, ms);
    this.#timers.set(key, id);
  }

  async #json<T>(url: string): Promise<T> { return (await fetch(url)).json(); }

  watchEnv() { this.#watch('env', async () => { this.envPull = await this.#json<Pull>('/engine/env/status'); return this.envPull.state === 'running'; }, 2000, () => this.load()); }
  watchSep() { this.#watch('sep', async () => { this.sepPull = await this.#json<Pull>('/engine/models/separation/status'); return this.sepPull.state === 'running'; }, 1500, () => this.load()); }
  watchFfmpeg() { this.#watch('ffmpeg', async () => { await this.loadFfmpeg(); return this.ffmpeg?.job.state === 'running'; }, 2000); }
  watchLlmInstall() { this.#watch('llm', async () => { await this.loadLlm(); return this.llm?.job.state === 'running'; }, 2000, () => this.load()); }
  watchPull(id: string) {
    this.#watch('pull:' + id, async () => {
      const st = await this.#json<Pull>(`/engine/models/${encodeURIComponent(id)}/status`);
      this.pulls[id] = st;
      return st.state === 'running';
    }, 1500, () => this.load());
  }

  /** Retoma el estado de las tareas que siguen en el motor (por ejemplo, tras recargar la página) y vuelve a seguirlas. */
  async syncJobs() {
    try {
      const [env, sep, ff, llm] = await Promise.all([
        this.#json<Pull>('/engine/env/status'), this.#json<Pull>('/engine/models/separation/status'),
        this.#json<{ installed: boolean; canInstall: boolean; job: Pull }>('/engine/ffmpeg/status'), this.#json<LlmServer>('/engine/llm/status'),
      ]);
      if (env.state !== 'idle') this.envPull = env;
      if (env.state === 'running') this.watchEnv();
      if (sep.state !== 'idle') this.sepPull = sep;
      if (sep.state === 'running') this.watchSep();
      this.ffmpeg = { ...ff, job: ff.job.state === 'idle' && this.ffmpeg?.job.state === 'error' ? this.ffmpeg.job : ff.job };
      if (ff.job.state === 'running') this.watchFfmpeg();
      this.llm = { ...llm, job: llm.job.state === 'idle' && this.llm?.job.state === 'error' ? this.llm.job : llm.job };
      if (llm.job.state === 'running') this.watchLlmInstall();
      const all = await this.#json<Record<string, Pull>>('/engine/models/pulls');
      for (const [id, st] of Object.entries(all)) {
        if (st.state === 'idle' || (this.pulls[id]?.state === 'error' && st.state !== 'running')) continue;
        this.pulls[id] = st;
        if (st.state === 'running') this.watchPull(id);
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

  envPull = $state<Pull>({ state: 'idle' });

  ffmpeg = $state<{ installed: boolean; canInstall: boolean; job: Pull } | null>(null);

  async loadFfmpeg() {
    try {
      const res = await fetch('/engine/ffmpeg/status');
      if (res.ok) this.ffmpeg = await res.json();
    } catch { /* sin motor: el estado general lo informa */ }
  }

  async installFfmpeg() {
    const res = await fetch('/engine/ffmpeg/install', { method: 'POST' });
    const body = await res.json();
    if (!res.ok) { if (this.ffmpeg) this.ffmpeg = { ...this.ffmpeg, job: { state: 'error', message: body.message } }; return; }
    if (this.ffmpeg) this.ffmpeg = { ...this.ffmpeg, job: body };
    this.watchFfmpeg();
  }

  /** Corta una tarea. El motor contesta al toque; si no se puede (por ejemplo, ya está instalando), el motivo queda en `notice`. */
  async #cancel(url: string, current: () => Pull | undefined, apply: (j: Pull) => void) {
    const j = current();
    if (j) apply({ ...j, cancelling: true, notice: undefined });
    try {
      const res = await fetch(url, { method: 'POST' });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const now = current();
        if (now) apply({ ...now, cancelling: false, notice: body.message ?? 'No se pudo cancelar.' });
      }
    } catch {
      const now = current();
      if (now) apply({ ...now, cancelling: false, notice: 'No pude hablar con el motor.' });
    }
  }

  cancelEnv() { return this.#cancel('/engine/env/cancel', () => this.envPull, j => (this.envPull = j)); }
  cancelSepModel() { return this.#cancel('/engine/models/separation/cancel', () => this.sepPull, j => (this.sepPull = j)); }
  cancelFfmpeg() { return this.#cancel('/engine/ffmpeg/cancel', () => this.ffmpeg?.job, j => { if (this.ffmpeg) this.ffmpeg = { ...this.ffmpeg, job: j }; }); }
  cancelLlmInstall() { return this.#cancel('/engine/llm/cancel', () => this.llm?.job, j => { if (this.llm) this.llm = { ...this.llm, job: j }; }); }
  cancelPull(id: string) { return this.#cancel(`/engine/models/${encodeURIComponent(id)}/cancel`, () => this.pulls[id], j => (this.pulls[id] = j)); }

  llm = $state<LlmServer | null>(null);

  async loadLlm() {
    try {
      const res = await fetch('/engine/llm/status');
      if (res.ok) this.llm = await res.json();
    } catch { /* sin motor: el estado general lo informa */ }
  }

  async installLlm() {
    const res = await fetch('/engine/llm/install', { method: 'POST' });
    const body = await res.json();
    if (!res.ok) { if (this.llm) this.llm = { ...this.llm, job: { state: 'error', message: body.message } }; return; }
    if (this.llm) this.llm = { ...this.llm, job: body };
    this.watchLlmInstall();
  }

  /** Servidores de modelos que el equipo ya tiene (Ollama, llama.cpp…), modelos .gguf y binarios. Solo mira: no instala ni prende nada. */
  detected = $state<LlmDetect | null>(null);
  detecting = $state(false);
  detectError = $state('');

  async detectLlm() {
    this.detecting = true;
    this.detectError = '';
    try {
      const res = await fetch('/engine/llm/detect');
      if (res.ok) this.detected = await res.json();
      else this.detectError = 'No se pudo buscar.';
    } catch { this.detectError = 'No pude hablar con el motor.'; }
    this.detecting = false;
  }

  /** Usa un servidor ya prendido para las recomendaciones (solo se llama tras la confirmación del usuario). */
  async useServer(s: DetectedServer): Promise<boolean> {
    const ok = await this.save({ llmUrl: s.url, llmProvider: s.kind === 'ollama' ? 'ollama' : 'llamacpp' });
    await this.detectLlm();
    return ok;
  }

  /** Prende llama-server con un modelo detectado y, cuando carga, lo deja en uso. Con confirmación previa. */
  async startLlamaCpp(modelPath: string) {
    this.detectError = '';
    const res = await fetch('/engine/llm/llamacpp/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model: modelPath }) });
    const body = await res.json();
    if (!res.ok) { this.detectError = body.message ?? 'No se pudo prender.'; return; }
    await this.detectLlm();
    this.#watch('llama', async () => {
      await this.detectLlm();
      return this.detected?.own.job.state === 'running';
    }, 1500, async () => {
      const own = this.detected?.own;
      if (own?.running && own.port) {
        const srv = this.detected?.servers.find(x => x.port === own.port);
        if (srv) await this.useServer(srv);
      }
    });
  }

  /** Apaga el llama-server de la app. Si era el que estaba en uso, las recomendaciones vuelven a Ollama (un servidor apagado no responde). */
  async stopLlamaCpp() {
    const port = this.detected?.own.port;
    const wasCurrent = !!this.detected?.servers.find(x => x.port === port && x.current);
    await fetch('/engine/llm/llamacpp/stop', { method: 'POST' });
    await this.detectLlm();
    if (wasCurrent) {
      const ollama = this.detected?.servers.find(x => x.kind === 'ollama');
      await this.save({ llmProvider: 'ollama', llmUrl: ollama?.url ?? 'http://127.0.0.1:11500' });
      await this.detectLlm();
    }
  }

  backends = $state<BackendReport | null>(null);
  /** Motor elegido por el usuario; null = el recomendado. */
  backend = $state<string | null>(null);

  async loadBackends() {
    try {
      const res = await fetch('/engine/backends');
      if (res.ok) this.backends = await res.json();
    } catch { /* sin motor: el estado general lo informa */ }
  }

  async installEnv() {
    this.envPull = { state: 'running', percent: 0, step: 'Preparando' };
    const res = await fetch('/engine/env/install', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(this.backend ? { backend: this.backend } : {}) });
    const body = await res.json();
    if (!res.ok) { this.envPull = { state: 'error', message: body.message }; return; }
    this.envPull = body;
    this.watchEnv();
  }

  async pullSeparation() {
    this.sepPull = { state: 'running', percent: 0, step: 'Preparando' };
    const res = await fetch('/engine/models/separation/download', { method: 'POST' });
    const body = await res.json();
    if (!res.ok) { this.sepPull = { state: 'error', message: body.message }; return; }
    this.sepPull = body;
    this.watchSep();
  }

  async pull(id: string) {
    this.error = '';
    this.pulls[id] = { state: 'running', percent: 0, step: 'Preparando' };
    const res = await fetch(`/engine/models/${encodeURIComponent(id)}/pull`, { method: 'POST' });
    const body = await res.json();
    if (!res.ok) { this.pulls[id] = { state: 'error', message: body.message }; return; }
    this.pulls[id] = body;
    this.watchPull(id);
  }

  /** Nombre de la descarga de modelo que está en curso, si hay una (el motor hace de a una). */
  get pullingNow(): string | null {
    return Object.entries(this.pulls).find(([, p]) => p.state === 'running')?.[0] ?? null;
  }
}

export const settings = new Settings();
