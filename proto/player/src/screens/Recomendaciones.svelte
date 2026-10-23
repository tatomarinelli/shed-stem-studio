<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { recs, REACTION_LABELS, type Item, type DiscType, type Mode, type Reaction, type RecsResult } from '../lib/recs.svelte';
  import { seed } from '../lib/seed.svelte';
  import AlbumCard from '../components/recs/AlbumCard.svelte';
  import Cover from '../components/Cover.svelte';
  import ProfileForm from '../components/recs/ProfileForm.svelte';
  import PresetsEditor from '../components/recs/PresetsEditor.svelte';
  import PresetWizard from '../components/recs/PresetWizard.svelte';
  import TagInput from '../components/recs/TagInput.svelte';
  import Working from '../components/recs/Working.svelte';
  import MemoryPanel from '../components/recs/MemoryPanel.svelte';
  import { schedule as scheduleText } from '../lib/presetText';


  const labels = REACTION_LABELS;
  const cadences = [[6, 'cada 6 h'], [12, 'cada 12 h'], [24, 'una vez por día'], [48, 'cada 2 días'], [72, 'cada 3 días'], [168, 'una vez por semana']] as const;
  const modes: { id: Mode; label: string }[] = [
    { id: 'estudiar', label: 'Estudiar' }, { id: 'concentrarme', label: 'Concentrarme' }, { id: 'sorprenderme', label: 'Sorprenderme' },
  ];

  let showProfile = $state(false);
  let showPresets = $state(false);
  let showWizard = $state(false);
  const HOW: Record<string, string> = { horario: 'por horario', defecto: 'por defecto', elegido: 'elegido por vos' };
  let ask = $state('');
  let genres = $state<string[]>([]);
  let strict = $state(true);
  let discType = $state<DiscType | ''>('');
  const types: { id: DiscType | ''; label: string }[] = [{ id: '', label: 'Cualquiera' }, { id: 'album', label: 'Álbum' }, { id: 'ep', label: 'EP' }, { id: 'live', label: 'En vivo' }];
  const cancelling = $derived(recs.message === 'Cancelando…');
  let estTimer = 0;
  $effect(() => {
    const body = { prompt: ask.trim(), genres: [...genres], mode };
    window.clearTimeout(estTimer);
    estTimer = window.setTimeout(() => recs.loadEstimate(body), 400);
    return () => window.clearTimeout(estTimer);
  });
  const estText = $derived(recs.estimate ? `≈ ${recs.estimate.total} s` : '');
  const estTip = $derived(recs.estimate ? `Modelo ≈ ${Math.round(recs.estimate.parts.model)} s · MusicBrainz ≈ ${Math.round(recs.estimate.parts.musicbrainz)} s${recs.estimate.parts.context ? ` · contexto ≈ ${Math.round(recs.estimate.parts.context)} s` : ''} (${recs.estimate.basis})` : '');
  let mode = $state<Mode | null>(null);
  let undo = $state<{ item: Item; label: string } | null>(null);
  let undoTimer = 0;

  const daily = $derived(recs.open(recs.daily));
  const asked = $derived(recs.open(recs.request));
  const running = (k: 'daily' | 'request') => recs.state === 'running' && recs.kind === k;
  const welcome = $derived(!!recs.profile && !recs.profileFilled && !recs.profile.dismissed && !showProfile);
  const seedLabel = $derived(seed.value ? [seed.value.artist, seed.value.album ?? seed.value.title].filter(Boolean).join(' · ') : '');

  let askSection = $state<HTMLElement>();
  /** El disco desde el que se pidió "parecidos": se conserva mientras corre la búsqueda, aunque la semilla ya se haya consumido. */
  let runningSeed = $state<{ artist: string; album?: string; title?: string } | null>(null);

  onMount(async () => {
    recs.loadGenres();
    await recs.load();
    // Llegó desde Música con "Recomendar parecidos": se muestra el pedido y arranca solo.
    if (seed.value) {
      await tick();
      askSection?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      await startSeed();
    }
  });

  async function startSeed() {
    const s = seed.value;
    if (!s || recs.state === 'running' || recs.state === 'no_engine') return;
    runningSeed = s;
    if (!(await recs.generate('request', { prompt: ask.trim(), mode, seed: s }))) runningSeed = null;
  }
  // La semilla se consume recién cuando la búsqueda termina bien; si falla, queda para reintentar.
  let seenRunning = false;
  $effect(() => {
    const st = recs.state;
    if (!runningSeed) { seenRunning = false; return; }
    if (st === 'running') seenRunning = true;
    else if (seenRunning && st === 'done') { seed.clear(); runningSeed = null; seenRunning = false; }
    else if (seenRunning && st === 'error') { runningSeed = null; seenRunning = false; }
  });

  async function react(item: Item, r: Reaction, known: boolean) {
    if (await recs.react(item.mbid, r, known)) {
      undo = { item, label: labels[r] };
      window.clearTimeout(undoTimer);
      undoTimer = window.setTimeout(() => (undo = null), 8000);
    }
  }
  async function revert(mbid: string) {
    await recs.react(mbid, null);
    if (undo?.item.mbid === mbid) undo = null;
  }
  async function request(e: SubmitEvent) {
    e.preventDefault();
    runningSeed = seed.value;
    if (!(await recs.generate('request', { prompt: ask.trim(), mode, seed: seed.value, ...(genres.length ? { genres, strict } : {}), ...(discType ? { type: discType } : {}) })) ) runningSeed = null;
  }
  const when = (t: number) => new Date(t * 1000).toLocaleString('es-AR', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  const day = (iso: string) => new Date(iso).toLocaleDateString('es-AR', { day: 'numeric', month: 'short' });
  const reqText = (r: RecsResult) => [r.request?.genres?.length && `género: ${r.request.genres.join(', ')}${r.request.genresDetected ? ' (detectado)' : ''}${r.request.strict ? '' : ' (flexible)'}`, r.request?.mode, r.request?.prompt && `“${r.request.prompt}”`, r.request?.seed && `parecido a ${r.request.seed.artist}`, r.request?.zone && `zona del mapa: ${r.request.zone.names.join(' + ')} (${r.request.zone.artists} artistas)`].filter(Boolean).join(' · ');
</script>

<div class="head">
  <h2>Recomendaciones</h2>
  <button onclick={() => { showProfile = !showProfile; showPresets = false; }} aria-expanded={showProfile} disabled={!recs.profile}>Mi perfil</button>
</div>

{#if recs.profile?.seeded && !recs.profile.seedSeen && !showProfile}
  <div class="note seedbox">
    <span>Tu perfil salió de tu historial. Corregí lo que no cuadre.</span>
    <div class="row">
      <button class="primary" onclick={() => (showProfile = true)}>Revisar</button>
      <button class="ghost" onclick={() => recs.saveProfile({ seedSeen: true })}>Está bien</button>
    </div>
  </div>
{/if}

{#if welcome}
  <div class="note welcome">
    <div>
      <b>Contame cómo estudiás.</b>
      <span class="muted">Instrumento, qué querés mejorar, qué te gusta. Lleva un minuto.</span>
    </div>
    <div class="row">
      <button class="primary" onclick={() => (showProfile = true)}>Completar</button>
      <button class="ghost" onclick={() => recs.saveProfile({ dismissed: true })}>Ahora no</button>
    </div>
  </div>
{/if}

{#if recs.presets && recs.activePreset}
  <div class="preset">
    <label class="plabel">Perfil
      <select aria-label="Perfil de recomendación" bind:value={recs.presetChoice}>
        <option value="">Automático · ahora {recs.activePreset.name} ({HOW[recs.activePreset.how]})</option>
        {#each recs.presets.presets as p (p.id)}<option value={p.id}>{p.name} · {scheduleText(p)}</option>{/each}
      </select>
    </label>
    <span class="grow"></span>
    <button class="ghost" onclick={() => { showPresets = !showPresets; showWizard = false; showProfile = false; }} aria-expanded={showPresets}>Editar perfiles</button>
    <button class="ghost" onclick={() => { showWizard = !showWizard; showPresets = false; showProfile = false; }} aria-expanded={showWizard}>+ Nuevo</button>
  </div>
{/if}

{#if showPresets && recs.presets}
  <PresetsEditor onclose={() => (showPresets = false)} oncreate={() => { showPresets = false; showWizard = true; }} />
{/if}
{#if showWizard && recs.presets}
  <PresetWizard onclose={() => (showWizard = false)} />
{/if}

{#if recs.state === 'no_engine'}
  <div class="note warn-box" role="alert">{recs.message}</div>
{/if}



{#if showProfile && recs.profile}
  <ProfileForm onclose={() => (showProfile = false)} />
{/if}

<!-- Disco de hoy -->
<section class="sec">
  <div class="sec-head">
    <h4>Disco de hoy</h4>
    {#if recs.daily}<span class="muted small meta">{recs.daily.preset ? `${recs.daily.preset.name} · ` : ''}{when(recs.daily.createdAt)}</span>{/if}
    <span class="grow"></span>
    <button class="ghost" onclick={() => recs.generate('daily')} disabled={recs.state === 'running' || recs.state === 'no_engine'}>{recs.daily ? 'Recomendar otro' : 'Generar'}</button>
  </div>
  {#if recs.schedule}
    <div class="sched muted small">
      <label>Nuevo disco
        <select aria-label="Cada cuánto" value={recs.schedule.cadenceHours} onchange={e => recs.setSchedule({ cadenceHours: +e.currentTarget.value })}>
          {#each cadences as [h, l] (h)}<option value={h}>{l}</option>{/each}
        </select>
      </label>
      <label class="check"><input type="checkbox" checked={recs.schedule.auto} onchange={e => recs.setSchedule({ auto: e.currentTarget.checked })} /> automático</label>
    </div>
  {/if}

  {#if running('daily')}
    <Working step={recs.step} done={recs.done} total={recs.total} found={recs.found} target={recs.target} {cancelling} oncancel={() => recs.cancel()} />
  {:else if recs.state === 'error' && recs.kind === 'daily'}
    <p class="warn" role="alert">{recs.message}</p>
  {:else if recs.message && recs.kind === 'daily' && (recs.state === 'done' || recs.state === 'idle')}
    <p class="muted small" role="status">{recs.message}</p>
  {/if}

  {#if daily.length}
    <AlbumCard item={daily[0]} big onreact={react} />
    {#if daily.length > 1}
      <div class="alts">
        <p class="muted small">Otras opciones</p>
        {#each daily.slice(1) as it (it.mbid)}<AlbumCard item={it} onreact={react} />{/each}
      </div>
    {/if}
  {:else if recs.daily && !running('daily')}
    <p class="muted">{recs.daily.pick ? 'Ya clasificaste todos. Tocá Recomendar otro.' : 'Ningún disco pasó la verificación. Probá con Recomendar otro.'}</p>
  {:else if !recs.daily && !running('daily') && recs.state !== 'no_engine'}
    <p class="muted">Todavía no hay disco de hoy.{recs.schedule?.auto ? ' Se genera solo cuando el modelo local está prendido.' : ''}</p>
  {/if}
</section>

{#if undo}
  <div class="undo" role="status">
    <span><b>{undo.item.album}</b> pasó al historial ({undo.label}).</span>
    <button class="ghost" onclick={() => revert(undo!.item.mbid)}>Deshacer</button>
  </div>
{/if}

<!-- Pedido a demanda -->
<section class="sec" class:live={running('request')} bind:this={askSection}>
  <div class="sec-head"><h4>Pedí algo</h4></div>
  <form class="ask" onsubmit={request}>
    <input bind:value={ask} placeholder="algo para tocar arriba, un disco de bossa…" maxlength="200" aria-label="Qué buscás" />
    <div class="seg" role="group" aria-label="Modo">
      {#each modes as m (m.id)}
        <button type="button" class:on={mode === m.id} aria-pressed={mode === m.id} onclick={() => (mode = mode === m.id ? null : m.id)}>{m.label}</button>
      {/each}
    </div>
    <button class="primary" type="submit" disabled={recs.state === 'running' || recs.state === 'no_engine' || (!ask.trim() && !mode && !seed.value && !genres.length)}>{running('request') ? 'Buscando…' : 'Buscar'}</button>
    {#if estText && !running('request')}<span class="est muted small" title={estTip}>{estText}</span>{/if}
  </form>
  <details class="tune">
    <summary>Afinar{genres.length || discType ? ` · ${[...genres, discType && types.find(t => t.id === discType)?.label].filter(Boolean).join(', ')}` : ''}</summary>
    <div class="tune-body">
      <TagInput label="Género" bind:value={genres} suggestions={recs.genreList} placeholder="dub, bossa nova, post-rock…" max={3} />
      {#if genres.length}
        <label class="check"><input type="checkbox" bind:checked={strict} /> Solo discos de ese género (si no alcanzan, muestro menos)</label>
      {/if}
      <div class="seg" role="group" aria-label="Tipo de disco">
        {#each types as t (t.id)}
          <button type="button" class:on={discType === t.id} aria-pressed={discType === t.id} onclick={() => (discType = t.id)}>{t.label}</button>
        {/each}
      </div>
    </div>
  </details>
  {#if seed.value && !running('request')}
    <div class="seedcard">
      <Cover title={seed.value.album ?? seed.value.title ?? seed.value.artist} artist={seed.value.artist} size={56} radius={10} />
      <div class="st"><b>Parecido a {seedLabel}</b><span class="muted">Se usa como punto de partida. Tocá Buscar para pedirlo.</span></div>
      <button class="ghost" onclick={() => seed.clear()} aria-label="Quitar este disco del pedido">Quitar</button>
    </div>
  {/if}

  {#if running('request')}
    <div class="seedcard run" role="status" aria-live="polite">
      {#if runningSeed}<Cover title={runningSeed.album ?? runningSeed.title ?? runningSeed.artist} artist={runningSeed.artist} size={56} radius={10} />{/if}
      <Working title={runningSeed ? `Buscando discos parecidos a ${[runningSeed.artist, runningSeed.album ?? runningSeed.title].filter(Boolean).join(' · ')}` : 'Buscando lo que pediste'}
        step={recs.step} done={recs.done} total={recs.total} found={recs.found} target={recs.target} {cancelling} oncancel={() => recs.cancel()} />
    </div>
  {:else if recs.state === 'error' && recs.kind === 'request'}
    <p class="warn" role="alert">{recs.message}</p>
  {:else if recs.message && recs.kind === 'request' && (recs.state === 'done' || recs.state === 'idle')}
    <p class="muted small" role="status">{recs.message}</p>
  {/if}

  {#if recs.request && !running('request')}
    <p class="muted small">{reqText(recs.request)}{recs.request.preset ? ` · ${recs.request.preset.name}` : ''} · {when(recs.request.createdAt)}</p>
    {#each asked as it, i (it.mbid)}<AlbumCard item={it} big={i === 0} onreact={react} />{:else}
      <p class="muted">{recs.request.pick ? 'Ya clasificaste todos.' : 'Ningún disco pasó la verificación.'}</p>
    {/each}
  {/if}
</section>

<!-- Historial -->
{#if recs.history.length}
  <details class="sec fold">
    <summary>Historial ({recs.history.length})</summary>
    <ul class="hist">
      {#each recs.history as h (h.mbid)}
        <li>
          <span class="t"><b>{h.album}</b> <span class="muted">{h.artist}</span></span>
          <span class="tag {h.action}">{labels[h.action]}</span>
          <span class="muted small">{h.preset ?? ''}</span>
          <span class="muted small">{day(h.at)}</span>
          <button class="ghost" onclick={() => revert(h.mbid)}>Deshacer</button>
        </li>
      {/each}
    </ul>
  </details>
{/if}

<MemoryPanel />

{#if recs.daily || recs.request}
  {@const r = (recs.request && (!recs.daily || recs.request.createdAt > recs.daily.createdAt) ? recs.request : recs.daily)!}
  <details class="sec fold">
    <summary>Qué vio el modelo</summary>
    <p class="muted small">{r.model}: {r.stats.verified} de {r.stats.proposed} propuestos existen en MusicBrainz, {r.stats.relevant} cerca de tus gustos · {r.stats.rounds} {r.stats.rounds === 1 ? 'ronda' : 'rondas'} · {r.stats.seconds} s{r.context ? ` · ${r.context}` : ''}</p>
    <ul class="disc">
      {#each [r.pick, ...r.alternatives].filter(Boolean) as v (v!.mbid)}<li><b>{v!.album}</b>: {v!.reason}</li>{/each}
    </ul>
    {#if r.stats.context}<p class="muted small">Contexto: {r.stats.context.wikipedia} de Wikipedia ({r.stats.context.summarized} resumidos y validados), {r.stats.context.fallback} solo con datos de MusicBrainz.</p>{/if}
    {#if r.discarded.length}
      <ul class="disc">
        {#each r.discarded as d (d.artist + d.album)}<li><b>{d.album}</b> de {d.artist}: <span class="warn">{d.why}</span></li>{/each}
      </ul>
    {/if}
    <pre>{r.prompt}</pre>
  </details>
{/if}

<style>
  h2 { margin: 0; font-size: 28px; letter-spacing: -0.02em; }
  h4 { margin: 0; font-size: 13px; text-transform: uppercase; letter-spacing: 0.09em; color: var(--muted); font-weight: 600; }
  .preset { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; font-size: 14.5px; }
  .preset select { padding: 4px 9px; font-size: 13.5px; }
  .head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
  .primary { background: var(--text); color: var(--bg); border-color: var(--text); font-weight: 600; }
  .ghost { background: transparent; }
  .note { background: var(--glass); backdrop-filter: blur(16px) saturate(1.3); border: 1px solid var(--glass-line); border-radius: var(--radius); padding: 12px 16px; }
  .warn-box { border-color: rgba(240, 164, 60, 0.4); }
  .welcome { display: flex; justify-content: space-between; align-items: center; gap: 14px; flex-wrap: wrap; border-color: rgba(240, 164, 60, 0.35); background: linear-gradient(100deg, rgba(240, 164, 60, 0.12), var(--glass) 60%); }
  .welcome div:first-child { display: grid; gap: 2px; }
  .row { display: flex; gap: 8px; }
  .seedbox { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
  .sec { display: grid; gap: 10px; }
  .sec-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; min-height: 34px; }
  .grow { flex: 1; }
  .meta { white-space: nowrap; }
  .sched { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; margin-top: -4px; }
  .sched label { display: flex; align-items: center; gap: 8px; }
  .sched select { padding: 3px 8px; font-size: 13px; }
  .plabel { display: flex; align-items: center; gap: 8px; color: var(--muted); min-width: 0; flex: 1 1 260px; max-width: 100%; }
  .plabel select { flex: 1; min-width: 0; max-width: 460px; text-overflow: ellipsis; }
  .small { font-size: 13px; margin: 0; }
  .check { display: flex; align-items: center; gap: 6px; font-size: 13.5px; color: var(--muted); cursor: pointer; }
  .check input { accent-color: var(--text); }
  .alts { display: grid; gap: 0; padding-left: 8px; }
  .alts > p { margin: 4px 0 2px 12px; }
  .est { white-space: nowrap; cursor: help; }
  .tune summary { cursor: pointer; color: var(--muted); font-size: 13.5px; width: fit-content; }
  .tune-body { display: grid; gap: 12px; margin-top: 10px; max-width: 560px; }
  .warn { color: #f0a43c; margin: 0; }
  .undo { position: sticky; bottom: 110px; z-index: 5; justify-self: start; display: flex; align-items: center; gap: 12px; padding: 8px 10px 8px 16px; border-radius: 12px; background: #1e3035; border: 1px solid var(--glass-line); box-shadow: 0 16px 40px -16px rgba(0, 0, 0, 0.8); animation: rise 0.3s var(--ease) both; }
  .ask { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .ask input { flex: 1 1 320px; background: rgba(0, 0, 0, 0.2); border: 1px solid var(--glass-line); border-radius: 9px; padding: 7px 12px; font-size: 15px; }
  .ask input:focus { border-color: var(--muted); outline: none; }
  .seg { display: flex; }
  .seg button { border-radius: 0; margin-left: -1px; }
  .seg button:first-child { border-radius: 9px 0 0 9px; margin-left: 0; }
  .seg button:last-child { border-radius: 0 9px 9px 0; }
  .seg .on { background: var(--loop); border-color: var(--loop); color: #14040a; font-weight: 600; }
  .seed { margin: 0; }
  .chip { display: inline-flex; align-items: center; gap: 4px; font-size: 13.5px; border: 1px solid color-mix(in srgb, var(--loop) 50%, transparent); background: color-mix(in srgb, var(--loop) 12%, transparent); border-radius: 999px; padding: 2px 4px 2px 12px; }
  .x { border: 0; background: transparent; padding: 0 6px; font-size: 16px; line-height: 1; }
  .fold { background: var(--glass); border: 1px solid var(--glass-line); border-radius: var(--radius); padding: 10px 16px; }
  summary { cursor: pointer; font-weight: 600; }
  .hist { list-style: none; margin: 6px 0 0; padding: 0; display: grid; gap: 2px; }
  .hist li { display: grid; grid-template-columns: 1fr auto auto auto auto; gap: 12px; align-items: center; padding: 4px 0; }
  .hist .t { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  @media (max-width: 600px) { .hist li { grid-template-columns: minmax(0, 1fr) auto auto; } .hist li > :nth-child(3), .hist li > :nth-child(4) { display: none; } }
  .hist button { padding: 3px 10px; font-size: 13px; }
  .tag { font-size: 12px; border-radius: 999px; padding: 1px 9px; border: 1px solid var(--glass-line); }
  .tag.loved { color: #7cc7a3; border-color: color-mix(in srgb, #7cc7a3 45%, transparent); font-weight: 600; }
  .tag.liked, .tag.heard { color: #7cc7a3; border-color: color-mix(in srgb, #7cc7a3 45%, transparent); }
  .tag.disliked { color: #f0a43c; border-color: color-mix(in srgb, #f0a43c 45%, transparent); }
  .tag.no { color: var(--muted); }
  .disc { list-style: none; padding: 0; margin: 8px 0; display: grid; gap: 4px; font-size: 14px; }
  pre { white-space: pre-wrap; background: rgba(0, 0, 0, 0.25); border-radius: 10px; padding: 10px 12px; font-size: 12.5px; line-height: 1.5; max-height: 260px; overflow: auto; }
  .sec.live { box-shadow: 0 0 0 1px rgba(124, 199, 163, 0.55), 0 0 28px -6px rgba(124, 199, 163, 0.45); animation: glow 2.2s ease-in-out infinite; }
  @keyframes glow { 50% { box-shadow: 0 0 0 1px rgba(124, 199, 163, 0.25), 0 0 14px -6px rgba(124, 199, 163, 0.2); } }
  .seedcard { display: flex; align-items: center; gap: 14px; padding: 12px 14px; border-radius: 14px; background: rgba(255, 255, 255, 0.06); border: 1px solid var(--glass-line); }
  .seedcard.run { border-color: rgba(124, 199, 163, 0.55); }
  .seedcard .st { display: grid; gap: 4px; flex: 1; min-width: 0; }
  .seedcard .st b { overflow-wrap: anywhere; }
  @media (prefers-reduced-motion: reduce) { .sec.live { animation: none; } }
</style>
