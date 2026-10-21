// Vista de la línea de tiempo del DAW: zoom (px por segundo) y desplazamiento. Una sola fuente de verdad para regla, ondas, loop y cabezal.
export const MAX_PPS = 400;      // las ondas tienen 100 picos por segundo: más zoom no agrega detalle
const WHEEL_ZOOM = 0.0022;

class View {
  viewW = $state(800);
  pps = $state(10);
  scroll = $state(0);
  follow = $state(true);
  dur = $state(1);

  get fitPps() { return this.viewW / Math.max(1, this.dur); }
  get zoomed() { return this.pps > this.fitPps * 1.02; }
  get totalW() { return this.dur * this.pps; }
  get zoomPct() { return Math.round((this.pps / this.fitPps) * 100); }

  x = (t: number) => t * this.pps - this.scroll;
  t = (x: number) => (x + this.scroll) / this.pps;

  /** Nuevo tema o nueva duración: se vuelve a ver todo. */
  reset(dur: number) { this.dur = dur; this.pps = this.fitPps; this.scroll = 0; }

  setViewport(w: number) {
    const wasFit = !this.zoomed;
    this.viewW = Math.max(1, w);
    if (wasFit) { this.pps = this.fitPps; this.scroll = 0; } else this.#clamp();
  }

  fit() { this.pps = this.fitPps; this.scroll = 0; }

  /** Zoom alrededor de un punto de la pantalla (cx en px desde el borde izquierdo): lo que está bajo el cursor no se mueve. */
  zoomAt(cx: number, factor: number) {
    const tAt = this.t(cx);
    this.pps = Math.min(MAX_PPS, Math.max(this.fitPps, this.pps * factor));
    this.scroll = tAt * this.pps - cx;
    this.#clamp();
  }
  zoomWheel(cx: number, deltaY: number) { this.zoomAt(cx, Math.exp(-deltaY * WHEEL_ZOOM)); }

  scrollBy(px: number) { this.scroll += px; this.#clamp(); }
  scrollTo(px: number) { this.scroll = px; this.#clamp(); }

  /** Centra o acompaña el cabezal para que no se salga de la ventana. */
  keepVisible(t: number, margin = 0.12) {
    const x = this.x(t);
    if (x < 0 || x > this.viewW * (1 - margin)) this.scrollTo(t * this.pps - this.viewW * margin);
  }

  #clamp() { this.scroll = Math.max(0, Math.min(this.scroll, Math.max(0, this.totalW - this.viewW))); }
}

export const view = new View();
