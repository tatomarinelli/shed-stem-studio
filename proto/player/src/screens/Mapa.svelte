<script lang="ts">
  // El mapa de tu música: lo que más pesa al centro, lo que menos hacia afuera y los recomendados en el anillo exterior.
  import { onMount } from 'svelte';
  import { graph, KINDS, KIND_LABEL, KIND_ONE, communityColor, type GNode, type Kind } from '../lib/graph.svelte';
  import GraphView from '../components/GraphView.svelte';
  import AlbumPanel from '../components/AlbumPanel.svelte';
  import { recs } from '../lib/recs.svelte';
  import type { Request } from '../lib/recs.svelte';
  import { nav } from '../lib/nav.svelte';

  onMount(() => { if (graph.state !== 'ready') void graph.load(); });

  let kinds = $state<Kind[]>(['album', 'artist', 'genre', 'rec']);
  let query = $state('');
  let selected = $state('');
  let view = $state<'mapa' | 'lista'>('mapa');
  let colorBy = $state<'type' | 'community'>('type');
  let communities = $state<number[]>([]);   // se pueden elegir varias: el mapa se enfoca en la unión

  const norm = (t: string) => t.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
  const visible = $derived((graph.data?.nodes ?? []).filter(n => kinds.includes(n.type)));
  const hits = $derived.by(() => {
    const q = norm(query.trim());
    if (!q) return [];
    return visible.filter(n => norm(n.label).includes(q) || norm(n.artist ?? '').includes(q)).sort((a, b) => b.w - a.w).slice(0, 8);
  });
  const list = $derived([...visible].sort((a, b) => b.w - a.w || a.label.localeCompare(b.label)).slice(0, 400));
  const node = $derived(selected ? graph.byId.get(selected) : undefined);
  const near = $derived(selected ? graph.neighbors(selected) : []);
  const stats = $derived(graph.data?.stats);
  const noGenre = $derived((graph.data?.nodes ?? []).filter(n => n.type === 'album' && n.genresFrom === 'none').length);

  const pick = (n: GNode) => { selected = n.id; communities = []; query = ''; };
  const pickId = (id: string) => { const n = graph.byId.get(id); if (n) pick(n); };
  const cname = (c: number) => graph.data?.communities[c]?.name ?? 'Sueltos';
  const focus = (c: number) => { selected = ''; communities = communities.includes(c) ? communities.filter(x => x !== c) : [...communities, c]; };
  const chosen = $derived(communities.map(c => graph.data?.communities[c]).filter((c): c is NonNullable<typeof c> => !!c));
  /** Pedido al recomendador: solo el nombre de las zonas. El motor lee del mapa todos sus artistas, géneros y discos (no los manda el navegador). */
  const askRecs = async () => {
    const names = chosen.map(c => c.name);
    const body: Partial<Request> = { prompt: `Algo parecido a mi zona de ${names.join(' y ')}`, map: { communities: names } };
    nav.go('recomendaciones');
    await recs.generate('request', body);
  };
  const toggle = (k: Kind) => { kinds = kinds.includes(k) ? kinds.filter(x => x !== k) : [...kinds, k]; if (node && !kinds.includes(node.type)) selected = ''; };
  const SRC: Record<string, string> = { tidal: 'TIDAL', ytmusic: 'YouTube Music', spotify: 'Spotify', local: 'Archivos locales' };
  const REACT: Record<string, string> = { loved: 'Me encantó', liked: 'Me gusta', disliked: 'No me gustó', no: 'No me interesa', heard: 'Lo conocía' };
  const EDGE: Record<string, string> = { by: 'Autor', 'has-genre': 'Género', 'subgenre-of': 'Jerarquía', similar: 'Parecido', 'similar-to': 'Se parece a', related: 'Artista parecido' };
  const num = (v: number) => v.toLocaleString('es-AR', { maximumFractionDigits: 2 });
  const evidence = (ev: { kind: string }[]) => ev.map(e => (e.kind === 'catalog' ? 'catálogo' : e.kind === 'rule' ? 'regla propia' : 'calculado')).join(', ');
</script>

<div class="head">
  <h2>Mapa</h2>
  {#if stats}<span class="muted small">{stats.album} discos · {stats.artist} artistas · {stats.genre} géneros · {stats.rec} recomendados</span>{/if}
</div>
{#if noGenre}
  <p class="muted small gen" aria-live="polite">
    {noGenre} discos sin género: solo se relacionan con su artista.
    {#if graph.enrich.running}<span>Buscando en MusicBrainz… {graph.enrich.done}/{graph.enrich.total}</span>
    {:else}<button class="link" onclick={() => graph.completeGenres()}>Completar con MusicBrainz</button>{/if}
  </p>
{/if}
<p class="muted intro">Al centro, lo que más pesa en tus gustos; hacia afuera, lo que menos; en el anillo exterior, lo recomendado. Todavía no mide cuánto escuchás cada cosa: el peso sale de lo que guardaste, cuándo y cómo reaccionaste.</p>

{#if graph.state === 'loading' || graph.state === 'idle'}
  <p class="muted" role="status">Armando el mapa…</p>
{:else if graph.state === 'no_engine'}
  <section class="empty"><p>El motor local está apagado.</p><p class="muted small">Iniciálo con "npm run engine" en proto/player.</p></section>
{:else if graph.state === 'error' || !graph.data}
  <section class="empty"><p>No se pudo armar el mapa.</p><button class="ghost" onclick={() => graph.load()}>Reintentar</button></section>
{:else if !graph.data.nodes.length}
  <section class="empty"><p>Todavía no hay música para mostrar.</p><a class="go" href="#/fuentes">Conectar una fuente</a></section>
{:else}
  <div class="bar">
    <div class="search">
      <input type="search" placeholder="Buscar un artista, género o disco" aria-label="Buscar en el mapa" bind:value={query}
        onkeydown={e => { if (e.key === 'Enter' && hits[0]) pick(hits[0]); }} />
      {#if hits.length}
        <ul class="hits" aria-label="Resultados">
          {#each hits as h (h.id)}<li><button onclick={() => pick(h)}><b>{h.label}</b> <span class="muted">{KIND_ONE[h.type]}{h.artist ? ` · ${h.artist}` : ''}</span></button></li>{/each}
        </ul>
      {/if}
    </div>
    <div class="chips" role="group" aria-label="Qué mostrar">
      {#each KINDS as k (k)}
        <label class="chip {k}" class:on={kinds.includes(k)}><input type="checkbox" checked={kinds.includes(k)} onchange={() => toggle(k)} /><i aria-hidden="true"></i>{KIND_LABEL[k]}</label>
      {/each}
    </div>
    <div class="seg" role="group" aria-label="Colorear por">
      <button class:on={colorBy === 'type'} aria-pressed={colorBy === 'type'} onclick={() => (colorBy = 'type')}>Tipo</button>
      <button class:on={colorBy === 'community'} aria-pressed={colorBy === 'community'} onclick={() => (colorBy = 'community')}>Comunidad</button>
    </div>
    <div class="seg" role="group" aria-label="Vista">
      <button class:on={view === 'mapa'} aria-pressed={view === 'mapa'} onclick={() => (view = 'mapa')}>Mapa</button>
      <button class:on={view === 'lista'} aria-pressed={view === 'lista'} onclick={() => (view = 'lista')}>Lista</button>
    </div>
  </div>

  <div class="stage">
    <div class="main">
      {#if view === 'mapa'}
        <GraphView data={graph.data} {selected} {kinds} {colorBy} {communities} onselect={id => { selected = id; if (id) communities = []; }} />
        <ul class="legend" aria-label="Qué significan los colores">
          {#if colorBy === 'type'}
            <li><i class="d" style="background:#7cc7a3"></i>Disco · misma banda</li>
            <li><i class="d" style="background:#f08fb0"></i>Otra banda: disco o artista parecido (al elegir uno)</li>
            <li><i class="d" style="background:#4fa3d9"></i>Artista, centro de su flor</li>
            <li><i class="d" style="background:#c58bf0"></i>Género</li>
            <li><i class="d" style="background:#f0a43c"></i>Recomendado</li>
          {:else}
            <li class="muted">Cada color es una comunidad: lo que se junta por géneros y artistas.</li>
          {/if}
        </ul>
      {:else}
        <table class="list">
          <caption class="sr">Nodos del mapa, de mayor a menor peso</caption>
          <thead><tr><th>Nombre</th><th>Tipo</th><th class="n">Peso</th></tr></thead>
          <tbody>
            {#each list as n (n.id)}
              <tr class:sel={n.id === selected}>
                <td><button class="link" onclick={() => pick(n)}>{n.label}</button>{#if n.artist}<span class="muted"> · {n.artist}</span>{/if}</td>
                <td>{KIND_ONE[n.type]}</td><td class="n">{num(n.w)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
        {#if visible.length > list.length}<p class="muted small">Se muestran los {list.length} de más peso; buscá para llegar al resto.</p>{/if}
      {/if}
    </div>

    <aside class="panel" aria-live="polite" aria-label="Detalle">
      {#if node}
        {#if node.type === 'album' || node.type === 'rec'}
          <AlbumPanel {node} />
        {:else}
          <h3>{node.label}</h3>
          <p class="muted small">{KIND_ONE[node.type]}</p>
        {/if}
        {#if node.type !== 'rec'}<p class="small">Peso <b>{num(node.w)}</b> hoy</p>{/if}
        {#if node.genresFrom === 'artist'}<p class="small muted">Sin géneros propios: usa los del artista.</p>{/if}
        {#if node.genresFrom === 'none'}<p class="small muted">Todavía no tiene géneros, por eso solo se relaciona con su artista. Completalos desde Música.</p>{/if}
        {#if node.reaction}<p class="small">Reacción: {REACT[node.reaction] ?? node.reaction}</p>{/if}
        {#if node.saved}<p class="small muted">Guardado el {node.saved}</p>{/if}
        {#if node.reason}<p class="small"><span class="muted">Motivo:</span> {node.reason}</p>{/if}

        <h4>Por qué está acá</h4>
        {#if near.length}
          <ul class="why">
            {#each near.slice(0, 14) as { node: o, edge } (edge.from + edge.to + edge.type)}
              <li>
                <span class="tag">{EDGE[edge.type] ?? edge.type}</span> {edge.why}
                <span class="muted small">({evidence(edge.evidence)})</span>
              </li>
            {/each}
          </ul>
          <h4>Vecinos</h4>
          <ul class="nb">
            {#each near.slice(0, 14) as { node: o, edge } (o.id + edge.type)}
              <li><button class="link" onclick={() => pick(o)}>{o.label}</button> <span class="muted small">{KIND_ONE[o.type]} · {num(edge.w)}</span></li>
            {/each}
          </ul>
          {#if near.length > 14}<p class="muted small">y {near.length - 14} más</p>{/if}
        {:else}
          <p class="muted small">Sin conexiones todavía.</p>
        {/if}
        <button class="ghost" onclick={() => (selected = '')}>Soltar</button>
      {:else}
        {#if chosen.length}
          <h3>{chosen.length === 1 ? chosen[0].name : `${chosen.length} comunidades`}</h3>
          <p class="muted small">{chosen.reduce((n, c) => n + c.size, 0)} nodos · {chosen.reduce((n, c) => n + c.albums, 0)} discos</p>
          {#each chosen as c (c.id)}
            <p class="small"><i class="d" style="background:{communityColor(c.id)}"></i> <b>{c.name}</b><br /><span class="muted">{c.artists.join(', ') || '—'}</span></p>
          {/each}
          <h4>Pedir algo parecido</h4>
          <p class="small muted">El recomendador lee de la red todos los artistas, géneros y discos de {chosen.length === 1 ? 'esta zona' : 'estas zonas'} ({chosen.reduce((n, c) => n + c.size, 0)} nodos) y propone artistas nuevos.</p>
          <button class="primary" onclick={askRecs} disabled={recs.state === 'running' || recs.state === 'no_engine'}>Buscar recomendación desde acá</button>
          <p class="muted small">Empieza a buscar y te lleva a Recomendaciones.</p>
          <button class="ghost" onclick={() => (communities = [])}>Soltar</button>
          <h4>Sumar comunidades</h4>
          <ul class="nb">
            {#each graph.data.communities as c (c.id)}
              <li><button class="link comm" class:on={communities.includes(c.id)} aria-pressed={communities.includes(c.id)} onclick={() => focus(c.id)}><i class="d" style="background:{communityColor(c.id)}"></i>{c.name}</button> <span class="muted small">{c.size}</span></li>
            {/each}
          </ul>
        {:else}
          <p class="muted">Tocá un disco, un artista o un género para ver con qué se conecta y por qué. Elegí una o más comunidades para pedir algo parecido.</p>
          <h4>Comunidades</h4>
          <ul class="nb">
            {#each graph.data.communities as c (c.id)}
              <li><button class="link comm" class:on={communities.includes(c.id)} aria-pressed={communities.includes(c.id)} onclick={() => focus(c.id)}><i class="d" style="background:{communityColor(c.id)}"></i>{c.name}</button> <span class="muted small">{c.size}</span></li>
            {/each}
          </ul>
          {#if graph.data.bridges.length}
            <h4>Puentes</h4>
            <ul class="why">
              {#each graph.data.bridges as b (b.id)}<li><button class="link" onclick={() => pickId(b.id)}>{b.label}</button> <span class="muted small">calculado</span><br />{b.why}</li>{/each}
            </ul>
          {/if}
          {#if graph.data.gaps.length}
            <h4>Te falta explorar</h4>
            <ul class="why">
              {#each graph.data.gaps as x (x.genre)}<li><b>{x.genre}</b> <span class="muted small">regla propia</span><br />{x.why}</li>{/each}
            </ul>
          {/if}
          <p class="muted small">Cada frase sale de datos de tu catálogo o de una regla; lo calculado se marca así.</p>
        {/if}
      {/if}
    </aside>
  </div>
{/if}

<style>
  .head { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; flex-wrap: wrap; }
  h2 { margin: 0; font-size: 28px; letter-spacing: -0.02em; }
  h3 { margin: 0; font-size: 19px; overflow-wrap: anywhere; }
  h4 { margin: 10px 0 4px; font-size: 12.5px; letter-spacing: 0.05em; text-transform: uppercase; color: var(--muted); }
  .small { font-size: 13px; margin: 0; }
  .gen { margin: 0; }
  .intro { margin: 0; max-width: 78ch; }
  .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
  .bar { display: flex; gap: 12px 18px; flex-wrap: wrap; align-items: center; }
  .search { position: relative; flex: 1 1 260px; max-width: 420px; }
  .search input { width: 100%; box-sizing: border-box; padding: 9px 14px; border-radius: 999px; border: 1px solid var(--glass-line); background: var(--glass); color: var(--text); font: inherit; outline: none; }
  .search input:focus-visible { border-color: var(--text); }
  .search input::placeholder { color: var(--muted); }
  .hits { position: absolute; z-index: 5; left: 0; right: 0; top: calc(100% + 4px); list-style: none; margin: 0; padding: 4px; border-radius: 10px; background: var(--panel-hi); border: 1px solid var(--glass-line); display: grid; }
  .hits button { width: 100%; text-align: left; background: none; border: 0; padding: 6px 8px; border-radius: 6px; color: var(--text); cursor: pointer; }
  .hits button:hover, .hits button:focus-visible { background: rgba(255, 255, 255, 0.07); }
  .chips { display: flex; gap: 8px; flex-wrap: wrap; }
  .chip { display: inline-flex; align-items: center; gap: 6px; padding: 4px 12px; border-radius: 999px; border: 1px solid var(--glass-line); color: var(--muted); cursor: pointer; font-size: 14px; }
  .chip input { position: absolute; opacity: 0; pointer-events: none; }
  .chip i { width: 9px; height: 9px; border-radius: 50%; background: currentColor; opacity: 0.35; }
  .chip.on { color: var(--text); }
  .chip.on i { opacity: 1; }
  .legend { list-style: none; margin: 8px 0 0; padding: 0; display: flex; flex-wrap: wrap; gap: 4px 16px; font-size: 13px; color: var(--muted); }
  .legend li { display: inline-flex; align-items: center; gap: 6px; }
  .d { display: inline-block; width: 9px; height: 9px; border-radius: 50%; flex: none; }
  .comm.on { font-weight: 700; text-decoration-thickness: 2px; }
  .panel .primary { justify-self: start; padding: 8px 16px; border-radius: 10px; background: var(--text); color: var(--bg); font-weight: 600; border: 0; cursor: pointer; margin-top: 4px; }
  .comm { display: inline-flex; align-items: center; gap: 7px; text-decoration: none; }
  .chip.album.on i { background: #7cc7a3; } .chip.artist.on i { background: #4fa3d9; } .chip.genre.on i { background: #c58bf0; } .chip.rec.on i { background: #f0a43c; }
  .chip:has(input:focus-visible) { outline: 2px solid var(--text); outline-offset: 2px; }
  .seg { display: inline-flex; border: 1px solid var(--glass-line); border-radius: 999px; overflow: hidden; }
  .seg button { background: none; border: 0; color: var(--muted); padding: 5px 16px; cursor: pointer; }
  .seg button.on { background: var(--text); color: var(--bg); font-weight: 600; }
  .stage { display: grid; grid-template-columns: minmax(0, 1fr) 410px; gap: 14px; align-items: start; }
  .main { min-width: 0; display: grid; grid-template-rows: minmax(420px, min(70vh, 740px)) auto; align-content: start; }
  .main:has(.list) { display: block; height: min(72vh, 760px); overflow: auto; }
  .panel { padding: 14px 16px; border-radius: var(--radius); background: var(--glass); border: 1px solid var(--glass-line); display: grid; gap: 4px; max-height: min(72vh, 760px); overflow: auto; align-content: start; }
  .panel p { margin: 0; }
  .why, .nb { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; font-size: 14px; }
  .why li { overflow-wrap: anywhere; }
  .tag { font-size: 11.5px; border: 1px solid var(--glass-line); border-radius: 999px; padding: 0 8px; color: var(--muted); margin-right: 4px; }
  .link { background: none; border: 0; padding: 0; color: var(--text); text-decoration: underline; text-underline-offset: 3px; cursor: pointer; text-align: left; }
  .panel > button.ghost { justify-self: start; margin-top: 8px; }
  .list { width: 100%; border-collapse: collapse; font-size: 14px; }
  .list th { text-align: left; font-size: 12.5px; color: var(--muted); padding: 6px 8px; position: sticky; top: 0; background: var(--bg); }
  .list td { padding: 5px 8px; border-top: 1px solid rgba(255, 255, 255, 0.05); }
  .list .n { text-align: right; font-variant-numeric: tabular-nums; }
  .list tr.sel td { background: rgba(124, 199, 163, 0.12); }
  .empty { padding: 28px 8px; display: grid; gap: 12px; justify-items: start; }
  .empty p { margin: 0; font-size: 18px; }
  .go { padding: 8px 16px; border-radius: 10px; background: var(--text); color: var(--bg); font-weight: 600; text-decoration: none; }
  @media (max-width: 900px) { .stage { grid-template-columns: minmax(0, 1fr); } .panel { max-height: none; } }
</style>
