<script lang="ts">
  import Cover from '../Cover.svelte';
  import TrackRow from '../TrackRow.svelte';
  import { recs, REACTION_LABELS, type About, type Item, type Reaction } from '../../lib/recs.svelte';
  import { player } from '../../lib/player.svelte';
  import { queueItem } from '../../lib/playback.svelte';
  import SaveBox from './SaveBox.svelte';
  let saving = $state(false);
  let known = $state(false);
  let { item, big = false, onreact }: { item: Item; big?: boolean; onreact: (item: Item, r: Reaction, known: boolean) => void } = $props();

  let ctx = $state<'idle' | 'loading' | 'none' | 'error'>('idle');
  let ctxAbout = $state<About | null>(null);
  const about = $derived(item.about ?? ctxAbout);
  async function loadAbout() {
    ctx = 'loading';
    try { ctxAbout = await recs.loadContext(item.mbid); ctx = ctxAbout ? 'idle' : 'none'; } catch { ctx = 'error'; }
  }

  const rates: { id: Reaction; label: string; hint: string }[] = [
    { id: 'loved', label: 'Me encantó', hint: 'Suma mucho a tu gusto' },
    { id: 'liked', label: 'Me gusta', hint: 'Suma un poco a tu gusto' },
    { id: 'disliked', label: 'No me gustó', hint: 'No te lo vuelvo a proponer' },
    { id: 'no', label: 'No me interesa', hint: 'Solo lo saco de la lista; no cambia tu gusto' },
  ];
  function rate(r: Reaction) { onreact(item, r, known); }
  const secs = (n: number | null) => (n == null ? '' : `${Math.floor(n / 60)}:${String(n % 60).padStart(2, '0')}`);
  const cachedIds = $derived(new Set(player.tracks.map(t => t.id)));
  const tracks = $derived(recs.albums[item.mbid]);
  // ▶ en un tema sigue con los demás del disco.
  const queue = $derived(tracks?.state === 'ready' ? tracks.tracks.map(t => queueItem({ title: t.title, artist: t.artist, album: item.album, sourceId: t.id, art: `/engine/cover/${item.mbid}`, seconds: t.duration ?? undefined })) : []);
  const size = $derived(big ? 220 : 72);
</script>

<article class="card" class:big>
  <div class="cover"><Cover title={item.album} artist={item.artist} {size} radius={big ? 16 : 10} src="/engine/cover/{item.mbid}" eager priority={big} /></div>
  <div class="body">
    <h3>{item.album}</h3>
    <p class="who">{item.artist}{item.year ? ` · ${item.year}` : ''}
      <a class="ok" href="https://musicbrainz.org/release-group/{item.mbid}" target="_blank" rel="noopener noreferrer" title="Verificado en MusicBrainz">✓ MusicBrainz</a>
    </p>
    {#if item.genres.length}
      <p class="genres">{#each item.genres as g (g)}<span>{g}</span>{/each}</p>
    {/if}
    {#if about?.text}
      <p class="why">{about.text}
        <a class="src" href={about.url} target="_blank" rel="noopener noreferrer">{about.source === 'wikipedia' ? 'Wikipedia' : 'MusicBrainz'}</a>
      </p>
    {:else}
      <button class="link" onclick={loadAbout} disabled={ctx === 'loading'}>
        {ctx === 'loading' ? 'Buscando contexto…' : ctx === 'none' ? 'No encontré contexto de este disco' : ctx === 'error' ? 'No pude armarlo. Reintentar' : 'Contarme más del disco'}
      </button>
    {/if}
    {#if item.trail}
      <details class="trail">
        <summary>Por qué este disco</summary>
        <ul>
          {#if item.genre}<li><b>Género:</b> {item.genre.why}</li>{/if}
          {#each item.overlap ?? [] as o (o.genre + o.user)}
            <li><b>Tus gustos:</b> {o.genre} ↔ {o.user} <span class="muted">({o.from.join(' y ')})</span></li>
          {/each}
          {#if item.trail.review?.note}<li><b>Revisor:</b> {item.trail.review.note}</li>{/if}
          {#if item.trail.classifier}
            <li><b>Clasificador ({item.trail.classifier.backend}):</b> {item.trail.classifier.label === 'entailment' ? 'lo ve del género' : item.trail.classifier.label === 'contradiction' ? 'no lo ve del género' : 'no se pronuncia'}
              ({Math.round(item.trail.classifier.p[item.trail.classifier.label] * 100)} %{item.trail.classifier.calibrated ? '' : ', sin calibrar'})</li>
          {/if}
          <li><b>Lo propuso:</b> {item.trail.proposedBy}, ronda {item.trail.round}{item.trail.confidence != null ? `, seguridad ${item.trail.confidence}%` : ''}</li>
          <li><b>Verificado:</b> existe en MusicBrainz{item.trail.mbScore != null ? ` (coincidencia ${item.trail.mbScore}%)` : ''} · {item.trail.type}</li>
          <li><b>Puntaje:</b> {item.trail.score.final.toFixed(2)} = cercanía a tus gustos {item.trail.score.fit.toFixed(2)}{item.trail.score.gate != null ? ` + género ${item.trail.score.gate.toFixed(2)}` : ''}</li>
        </ul>
      </details>
    {/if}
    <div class="acts">
      <button class="primary" onclick={() => recs.openAlbum(item.mbid, item.artist, item.album)} disabled={tracks?.state === 'loading'}>
        {tracks?.state === 'loading' ? 'Buscando…' : 'Ver temas'}
      </button>
      <button class="ghost" onclick={() => (saving = !saving)} aria-expanded={saving}>Guardar</button>
    </div>
      <div class="rate" role="group" aria-label="Qué te pareció este disco">
        {#each rates as r (r.id)}
          <button class={r.id} onclick={() => rate(r.id)} title={r.hint}>{r.label}</button>
        {/each}
      </div>
      <label class="known"><input type="checkbox" bind:checked={known} /> Ya lo conocía</label>
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
  .link { justify-self: start; border: 0; background: transparent; padding: 0; color: var(--muted); font-size: 13px; text-decoration: underline; text-underline-offset: 3px; cursor: pointer; }
  .link:hover:not(:disabled) { color: var(--text); }
  .trail { margin-top: 6px; }
  .trail summary { cursor: pointer; color: var(--muted); font-size: 13px; width: fit-content; }
  .trail ul { list-style: none; margin: 6px 0 0; padding: 8px 12px; display: grid; gap: 4px; font-size: 13px; color: var(--muted); border-radius: 10px; background: rgba(0, 0, 0, 0.18); }
  .trail b { color: var(--text); font-weight: 600; }
  .acts { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; align-items: center; }
  .ghost { background: transparent; }
  .rate { display: inline-flex; flex-wrap: wrap; margin-top: 18px; border: 1px solid var(--glass-line); border-radius: 10px; overflow: hidden; align-self: start; }
  .known { display: flex; gap: 6px; align-items: center; margin-top: 8px; font-size: 13px; color: var(--muted); cursor: pointer; width: fit-content; }
  .rate button { border: 0; border-radius: 0; background: transparent; border-right: 1px solid var(--glass-line); }
  .rate button:last-child { border-right: 0; color: var(--muted); }
  .rate button:hover { background: rgba(255, 255, 255, 0.08); }
  .rate .loved { color: #7cc7a3; font-weight: 600; }
  .card:not(.big) .acts button { padding: 4px 10px; font-size: 13.5px; }
  .primary { background: var(--text); color: var(--bg); border-color: var(--text); font-weight: 600; }
  .tracks, .full { grid-column: 1 / -1; }
  .tracks { list-style: none; margin: 4px 0 0; padding: 6px; display: grid; gap: 2px; border-radius: 12px; background: rgba(0, 0, 0, 0.18); }
  .warn { color: #f0a43c; margin: 0; }
  @media (max-width: 700px) { .card.big { grid-template-columns: 1fr; } }
</style>
