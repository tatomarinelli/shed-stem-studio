// El mapa de conocimiento que arma el motor (GET /engine/graph): artistas, géneros y discos tuyos, con los recomendados afuera.
export type Kind = 'artist' | 'genre' | 'album' | 'rec';
export const KINDS: Kind[] = ['album', 'artist', 'genre', 'rec'];
export const KIND_LABEL: Record<Kind, string> = { album: 'Discos', artist: 'Artistas', genre: 'Géneros', rec: 'Recomendados' };
export const KIND_ONE: Record<Kind, string> = { album: 'Disco', artist: 'Artista', genre: 'Género', rec: 'Recomendado' };

export interface GNode {
  id: string; type: Kind; label: string; w: number; x: number; y: number; angle: number; radius: number; group: string;
  community: number; artist?: string; genresFrom?: 'album' | 'artist' | 'none'; year?: number | null; sources?: string[]; artUrl?: string | null; key?: string; mbid?: string; links?: Record<string, string>; saved?: string | null; reaction?: string; reason?: string;
}
export interface GEdge { from: string; to: string; type: string; scope?: 'same-artist' | 'other-artist'; w: number; at: number | null; evidence: { kind: string; [k: string]: unknown }[]; why: string }
export interface Community { id: number; name: string; size: number; albums: number; genres: string[]; artists: string[] }
export interface Bridge { id: string; label: string; type: Kind; score: number; communities: number[]; why: string }
export interface Gap { genre: string; near: string[]; score: number; why: string }
export interface GraphData { nodes: GNode[]; edges: GEdge[]; communities: Community[]; bridges: Bridge[]; gaps: Gap[]; stats: Record<string, number> }
/** Colores de comunidad: 8 tonos y el resto gris (más colores no se distinguen). */
export const COMMUNITY_COLORS = ['#7cc7a3', '#4fa3d9', '#c58bf0', '#f0a43c', '#f08fb0', '#e6d36a', '#5fd0d0', '#e07a5f'];
export const communityColor = (c: number) => (c >= 0 && c < COMMUNITY_COLORS.length ? COMMUNITY_COLORS[c] : '#6f8288');

class GraphStore {
  state = $state<'idle' | 'loading' | 'ready' | 'error' | 'no_engine'>('idle');
  data = $state.raw<GraphData | null>(null);
  byId = $state.raw<Map<string, GNode>>(new Map());
  edgesOf = $state.raw<Map<string, GEdge[]>>(new Map());

  async load() {
    this.state = 'loading';
    try {
      const res = await fetch('/engine/graph');
      if (!res.ok) throw new Error(String(res.status));
      const d = (await res.json()) as GraphData;
      const ids = new Map(d.nodes.map(n => [n.id, n] as const));
      const adj = new Map<string, GEdge[]>();
      for (const e of d.edges) for (const k of [e.from, e.to]) (adj.get(k) ?? adj.set(k, []).get(k)!).push(e);
      this.data = d; this.byId = ids; this.edgesOf = adj;
      this.state = 'ready';
    } catch (e) {
      this.state = e instanceof TypeError ? 'no_engine' : 'error';
    }
  }

  enrich = $state({ running: false, done: 0, total: 0 });

  /** Busca en MusicBrainz los géneros de los artistas cuyos discos no tienen (a pedido) y recarga el mapa al terminar. */
  async completeGenres() {
    const call = async (method: 'GET' | 'POST') => { try { const r = await fetch('/engine/graph/enrich', { method }); if (r.ok) this.enrich = await r.json(); } catch { /* motor apagado */ } };
    await call('POST');
    while (this.enrich.running) { await new Promise(r => setTimeout(r, 2000)); await call('GET'); }
    await this.load();
  }

  /** Vecinos de un nodo con la arista que los une, del más fuerte al más débil. */
  neighbors(id: string): { node: GNode; edge: GEdge }[] {
    const out: { node: GNode; edge: GEdge }[] = [];
    for (const e of this.edgesOf.get(id) ?? []) {
      const n = this.byId.get(e.from === id ? e.to : e.from);
      if (n) out.push({ node: n, edge: e });
    }
    return out.sort((a, b) => b.edge.w - a.edge.w || a.node.label.localeCompare(b.node.label));
  }
}
export const graph = new GraphStore();
