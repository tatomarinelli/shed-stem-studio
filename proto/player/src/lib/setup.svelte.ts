// Asistente de primer inicio: el estado de cada paso lo calcula el motor (GET /engine/setup/status).
export type StepState = 'done' | 'pending' | 'running' | 'error' | 'skipped';
export interface Step { id: string; label: string; state: StepState; detail: Record<string, unknown> }
export interface SetupStatus { steps: Step[]; complete: boolean; missing: string[]; closed: boolean; show: boolean; notice: boolean }

/** Páginas del asistente, en orden. "modelos" junta los pasos del motor "separacion" y "modelo"; las de las puntas son solo de pantalla. */
export const PAGES = ['bienvenida', 'carpetas', 'modelos', 'musica', 'perfil', 'listo'] as const;
export type Page = (typeof PAGES)[number];
export const TITLES: Record<Page, string> = {
  bienvenida: 'Bienvenida', carpetas: 'Dónde guardar', modelos: 'Modelos', musica: 'Fuentes', perfil: 'Perfil de gustos', listo: 'Listo',
};
/** Páginas que se pueden dejar para más tarde. */
export const SKIPPABLE: Page[] = ['modelos', 'musica', 'perfil'];
/** Pasos del motor que cubre cada página. */
const ENGINE_STEPS: Partial<Record<Page, string[]>> = { modelos: ['separacion', 'modelo'], musica: ['musica'], perfil: ['perfil'] };
/** A qué página lleva cada paso del motor (para "Ir al paso"). */
export const PAGE_OF: Record<string, Page> = { separacion: 'modelos', modelo: 'modelos', musica: 'musica', perfil: 'perfil' };

const post = (url: string, body: unknown = {}) => fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

class Setup {
  status = $state<SetupStatus | null>(null);
  engine = $state<'unknown' | 'ok' | 'off'>('unknown');
  open = $state(false);
  page = $state<Page>('bienvenida');
  noticeHidden = $state(false);
  #timer = 0;

  get index() { return PAGES.indexOf(this.page); }
  step(id: string) { return this.status?.steps.find(s => s.id === id); }

  /** Estado de una página: el peor de los pasos del motor que cubre. */
  pageState(page: Page): StepState | '' {
    const ids = ENGINE_STEPS[page];
    if (!ids) return '';
    const st = ids.map(id => this.step(id)?.state ?? 'pending');
    if (st.every(x => x === 'done')) return 'done';
    for (const x of ['error', 'running'] as const) if (st.includes(x)) return x;
    if (st.every(x => x === 'done' || x === 'skipped')) return 'skipped';
    return 'pending';
  }

  async load() {
    try {
      const res = await fetch('/engine/setup/status');
      if (!res.ok) throw new Error();
      this.status = await res.json();
      this.engine = 'ok';
    } catch {
      this.engine = 'off';
    }
  }

  /** Al abrir la app: si es la primera vez y falta algo esencial, se abre el asistente. */
  async init() {
    await this.load();
    if (this.status?.show) this.start();
  }

  /** Abre el asistente en el primer paso que todavía no está resuelto. */
  start(from?: Page) {
    if (from) this.page = from;
    else {
      const fresh = SKIPPABLE.every(p => this.pageState(p) === 'pending');   // nada configurado ni saltado todavía
      const firstOpen = SKIPPABLE.find(p => !['done', 'skipped'].includes(this.pageState(p)));
      this.page = fresh || !firstOpen ? 'bienvenida' : firstOpen;
    }
    this.open = true;
    this.poll(true);
  }

  poll(on: boolean) {
    window.clearInterval(this.#timer);
    if (on) this.#timer = window.setInterval(() => void this.load(), 3000);
  }

  go(page: Page) { this.page = page; }
  next() { this.page = PAGES[Math.min(PAGES.length - 1, this.index + 1)]; }
  back() { this.page = PAGES[Math.max(0, this.index - 1)]; }

  async skip(page: Page) {
    for (const id of ENGINE_STEPS[page] ?? []) {
      if (this.step(id)?.state === 'done') continue;
      const res = await post('/engine/setup/skip', { step: id });
      if (res.ok) this.status = await res.json();
    }
    this.next();
  }

  async unskip(id: string) {
    const res = await post('/engine/setup/unskip', { step: id });
    if (res.ok) this.status = await res.json();
  }

  async finish() {
    const res = await post('/engine/setup/finish');
    if (res.ok) this.status = await res.json();
    this.open = false;
    this.poll(false);
  }

  /** "Repetir configuración inicial" desde Ajustes. */
  async restart() {
    const res = await post('/engine/setup/reset');
    if (res.ok) this.status = await res.json();
    this.noticeHidden = false;
    this.start('bienvenida');
  }
}

export const setup = new Setup();
