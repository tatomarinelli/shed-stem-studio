<script lang="ts">
  // Asistente para CREAR un perfil de sugerencia: un paso por pantalla. Editar uno existente usa el formulario normal.
  import { onMount } from 'svelte';
  import { recs, type Intent, type Preset, type Range } from '../../lib/recs.svelte';
  import { suggest } from '../../lib/suggest.svelte';
  import { overlap, range as rangeText } from '../../lib/presetText';
  import TagInput from './TagInput.svelte';

  let { onclose }: { onclose: () => void } = $props();
  onMount(() => suggest.load());

  const STEPS = ['Para qué', 'Cuándo', 'Qué escuchar', 'Qué evitar', 'Novedad', 'Voz', 'Nombre', 'Resumen'];
  let step = $state(0);
  let intent = $state<Intent | null>(null);
  let manual = $state(false);
  let ranges = $state<Range[]>([{ days: [0, 1, 2, 3, 4], start: '09:00', end: '18:00' }]);
  let favor = $state<string[]>([]);
  let avoid = $state<string[]>([]);
  let discovery = $state<Preset['discovery']>(null);
  let voice = $state<'' | 'instrumental' | 'voz'>('');
  let name = $state('');
  let nameTouched = $state(false);
  let prompt = $state('');
  let wins = $state<Record<string, 'new' | 'other'>>({});
  let error = $state('');
  let saving = $state(false);

  const INTENTS: { id: Intent; label: string; hint: string }[] = [
    { id: 'estudiar', label: 'Estudiar', hint: 'discos para aprender y sacar de oído' },
    { id: 'concentrarme', label: 'Concentrarme', hint: 'de fondo, sin distraer' },
    { id: 'sorprenderme', label: 'Sorprenderme', hint: 'fuera de lo de siempre' },
    { id: 'libre', label: 'Libre', hint: 'para disfrutar' },
  ];
  const DAYS = ['L', 'M', 'M', 'J', 'V', 'S', 'D'];
  const DAY_NAMES = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];
  const NAMES: Record<Intent, string> = { estudiar: 'Estudio', concentrarme: 'Concentración', sorprenderme: 'Sorpresa', libre: 'Libre' };

  // Nombre sugerido a partir de las respuestas (editable).
  const suggested = $derived.by(() => {
    if (!intent) return '';
    let n = NAMES[intent];
    if (favor.length) n += ` de ${favor[0]}`;
    else if (!manual && ranges.length === 1) {
      const r = ranges[0], h = +r.start.slice(0, 2);
      n += r.days.join() === '5,6' ? ' de finde' : h >= 19 || h < 5 ? ' de noche' : h < 12 ? ' de mañana' : '';
    }
    return n.slice(0, 30);
  });
  $effect(() => { if (!nameTouched) name = suggested; });

  const draft = $derived<Preset>({
    id: 'nuevo-' + Date.now().toString(36), name: name.trim(), intent: intent ?? 'libre', schedule: manual ? [] : ranges, priority: 0,
    discovery, favor, avoid, examples: [], instrumental: voice === 'instrumental', prompt: voice === 'voz' ? [prompt, 'con voz'].filter(Boolean).join('; ') : prompt,
    note: '', over: [],
  });
  const clashes = $derived((recs.presets?.presets ?? []).map(p => ({ p, when: overlap(draft, p) })).filter(x => x.when));

  const required = $derived(step === 0 ? !!intent : step === 6 ? !!name.trim() : true);
  const toggleDay = (r: Range, d: number) => (r.days = r.days.includes(d) ? r.days.filter(x => x !== d) : [...r.days, d].sort());

  async function save() {
    if (!recs.presets) return;
    saving = true; error = '';
    const p = { ...draft, schedule: draft.schedule.filter(r => r.days.length) };
    const others = recs.presets.presets.map(o => ({ ...o, over: [...o.over] }));
    for (const c of clashes) {
      if (wins[c.p.id] === 'new') p.over.push(c.p.id);
      else if (wins[c.p.id] === 'other') others.find(o => o.id === c.p.id)!.over.push(p.id);
    }
    const err = await recs.savePresets({ ...recs.presets, presets: [...others, p] });
    saving = false;
    if (err) error = err; else onclose();
  }
</script>

<div class="panel">
  <div class="top">
    <h3>Nuevo perfil</h3>
    <span class="muted small">{step + 1} de {STEPS.length} · {STEPS[step]}</span>
  </div>
  <div class="progress" role="progressbar" aria-valuemin="1" aria-valuemax={STEPS.length} aria-valuenow={step + 1}><i style="width:{((step + 1) / STEPS.length) * 100}%"></i></div>

  <div class="step">
    {#if step === 0}
      <h4>¿Para qué es?</h4>
      <div class="cards">
        {#each INTENTS as it (it.id)}
          <button type="button" class="big" class:on={intent === it.id} aria-pressed={intent === it.id} onclick={() => (intent = it.id)}>
            <b>{it.label}</b><span>{it.hint}</span>
          </button>
        {/each}
      </div>
    {:else if step === 1}
      <h4>¿Cuándo?</h4>
      <label class="check"><input type="checkbox" bind:checked={manual} /> Solo cuando yo lo elija</label>
      {#if !manual}
        {#each ranges as r, i (i)}
          <div class="range">
            <div class="days">
              {#each DAYS as d, j (j)}
                <button type="button" class:on={r.days.includes(j)} aria-pressed={r.days.includes(j)} aria-label={DAY_NAMES[j]} onclick={() => toggleDay(r, j)}>{d}</button>
              {/each}
            </div>
            <input type="time" bind:value={r.start} aria-label="Desde" /> <span class="muted">a</span> <input type="time" bind:value={r.end} aria-label="Hasta" />
            {#if ranges.length > 1}<button type="button" class="ghost x" aria-label="Quitar horario" onclick={() => ranges.splice(i, 1)}>×</button>{/if}
          </div>
        {/each}
        <div><button type="button" class="ghost" onclick={() => ranges.push({ days: [5, 6], start: '10:00', end: '13:00' })}>+ Otro horario</button></div>
      {/if}
    {:else if step === 2}
      <h4>¿Qué querés escuchar?</h4>
      <TagInput label="Estilos o artistas" bind:value={favor} suggestions={[...suggest.styles, ...suggest.artistList.slice(0, 20)]} placeholder="escribí o tocá abajo" max={12} show={18} />
    {:else if step === 3}
      <h4>¿Qué querés evitar?</h4>
      <TagInput label="Estilos o artistas" bind:value={avoid} suggestions={[...suggest.styles, ...suggest.artistList.slice(0, 20)]} placeholder="escribí o tocá abajo" max={12} show={18} />
    {:else if step === 4}
      <h4>¿Cuánta novedad?</h4>
      <div class="seg">
        {#each [[null, 'Como en Mi perfil'], ['nada', 'Poca'], ['algo', 'Algo'], ['mucho', 'Mucha']] as [v, l] (l)}
          <button type="button" class:on={discovery === v} aria-pressed={discovery === v} onclick={() => (discovery = v as Preset['discovery'])}>{l}</button>
        {/each}
      </div>
    {:else if step === 5}
      <h4>¿Con voz o instrumental?</h4>
      <div class="seg">
        {#each [['', 'Me da igual'], ['instrumental', 'Instrumental'], ['voz', 'Con voz']] as [v, l] (v)}
          <button type="button" class:on={voice === v} aria-pressed={voice === v} onclick={() => (voice = v as typeof voice)}>{l}</button>
        {/each}
      </div>
    {:else if step === 6}
      <h4>Nombre</h4>
      <label>Nombre<input bind:value={name} oninput={() => (nameTouched = true)} maxlength="30" /></label>
      <label>Consigna<input bind:value={prompt} maxlength="160" placeholder="opcional" /></label>
    {:else}
      <h4>Resumen</h4>
      <dl>
        <dt>Nombre</dt><dd>{draft.name}</dd>
        <dt>Para</dt><dd>{INTENTS.find(i => i.id === draft.intent)?.label}</dd>
        <dt>Cuándo</dt><dd>{draft.schedule.length ? draft.schedule.map(rangeText).join(' · ') : 'solo cuando lo elijas'}</dd>
        {#if favor.length}<dt>Escuchar</dt><dd>{favor.join(', ')}</dd>{/if}
        {#if avoid.length}<dt>Evitar</dt><dd>{avoid.join(', ')}</dd>{/if}
        {#if discovery}<dt>Novedad</dt><dd>{discovery === 'nada' ? 'poca' : discovery === 'mucho' ? 'mucha' : 'algo'}</dd>{/if}
        {#if voice}<dt>Voz</dt><dd>{voice === 'voz' ? 'con voz' : 'instrumental'}</dd>{/if}
        {#if prompt}<dt>Consigna</dt><dd>{prompt}</dd>{/if}
      </dl>
      {#each clashes as c (c.p.id)}
        <div class="clash" role="alert">
          <p>Se pisa con <b>{c.p.name}</b> {c.when}. ¿Cuál manda?</p>
          <div class="seg">
            <button type="button" class:on={wins[c.p.id] === 'new'} onclick={() => (wins[c.p.id] = 'new')}>{draft.name || 'Este'}</button>
            <button type="button" class:on={wins[c.p.id] === 'other'} onclick={() => (wins[c.p.id] = 'other')}>{c.p.name}</button>
            <button type="button" class:on={!wins[c.p.id]} onclick={() => delete wins[c.p.id]}>El más corto</button>
          </div>
        </div>
      {/each}
    {/if}
  </div>

  {#if error}<p class="warn" role="alert">{error}</p>{/if}
  <div class="row">
    <button type="button" onclick={() => (step === 0 ? onclose() : step--)}>{step === 0 ? 'Cancelar' : 'Atrás'}</button>
    <span class="grow"></span>
    {#if step > 0 && step < 6}<button type="button" class="ghost" onclick={() => step++}>Saltar</button>{/if}
    {#if step < STEPS.length - 1}
      <button type="button" class="primary" disabled={!required} onclick={() => step++}>Siguiente</button>
    {:else}
      <button type="button" class="primary" disabled={saving || !draft.name} onclick={save}>{saving ? 'Guardando…' : 'Crear perfil'}</button>
    {/if}
  </div>
</div>

<style>
  .panel { display: grid; gap: 14px; padding: 18px 20px; border-radius: var(--radius); background: var(--glass); backdrop-filter: blur(16px) saturate(1.3); border: 1px solid var(--glass-line); max-width: 760px; animation: rise 0.35s var(--ease) both; }
  .top { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
  h3 { margin: 0; font-size: 20px; }
  h4 { margin: 0 0 4px; font-size: 22px; letter-spacing: -0.015em; }
  .small { font-size: 13px; }
  .progress { height: 4px; border-radius: 2px; background: var(--line); overflow: hidden; }
  .progress i { display: block; height: 100%; background: linear-gradient(90deg, #f0a43c, #ff4d8d); transition: width 0.3s var(--ease); }
  .step { display: grid; gap: 12px; min-height: 170px; align-content: start; animation: rise 0.3s var(--ease) both; }
  .cards { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
  .big { display: grid; gap: 2px; text-align: left; padding: 14px 16px; border-radius: 12px; }
  .big b { font-size: 17px; }
  .big span { font-size: 13.5px; opacity: 0.75; }
  .on { background: var(--text) !important; color: var(--bg); border-color: var(--text) !important; }
  .range { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .days { display: flex; gap: 3px; }
  .days button { width: 30px; height: 30px; padding: 0; border-radius: 50%; font-size: 13px; }
  input[type='time'] { background: rgba(0, 0, 0, 0.2); border: 1px solid var(--glass-line); border-radius: 9px; padding: 5px 8px; color-scheme: dark; }
  label { display: grid; gap: 4px; font-size: 13.5px; color: var(--muted); }
  label input:not([type='checkbox']) { background: rgba(0, 0, 0, 0.2); border: 1px solid var(--glass-line); border-radius: 9px; padding: 7px 11px; color: var(--text); font-size: 15px; }
  .check { display: flex; align-items: center; gap: 8px; color: var(--text); font-size: 14.5px; cursor: pointer; }
  .check input { accent-color: var(--text); width: 16px; height: 16px; }
  .seg { display: flex; flex-wrap: wrap; }
  .seg button { border-radius: 0; margin-left: -1px; }
  .seg button:first-child { border-radius: 9px 0 0 9px; margin-left: 0; }
  .seg button:last-child { border-radius: 0 9px 9px 0; }
  dl { display: grid; grid-template-columns: auto 1fr; gap: 4px 14px; margin: 0; }
  dt { color: var(--muted); font-size: 13.5px; }
  dd { margin: 0; }
  .clash { display: grid; gap: 8px; padding: 10px 12px; border-radius: 10px; border: 1px solid rgba(240, 164, 60, 0.4); background: rgba(240, 164, 60, 0.08); }
  .clash p { margin: 0; }
  .row { display: flex; gap: 8px; align-items: center; }
  .grow { flex: 1; }
  .ghost { background: transparent; }
  .x { padding: 2px 9px; font-size: 16px; }
  .warn { color: #f0a43c; margin: 0; }
  .primary { background: var(--text); color: var(--bg); border-color: var(--text); font-weight: 600; }
  @media (max-width: 640px) { .cards { grid-template-columns: 1fr; } }
</style>
