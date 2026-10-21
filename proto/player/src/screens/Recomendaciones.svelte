<script lang="ts">
  import { onMount } from 'svelte';
  import { recs, type Item, type Mode, type Reaction, type RecsResult } from '../lib/recs.svelte';
  import { seed } from '../lib/seed.svelte';
  import AlbumCard from '../components/recs/AlbumCard.svelte';
  import ProfileForm from '../components/recs/ProfileForm.svelte';
  import PresetsEditor from '../components/recs/PresetsEditor.svelte';
  import PresetWizard from '../components/recs/PresetWizard.svelte';
  import { schedule as scheduleText } from '../lib/presetText';

  onMount(() => { recs.load(); });

  const steps: Record<string, string> = {
    profile: 'Leyendo tus gustos…',
    model: 'Pensando discos con el modelo local…',
    verify: 'Verificando en MusicBrainz…',
    wait_mb: 'Esperando turno en MusicBrainz…',
    context: 'Buscando el contexto de cada disco…',
  };
  const labels: Record<Reaction, string> = { heard: 'Ya lo escuché', loved: 'Me encantó', no: 'No me va' };
  const cadences = [[6, 'cada 6 h'], [12, 'cada 12 h'], [24, 'una vez por día'], [48, 'cada 2 días'], [72, 'cada 3 días'], [168, 'una vez por semana']] as const;
  const modes: { id: Mode; label: string }[] = [
    { id: 'estudiar', label: 'Estudiar' }, { id: 'concentrarme', label: 'Concentrarme' }, { id: 'sorprenderme', label: 'Sorprenderme' },
  ];

  let showProfile = $state(false);
  let showPresets = $state(false);
  let showWizard = $state(false);
  const HOW: Record<string, string> = { horario: 'por horario', defecto: 'por defecto', elegido: 'elegido por vos' };
  const presetName = $derived(recs.presets?.presets.find(p => p.id === recs.presetChoice)?.name);
  let ask = $state('');
  let mode = $state<Mode | null>(null);
  let undo = $state<{ item: Item; label: string } | null>(null);
  let undoTimer = 0;

  const daily = $derived(recs.open(recs.daily));
  const asked = $derived(recs.open(recs.request));
  const running = (k: 'daily' | 'request') => recs.state === 'running' && recs.kind === k;
  const welcome = $derived(!!recs.profile && !recs.profileFilled && !recs.profile.dismissed && !showProfile);
  const seedLabel = $derived(seed.value ? [seed.value.artist, seed.value.album ?? seed.value.title].filter(Boolean).join(' · ') : '');

  async function react(item: Item, r: Reaction) {
    if (await recs.react(item.mbid, r)) {
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
    const ok = await recs.generate('request', { prompt: ask.trim(), mode, seed: seed.value });
    if (ok) seed.clear();
  }
  const when = (t: number) => new Date(t * 1000).toLocaleString('es-AR', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  const day = (iso: string) => new Date(iso).toLocaleDateString('es-AR', { day: 'numeric', month: 'short' });
  const reqText = (r: RecsResult) => [r.request?.mode, r.request?.prompt && `“${r.request.prompt}”`, r.request?.seed && `parecido a ${r.request.seed.artist}`].filter(Boolean).join(' · ');
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
    <span>Perfil: <b>{presetName ?? recs.activePreset.name}</b> <span class="muted">· {presetName ? HOW.elegido : HOW[recs.activePreset.how]}</span></span>
    <select aria-label="Usar otro perfil" bind:value={recs.presetChoice}>
      <option value="">automático ({recs.activePreset.name})</option>
      {#each recs.presets.presets as p (p.id)}<option value={p.id}>{p.name} · {scheduleText(p)}</option>{/each}
    </select>
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
    {#if recs.schedule}
      <select aria-label="Cada cuánto" value={recs.schedule.cadenceHours} onchange={e => recs.setSchedule({ cadenceHours: +e.currentTarget.value })}>
        {#each cadences as [h, l] (h)}<option value={h}>{l}</option>{/each}
      </select>
      <label class="check"><input type="checkbox" checked={recs.schedule.auto} onchange={e => recs.setSchedule({ auto: e.currentTarget.checked })} /> automático</label>
    {/if}
    <span class="grow"></span>
    {#if recs.daily}<span class="muted small">{recs.daily.preset ? `${recs.daily.preset.name} · ` : ''}{when(recs.daily.createdAt)}</span>{/if}
    <button class="ghost" onclick={() => recs.generate('daily')} disabled={recs.state === 'running' || recs.state === 'no_engine'}>{recs.daily ? 'Otro' : 'Generar'}</button>
  </div>

  {#if running('daily')}
    <div class="working" role="status"><p>{steps[recs.step] ?? 'Trabajando…'}</p><div class="bar"><i></i></div></div>
  {:else if recs.state === 'error' && recs.kind === 'daily'}
    <p class="warn" role="alert">{recs.message}</p>
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
    <p class="muted">{recs.daily.pick ? 'Ya clasificaste todos. Pedí otro.' : 'Ningún disco pasó la verificación. Probá con Otro.'}</p>
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
<section class="sec">
  <div class="sec-head"><h4>Pedí algo</h4></div>
  <form class="ask" onsubmit={request}>
    <input bind:value={ask} placeholder="algo para tocar arriba, un disco de bossa…" maxlength="200" aria-label="Qué buscás" />
    <div class="seg" role="group" aria-label="Modo">
      {#each modes as m (m.id)}
        <button type="button" class:on={mode === m.id} aria-pressed={mode === m.id} onclick={() => (mode = mode === m.id ? null : m.id)}>{m.label}</button>
      {/each}
    </div>
    <button class="primary" type="submit" disabled={recs.state === 'running' || recs.state === 'no_engine' || (!ask.trim() && !mode && !seed.value)}>Buscar</button>
  </form>
  {#if seed.value}
    <p class="seed"><span class="chip">Parecido a {seedLabel} <button class="x" aria-label="Quitar semilla" onclick={() => seed.clear()}>×</button></span></p>
  {/if}

  {#if running('request')}
    <div class="working" role="status"><p>{steps[recs.step] ?? 'Trabajando…'}</p><div class="bar"><i></i></div></div>
  {:else if recs.state === 'error' && recs.kind === 'request'}
    <p class="warn" role="alert">{recs.message}</p>
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
  .sec-head select { padding: 4px 9px; font-size: 13.5px; }
  .grow { flex: 1; }
  .small { font-size: 13px; margin: 0; }
  .check { display: flex; align-items: center; gap: 6px; font-size: 13.5px; color: var(--muted); cursor: pointer; }
  .check input { accent-color: var(--text); }
  .alts { display: grid; gap: 0; padding-left: 8px; }
  .alts > p { margin: 4px 0 2px 12px; }
  .working { display: grid; gap: 8px; max-width: 520px; padding: 14px 0; }
  .working p { margin: 0; font-size: 18px; font-weight: 600; }
  .bar { height: 5px; border-radius: 3px; background: var(--line); overflow: hidden; }
  .bar i { display: block; height: 100%; width: 40%; border-radius: 3px; background: linear-gradient(90deg, #f0a43c, #ff4d8d, #4fa3d9); animation: slide 1.4s var(--ease) infinite; }
  @keyframes slide { from { transform: translateX(-100%); } to { transform: translateX(260%); } }
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
  .hist button { padding: 3px 10px; font-size: 13px; }
  .tag { font-size: 12px; border-radius: 999px; padding: 1px 9px; border: 1px solid var(--glass-line); }
  .tag.loved { color: var(--loop); border-color: color-mix(in srgb, var(--loop) 45%, transparent); }
  .tag.heard { color: #7cc7a3; border-color: color-mix(in srgb, #7cc7a3 45%, transparent); }
  .tag.no { color: var(--muted); }
  .disc { list-style: none; padding: 0; margin: 8px 0; display: grid; gap: 4px; font-size: 14px; }
  pre { white-space: pre-wrap; background: rgba(0, 0, 0, 0.25); border-radius: 10px; padding: 10px 12px; font-size: 12.5px; line-height: 1.5; max-height: 260px; overflow: auto; }
</style>
