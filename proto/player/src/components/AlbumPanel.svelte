<script lang="ts">
  // Un disco del mapa (tuyo o recomendado): portada al costado, abrirlo en TIDAL / YouTube Music, ver sus temas y escucharlo.
  import type { GNode } from '../lib/graph.svelte';
  import { recs, type AlbumTracks } from '../lib/recs.svelte';
  import { seed } from '../lib/seed.svelte';
  import { nav } from '../lib/nav.svelte';
  import { playback, queueItem } from '../lib/playback.svelte';
  import Cover from './Cover.svelte';
  import TrackRow from './TrackRow.svelte';
  import SourceLogo from './SourceLogo.svelte';

  let { node }: { node: GNode } = $props();
  interface Ids { local?: string; tidal?: string; spotify?: string; ytmusic?: string }
  interface OwnTrack { title: string; artist: string; album: string; duration: number; ids: Ids }

  const SRC: Record<string, string> = { local: 'Mis archivos', tidal: 'TIDAL', spotify: 'Spotify', ytmusic: 'YouTube Music' };
  const mm = (s: number | null | undefined) => (s == null ? '' : `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`);
  const isRec = $derived(node.type === 'rec');
  const art = $derived(isRec && node.mbid ? `/engine/cover/${node.mbid}` : node.artUrl ?? undefined);

  // temas: los de tu disco vienen del catálogo; los de un recomendado se buscan en tus fuentes de audio
  let own = $state<{ state: 'idle' | 'loading' | 'ready' | 'error'; tracks: OwnTrack[]; message: string }>({ state: 'idle', tracks: [], message: '' });
  let shown = $state(false);
  $effect(() => { node.id; shown = false; own = { state: 'idle', tracks: [], message: '' }; });

  const recKey = $derived(node.mbid ?? node.id);
  const rec = $derived<AlbumTracks | undefined>(isRec ? recs.albums[recKey] : undefined);
  const ready = $derived(isRec ? rec?.state === 'ready' : own.state === 'ready');
  const loading = $derived(isRec ? rec?.state === 'loading' : own.state === 'loading');
  const problem = $derived(isRec ? (rec?.state === 'error' ? rec.message : rec?.state === 'missing' ? 'No está en tus fuentes de audio.' : '') : own.state === 'error' ? own.message : '');

  const queue = $derived(isRec
    ? (rec?.state === 'ready' ? rec.tracks.map(t => queueItem({ title: t.title, artist: t.artist, album: node.label, sourceId: t.id, art, seconds: t.duration ?? undefined })) : [])
    : own.tracks.map(t => queueItem({ title: t.title, artist: t.artist, album: t.album, ids: t.ids, art, seconds: t.duration })));

  async function load() {
    if (isRec) { await recs.openAlbum(recKey, node.artist ?? '', node.label); return; }
    if (own.state === 'loading' || !node.key) return;
    own = { state: 'loading', tracks: [], message: '' };
    const id = node.id;
    try {
      const res = await fetch(`/engine/music/album?key=${encodeURIComponent(node.key)}`);
      const r = await res.json();
      if (id !== node.id) return;
      own = res.ok ? { state: 'ready', tracks: r.tracks, message: '' } : { state: 'error', tracks: [], message: r.message ?? 'No pude leer el álbum.' };
    } catch { own = { state: 'error', tracks: [], message: 'No pude hablar con el motor.' }; }
  }
  const toggle = async () => { shown = !shown; if (shown && !ready && !loading) await load(); };
  async function listen() {
    if (!ready) { shown = true; await load(); }
    if (queue.length) playback.playFrom(queue, 0);
  }
</script>

<div class="album">
  <div class="cv"><Cover title={node.label} artist={node.artist ?? ''} size={112} radius={12} src={art} /></div>
  <div class="txt">
    <h3>{node.label}</h3>
    <span class="muted small">{node.artist}{node.year ? `, ${node.year}` : ''}</span>
    {#if node.sources?.length}
      <span class="tags">{#each node.sources as s (s)}
        {#if node.links?.[s]}<a class="tag" href={node.links[s]} target="_blank" rel="noopener noreferrer" title="Abrir en {SRC[s] ?? s}"><SourceLogo id={s} size={12} />{SRC[s] ?? s}<span aria-hidden="true">↗</span></a>
        {:else}<em>{SRC[s] ?? s}</em>{/if}
      {/each}</span>
    {/if}
  </div>
</div>
<div class="btns">
  <button class="primary" onclick={listen} disabled={loading}>{loading ? 'Buscando…' : 'Escuchar el álbum'}</button>
  <button class="ghost" onclick={toggle} aria-expanded={shown}>{shown ? 'Ocultar temas' : 'Ver temas'}</button>
  <button class="ghost" onclick={() => { seed.set({ artist: node.artist ?? '', album: node.label }); nav.go('recomendaciones'); }}>Recomendar parecidos</button>
</div>
{#if shown}
  {#if problem}<p class="warn small" role="alert">{problem}</p>
  {:else if loading || !ready}<p class="muted small">Cargando temas…</p>
  {:else}
    <ul class="tracks">
      {#if isRec && rec?.state === 'ready'}
        {#each rec.tracks as t, i (t.id)}<TrackRow compact n={i + 1} title={t.title} artist={t.artist} duration={mm(t.duration)} sourceId={t.id} album={node.label} {art} {queue} qi={i} />{/each}
      {:else}
        {#each own.tracks as t, i (i + t.title)}<TrackRow compact n={i + 1} title={t.title} artist={t.artist} album={t.album} duration={mm(t.duration)} ids={t.ids} {art} {queue} qi={i} />{:else}<li class="muted small">Sin temas.</li>{/each}
      {/if}
    </ul>
  {/if}
{/if}

<style>
  .album { display: grid; grid-template-columns: 112px minmax(0, 1fr); gap: 14px; align-items: start; }
  .cv :global(img), .cv :global(svg), .cv :global(.cv) { display: block; width: 112px !important; height: 112px !important; filter: drop-shadow(0 12px 20px rgba(0, 0, 0, 0.45)); }
  .txt { display: grid; gap: 4px; align-content: start; min-width: 0; }
  h3 { margin: 0; font-size: 19px; overflow-wrap: anywhere; line-height: 1.15; }
  .small { font-size: 13px; }
  .tags { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 2px; }
  .tag { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 600; padding: 1px 8px 1px 6px; border-radius: 999px; border: 1px solid var(--glass-line); color: var(--text); background: rgba(255, 255, 255, 0.06); text-decoration: none; }
  .tags em { font-size: 11px; font-style: normal; color: var(--muted); border: 1px solid var(--glass-line); border-radius: 999px; padding: 1px 8px; }
  .btns { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0 2px; }
  .btns button { font-size: 13px; padding: 6px 11px; }
  .btns .primary { padding: 6px 12px; border-radius: 10px; background: var(--text); color: var(--bg); font-weight: 600; border: 0; cursor: pointer; }
  .btns .primary:disabled { opacity: 0.6; cursor: default; }
  .tracks { list-style: none; margin: 4px 0 0; padding: 4px; display: grid; gap: 2px; border-radius: 12px; background: rgba(0, 0, 0, 0.18); }
  .warn { margin: 0; }
</style>
