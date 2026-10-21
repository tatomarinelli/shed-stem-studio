<script lang="ts">
  import { onMount } from 'svelte';
  import { player } from '../lib/player.svelte';
  import { stemlist } from '../lib/stemlist.svelte';
  import { separation } from '../lib/separation.svelte';
  import { nav } from '../lib/nav.svelte';
  import Stack from '../components/Stack.svelte';
  import Metrics from '../components/Metrics.svelte';
  import Cover from '../components/Cover.svelte';
  import SectionChips from '../components/SectionChips.svelte';
  import AnalysisBar from '../components/AnalysisBar.svelte';
  import { analysis } from '../lib/analysis.svelte';
  import { untrack } from 'svelte';

  onMount(() => { void stemlist.load(); separation.watch(true); return () => separation.watch(false); });

  let query = $state('');
  let confirming = $state('');
  let failed = $state('');
  let listOpen = $state(true);

  const size = (b: number) => (b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : `${Math.max(1, Math.round(b / 1e6))} MB`);
  const norm = (s: string) => s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  const shown = $derived(stemlist.items.filter(i => !query || norm(`${i.title} ${i.artist}`).includes(norm(query))));
  const totals = $derived(stemlist.totals);
  const ready = $derived(player.status === 'ready' && !!player.track);

  // Al cambiar de tema se busca su análisis; cuando está, los pulsos van al motor de audio (click).
  $effect(() => { const id = ready ? player.track?.id : null; untrack(() => { if (id) analysis.load(id); else { analysis.data = null; player.setBeats(null); } }); });
  $effect(() => { const d = analysis.data; if (ready) untrack(() => player.setBeats(d?.tempo.beats ?? null, d?.tempo.downbeats ?? [])); });

  async function remove(id: string) {
    failed = '';
    const err = await stemlist.remove(id);
    if (err) { failed = err; return; }
    confirming = '';
    if (player.track?.id === id) player.unload();
    await player.init();
  }
</script>

<div class="studio" class:solo={!listOpen && ready}>
  {#if listOpen || !ready}
    <aside class="lib" aria-label="Temas descargados">
      <div class="top">
        <h3>Descargados</h3>
        <span class="muted num">{totals.count}</span>
        {#if ready}<button class="ghost" onclick={() => (listOpen = false)} aria-label="Ocultar la lista">Ocultar</button>{/if}
      </div>
      {#if separation.active.length}
        <ul class="proc" aria-label="En proceso" aria-live="polite">
          {#each separation.active as j (j.id)}
            <li class:err={j.state === 'error'}>
              <div class="pm"><b>{j.title || 'Tema ' + j.id}</b>{#if j.artist}<span class="muted">{j.artist}</span>{/if}</div>
              {#if j.state === 'running'}
                <div class="pbar" role="progressbar" aria-valuenow={j.percent} aria-valuemin="0" aria-valuemax="100"><i style="width:{Math.max(4, j.percent)}%"></i></div>
                <span class="muted num">{separation.stageLabel(j.stage)} {j.percent ? `${j.percent} %` : '…'}</span>
              {:else if j.state === 'error'}<span class="warn" role="alert">{j.message || 'No se pudo separar.'}</span>
              {:else}<span class="ok">Listo</span>{/if}
            </li>
          {/each}
        </ul>
      {/if}
      <input type="search" placeholder="Buscar" bind:value={query} aria-label="Buscar entre los descargados" />
      {#if stemlist.error}<p class="warn" role="alert">{stemlist.error}</p>{/if}
      <ul>
        {#each shown as t (t.id)}
          {@const active = ready && player.track?.id === t.id}
          <li class:active>
            <button class="row" onclick={() => player.load(t.id)} disabled={player.status === 'loading'} aria-current={active ? 'true' : undefined}>
              <Cover title={t.title} artist={t.artist} size={40} radius={8} src="/engine/art/{t.id}" />
              <span class="txt"><b>{t.title}</b><span class="muted">{t.artist}</span></span>
              <span class="muted num sz">{size(t.bytes)}</span>
            </button>
            {#if t.writable}
              {#if confirming === t.id}
                <div class="confirm" role="alert">
                  <span>¿Borrar los stems? Liberás {size(t.bytes)}.</span>
                  <button class="danger" onclick={() => remove(t.id)}>Borrar</button>
                  <button class="ghost" onclick={() => (confirming = '')}>Cancelar</button>
                </div>
              {:else}
                <button class="del" onclick={() => (confirming = t.id)} aria-label="Borrar {t.title}" title="Borrar los stems">Borrar</button>
              {/if}
            {:else}
              <span class="ro muted" title="Está en la caché anterior, que es de solo lectura">solo lectura</span>
            {/if}
          </li>
        {:else}
          <li class="empty-li muted">
            {#if stemlist.loaded && !stemlist.items.length}
              Todavía no separaste ningún tema. <a href="#/musica" onclick={() => nav.go('musica')}>Buscalo en Música</a>.
            {:else if stemlist.loaded}
              Nada coincide con "{query}".
            {:else}Leyendo…{/if}
          </li>
        {/each}
      </ul>
      {#if failed}<p class="warn" role="alert">{failed}</p>{/if}
      <p class="foot muted num">{size(totals.writable)} propios{totals.readonly ? `, ${size(totals.readonly)} anteriores` : ''}</p>
    </aside>
  {/if}

  <section class="daw">
    {#if ready && player.track}
      <div class="head">
        {#if !listOpen}<button onclick={() => (listOpen = true)}>Mostrar la lista</button>{/if}
        <div class="now">
          <Cover title={player.track.title} artist={player.track.artist} size={56} radius={10} src="/engine/art/{player.track.id}" />
          <div class="nt"><b>{player.track.title}</b><span class="muted">{player.track.artist}</span></div>
        </div>
        <SectionChips />
      </div>
      <AnalysisBar />
      <Stack />
      <Metrics />
    {:else if player.status === 'loading'}
      <div class="empty">
        <p class="big">Cargando {player.progress.name || 'stems'}…</p>
        <progress max={player.progress.total || 1} value={player.progress.done}></progress>
        <p class="muted num">{player.progress.done} de {player.progress.total}</p>
      </div>
    {:else if player.status === 'error'}
      <div class="empty">
        <p class="big err">No se pudo cargar el tema.</p>
        <p class="muted">{player.error}</p>
      </div>
    {:else if separation.processing.length}
      <div class="empty working" role="status" aria-live="polite">
        {#each separation.processing as j (j.id)}
          <p class="big">Separando «{j.title || 'el tema'}»</p>
          {#if j.artist}<p class="muted">{j.artist}</p>{/if}
          <div class="pbar big" role="progressbar" aria-valuenow={j.percent} aria-valuemin="0" aria-valuemax="100"><i style="width:{Math.max(4, j.percent)}%"></i></div>
          <p class="muted num">{separation.stageLabel(j.stage)} {j.percent ? `${j.percent} %` : '…'} · cuando termine aparece en la lista</p>
          <button onclick={() => separation.cancel(j.id)}>Cancelar</button>
        {/each}
      </div>
    {:else}
      <div class="empty">
        <p class="big">Elegí un tema de la lista para estudiarlo.</p>
      </div>
    {/if}
  </section>
</div>

<style>
  .studio { display: grid; grid-template-columns: 300px minmax(0, 1fr); gap: 16px; align-items: start; }
  .studio.solo { grid-template-columns: minmax(0, 1fr); }
  .lib { position: sticky; top: 12px; display: grid; gap: 8px; max-height: calc(100vh - 150px); overflow: auto; padding: 12px; border-radius: var(--radius); background: var(--glass); backdrop-filter: blur(16px) saturate(1.3); border: 1px solid var(--glass-line); box-shadow: 0 20px 50px -24px rgba(0,0,0,0.7); animation: rise 0.4s var(--ease) both; }
  .top { display: flex; align-items: center; gap: 8px; }
  .top h3 { margin: 0; font-size: 18px; flex: 1; }
  .lib input[type='search'] { background: rgba(255,255,255,0.06); border: 1px solid var(--glass-line); border-radius: 9px; padding: 7px 10px; }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; }
  li { display: grid; border-radius: 12px; transition: background 0.2s; }
  li:hover { background: rgba(255,255,255,0.05); }
  li.active { background: rgba(124, 199, 163, 0.12); box-shadow: inset 0 0 0 1px color-mix(in srgb, #7cc7a3 50%, transparent); }
  .row { display: grid; grid-template-columns: 40px 1fr auto; align-items: center; gap: 10px; text-align: left; padding: 6px 8px; background: transparent; border: 0; border-radius: 12px; width: 100%; }
  .txt { display: grid; min-width: 0; }
  .txt b, .txt span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .sz { font-size: 12.5px; }
  .del, .ro { justify-self: end; font-size: 12px; padding: 0 10px 6px; opacity: 0; transition: opacity 0.2s; background: transparent; border: 0; color: var(--muted); }
  li:hover .del, li:hover .ro, li:focus-within .del, li:focus-within .ro { opacity: 1; }
  .del:hover { color: var(--loop); }
  .confirm { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 4px 10px 8px; font-size: 13px; animation: rise 0.2s var(--ease) both; }
  .danger { background: var(--loop); border-color: var(--loop); color: #14040a; font-weight: 600; padding: 3px 12px; }
  .ghost { background: transparent; padding: 3px 10px; }
  .empty-li { padding: 10px; }
  .foot { margin: 0; font-size: 12.5px; }
  .warn { color: #f0a43c; margin: 0; font-size: 13px; }
  .daw { display: grid; gap: 16px; min-width: 0; }
  .head { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
  .now { display: flex; align-items: center; gap: 14px; animation: rise 0.5s var(--ease) both; }
  .nt { display: grid; }
  .now b { font-size: 28px; font-weight: 700; letter-spacing: -0.02em; line-height: 1.1; }
  .empty { padding: 8vh 0 0; max-width: 540px; display: grid; gap: 10px; animation: rise 0.6s var(--ease) both; }
  .empty p { margin: 0; }
  .big { font-size: 24px; line-height: 1.2; letter-spacing: -0.015em; font-weight: 600; }
  .err { color: var(--loop); }
  progress { width: 100%; height: 6px; appearance: none; border: 0; border-radius: 3px; overflow: hidden; background: var(--line); }
  progress::-webkit-progress-bar { background: var(--line); }
  progress::-webkit-progress-value { background: linear-gradient(90deg, #f0a43c, #ff4d8d, #4fa3d9, #f0a43c); background-size: 200% 100%; animation: shimmer 2.4s linear infinite; transition: width 0.3s var(--ease); }
  @media (max-width: 1000px) { .studio { grid-template-columns: 1fr; } .lib { position: static; max-height: 40vh; } }
  .proc { list-style: none; margin: 0 0 4px; padding: 0; display: grid; gap: 8px; }
  .proc li { display: grid; gap: 5px; padding: 10px 12px; border-radius: 12px; background: rgba(79, 163, 217, 0.1); border: 1px solid rgba(79, 163, 217, 0.35); }
  .proc li.err { background: rgba(240, 164, 60, 0.08); border-color: rgba(240, 164, 60, 0.4); }
  .pm { display: grid; gap: 1px; min-width: 0; }
  .pm b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .pbar { height: 6px; border-radius: 3px; background: rgba(255,255,255,0.1); overflow: hidden; }
  .pbar i { display: block; height: 100%; border-radius: 3px; background: linear-gradient(90deg, #4fa3d9, #7cc7a3); transition: width 0.6s var(--ease); }
  .pbar.big { height: 10px; width: min(420px, 80%); }
  .working { display: grid; gap: 6px; justify-items: center; }
  .ok { color: #7cc7a3; } .warn { color: #f0a43c; }
</style>
