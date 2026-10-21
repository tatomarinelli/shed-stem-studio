<script lang="ts">
  import { onMount } from 'svelte';
  import { recs, type Profile } from '../../lib/recs.svelte';
  import TagInput from './TagInput.svelte';
  import { suggest } from '../../lib/suggest.svelte';

  let { onclose, prefill }: { onclose: () => void; prefill?: { loves: string[]; essentials: string[] } | null } = $props();

  const p = recs.profile!;
  let instrument = $state(p.instrument);
  let level = $state(p.level);
  let improve = $state<string[]>([...p.improve]);
  // svelte-ignore state_referenced_locally
  let loves = $state<string[]>(p.loves.length ? [...p.loves] : [...(prefill?.loves ?? [])]);
  let avoids = $state<string[]>([...p.avoids]);
  // svelte-ignore state_referenced_locally
  let essentials = $state<string[]>(p.essentials.length ? [...p.essentials] : [...(prefill?.essentials ?? [])]);
  let ownArtists = $state<string[]>([...(p.ownArtists ?? [])]);
  let discovery = $state(p.discovery);
  let listening = $state(p.listening);
  let pace = $state(p.pace);
  let notes = $state(p.notes);
  let useTime = $state(p.useTime);
  let useWeather = $state(p.useWeather);
  let city = $state(p.city);
  let saving = $state(false);
  let error = $state('');

  const improveOpts = [['teoria', 'Teoría'], ['modos', 'Modos'], ['oido', 'Oído'], ['repertorio', 'Repertorio'], ['improvisacion', 'Improvisación'],
    ['ritmo', 'Ritmo'], ['lectura', 'Lectura'], ['tecnica', 'Técnica']];
  const toggle = (id: string) => (improve = improve.includes(id) ? improve.filter(x => x !== id) : [...improve, id]);

  onMount(() => suggest.load());
  const styleSugg = $derived(suggest.styles);
  const artistSugg = $derived(suggest.artistList);

  async function save(e: SubmitEvent) {
    e.preventDefault();
    if (useWeather && !city.trim()) { error = 'Escribí tu ciudad para usar el clima.'; return; }
    saving = true; error = '';
    const patch: Partial<Profile> = { instrument, level, improve, loves, avoids, essentials, ownArtists,
      discovery, listening, pace, notes, useTime, useWeather, city };
    const err = await recs.saveProfile({ ...patch, seedSeen: true });
    saving = false;
    if (err) error = err; else onclose();
  }
</script>

<form class="panel" onsubmit={save}>
  <div class="top">
    <h3>Mi perfil</h3>
    <span class="muted">{p.seeded || (prefill && (prefill.loves.length || prefill.essentials.length)) ? 'Deducido de tus favoritos: corregí lo que no cuadre.' : 'Complementa lo que leo de tus fuentes.'}</span>
  </div>

  <div class="grid">
    <label>Instrumento<input bind:value={instrument} placeholder="guitarra" maxlength="40" /></label>
    <label>Nivel
      <select bind:value={level}>
        <option value="">—</option><option value="principiante">Principiante</option><option value="intermedio">Intermedio</option>
        <option value="avanzado">Avanzado</option><option value="profesional">Profesional</option>
      </select>
    </label>
    <label>Estudio por día
      <select bind:value={pace}>
        <option value="">—</option><option value="15">15 min</option><option value="30">30 min</option><option value="60">1 h</option><option value="90">1 h 30 o más</option>
      </select>
    </label>
  </div>

  <fieldset>
    <legend>Quiero mejorar</legend>
    <div class="chips">
      {#each improveOpts as [id, label] (id)}
        <button type="button" class="chip" class:on={improve.includes(id)} aria-pressed={improve.includes(id)} onclick={() => toggle(id)}>{label}</button>
      {/each}
    </div>
  </fieldset>

  <TagInput label="Estilos que amo" bind:value={loves} suggestions={styleSugg} placeholder="escribí o tocá abajo" max={12} show={16} />
  <TagInput label="Estilos que evito" bind:value={avoids} suggestions={styleSugg} placeholder="escribí o tocá abajo" max={12} show={8} />
  <TagInput label="Artistas imprescindibles" bind:value={essentials} suggestions={artistSugg} placeholder="escribí o tocá abajo" />
  <TagInput label="Tu banda o proyecto (nunca se recomienda ni cuenta como gusto)" bind:value={ownArtists} max={5} placeholder="nombre de tu banda" />

  <div class="grid two">
    <fieldset>
      <legend>Música nueva</legend>
      <div class="seg">
        {#each [['nada', 'Nada'], ['algo', 'Algo'], ['mucho', 'Mucha']] as [v, l] (v)}
          <button type="button" class:on={discovery === v} aria-pressed={discovery === v} onclick={() => (discovery = v as Profile['discovery'])}>{l}</button>
        {/each}
      </div>
    </fieldset>
    <fieldset>
      <legend>Escucho</legend>
      <div class="seg">
        {#each [['discos', 'Discos enteros'], ['temas', 'Temas sueltos'], ['ambos', 'Las dos']] as [v, l] (v)}
          <button type="button" class:on={listening === v} aria-pressed={listening === v} onclick={() => (listening = v as Profile['listening'])}>{l}</button>
        {/each}
      </div>
    </fieldset>
  </div>

  <label>Algo más<input bind:value={notes} placeholder="opcional" maxlength="300" /></label>

  <fieldset>
    <legend>Contexto (opcional)</legend>
    <label class="check"><input type="checkbox" bind:checked={useTime} /> Tener en cuenta la hora y el día</label>
    <label class="check"><input type="checkbox" bind:checked={useWeather} /> Tener en cuenta el clima</label>
    {#if useWeather}
      <label class="city">Ciudad<input bind:value={city} placeholder="tu ciudad" maxlength="80" /></label>
      <p class="muted small">Solo se envía la ciudad a Open-Meteo.{#if p.geo && p.city === city} Ubicada: {p.geo.name}, {p.geo.country}.{/if}</p>
    {/if}
  </fieldset>

  {#if error}<p class="warn" role="alert">{error}</p>{/if}
  <div class="acts">
    <button class="primary" type="submit" disabled={saving}>{saving ? 'Guardando…' : 'Guardar'}</button>
    <button type="button" onclick={onclose}>Cancelar</button>
  </div>

  {#if recs.memory}
    <details>
      <summary>Lo que sé de vos</summary>
      <pre>{recs.memory}</pre>
    </details>
  {/if}
</form>

<style>
  .panel { display: grid; gap: 14px; padding: 18px 20px; border-radius: var(--radius); background: var(--glass); backdrop-filter: blur(16px) saturate(1.3); border: 1px solid var(--glass-line); max-width: 860px; animation: rise 0.35s var(--ease) both; }
  .top { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
  h3 { margin: 0; font-size: 20px; }
  .grid { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 12px; }
  .grid.two { grid-template-columns: 1fr 1fr; }
  label { display: grid; gap: 4px; font-size: 13.5px; color: var(--muted); }
  input:not([type='checkbox']) { background: rgba(0, 0, 0, 0.2); border: 1px solid var(--glass-line); border-radius: 9px; padding: 7px 11px; color: var(--text); font-size: 15px; }
  input:focus { border-color: var(--muted); outline: none; }
  select { color: var(--text); font-size: 15px; }
  fieldset { border: 0; padding: 0; margin: 0; display: grid; gap: 6px; min-width: 0; }
  legend { font-size: 13.5px; color: var(--muted); padding: 0; margin-bottom: 6px; }
  .chips, .seg { display: flex; gap: 6px; flex-wrap: wrap; }
  .chip, .seg button { font-size: 14px; padding: 5px 12px; }
  .chip { border-radius: 999px; }
  .seg { gap: 0; }
  .seg button { border-radius: 0; margin-left: -1px; }
  .seg button:first-child { border-radius: 9px 0 0 9px; margin-left: 0; }
  .seg button:last-child { border-radius: 0 9px 9px 0; }
  .on { background: var(--text) !important; color: var(--bg); border-color: var(--text) !important; font-weight: 600; }
  .check { display: flex; align-items: center; gap: 8px; color: var(--text); font-size: 14.5px; cursor: pointer; }
  .check input { accent-color: var(--text); width: 16px; height: 16px; }
  .city { max-width: 320px; }
  .small { font-size: 12.5px; margin: 0; }
  .warn { color: #f0a43c; margin: 0; }
  .acts { display: flex; gap: 8px; }
  .primary { background: var(--text); color: var(--bg); border-color: var(--text); font-weight: 600; }
  summary { cursor: pointer; color: var(--muted); font-size: 14px; }
  pre { white-space: pre-wrap; background: rgba(0, 0, 0, 0.25); border-radius: 10px; padding: 10px 12px; font-size: 13px; line-height: 1.5; max-height: 300px; overflow: auto; font-family: inherit; }
  @media (max-width: 700px) { .grid, .grid.two { grid-template-columns: 1fr; } }
</style>
