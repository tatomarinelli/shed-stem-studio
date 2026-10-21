<script lang="ts">
  // Desplegable con búsqueda y conteos. value '' = sin filtro.
  let { label, items, value = $bindable(''), onchange }:
    { label: string; items: { name: string; count: number }[]; value?: string; onchange?: () => void } = $props();
  let open = $state(false);
  let q = $state('');
  let root: HTMLDivElement;
  const norm = (s: string) => s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  const shown = $derived(items.filter(i => !q || norm(i.name).includes(norm(q))).slice(0, 150));
  function pick(v: string) { value = v; open = false; q = ''; onchange?.(); }
  function away(e: MouseEvent) { if (open && !root.contains(e.target as Node)) open = false; }
</script>

<svelte:window onclick={away} />

<div class="combo" bind:this={root}>
  <button class="trigger" class:set={!!value} aria-haspopup="listbox" aria-expanded={open} onclick={() => (open = !open)}>
    <span>{value || label}</span>
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
  </button>
  {#if open}
    <div class="pop" role="listbox" aria-label={label} onkeydown={e => e.key === 'Escape' && (open = false)} tabindex="-1">
      <!-- svelte-ignore a11y_autofocus -->
      <input type="search" placeholder="Buscar" bind:value={q} aria-label="Buscar {label.toLowerCase()}" autofocus />
      <ul>
        <li><button role="option" aria-selected={!value} onclick={() => pick('')}>Todos</button></li>
        {#each shown as i (i.name)}
          <li><button role="option" aria-selected={value === i.name} onclick={() => pick(i.name)}><span>{i.name}</span><span class="muted num">{i.count}</span></button></li>
        {:else}
          <li class="muted none">Sin resultados.</li>
        {/each}
      </ul>
    </div>
  {/if}
</div>

<style>
  .combo { position: relative; }
  .trigger { display: flex; align-items: center; gap: 8px; max-width: 220px; }
  .trigger span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .trigger.set { background: rgba(255,255,255,0.16); border-color: rgba(255,255,255,0.32); }
  .pop { position: absolute; top: calc(100% + 6px); left: 0; z-index: 30; width: 280px; display: grid; gap: 6px; padding: 8px; border-radius: 14px; background: rgba(18, 30, 33, 0.96); border: 1px solid var(--glass-line); backdrop-filter: blur(20px); box-shadow: 0 24px 60px -20px rgba(0,0,0,0.9); animation: rise 0.2s var(--ease) both; }
  input { background: rgba(255,255,255,0.06); border: 1px solid var(--glass-line); border-radius: 9px; padding: 7px 10px; width: 100%; }
  ul { list-style: none; margin: 0; padding: 0; max-height: 300px; overflow: auto; display: grid; gap: 1px; }
  li button { width: 100%; display: flex; justify-content: space-between; gap: 10px; text-align: left; background: transparent; border: 0; padding: 6px 10px; border-radius: 8px; }
  li button span:first-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  li button:hover, li button[aria-selected='true'] { background: rgba(255,255,255,0.1); }
  .none { padding: 6px 10px; }
</style>
