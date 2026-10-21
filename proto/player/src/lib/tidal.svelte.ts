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
  #poll = 0;

  get label() {
    return { idle: 'sin conectar', connecting: 'conectando', ready: 'conectado', no_engine: 'motor apagado', blocked: 'sin sesión', logging_in: 'esperando autorización' }[this.state];
  }

  async connect() {
    if (this.state === 'connecting' || this.state === 'ready' || this.state === 'logging_in') return;
    this.state = 'connecting';
    this.message = '';
    let status: { tidal: { connected: boolean; message?: string } };
    try {
      status = await (await fetch('/engine/status')).json();
    } catch {
      this.state = 'no_engine';
      this.message = 'El motor local no está corriendo. Iniciálo con "npm run engine" en proto/player y volvé a intentar.';
      return;
    }
    if (!status.tidal.connected) {
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

  async login() {
    window.clearInterval(this.#poll);
    this.message = '';
    try {
      const res = await fetch('/engine/tidal/login/start', { method: 'POST' });
      const body = await res.json();
      if (!res.ok) throw new Error(body.message);
      this.loginCode = body.code;
      this.loginUrl = body.url;
      this.state = 'logging_in';
    } catch (e) {
      this.state = 'blocked';
      this.message = e instanceof Error && e.message ? e.message : 'No se pudo iniciar el login de TIDAL.';
      return;
    }
    this.#poll = window.setInterval(async () => {
      const st = await (await fetch('/engine/tidal/login/status')).json();
      if (st.state === 'pending') return;
      window.clearInterval(this.#poll);
      if (st.state === 'done') { this.state = 'idle'; await this.connect(); }
      else { this.state = 'blocked'; this.message = st.message || 'No se pudo iniciar sesión.'; }
    }, 2000);
  }

  cancelLogin() {
    window.clearInterval(this.#poll);
    this.state = 'blocked';
    this.message = 'Cancelaste el inicio de sesión.';
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
