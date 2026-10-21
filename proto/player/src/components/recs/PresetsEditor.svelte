<script lang="ts">
  import { recs, type Presets, type Preset, type Intent } from '../../lib/recs.svelte';
  import TagInput from './TagInput.svelte';
  import { suggest } from '../../lib/suggest.svelte';
  import { schedule as scheduleText } from '../../lib/presetText';
  import { onMount } from 'svelte';

  let { onclose, oncreate }: { onclose: () => void; oncreate: () => void } = $props();
  onMount(() => suggest.load());
  let confirmDelete = $state(false);

  let data = $state<Presets>(JSON.parse(JSON.stringify(recs.presets)));
  let sel = $state(data.presets.find(p => p.id === recs.activePreset?.id)?.id ?? data.presets[0].id);
  let error = $state('');
  let saving = $state(false);
  const cur = $derived(data.presets.find(p => p.id === sel) ?? data.presets[0]);

  const DAYS = ['L', 'M', 'M', 'J', 'V', 'S', 'D'];
  const DAY_NAMES = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];
  const intents: [Intent, string][] = [['estudiar', 'Estudiar'], ['concentrarme', 'Concentrarme'], ['sorprenderme', 'Sorprenderme'], ['libre', 'Libre']];
  const sugg = $derived(suggest.styles);
  const artists = $derived(suggest.artistList);

  function duplicate() {
    const p: Preset = { ...JSON.parse(JSON.stringify(cur)), id: `copia-${Date.now().toString(36)}`, name: `${cur.name} (copia)`.slice(0, 30), over: [] };
    data.presets.push(p);
    sel = p.id;
  }
  function remove() {
    if (data.presets.length < 2) return;
    data.presets = data.presets.filter(p => p.id !== sel).map(p => ({ ...p, over: p.over.filter(o => o !== sel) }));
    if (data.default === sel) data.default = data.presets[0].id;
    sel = data.presets[0].id;
    confirmDelete = false;
  }
  const nameOf = (id: string) => data.presets.find(p => p.id === id)?.name ?? id;
  const toggleDay = (r: { days: number[] }, d: number) => (r.days = r.days.includes(d) ? r.days.filter(x => x !== d) : [...r.days, d].sort());
  const addRange = () => cur.schedule.push({ days: [0, 1, 2, 3, 4], start: '09:00', end: '18:00' });

  async function save() {
    saving = true; error = '';
    const err = await recs.savePresets(data);
    saving = false;
    if (err) error = err; else onclose();
  }
</script>

<div class="panel">
  <div class="top">
    <h3>Perfiles</h3>
    <span class="muted">Cambian la intención según el día y la hora. Los gustos son los mismos.</span>
  </div>

  <div class="tabs" role="tablist">
    {#each data.presets as p (p.id)}
      <button role="tab" aria-selected={p.id === sel} class:on={p.id === sel} onclick={() => { sel = p.id; confirmDelete = false; }} title={scheduleText(p)}>{p.name}{#if data.default === p.id}<small> · por defecto</small>{/if}</button>
    {/each}
    <button class="ghost" onclick={oncreate} disabled={data.presets.length >= 8}>+ Nuevo</button>
  </div>

  {#key sel}
    <div class="edit">
      <div class="grid">
        <label>Nombre<input bind:value={cur.name} maxlength="30" /></label>
        <label>Para
          <select bind:value={cur.intent}>{#each intents as [v, l] (v)}<option value={v}>{l}</option>{/each}</select>
        </label>
        <label>Música nueva
          <select bind:value={cur.discovery}>
            <option value={null}>como en Mi perfil</option><option value="nada">nada</option><option value="algo">algo</option><option value="mucho">mucha</option>
          </select>
        </label>
      </div>

      <fieldset>
        <legend>Horario</legend>
        {#each cur.schedule as r, i (i)}
          <div class="range">
            <div class="days">
              {#each DAYS as d, j (j)}
                <button type="button" class:on={r.days.includes(j)} aria-pressed={r.days.includes(j)} aria-label={DAY_NAMES[j]} onclick={() => toggleDay(r, j)}>{d}</button>
              {/each}
            </div>
            <input type="time" bind:value={r.start} aria-label="Desde" />
            <span class="muted">a</span>
            <input type="time" bind:value={r.end} aria-label="Hasta" />
            <button type="button" class="ghost x" aria-label="Quitar horario" onclick={() => cur.schedule.splice(i, 1)}>×</button>
          </div>
        {:else}
          <p class="muted small">Sin horario: solo a demanda{data.default === cur.id ? ' o cuando no toca ningún otro' : ''}.</p>
        {/each}
        <div><button type="button" class="ghost" onclick={addRange}>+ Horario</button></div>
      </fieldset>

      <p class="muted small">{scheduleText(cur)}</p>
      <div class="grid two">
        <TagInput label="Favorecer" bind:value={cur.favor} suggestions={sugg} placeholder="estilos" max={12} show={8} />
        <TagInput label="Evitar" bind:value={cur.avoid} suggestions={sugg} placeholder="estilos" max={12} show={8} />
      </div>
      <TagInput label="Referencias" bind:value={cur.examples} suggestions={artists} placeholder="artistas" max={12} show={8} />
      <label class="check"><input type="checkbox" bind:checked={cur.instrumental} /> Mayormente instrumental</label>
      <label>Consigna<input bind:value={cur.prompt} maxlength="160" placeholder="opcional" /></label>

      {#if cur.note}<p class="muted small">{cur.note}</p>{/if}
      <div class="row wrap">
        <label class="check"><input type="radio" name="def" checked={data.default === cur.id} onchange={() => (data.default = cur.id)} /> Por defecto</label>
        <label class="prio">Prioridad si empatan<input type="number" min="0" max="9" bind:value={cur.priority} /></label>
        {#each cur.over as o (o)}
          <span class="chip">manda sobre {nameOf(o)} <button type="button" class="x" aria-label="Quitar" onclick={() => (cur.over = cur.over.filter(x => x !== o))}>×</button></span>
        {/each}
        <span class="grow"></span>
        <button type="button" class="ghost" onclick={duplicate} disabled={data.presets.length >= 8}>Duplicar</button>
        {#if confirmDelete}
          <span class="confirm">¿Borrar {cur.name}? <button type="button" class="danger" onclick={remove}>Sí, borrar</button> <button type="button" onclick={() => (confirmDelete = false)}>No</button></span>
        {:else}
          <button type="button" class="ghost" onclick={() => (confirmDelete = true)} disabled={data.presets.length < 2}>Borrar</button>
        {/if}
      </div>
    </div>
  {/key}

  {#if error}<p class="warn" role="alert">{error}</p>{/if}
  <div class="row">
    <button class="primary" onclick={save} disabled={saving}>{saving ? 'Guardando…' : 'Guardar'}</button>
    <button onclick={onclose}>Cancelar</button>
  </div>
</div>

<style>
  .panel { display: grid; gap: 14px; padding: 18px 20px; border-radius: var(--radius); background: var(--glass); backdrop-filter: blur(16px) saturate(1.3); border: 1px solid var(--glass-line); max-width: 860px; animation: rise 0.35s var(--ease) both; }
  .top { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
  h3 { margin: 0; font-size: 20px; }
  .tabs { display: flex; gap: 6px; flex-wrap: wrap; }
  .tabs button { border-radius: 999px; font-size: 14px; padding: 5px 13px; }
  .tabs small { font-weight: 400; opacity: 0.7; }
  .on { background: var(--text) !important; color: var(--bg); border-color: var(--text) !important; font-weight: 600; }
  .edit { display: grid; gap: 12px; }
  .grid { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 12px; }
  .grid.two { grid-template-columns: 1fr 1fr; }
  label { display: grid; gap: 4px; font-size: 13.5px; color: var(--muted); }
  input:not([type='checkbox']):not([type='radio']) { background: rgba(0, 0, 0, 0.2); border: 1px solid var(--glass-line); border-radius: 9px; padding: 7px 11px; color: var(--text); font-size: 15px; }
  input[type='time'] { padding: 5px 8px !important; color-scheme: dark; }
  select { color: var(--text); font-size: 15px; }
  fieldset { border: 0; padding: 0; margin: 0; display: grid; gap: 8px; }
  legend { font-size: 13.5px; color: var(--muted); padding: 0; margin-bottom: 6px; }
  .range { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .days { display: flex; gap: 3px; }
  .days button { width: 30px; height: 30px; padding: 0; border-radius: 50%; font-size: 13px; }
  .x { padding: 2px 9px; font-size: 16px; }
  .ghost { background: transparent; }
  .check { display: flex; align-items: center; gap: 8px; color: var(--text); font-size: 14.5px; cursor: pointer; }
  .check input { accent-color: var(--text); width: 16px; height: 16px; }
  .row { display: flex; gap: 8px; align-items: center; }
  .wrap { flex-wrap: wrap; }
  .prio { display: flex; align-items: center; gap: 6px; }
  .prio input { width: 56px; padding: 4px 8px !important; }
  .chip { font-size: 13px; border: 1px solid var(--glass-line); border-radius: 999px; padding: 1px 4px 1px 10px; }
  .confirm { display: flex; align-items: center; gap: 6px; font-size: 14px; }
  .danger { background: var(--loop); border-color: var(--loop); color: #14040a; font-weight: 600; }
  .grow { flex: 1; }
  .small { font-size: 13px; margin: 0; }
  .warn { color: #f0a43c; margin: 0; }
  .primary { background: var(--text); color: var(--bg); border-color: var(--text); font-weight: 600; }
  @media (max-width: 700px) { .grid, .grid.two { grid-template-columns: 1fr; } }
</style>
