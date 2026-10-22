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
