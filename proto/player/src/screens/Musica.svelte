<script lang="ts">
  import { untrack, tick } from 'svelte';
  import { music } from '../lib/music.svelte';
  import { seed } from '../lib/seed.svelte';
  import { nav } from '../lib/nav.svelte';
  import { player } from '../lib/player.svelte';
  import { library } from '../lib/library.svelte';
  import Cover from '../components/Cover.svelte';
  import Combo from '../components/Combo.svelte';
  import TrackRow from '../components/TrackRow.svelte';
  import { playback, queueItem } from '../lib/playback.svelte';

  interface Ids { local?: string; tidal?: string; spotify?: string; ytmusic?: string }
  interface Album { key: string; title: string; artist: string; year: number | null; genres: string[]; sources: string[]; localIds: string[]; tidalId: string | null; artUrl?: string }
  interface Track { key: string; title: string; artist: string; album: string; duration: number; genres: string[]; sources: string[]; ids: Ids; artUrl?: string }
  interface Facets { artists: { name: string; count: number }[]; genres: { name: string; count: number }[]; sources: Record<string, number> }

  const LIMIT = 60;
  const SRC: Record<string, string> = { local: 'Mis archivos', tidal: 'TIDAL', spotify: 'Spotify', ytmusic: 'YouTube Music' };
  const SRC_ORDER = ['local', 'tidal', 'spotify', 'ytmusic'];

  let kind = $state<'albums' | 'tracks'>('albums');
  let source = $state('');
  let artist = $state('');
  let genre = $state('');
  let sort = $state<'saved' | 'alpha' | 'artist'>('saved');
  let query = $state('');
  let debounced = $state('');
  let items = $state<(Album | Track)[]>([]);
  let total = $state(0);
  let facets = $state<Facets>({ artists: [], genres: [], sources: {} });
  let loading = $state(true);
  let more = $state(false);
  let failed = $state(false);
  let sentinel = $state<HTMLElement>();
  let seq = 0;

  let gridEl = $state<HTMLElement>();
  let detailEl = $state<HTMLElement>();
  let cols = $state(1);
  let openAlbum = $state<Album | null>(null);
  let albumTracks = $state<{ title: string; artist: string; album: string; duration: number; ids: Ids }[] | null>(null);
  let albumError = $state('');

  let t = 0;
  $effect(() => { const q = query; window.clearTimeout(t); t = window.setTimeout(() => (debounced = q.trim()), 250); return () => window.clearTimeout(t); });

  const params = (offset: number) => {
    const p = new URLSearchParams({ kind, sort, limit: String(LIMIT), offset: String(offset) });
    if (debounced) p.set('q', debounced);
    if (source) p.set('source', source);
    if (artist) p.set('artist', artist);
    if (genre) p.set('genre', genre);
    return p;
  };

  async function load(reset: boolean) {
    const my = ++seq;
    if (reset) { loading = true; more = false; } else more = true;
    try {
      const res = await fetch(`/engine/music?${params(reset ? 0 : items.length)}`);
      if (!res.ok) throw new Error();
      const r = await res.json();
      if (my !== seq) return;
      items = reset ? r.items : [...items, ...r.items];
      total = r.total; facets = r.facets; failed = false;
      music.status = r.status; music.sources = r.facets.sources;
      if (music.working) music.loadStatus();
    } catch {
      if (my === seq) failed = true;
    } finally {
      if (my === seq) { loading = false; more = false; }
    }
  }

  // Cualquier cambio de filtro, búsqueda, vista o catálogo vuelve a pedir desde el principio.
  $effect(() => { kind; source; artist; genre; sort; debounced; music.version; untrack(() => load(true)); });
  $effect(() => { untrack(() => { library.load(); }); });
  $effect(() => {
    if (!sentinel) return;
    const io = new IntersectionObserver(es => { if (es[0].isIntersecting && !loading && !more && !failed && items.length < total) load(false); }, { rootMargin: '600px' });
    io.observe(sentinel);
    return () => io.disconnect();
  });

  // El detalle del álbum se abre en la grilla, justo debajo de la fila del álbum elegido (no flota en un costado de la pantalla).
  $effect(() => {
    if (!gridEl) return;
    const el = gridEl;
    const measure = () => { cols = Math.max(1, getComputedStyle(el).gridTemplateColumns.split(' ').length); };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  });
  const rowEnd = $derived.by(() => {
    if (!openAlbum) return -1;
    const i = items.findIndex(x => x.key === openAlbum!.key);
    return i < 0 ? -1 : Math.min(items.length - 1, (Math.floor(i / cols) + 1) * cols - 1);
  });
  // Si cambia la búsqueda o un filtro, el álbum abierto puede ya no estar: se cierra.
  $effect(() => { kind; source; artist; genre; sort; debounced; untrack(() => (openAlbum = null)); });

  const filtered = $derived(!!(debounced || source || artist || genre));
  const noSources = $derived(!loading && !failed && !filtered && !SRC_ORDER.some(x => facets.sources[x]) && !music.working);
  const st = $derived(music.status);
  const busy = $derived(music.working);
  // Última vez que se trajo algo de las cuentas (TIDAL, Spotify, YouTube Music); se actualiza solo con el botón.
  const updatedAt = $derived(Math.max(0, st?.tidal.fetchedAt ?? 0, ...Object.values(st?.providers ?? {}).map(p => p.fetchedAt ?? 0)));
  const ago = (t: number) => {
    const s = Math.max(0, Date.now() / 1000 - t);
    return s < 90 ? 'recién' : s < 5400 ? `hace ${Math.round(s / 60)} min` : s < 129600 ? `hace ${Math.round(s / 3600)} h` : `hace ${Math.round(s / 86400)} días`;
  };
  const mm = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
  const badge = (s: string[]) => (source ? '' : s.map(x => SRC[x] ?? x).join(' + '));
  const clear = () => { query = ''; source = ''; artist = ''; genre = ''; };

  async function open(a: Album) {
    if (openAlbum?.key === a.key) { openAlbum = null; return; }  // otro clic en el mismo álbum lo cierra
    openAlbum = a; albumTracks = null; albumError = '';
    tick().then(() => detailEl?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }));
    try {
      const res = await fetch(`/engine/music/album?key=${encodeURIComponent(a.key)}`);
      const r = await res.json();
      if (openAlbum?.key !== a.key) return;
      if (!res.ok) albumError = r.message ?? 'No pude leer el álbum.'; else albumTracks = r.tracks;
      tick().then(() => detailEl?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }));
    } catch { albumError = 'No pude hablar con el motor.'; }
  }
  // Cola del álbum abierto: ▶ en una fila sigue hasta el final del disco.
  const albumQueue = $derived(openAlbum && albumTracks ? albumTracks.map(x => queueItem({ title: x.title, artist: x.artist, album: x.album, ids: x.ids, art: openAlbum!.artUrl, seconds: x.duration })) : []);
  const similar = (s: { artist: string; album?: string; title?: string }) => { seed.set(s); nav.go('recomendaciones'); };
  const asAlbum = (i: Album | Track) => i as Album;
  const asTrack = (i: Album | Track) => i as Track;
</script>

<div class="head">
  <h2>Música</h2>
  <div class="status">
    {#if st?.genres.running}<span class="muted num">Completando géneros {st.genres.done} de {st.genres.total}</span>{/if}
    {#if busy && !st?.genres.running}<span class="muted">Actualizando…</span>{:else if updatedAt}<span class="muted num" title="La música de tus cuentas se guarda en esta computadora y solo se vuelve a pedir con Actualizar">Actualizado {ago(updatedAt)}</span>{/if}
    <button class="ghost" onclick={() => music.refresh()} disabled={busy}>Actualizar</button>
  </div>
</div>

{#if noSources}
  <section class="empty">
    <b>Todavía no hay música</b>
    <p class="muted">Agregá una carpeta o conectá TIDAL, Spotify o YouTube Music.</p>
    <a class="btn" href="#/fuentes">Ir a Fuentes</a>
  </section>
{:else}
  <div class="bar">
    <input type="search" placeholder="Buscar artista, disco o tema" bind:value={query} aria-label="Buscar en tu música" />
    <div class="seg" role="group" aria-label="Fuente">
      <button class:on={source === ''} onclick={() => (source = '')}>Todas</button>
      {#each SRC_ORDER.filter(s => facets.sources[s] || source === s) as s (s)}
        <button class:on={source === s} onclick={() => (source = s)}>{SRC[s]} <span class="num">{facets.sources[s] ?? 0}</span></button>
      {/each}
    </div>
    <Combo label="Artista" items={facets.artists} bind:value={artist} />
    <Combo label="Género" items={facets.genres} bind:value={genre} />
    <label class="ord">Orden
      <select bind:value={sort} aria-label="Orden">
        <option value="saved">Guardado</option>
        <option value="alpha">Alfabético</option>
        <option value="artist">Artista</option>
      </select>
    </label>
    <div class="seg view" role="group" aria-label="Vista">
      <button class:on={kind === 'albums'} onclick={() => (kind = 'albums')}>Álbumes</button>
      <button class:on={kind === 'tracks'} onclick={() => (kind = 'tracks')}>Temas</button>
    </div>
  </div>

  <div class="count muted num">
    {#if !loading && !failed}{total} {kind === 'albums' ? (total === 1 ? 'álbum' : 'álbumes') : (total === 1 ? 'tema' : 'temas')}{/if}
    {#if filtered}<button class="link" onclick={clear}>Limpiar filtros</button>{/if}
  </div>

  {#if failed}
    <section class="empty"><b>No pude hablar con el motor</b><button onclick={() => load(true)}>Reintentar</button></section>
  {:else if loading && !items.length}
    <div class="grid" aria-busy="true" aria-label="Cargando">
      {#each Array(12) as _, i (i)}<div class="card sk"><div class="art"></div><i></i><i class="s"></i></div>{/each}
    </div>
  {:else if !items.length}
    <section class="empty">
      <b>{filtered ? 'No hay resultados' : busy ? 'Leyendo tu música…' : 'Todavía no hay ' + (kind === 'albums' ? 'álbumes' : 'temas')}</b>
      {#if filtered}<button onclick={clear}>Limpiar filtros</button>{/if}
    </section>
  {:else if kind === 'albums'}
    <div class="grid" bind:this={gridEl}>
      {#each items as it, idx (it.key + (it as Album).tidalId)}
        {@const a = asAlbum(it)}
        <button class="card" class:sel={openAlbum?.key === a.key} onclick={() => open(a)} aria-label="{a.title}, {a.artist}">
          <div class="art"><Cover title={a.title} artist={a.artist} size={400} radius={12} src={a.artUrl} /></div>
          <b>{a.title}</b>
          <span class="muted line">{a.artist}{a.year ? `, ${a.year}` : ''}</span>
          {#if !source}<span class="tags">{#each a.sources as s (s)}<em>{SRC[s] ?? s}</em>{/each}</span>{/if}
        </button>
        {#if openAlbum && idx === rowEnd}
          <section class="detail" bind:this={detailEl} aria-label="Detalle del álbum">
            <button class="x ghost" onclick={() => (openAlbum = null)} aria-label="Cerrar" title="Cerrar (Esc)">✕</button>
            <div class="ah">
              <Cover title={openAlbum.title} artist={openAlbum.artist} size={132} radius={12} src={openAlbum.artUrl} />
              <div>
                <h3>{openAlbum.title}</h3>
                <span class="muted">{openAlbum.artist}{openAlbum.year ? `, ${openAlbum.year}` : ''}</span>
                <span class="tags">{#each openAlbum.sources as s (s)}<em>{SRC[s] ?? s}</em>{/each}</span>
                {#if openAlbum.genres.length}<span class="muted g">{openAlbum.genres.join(', ')}</span>{/if}
                <div class="btns">
                  <button class="primary" onclick={() => playback.playFrom(albumQueue, 0)} disabled={!albumQueue.length}>Escuchar el álbum</button>
                  <button class="ghost" onclick={() => similar({ artist: openAlbum!.artist, album: openAlbum!.title })}>Recomendar parecidos</button>
                </div>
              </div>
            </div>
            {#if !openAlbum.tidalId && !openAlbum.localIds.length}<p class="muted">Temas de tu cuenta ({openAlbum.sources.map(x => SRC[x] ?? x).join(', ')}). Para escucharlos, la app busca el audio en tus archivos o en TIDAL.</p>{/if}
            {#if albumError}<p class="err" role="alert">{albumError}</p>
            {:else if !albumTracks}<p class="muted">Cargando temas…</p>
            {:else}
              <ul class="list">
                {#each albumTracks as x, i (i + x.title)}
                  <TrackRow compact n={i + 1} title={x.title} artist={x.artist} album={x.album} duration={mm(x.duration)} ids={x.ids} art={openAlbum.artUrl} queue={albumQueue} qi={i} />
                {:else}<li class="muted">Sin temas.</li>{/each}
              </ul>
            {/if}
          </section>
        {/if}
      {/each}
    </div>
  {:else}
    <ul class="list">
      {#each items as it (it.key + JSON.stringify(asTrack(it).ids))}
        {@const x = asTrack(it)}
        <TrackRow compact title={x.title} artist={x.artist} album={x.album} meta={x.album} duration={mm(x.duration)} ids={x.ids} art={x.artUrl} badge={badge(x.sources)} />
      {/each}
    </ul>
  {/if}
  <div bind:this={sentinel} class="sentinel muted">{more ? 'Cargando más…' : ''}</div>
{/if}

<svelte:window onkeydown={e => { if (e.key === 'Escape' && openAlbum && !(e.target instanceof HTMLElement && e.target.matches('input, select, textarea'))) openAlbum = null; }} />

<style>
  .head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
  h2 { margin: 0; font-size: 28px; letter-spacing: -0.02em; }
  .status { display: flex; align-items: center; gap: 12px; font-size: 14px; }
  .ghost { background: transparent; }
  .bar { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; padding: 10px; border-radius: var(--radius); background: var(--glass); border: 1px solid var(--glass-line); backdrop-filter: blur(16px) saturate(1.3); position: sticky; top: 8px; z-index: 5; }
  .bar input { flex: 1; min-width: 220px; max-width: 380px; background: rgba(255,255,255,0.06); border: 1px solid var(--glass-line); border-radius: 10px; padding: 8px 12px; }
  .seg { display: flex; gap: 2px; padding: 3px; border-radius: 12px; background: rgba(255,255,255,0.05); }
  .seg button { border: 0; background: transparent; border-radius: 9px; padding: 5px 12px; }
  .seg button.on { background: rgba(255,255,255,0.16); }
  .seg .num { font-size: 12px; color: var(--muted); margin-left: 4px; }
  .ord { display: flex; align-items: center; gap: 6px; font-size: 13.5px; color: var(--muted); }
  .ord select { background: rgba(255,255,255,0.06); color: var(--text); border: 1px solid var(--glass-line); border-radius: 9px; padding: 5px 8px; }
  .view { margin-left: auto; }
  .count { font-size: 13.5px; display: flex; gap: 14px; min-height: 20px; }
  .link { background: none; border: 0; padding: 0; color: var(--text); text-decoration: underline; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(168px, 1fr)); gap: 18px 16px; }
  .card { display: grid; gap: 3px; text-align: left; padding: 8px; border-radius: 16px; background: transparent; border: 1px solid transparent; align-content: start; transition: background 0.2s, transform 0.25s var(--ease); }
  .card:hover { background: rgba(255,255,255,0.06); transform: translateY(-2px); }
  .card.sel { background: rgba(255,255,255,0.1); border-color: var(--glass-line); }
  .art { aspect-ratio: 1; border-radius: 12px; overflow: hidden; margin-bottom: 6px; box-shadow: 0 14px 28px -14px rgba(0,0,0,0.8); }
  .art :global(img), .art :global(svg), .art :global(.cv) { width: 100% !important; height: 100% !important; display: block; }
  .card b, .line { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .card b { font-weight: 600; }
  .line { font-size: 13.5px; }
  .tags { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 3px; }
  em { font-style: normal; font-size: 11px; font-weight: 600; letter-spacing: 0.02em; padding: 1px 8px; border-radius: 999px; border: 1px solid var(--glass-line); color: var(--muted); background: rgba(255,255,255,0.04); }
  .sk i { height: 12px; border-radius: 6px; background: linear-gradient(90deg, rgba(255,255,255,0.04), rgba(255,255,255,0.12), rgba(255,255,255,0.04)); background-size: 200% 100%; animation: shimmer 1.6s linear infinite; }
  .sk i.s { width: 60%; }
  .sk .art { background: linear-gradient(90deg, rgba(255,255,255,0.04), rgba(255,255,255,0.1), rgba(255,255,255,0.04)); background-size: 200% 100%; animation: shimmer 1.6s linear infinite; box-shadow: none; }
  .list { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
  .sentinel { text-align: center; min-height: 24px; font-size: 13px; }
  .empty { display: grid; gap: 8px; justify-items: start; padding: 28px; border-radius: var(--radius); background: var(--glass); border: 1px dashed rgba(255,255,255,0.2); }
  .empty b { font-size: 19px; } .empty p { margin: 0; }
  .btn, .primary { background: var(--text); color: var(--bg); border: 1px solid var(--text); font-weight: 600; border-radius: 9px; padding: 7px 14px; text-decoration: none; justify-self: start; }
  .err { color: var(--loop); margin: 0; }
  .detail { grid-column: 1 / -1; position: relative; display: grid; gap: 14px; padding: 18px 20px; border-radius: 18px; background: rgba(255, 255, 255, 0.06); border: 1px solid var(--glass-line); animation: rise 0.3s var(--ease) both; scroll-margin: 70px 0 150px; }
  .x { position: absolute; top: 12px; right: 12px; width: 32px; height: 32px; padding: 0; border-radius: 50%; }
  .ah { display: flex; gap: 18px; align-items: flex-end; padding-right: 40px; }
  .ah div { display: grid; gap: 4px; min-width: 0; }
  .ah h3 { margin: 0; font-size: 22px; letter-spacing: -0.01em; }
  .g { font-size: 13px; }
  .btns { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 4px; }
</style>
