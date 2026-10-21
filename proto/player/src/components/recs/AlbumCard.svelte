<script lang="ts">
  import Cover from '../Cover.svelte';
  import TrackRow from '../TrackRow.svelte';
  import { recs, type Item, type Reaction } from '../../lib/recs.svelte';
  import { player } from '../../lib/player.svelte';
  import { queueItem } from '../../lib/playback.svelte';
  import SaveBox from './SaveBox.svelte';
  let saving = $state(false);

  let { item, big = false, onreact }: { item: Item; big?: boolean; onreact: (item: Item, r: Reaction) => void } = $props();

  const reactions: { id: Reaction; label: string }[] = [
    { id: 'heard', label: 'Ya lo escuché' },
    { id: 'loved', label: 'Me encantó' },
    { id: 'no', label: 'No me va' },
  ];
  const secs = (n: number | null) => (n == null ? '' : `${Math.floor(n / 60)}:${String(n % 60).padStart(2, '0')}`);
  const cachedIds = $derived(new Set(player.tracks.map(t => t.id)));
  const tracks = $derived(recs.albums[item.mbid]);
  // ▶ en un tema sigue con los demás del disco.
  const queue = $derived(tracks?.state === 'ready' ? tracks.tracks.map(t => queueItem({ title: t.title, artist: t.artist, album: item.album, sourceId: t.id, art: `/engine/cover/${item.mbid}`, seconds: t.duration ?? undefined })) : []);
  const size = $derived(big ? 220 : 72);
</script>

<article class="card" class:big>
  <div class="cover"><Cover title={item.album} artist={item.artist} {size} radius={big ? 16 : 10} src="/engine/cover/{item.mbid}" /></div>
  <div class="body">
    <h3>{item.album}</h3>
    <p class="who">{item.artist}{item.year ? ` · ${item.year}` : ''}
      <a class="ok" href="https://musicbrainz.org/release-group/{item.mbid}" target="_blank" rel="noopener noreferrer" title="Verificado en MusicBrainz">✓ MusicBrainz</a>
    </p>
    {#if item.genres.length}
      <p class="genres">{#each item.genres as g (g)}<span>{g}</span>{/each}</p>
    {/if}
    {#if item.about?.text}
      <p class="why">{item.about.text}
        <a class="src" href={item.about.url} target="_blank" rel="noopener noreferrer">{item.about.source === 'wikipedia' ? 'Wikipedia' : 'MusicBrainz'}</a>
      </p>
    {/if}
    <div class="acts">
      <button class="primary" onclick={() => recs.openAlbum(item.mbid, item.artist, item.album)} disabled={tracks?.state === 'loading'}>
        {tracks?.state === 'loading' ? 'Buscando…' : 'Ver temas'}
      </button>
      <button onclick={() => (saving = !saving)} aria-expanded={saving}>Guardar</button>
      {#each reactions as x (x.id)}
        <button onclick={() => onreact(item, x.id)}>{x.label}</button>
      {/each}
    </div>
  </div>
  {#if saving}<SaveBox artist={item.artist} album={item.album} onclose={() => (saving = false)} />{/if}
  {#if tracks?.state === 'ready'}
    <ul class="tracks">
      {#each tracks.tracks as t, i (t.id)}
        <TrackRow compact n={i + 1} title={t.title} artist={t.artist} duration={secs(t.duration)} sourceId={t.id} album={item.album} art="/engine/cover/{item.mbid}" {queue} qi={i} badge={cachedIds.has(t.id) ? 'Ya separado' : ''} />
      {/each}
    </ul>
  {:else if tracks?.state === 'missing'}
    <p class="warn full">No está en tus fuentes de audio.</p>
  {:else if tracks?.state === 'error'}
    <p class="warn full" role="alert">{tracks.message}</p>
  {/if}
</article>

<style>
  .card { display: grid; grid-template-columns: 72px 1fr; gap: 14px; padding: 12px; border-radius: var(--radius); align-items: start; transition: background 0.2s; animation: rise 0.4s var(--ease) both; }
  .card:hover { background: rgba(255, 255, 255, 0.04); }
  .card.big { grid-template-columns: 220px 1fr; gap: 26px; padding: 20px; background: var(--glass); backdrop-filter: blur(16px) saturate(1.3); border: 1px solid var(--glass-line); box-shadow: 0 24px 60px -28px rgba(0, 0, 0, 0.8); }
  .cover :global(img), .cover :global(svg) { display: block; filter: drop-shadow(0 14px 24px rgba(0, 0, 0, 0.45)); }
  .body { display: grid; gap: 4px; align-content: start; min-width: 0; max-width: 760px; }
  .body p { margin: 0; }
  h3 { margin: 0; font-size: 17px; line-height: 1.15; letter-spacing: -0.01em; }
  .big h3 { font-size: 32px; letter-spacing: -0.025em; font-variation-settings: 'wdth' 90; }
  .who { color: var(--muted); display: flex; gap: 10px; flex-wrap: wrap; align-items: baseline; }
  .big .who { font-size: 17px; color: var(--text); }
  .ok { color: #7cc7a3; font-size: 12.5px; text-decoration: none; border: 1px solid color-mix(in srgb, #7cc7a3 40%, transparent); border-radius: 999px; padding: 0 8px; }
  .ok:hover { text-decoration: underline; }
  .genres { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px !important; }
  .genres span { font-size: 12px; color: var(--muted); background: rgba(255, 255, 255, 0.05); border-radius: 999px; padding: 1px 9px; }
  .why { margin-top: 6px !important; color: var(--muted); }
  .card:not(.big) .why { display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .big .why { color: var(--text); font-size: 15.5px; max-width: 64ch; }
  .src { font-size: 12.5px; color: var(--muted); margin-left: 4px; }
  .acts { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
  .card:not(.big) .acts button { padding: 4px 10px; font-size: 13.5px; }
  .primary { background: var(--text); color: var(--bg); border-color: var(--text); font-weight: 600; }
  .tracks, .full { grid-column: 1 / -1; }
  .tracks { list-style: none; margin: 4px 0 0; padding: 6px; display: grid; gap: 2px; border-radius: 12px; background: rgba(0, 0, 0, 0.18); }
  .warn { color: #f0a43c; margin: 0; }
  @media (max-width: 700px) { .card.big { grid-template-columns: 1fr; } }
</style>
