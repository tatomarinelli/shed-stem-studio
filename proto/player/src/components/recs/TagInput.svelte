<script lang="ts">
  // Lista de etiquetas: se agregan tocando sugerencias o escribiendo (Enter o coma). Un clic en una etiqueta la quita.
  let { value = $bindable([]), suggestions = [], placeholder = '', label, max = 15, show = 12 }:
    { value?: string[]; suggestions?: { name: string; mine?: boolean }[]; placeholder?: string; label: string; max?: number; show?: number } = $props();

  let text = $state('');
  let focused = $state(false);
  let active = $state(0);
  const has = (s: string) => value.some(v => v.toLowerCase() === s.toLowerCase());
  const free = $derived(suggestions.filter(s => !has(s.name)));
  const matches = $derived(text.trim() ? free.filter(s => s.name.toLowerCase().includes(text.trim().toLowerCase())).slice(0, 8) : []);
  const id = `tags-${Math.random().toString(36).slice(2, 8)}`;

  function add(s: string) {
    s = s.trim();
    if (s && !has(s) && value.length < max) value = [...value, s];
    text = ''; active = 0;
  }
  const remove = (s: string) => (value = value.filter(v => v !== s));
  function key(e: KeyboardEvent) {
    if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); add(matches[active]?.name ?? text); }
    else if (e.key === 'ArrowDown' && matches.length) { e.preventDefault(); active = (active + 1) % matches.length; }
    else if (e.key === 'ArrowUp' && matches.length) { e.preventDefault(); active = (active - 1 + matches.length) % matches.length; }
    else if (e.key === 'Backspace' && !text && value.length) value = value.slice(0, -1);
    else if (e.key === 'Escape') text = '';
  }
</script>

<div class="tags">
  <label for={id}>{label}</label>
  <div class="box" class:focused>
    {#each value as v (v)}
      <button type="button" class="tag on" onclick={() => remove(v)} aria-label="Quitar {v}">{v} <span aria-hidden="true">×</span></button>
    {/each}
    <input {id} bind:value={text} placeholder={value.length ? '' : placeholder} onkeydown={key} autocomplete="off"
      onfocus={() => (focused = true)} onblur={() => setTimeout(() => { focused = false; if (text.trim()) add(text); }, 150)}
      role="combobox" aria-expanded={focused && matches.length > 0} aria-controls="{id}-list" />
    {#if focused && matches.length}
      <ul class="menu" id="{id}-list" role="listbox">
        {#each matches as m, i (m.name)}
          <li role="option" aria-selected={i === active}><button type="button" class:hi={i === active} onmousedown={e => { e.preventDefault(); add(m.name); }}>{m.name}{#if m.mine}<small>tuyo</small>{/if}</button></li>
        {/each}
      </ul>
    {/if}
  </div>
  {#if free.length && value.length < max}
    <div class="sugg">
      {#each free.slice(0, show) as s (s.name)}
        <button type="button" class="tag" class:mine={s.mine} onclick={() => add(s.name)}>+ {s.name}</button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .tags { display: grid; gap: 5px; min-width: 0; }
  label { font-size: 13.5px; color: var(--muted); }
  .box { position: relative; display: flex; flex-wrap: wrap; gap: 5px; align-items: center; background: rgba(0, 0, 0, 0.2); border: 1px solid var(--glass-line); border-radius: 9px; padding: 5px 6px; min-height: 38px; }
  .box.focused { border-color: var(--muted); }
  input { flex: 1 1 120px; min-width: 80px; background: transparent; border: 0; outline: none; padding: 2px 4px; font-size: 15px; color: var(--text); }
  .tag { font-size: 13px; padding: 2px 10px; border-radius: 999px; }
  .tag.on { background: var(--text); color: var(--bg); border-color: var(--text); font-weight: 600; }
  .tag.on span { opacity: 0.6; margin-left: 2px; }
  .sugg { display: flex; flex-wrap: wrap; gap: 5px; }
  .sugg .tag { background: transparent; color: var(--muted); }
  .sugg .tag.mine { color: var(--text); border-color: color-mix(in srgb, #7cc7a3 45%, transparent); }
  .sugg .tag:hover { color: var(--text); }
  .menu { position: absolute; z-index: 20; top: calc(100% + 4px); left: 0; min-width: 220px; list-style: none; margin: 0; padding: 4px; border-radius: 10px; background: #1e3035; border: 1px solid var(--glass-line); box-shadow: 0 16px 40px -16px rgba(0, 0, 0, 0.8); }
  .menu button { width: 100%; text-align: left; border: 0; background: transparent; border-radius: 7px; padding: 5px 10px; display: flex; justify-content: space-between; gap: 10px; }
  .menu button.hi, .menu button:hover { background: rgba(255, 255, 255, 0.08); }
  small { color: #7cc7a3; font-size: 11px; }
</style>
