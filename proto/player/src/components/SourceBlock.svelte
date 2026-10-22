<script lang="ts">
  import type { Snippet } from 'svelte';
  import SourceLogo from './SourceLogo.svelte';

  let { id, title, status = '', ok = false, children }: { id: string; title: string; status?: string; ok?: boolean; children: Snippet } = $props();

  // Cada bloque recuerda si lo dejaste abierto (solo comodidad: sin almacenamiento arranca cerrado).
  const key = () => `fuentes-abierta-${id}`;
  let open = $state((() => { try { return localStorage.getItem(key()) === '1'; } catch { return false; } })());
  function toggle(e: Event) {
    open = (e.currentTarget as HTMLDetailsElement).open;
    try { localStorage.setItem(key(), open ? '1' : '0'); } catch { /* sin almacenamiento */ }
  }
</script>

<details class="block" data-source={id} {open} ontoggle={toggle}>
  <summary>
    <SourceLogo {id} />
    <span class="name">{title}</span>
    {#if status}<span class="state" class:ok role="status">{status}</span>{/if}
    <span class="chev" aria-hidden="true">▾</span>
  </summary>
  <div class="body">{@render children()}</div>
</details>

<style>
  .block { background: var(--glass); backdrop-filter: blur(16px) saturate(1.3); border: 1px solid var(--glass-line); border-radius: var(--radius); box-shadow: 0 20px 50px -24px rgba(0,0,0,0.7); animation: rise 0.45s var(--ease) both; }
  summary { display: flex; align-items: center; gap: 12px; padding: 14px 16px; cursor: pointer; list-style: none; }
  summary::-webkit-details-marker { display: none; }
  .name { font-size: 18px; font-weight: 600; flex: 1; }
  .state { font-size: 12.5px; color: var(--muted); }
  .state.ok { color: #7cc7a3; }
  .chev { color: var(--muted); transition: transform 0.2s var(--ease); }
  details[open] .chev { transform: rotate(180deg); }
  .body { padding: 0 16px 16px; display: grid; gap: 12px; }
</style>
