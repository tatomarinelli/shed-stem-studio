export interface ProviderStatus {
  id: 'spotify' | 'ytmusic' | 'tidal';
  label: string;
  configured: boolean;
  connected: boolean;
  needsSecret: boolean;
  capabilities: { audio: boolean; albums: boolean; playlists: boolean; savedTracks: boolean; write: boolean };
  /** Cómo se guardó la sesión: dpapi (Windows), keyring (llavero de Linux) o file-600 (archivo sin cifrar, solo tu usuario). */
  protection: 'dpapi' | 'keyring' | 'file-600' | null;
  redirectUri: string;
  note: string;
  managedBy?: string;
  /** Solo YouTube Music: la biblioteca completa con ytmusicapi (no oficial) y el estado de la API oficial. */
  unofficial?: { installed: boolean; connected: boolean; install: { state: string; error?: string }; pairing: boolean; extension: boolean; browser: string | null; protection: ProviderStatus['protection'] };
  official?: { configured: boolean; connected: boolean };
}

class Providers {
  list = $state<ProviderStatus[]>([]);
  loaded = $state(false);
  busy = $state('');
  waiting = $state('');
  messages = $state<Record<string, string>>({});
  #poll = 0;

  /** Solo las cuentas nuevas (TIDAL tiene su propia tarjeta en Fuentes). */
  get accounts() { return this.list.filter(p => p.managedBy !== 'tidal'); }

  async load() {
    try {
      const res = await fetch('/engine/providers');
      if (res.ok) this.list = (await res.json()).providers;
    } catch { /* motor apagado: Ajustes ya lo avisa */ }
    this.loaded = true;
  }

  async #post(id: string, path: string, body?: unknown) {
    const res = await fetch(`/engine/providers/${id}/${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body ?? {}) });
    const out = await res.json();
    if (!res.ok) throw new Error(out.message ?? 'No se pudo completar la acción.');
    return out;
  }

  async saveApp(id: string, clientId: string, clientSecret = '') {
    this.busy = id; this.messages[id] = '';
    try { await this.#post(id, 'app', { clientId, clientSecret }); await this.load(); return true; }
    catch (e) { this.messages[id] = e instanceof Error ? e.message : 'Error'; return false; }
    finally { this.busy = ''; }
  }

  /** Abre la autorización del servicio en el navegador y espera a que el motor reciba la vuelta. */
  async connect(id: string) {
    this.busy = id; this.messages[id] = '';
    try {
      const { url } = await this.#post(id, 'auth/start');
      window.open(url, '_blank', 'noopener,noreferrer');
      this.waiting = id;
      const until = Date.now() + 5 * 60_000;
      window.clearInterval(this.#poll);
      this.#poll = window.setInterval(async () => {
        await this.load();
        if (this.list.find(p => p.id === id)?.connected || Date.now() > until) { this.waiting = ''; window.clearInterval(this.#poll); }
      }, 2000);
    } catch (e) { this.messages[id] = e instanceof Error ? e.message : 'Error'; }
    finally { this.busy = ''; }
  }

  /** Acciones de la biblioteca completa de YouTube Music (instalar la librería, pegar o quitar los encabezados). */
  async ytAction(path: 'install' | 'headers' | 'headers/clear', body?: unknown) {
    this.busy = 'ytmusic'; this.messages.ytmusic = '';
    try {
      await this.#post('ytmusic', path, body);
      await this.load();
      if (path === 'install') this.#pollInstall();
      return true;
    } catch (e) { this.messages.ytmusic = e instanceof Error ? e.message : 'Error'; return false; }
    finally { this.busy = ''; }
  }

  /** Abre music.youtube.com con un token de un solo uso: la extensión toma la sesión y se la pasa al motor. */
  async pairYt(launch = false) {
    this.busy = 'ytmusic'; this.messages.ytmusic = '';
    try {
      const { url, launched } = await this.#post('ytmusic', 'pair', { launch });
      if (!launched) {
        if (launch) this.messages.ytmusic = 'No pude abrir un navegador propio: abrí YouTube Music en el tuyo (con la extensión).';
        window.open(url, '_blank', 'noopener,noreferrer');
      }
      this.waiting = 'ytmusic';
      const until = Date.now() + 10 * 60_000;
      window.clearInterval(this.#poll);
      this.#poll = window.setInterval(async () => {
        await this.load();
        const got = this.list.find(p => p.id === 'ytmusic')?.unofficial?.connected;
        if (got || Date.now() > until) { this.waiting = ''; window.clearInterval(this.#poll); if (!got) this.messages.ytmusic = 'No llegó la sesión. Probá de nuevo.'; }
      }, 2000);
    } catch (e) { this.messages.ytmusic = e instanceof Error ? e.message : 'Error'; }
    finally { this.busy = ''; }
  }

  async cancelPairYt() { this.cancelWait(); try { await this.#post('ytmusic', 'pair/cancel'); } catch { /* el token vence solo */ } }

  #pollInstall() {
    window.clearInterval(this.#poll);
    this.#poll = window.setInterval(async () => {
      await this.load();
      if (this.list.find(p => p.id === 'ytmusic')?.unofficial?.install.state !== 'running') window.clearInterval(this.#poll);
    }, 1500);
  }

  cancelWait() { this.waiting = ''; window.clearInterval(this.#poll); }

  /** Borra la sesión de esta computadora. No toca nada de la cuenta en el servicio. */
  async logout(id: string) {
    this.busy = id;
    try { await this.#post(id, 'logout'); await this.load(); }
    catch (e) { this.messages[id] = e instanceof Error ? e.message : 'Error'; }
    finally { this.busy = ''; }
  }
}

export const providers = new Providers();
