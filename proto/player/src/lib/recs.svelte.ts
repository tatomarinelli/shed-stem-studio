// Recomendaciones: estado del motor (disco de hoy, pedido a demanda, perfil, memoria, historial).
export type Reaction = 'heard' | 'loved' | 'no';
export type Mode = 'estudiar' | 'concentrarme' | 'sorprenderme';
export interface About { text: string; source: 'wikipedia' | 'musicbrainz'; url: string; lang: string; summarized: boolean }
export interface Item { mbid: string; artist: string; album: string; year: number | null; genres: string[]; reason: string; fit: number; confidence: number | null; score: number; about?: About | null }
export interface Discarded { artist: string; album: string; year: number | null; why: string; category: string }
export interface Request { prompt: string; mode: Mode | null; seed: { artist: string; album?: string; title?: string } | null; presetId?: string }
export type Intent = Mode | 'libre';
export interface Range { days: number[]; start: string; end: string }
export interface Preset { id: string; name: string; intent: Intent; schedule: Range[]; priority: number; discovery: 'nada' | 'algo' | 'mucho' | null; favor: string[]; avoid: string[]; examples: string[]; instrumental: boolean; prompt: string; note: string; over: string[] }
export interface Presets { version: number; default: string; presets: Preset[] }
export interface PresetUse { id: string; name: string; how: 'horario' | 'defecto' | 'elegido' }
export interface Stats { rounds: number; proposed: number; verified: number; verifiedRate: number; relevant: number; seconds: number; modelSeconds: number; promptTokens: number[]; discardedBy: Record<string, number>; context?: { wikipedia: number; summarized: number; fallback: number } }
export interface RecsResult { kind: 'daily' | 'request'; model: string; createdAt: number; request: Request | null; context: string; preset?: PresetUse; pick: Item | null; alternatives: Item[]; discarded: Discarded[]; stats: Stats; prompt: string }
export interface Profile {
  instrument: string; level: string; improve: string[]; loves: string[]; avoids: string[]; essentials: string[]; ownArtists: string[];
  discovery: 'nada' | 'algo' | 'mucho'; listening: 'discos' | 'temas' | 'ambos'; pace: string; notes: string;
  useTime: boolean; useWeather: boolean; city: string; geo: { name: string; country: string } | null; dismissed: boolean; updatedAt: number | null; seeded?: boolean; seedSeen?: boolean;
}
export interface Schedule { auto: boolean; cadenceHours: number; halfLifeDays: number; lastAt: number | null; due: boolean }
export interface HistoryItem { mbid: string; artist: string; album: string; action: Reaction; at: string; preset?: string | null }
export interface AlbumTracks { state: 'loading' | 'ready' | 'missing' | 'error'; tracks: { id: string; title: string; artist: string; album: string; duration: number | null }[]; message?: string }

const post = (url: string, body: unknown) => fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

class Recs {
  state = $state<'idle' | 'running' | 'done' | 'error' | 'no_engine'>('idle');
  step = $state('');
  message = $state('');
  kind = $state<'daily' | 'request' | null>(null);
  daily = $state<RecsResult | null>(null);
  request = $state<RecsResult | null>(null);
  reactions = $state<Record<string, Reaction>>({});
  history = $state<HistoryItem[]>([]);
  profile = $state<Profile | null>(null);
  profileFilled = $state(false);
  schedule = $state<Schedule | null>(null);
  memory = $state('');
  presets = $state<Presets | null>(null);
  activePreset = $state<PresetUse | null>(null);
  /** Perfil elegido a mano para las próximas generaciones ('' = el que toca por horario). No cambia el horario guardado. */
  presetChoice = $state('');
  albums = $state<Record<string, AlbumTracks>>({});
  #timer = 0;

  async load() {
    try {
      const s = await (await fetch('/engine/recs/status')).json();
      this.state = s.state; this.step = s.step; this.message = s.message; this.kind = s.kind;
      this.daily = s.daily; this.request = s.request; this.reactions = s.reactions; this.history = s.history;
      this.profile = s.profile; this.profileFilled = s.profileFilled; this.schedule = s.schedule; this.memory = s.memory;
      this.presets = s.presets; this.activePreset = s.activePreset;
    } catch {
      this.state = 'no_engine';
      this.message = 'El motor local está apagado. Iniciálo con "npm run engine" en proto/player.';
      return;
    }
    window.clearTimeout(this.#timer);
    if (this.state === 'running') this.#timer = window.setTimeout(() => this.load(), 1500);
  }

  /** Lo que todavía no clasificó, en orden: el recomendado primero. */
  open(r: RecsResult | null): Item[] {
    if (!r) return [];
    return [r.pick, ...r.alternatives].filter((x): x is Item => !!x && !this.reactions[x.mbid]);
  }

  async generate(kind: 'daily' | 'request', body: Partial<Request> = {}) {
    this.state = 'running'; this.kind = kind; this.step = 'profile'; this.message = '';
    const res = await post('/engine/recs/generate', { kind, ...body, ...(this.presetChoice ? { presetId: this.presetChoice } : {}) });
    if (!res.ok) { this.state = 'error'; this.message = (await res.json()).message ?? 'No se pudo empezar.'; return false; }
    await this.load();
    return true;
  }

  async react(mbid: string, reaction: Reaction | null) {
    const res = await post('/engine/recs/reaction', { key: mbid, reaction });
    if (!res.ok) { this.message = (await res.json()).message ?? 'No se pudo guardar.'; return false; }
    this.reactions = (await res.json()).reactions;
    await this.load();
    return true;
  }

  async saveProfile(patch: Partial<Profile>): Promise<string | null> {
    const res = await post('/engine/recs/profile', patch);
    const body = await res.json();
    if (!res.ok) return body.message ?? 'No se pudo guardar.';
    this.profile = body.profile;
    await this.load();
    return null;
  }

  async savePresets(data: Presets): Promise<string | null> {
    const res = await post('/engine/recs/presets', data);
    const body = await res.json();
    if (!res.ok) return body.message ?? 'No se pudo guardar.';
    this.presets = body.presets;
    if (this.presetChoice && !body.presets.presets.some((p: Preset) => p.id === this.presetChoice)) this.presetChoice = '';
    await this.load();
    return null;
  }

  async setSchedule(patch: { auto?: boolean; cadenceHours?: number }) {
    const res = await post('/engine/recs/schedule', patch);
    if (res.ok) this.schedule = (await res.json()).schedule;
  }

  /** Busca el disco en las fuentes de audio y trae sus temas, para escucharlos o separarlos. */
  async openAlbum(mbid: string, artist: string, album: string) {
    if (this.albums[mbid]?.state === 'ready' || this.albums[mbid]?.state === 'loading') return;
    this.albums[mbid] = { state: 'loading', tracks: [] };
    try {
      const res = await fetch(`/engine/album?artist=${encodeURIComponent(artist)}&album=${encodeURIComponent(album)}`);
      const body = await res.json();
      if (!res.ok) { this.albums[mbid] = { state: 'error', tracks: [], message: body.message ?? 'No pude buscar el disco.' }; return; }
      this.albums[mbid] = body.tracks.length ? { state: 'ready', tracks: body.tracks } : { state: 'missing', tracks: [] };
    } catch {
      this.albums[mbid] = { state: 'error', tracks: [], message: 'No pude hablar con el motor.' };
    }
  }
}

export const recs = new Recs();
