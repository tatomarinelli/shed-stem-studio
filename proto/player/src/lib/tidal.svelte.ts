export interface TidalTrack { id: string; title: string; artist: string; album: string; duration: number | null }
export interface TidalAlbum { id: string; title: string; artist: string; year: number | null; tracks: number | null }
export interface TidalPlaylist { id: string; name: string; tracks: number | null; own: boolean }
export interface TidalLibrary { tracks: TidalTrack[]; albums: TidalAlbum[]; artists: string[]; playlists: TidalPlaylist[] }

type State = 'idle' | 'connecting' | 'ready' | 'no_engine' | 'blocked' | 'logging_in';

class Tidal {
  state = $state<State>('idle');
  message = $state('');
  library = $state<TidalLibrary | null>(null);
  playlistTracks = $state<Record<string, TidalTrack[]>>({});
  loadingPlaylist = $state('');
  loginCode = $state('');
  loginUrl = $state('');

  get label() {
    return { idle: 'sin conectar', connecting: 'conectando', ready: 'conectado', no_engine: 'motor apagado', blocked: 'sin sesión', logging_in: 'esperando autorización' }[this.state];
  }

  async connect() {
    if (this.state === 'connecting' || this.state === 'ready' || this.state === 'logging_in') return;
    this.state = 'connecting';
    this.message = '';
    let status: { tidal: { connected: boolean; message?: string; login?: { code: string; url: string; expiresIn: number; attempt?: number } } };
    try {
      status = await (await fetch('/engine/status')).json();
    } catch {
      this.state = 'no_engine';
      this.message = 'El motor local no está corriendo. Iniciálo con "npm run engine" en proto/player y volvé a intentar.';
      return;
    }
    if (!status.tidal.connected) {
      if (status.tidal.login) { this.#adopt(status.tidal.login); return; } // ya hay un código vigente en el motor: se retoma, no se pide otro
      this.state = 'blocked';
      this.message = status.tidal.message ?? 'No hay una sesión de TIDAL disponible.';
      return;
    }
    const res = await fetch('/engine/tidal/library');
    const body = await res.json();
    if (!res.ok) {
      this.state = 'blocked';
      this.message = body.message ?? 'TIDAL no respondió.';
      return;
    }
    this.library = body;
    this.state = 'ready';
  }

  /** Segundos que le quedan al código vigente. */
  loginLeft = $state(0);
  /** Aviso corto cuando se pidió un código nuevo. */
  loginNotice = $state('');
  #expiresAt = 0;
  #attempt = 0;
  #autoRenewals = 0;
  #starting = false;
  #poll = 0;
  #tick = 0;

  #stopTimers() {
    window.clearInterval(this.#poll);
    window.clearInterval(this.#tick);
    this.#poll = this.#tick = 0;
  }

  /** Muestra el código que tiene el motor (el único vigente) y empieza a sondear. */
  #adopt(b: { code: string; url: string; expiresIn: number; attempt?: number }) {
    this.loginCode = b.code;
    this.loginUrl = b.url;
    this.#attempt = b.attempt ?? 0;
    this.#expiresAt = Date.now() + b.expiresIn * 1000;
    this.loginLeft = Math.max(0, Math.ceil(b.expiresIn));
    this.state = 'logging_in';
    if (this.#poll) return;
    this.#tick = window.setInterval(() => {
      this.loginLeft = Math.max(0, Math.ceil((this.#expiresAt - Date.now()) / 1000));
      if (this.loginLeft === 0) void this.#expired();
    }, 1000);
    this.#poll = window.setInterval(() => void this.#check(), 2000);
  }

  async #check() {
    if (this.state !== 'logging_in') return;
    let st: { state: string; message?: string; code?: string; url?: string; expiresIn?: number; attempt?: number };
    try { st = await (await fetch('/engine/tidal/login/status')).json(); } catch { return; }
    if (this.state !== 'logging_in') return;
    if (st.state === 'pending' && st.code) {
      if (st.attempt !== this.#attempt) this.#adopt({ code: st.code, url: st.url ?? '', expiresIn: st.expiresIn ?? 0, attempt: st.attempt });
      return;
    }
    this.#stopTimers();
    if (st.state === 'done') { this.state = 'idle'; await this.connect(); }
    else if (st.state === 'expired') { this.state = 'logging_in'; await this.#expired(); }
    else { this.state = 'blocked'; this.message = st.message || 'No se pudo iniciar sesión.'; }
  }

  /** Venció el código: pide uno nuevo solo (hasta 2 veces seguidas) y avisa. */
  async #expired() {
    if (this.#starting) return;
    if (this.#autoRenewals >= 2) {
      this.#stopTimers();
      this.state = 'blocked';
      this.message = 'El código venció. Tocá Conectar TIDAL para pedir otro.';
      return;
    }
    this.#autoRenewals++;
    await this.#start(true, 'Pedimos un código nuevo.');
  }

  async #start(renew: boolean, notice = '') {
    if (this.#starting) return;
    this.#starting = true;
    this.message = '';
    try {
      const res = await fetch('/engine/tidal/login/start' + (renew ? '?renew=1' : ''), { method: 'POST' });
      const body = await res.json();
      if (!res.ok) throw new Error(body.message);
      this.loginNotice = notice;
      this.#adopt(body);
    } catch (e) {
      this.#stopTimers();
      this.state = 'blocked';
      this.message = e instanceof Error && e.message ? e.message : 'No se pudo iniciar el login de TIDAL.';
    } finally {
      this.#starting = false;
    }
  }

  /** Conectar: un solo clic, un solo intento (si ya hay uno en curso no pide otro). */
  async login() {
    if (this.state === 'logging_in' || this.#starting) return;
    this.#autoRenewals = 0;
    this.loginNotice = '';
    await this.#start(false);
    this.#openLogin();
  }

  /** Abre el enlace de autorización en el navegador (en la app de escritorio lo manda al navegador del sistema). Si algo lo bloquea, el enlace queda visible debajo del botón. */
  #openLogin() {
    if (this.state === 'logging_in' && this.loginUrl) window.open(this.loginUrl, '_blank', 'noopener,noreferrer');
  }

  /** Pedir otro código a mano. */
  async renew() {
    this.#autoRenewals = 0;
    await this.#start(true, 'Pedimos un código nuevo.');
    this.#openLogin();
  }

  async cancelLogin() {
    this.#stopTimers();
    this.state = 'blocked';
    this.message = 'Cancelaste el inicio de sesión.';
    try { await fetch('/engine/tidal/login/cancel', { method: 'POST' }); } catch { /* el motor se entera por el vencimiento */ }
  }

  async logout() {
    await fetch('/engine/tidal/logout', { method: 'POST' });
    this.library = null;
    this.playlistTracks = {};
    this.state = 'blocked';
    this.message = 'Desconectaste TIDAL. La sesión se borró de esta computadora.';
  }

  async loadPlaylist(id: string) {
    if (this.playlistTracks[id] || this.loadingPlaylist === id) return;
    this.loadingPlaylist = id;
    try {
      const res = await fetch(`/engine/tidal/playlists/${encodeURIComponent(id)}`);
      const body = await res.json();
      if (res.ok) this.playlistTracks[id] = body.tracks;
      else this.message = body.message ?? 'No se pudo leer la playlist.';
    } finally {
      this.loadingPlaylist = '';
    }
  }
}

export const tidal = new Tidal();
