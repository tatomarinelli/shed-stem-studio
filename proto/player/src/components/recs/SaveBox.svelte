<script lang="ts">
  // Guardar un álbum (o una lista de temas como playlist) en uno o varios destinos. ESCRIBE en las cuentas del usuario:
  // siempre con confirmación explícita que dice qué y dónde. Reutilizable desde otras pantallas (kind='playlist').
  import { onMount } from 'svelte';

  type Dest = { id: string; label: string; state: 'connected' | 'disconnected' | 'unavailable'; note: string; caps: { album: boolean; playlist: boolean } };
  type Result = { ok: boolean; saved: number; notFound: string[]; error?: string; dry?: boolean };
  let { kind = 'album', artist = '', album = '', tracks = [], defaultName = '', onclose }:
    { kind?: 'album' | 'playlist'; artist?: string; album?: string; tracks?: { artist: string; title: string; album?: string }[]; defaultName?: string; onclose: () => void } = $props();

  const KEY = 'stemshed.saveDestinations';
  let dests = $state<Dest[]>([]);
  let chosen = $state<string[]>([]);
  let name = $state('');
  onMount(() => { name = defaultName; });
  let step = $state<'pick' | 'confirm' | 'saving' | 'done'>('pick');
  let results = $state<Record<string, Result>>({});
  let dry = $state(false);
  let error = $state('');

  onMount(async () => {
    try {
      const r = await (await fetch('/engine/destinations')).json();
      dests = r.destinations; dry = r.dryRun;
    } catch { error = 'No pude hablar con el motor.'; return; }
    let last: string[] = [];
    try { last = JSON.parse(localStorage.getItem(KEY) ?? '[]'); } catch { /* sin almacenamiento */ }
    chosen = last.filter(id => usable(dests.find(d => d.id === id)));
  });
  const usable = (d?: Dest) => !!d && d.state === 'connected' && d.caps[kind];
  const labelOf = (id: string) => dests.find(d => d.id === id)?.label ?? id;
  const where = $derived(chosen.map(labelOf).join(' y '));
  const what = $derived(kind === 'album' ? `«${album}» de ${artist}` : `la playlist «${name.trim()}» (${tracks.length} temas)`);

  function toggle(id: string) { chosen = chosen.includes(id) ? chosen.filter(x => x !== id) : [...chosen, id]; }
  async function save() {
    step = 'saving'; error = '';
    try { localStorage.setItem(KEY, JSON.stringify(chosen)); } catch { /* sin almacenamiento */ }
    const items = kind === 'album' ? [{ artist, album }] : tracks;
    try {
      const res = await fetch('/engine/save', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kind, items, destinations: chosen, name: kind === 'playlist' ? name.trim() : undefined, confirm: true }) });
      const body = await res.json();
      if (!res.ok) { error = body.message ?? 'No se pudo guardar.'; step = 'pick'; return; }
      results = body.results; step = 'done';
    } catch { error = 'No pude hablar con el motor.'; step = 'pick'; }
  }
  const resultText = (id: string, r: Result) =>
    r.error ? `${labelOf(id)}: ${r.error}` :
    !r.ok ? `No se encontró en ${labelOf(id)}.` :
    `${r.dry ? 'Prueba, no se guardó: ' : 'Guardado en '}${labelOf(id)}${kind === 'playlist' ? ` (${r.saved} temas)` : ''}${r.notFound.length ? `; faltan ${r.notFound.length}` : ''}.`;
</script>

<div class="save" role="dialog" aria-label="Guardar">
  {#if step === 'pick'}
    {#if kind === 'playlist'}<label class="name">Nombre<input bind:value={name} maxlength="80" /></label>{/if}
    <div class="dests">
      {#each dests as d (d.id)}
        <label class="dest" class:off={!usable(d)}>
          <input type="checkbox" checked={chosen.includes(d.id)} disabled={!usable(d)} onchange={() => toggle(d.id)} />
          {d.label}{#if !usable(d)}<small>{d.note || 'no disponible'}</small>{/if}
        </label>
      {/each}
    </div>
    {#if error}<p class="warn" role="alert">{error}</p>{/if}
    <div class="row">
      <button class="primary" disabled={!chosen.length || (kind === 'playlist' && !name.trim())} onclick={() => (step = 'confirm')}>Guardar</button>
      <button class="ghost" onclick={onclose}>Cancelar</button>
    </div>
  {:else if step === 'confirm'}
    <p>¿Guardar {what} en {where}?{' '}{#if kind === 'album'}Se agrega a tus favoritos.{:else}Se crea una playlist nueva.{/if}{#if dry}{' '}<b>(modo prueba: no se escribe nada)</b>{/if}</p>
    <div class="row">
      <button class="primary" onclick={save}>Sí, guardar</button>
      <button class="ghost" onclick={() => (step = 'pick')}>No</button>
    </div>
  {:else if step === 'saving'}
    <p class="muted">Guardando…</p>
  {:else}
    <ul class="res">
      {#each Object.entries(results) as [id, r] (id)}<li class:okk={r.ok} class:bad={!r.ok}>{resultText(id, r)}</li>{/each}
    </ul>
    <div class="row"><button class="ghost" onclick={onclose}>Cerrar</button></div>
  {/if}
</div>

<style>
  .save { grid-column: 1 / -1; display: grid; gap: 10px; padding: 12px 14px; border-radius: 12px; background: rgba(0, 0, 0, 0.2); border: 1px solid var(--glass-line); animation: rise 0.25s var(--ease) both; }
  .save p { margin: 0; }
  .dests { display: flex; gap: 14px; flex-wrap: wrap; }
  .dest { display: flex; align-items: center; gap: 7px; cursor: pointer; }
  .dest input { accent-color: var(--text); width: 16px; height: 16px; }
  .dest.off { opacity: 0.55; cursor: default; }
  .dest small { color: var(--muted); font-size: 12.5px; margin-left: 4px; }
  .name { display: grid; gap: 4px; font-size: 13.5px; color: var(--muted); max-width: 360px; }
  .name input { background: rgba(0, 0, 0, 0.2); border: 1px solid var(--glass-line); border-radius: 9px; padding: 6px 10px; color: var(--text); }
  .row { display: flex; gap: 8px; }
  .primary { background: var(--text); color: var(--bg); border-color: var(--text); font-weight: 600; }
  .ghost { background: transparent; }
  .res { list-style: none; margin: 0; padding: 0; display: grid; gap: 3px; }
  .okk { color: #7cc7a3; }
  .bad, .warn { color: #f0a43c; }
</style>
