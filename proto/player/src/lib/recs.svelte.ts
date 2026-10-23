// Recomendaciones: estado del motor (disco de hoy, pedido a demanda, perfil, memoria, historial).
export type Reaction = 'loved' | 'liked' | 'disliked' | 'no' | 'heard'; // 'heard' = el viejo "Ya lo escuché" (solo se lee)
export const REACTION_LABELS: Record<Reaction, string> = { loved: 'Me encantó', liked: 'Me gusta', disliked: 'No me gustó', no: 'No me interesa', heard: 'Lo conocía' };
export type Mode = 'estudiar' | 'concentrarme' | 'sorprenderme';
export interface About { text: string; source: 'wikipedia' | 'musicbrainz'; url: string; lang: string; summarized: boolean }
export interface Item { mbid: string; artist: string; album: string; year: number | null; genres: string[]; reason: string; fit: number; confidence: number | null; score: number; about?: About | null; overlap?: { genre: string; user: string; from: string[]; v: number }[]; genre?: GenreCheck | null; trail?: Trail }
export interface Discarded { artist: string; album: string; year: number | null; why: string; category: string }
export type DiscType = 'album' | 'ep' | 'live';
export interface Request { map?: { communities: string[] }; zone?: { names: string[]; artists: number; genres: string[]; gaps: string[]; bridges: string[] }; prompt: string; mode: Mode | null; seed: { artist: string; album?: string; title?: string } | null; presetId?: string; genres?: string[]; strict?: boolean; type?: DiscType; genresDetected?: boolean }
export interface GenreCheck { status: 'match' | 'weak' | 'off' | 'unknown'; score: number; why: string; source: 'disco' | 'artista' | null; matched: { want: string; have: string; via: string } | null }
export interface ClassifierVerdict { label: 'entailment' | 'neutral' | 'contradiction'; p: { entailment: number; neutral: number; contradiction: number }; backend: string; calibrated: boolean }
export interface ReviewVerdict { fit: 'si' | 'dudoso' | 'no'; issue: string; note: string | null }
export interface Trail { proposedBy: string; round: number; classifier?: ClassifierVerdict | null; review?: ReviewVerdict | null; diversity?: number; confidence: number | null; mbScore: number | null; type: string; score: { fit: number; base: number; gate: number | null; final: number } }
export type Intent = Mode | 'libre';
export interface Range { days: number[]; start: string; end: string }
export interface Preset { id: string; name: string; intent: Intent; schedule: Range[]; priority: number; discovery: 'nada' | 'algo' | 'mucho' | null; favor: string[]; avoid: string[]; examples: string[]; instrumental: boolean; prompt: string; note: string; over: string[] }
export interface Presets { version: number; default: string; presets: Preset[] }
export interface PresetUse { id: string; name: string; how: 'horario' | 'defecto' | 'elegido' }
export interface Stats { rounds: number; proposed: number; verified: number; verifiedRate: number; relevant: number; seconds: number; modelSeconds: number; promptTokens: number[]; discardedBy: Record<string, number>; context?: { wikipedia: number; summarized: number; fallback: number }; verifySeconds?: number; contextSeconds?: number; cancelled?: boolean; genres?: { wanted: string[]; strict: boolean } }
export interface RecsResult { kind: 'daily' | 'request'; model: string; createdAt: number; request: Request | null; context: string; preset?: PresetUse; pick: Item | null; alternatives: Item[]; discarded: Discarded[]; stats: Stats; prompt: string }
export interface Agent { id: 'planificador' | 'buscador' | 'revisor' | 'clasificador'; label: string; role: string; model: string | null; state: 'idle' | 'running' | 'done' | 'skipped' | 'cancelled'; detail: string; seconds: number; calls: number }
export interface LogEntry { t: number; agent: Agent['id']; text: string; kind: 'info' | 'ok' | 'discard' | 'warn' | 'skip' }
/** Cómo entendió el pedido el planificador. Todo es opinión del modelo (la época se comprueba luego con MusicBrainz); si la época vino de lo escrito, `era.source` es 'reglas'. */
export type PlannerView = { enabled: false } | {
  enabled: true; model: string | null; ran: boolean; ok: boolean; seconds: number;
  era: { from: number; to: number; source: 'reglas' | 'modelo'; strict: boolean } | null;
  mood: string | null; instrumental: boolean | null; language: string | null; refs: string[]; genres: string[]; brief: string | null; added: string[]; dropped: number;
};
export interface RunInputs {
  kind: 'daily' | 'request';
  request: { era: { from: number; to: number; source: 'reglas' | 'modelo'; strict: boolean } | null; genres: string[]; countries: string[]; countryNames: string[]; countriesDetected: boolean; canon: boolean; strict: boolean | null; genresDetected: boolean; type: DiscType | null; mode: Mode | null; modeFrom: 'pedido' | 'perfil' | null; hasText: boolean; text: string | null; seed: string | null };
  profile: { filled: boolean; instrument: string | null; level: string | null; focus: string[]; focusSkipped: boolean; loves: string[]; avoids: string[]; discovery: 'nada' | 'algo' | 'mucho' | null; listening: string | null; ownArtists: string[] };
  preset: { name: string | null; how: 'horario' | 'defecto' | 'elegido' | null; intent: string | null; instrumental: boolean; favor: string[]; hasPrompt: boolean };
  plan: { kind: string; label: string; useInstrument: boolean; useGoals: boolean; useTaste: boolean; requestPct: number; why: string[] };
  scoring: { tastePct: number; genreWeightPct: number | null; textWeightPct: number | null };
  taste: { artists: { name: string; w: number }[]; genres: { name: string; w: number }[]; decades: { name: string; w: number }[]; favorites: number; reactions: number; halfLifeDays: number };
  exclusions: { known: number; shownRecently: number };
  context: string | null;
  planner?: PlannerView;
  engine: { model: string; method: 'artistas' | 'discos'; reviewer: string | null; reviewerSkipped: boolean; classifier: string | null; planner?: string | null; maxRounds: number; target: number; artistsPerRound: number; diversity: number; ctxLimit: number };
}
export interface LastRun { kind: 'daily' | 'request'; createdAt: number; agents: Agent[]; log: LogEntry[]; inputs?: RunInputs | null }
export interface Estimate { total: number; parts: { model: number; musicbrainz: number; context: number }; basis: string }
export interface Observation { id: string; kind: string; key: string; text: string; confidence: number; evidence: string[]; effect: string; status: 'proposed' | 'confirmed' | 'rejected' }
export interface Facets {
  identity: Record<string, unknown>; taste: { artists: { name: string; w: number }[]; genres: { name: string; w: number }[]; decades: { name: string; w: number }[]; sources: { favorites: number; reactions: number } };
  avoid: { styles: string[]; confirmedStyles: string[]; discarded: { artist: string; album: string; action: Reaction }[] };
  habits: { reactions: Record<string, number>; knownRate: number | null; shownByPreset: Record<string, number> };
  learning: { focus: string[]; instrument: string; level: string };
  observations: { items: Observation[] }; graph: { nodes: unknown[]; edges: unknown[] };
}
export interface Profile {
  instrument: string; level: string; improve: string[]; loves: string[]; avoids: string[]; essentials: string[]; ownArtists: string[];
  discovery: 'nada' | 'algo' | 'mucho'; listening: 'discos' | 'temas' | 'ambos'; pace: string; notes: string;
  useTime: boolean; useWeather: boolean; city: string; geo: { name: string; country: string } | null; dismissed: boolean; updatedAt: number | null; seeded?: boolean; seedSeen?: boolean;
}
export interface Schedule { auto: boolean; cadenceHours: number; halfLifeDays: number; lastAt: number | null; due: boolean }
export interface HistoryItem { mbid: string; artist: string; album: string; action: Reaction; at: string; preset?: string | null; known?: boolean }
export interface AlbumTracks { state: 'loading' | 'ready' | 'missing' | 'error'; tracks: { id: string; title: string; artist: string; album: string; duration: number | null }[]; message?: string }

import { preloadCovers } from './coverCache';

const post = (url: string, body: unknown) => fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

class Recs {
  state = $state<'idle' | 'running' | 'done' | 'error' | 'no_engine'>('idle');
  step = $state('');
  message = $state('');
  done = $state(0);
  total = $state(0);
  found = $state(0);
  target = $state(4);
  agents = $state<Agent[]>([]);
  log = $state<LogEntry[]>([]);
  lastRun = $state<LastRun | null>(null);
  inputs = $state<RunInputs | null>(null);
  estimate = $state<Estimate | null>(null);
  facets = $state<Facets | null>(null);
  genreList = $state<{ name: string; mine?: boolean }[]>([]);
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
      this.done = s.done ?? 0; this.total = s.total ?? 0; this.found = s.found ?? 0; this.target = s.target ?? 4;
      this.agents = s.agents ?? []; this.log = s.log ?? []; this.lastRun = s.lastRun ?? null; this.inputs = s.inputs ?? null;
      this.daily = s.daily; this.request = s.request;
      preloadCovers(([s.daily, s.request] as (RecsResult | null)[]).flatMap(r => (r ? [r.pick, ...r.alternatives] : [])).filter((v): v is Item => !!v).map(v => `/engine/cover/${v.mbid}`)); this.reactions = s.reactions; this.history = s.history;
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

  async cancel() {
    try { await post('/engine/recs/cancel', {}); } catch { /* el próximo sondeo muestra el estado real */ }
    await this.load();
  }

  async loadEstimate(body: Partial<Request> & { context?: 'demand' | 'now' }) {
    try { this.estimate = (await (await post('/engine/recs/estimate', body)).json()).estimate; } catch { this.estimate = null; }
  }

  async loadMemory() {
    try { this.facets = (await (await fetch('/engine/recs/memory')).json()).facets; } catch { /* se reintenta al abrir */ }
  }

  async setObservation(id: string, status: Observation['status']) {
    const res = await post('/engine/recs/observation', { id, status });
    if (res.ok) this.facets = (await res.json()).facets;
  }

  /** Contexto del disco a demanda (Wikipedia + resumen). null si no hay. */
  async loadContext(mbid: string): Promise<About | null> {
    const res = await fetch(`/engine/recs/context?mbid=${encodeURIComponent(mbid)}`);
    if (!res.ok) throw new Error((await res.json()).message ?? 'No pude armar el contexto.');
    return (await res.json()).about;
  }

  async loadGenres() {
    if (this.genreList.length) return;
    try { this.genreList = (await (await fetch('/engine/recs/genres')).json()).genres; } catch { /* sin sugerencias: se escribe a mano */ }
  }

  async react(mbid: string, reaction: Reaction | null, known = false) {
    const res = await post('/engine/recs/reaction', { key: mbid, reaction, ...(known ? { known } : {}) });
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
