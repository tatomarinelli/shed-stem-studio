<script lang="ts">
  import { downloads } from '../lib/downloads.svelte';

  // `ids`: ids del tema en cada fuente (para ver su estado); `resolve`: elige el id que se baja, según el orden de fuentes de Ajustes.
  // `localId`: el archivo propio, si lo hay (para "Mostrar archivo original").
  let { ids, resolve, localId, localOnly = false, size = 30 }:
    { ids: string[]; resolve: () => Promise<string | null>; localId?: string; localOnly?: boolean; size?: number } = $props();

  let open = $state(false);
  let starting = $state(false);
  const dl = $derived(ids.map(i => downloads.of(i)).find(j => j && j.state !== 'idle'));
  const dlId = $derived(ids.find(i => downloads.of(i)?.state === 'running'));
  const dir = (p?: string) => p ?? downloads.dir;

  $effect(() => { downloads.ensure(); });

  async function start() {
    open = false;
    starting = true;
    try {
      const id = await resolve();
      if (id) await downloads.start(id);
    } finally { starting = false; }
  }
  const reveal = (id?: string, original = false) => { open = false; if (id) void downloads.reveal({ id, original }); };
  const doneId = $derived(ids.find(i => downloads.of(i)?.state === 'done'));
</script>

<svelte:window onclick={e => { if (open && !(e.target as HTMLElement).closest?.('.dlm')) open = false; }} onkeydown={e => { if (e.key === 'Escape') open = false; }} />

<span class="dlm">
  {#if dl?.state === 'running'}
    <span class="pct num" role="status" title={dl.step}>{dl.percent ?? 0} %</span>
    <button class="chip" onclick={() => dlId && downloads.cancel(dlId)} disabled={dl.cancelling} title="Cancelar la descarga">{dl.cancelling ? 'Cancelando…' : 'Cancelar'}</button>
  {:else if dl?.state === 'done' && doneId}
    <button class="chip done" onclick={() => reveal(doneId)} title={dl.file ?? 'Abrir la carpeta'}>Descargado · Abrir carpeta</button>
  {:else if dl?.state === 'error'}
    <span class="err" role="alert" title={dl.message}>!</span>
  {/if}
  <button class="ib" onclick={() => (open = !open)} aria-haspopup="menu" aria-expanded={open} aria-label="Más acciones" title="Descargar y más" style="min-width:{size}px;height:{size}px">
    <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="19" cy="12" r="1.8"/></svg>
  </button>
  {#if open}
    <div class="menu" role="menu">
      {#if dl?.state === 'running'}
        <button role="menuitem" onclick={() => { open = false; if (dlId) void downloads.cancel(dlId); }}>Cancelar la descarga</button>
      {:else if dl?.state === 'done' && doneId}
        <button role="menuitem" onclick={() => reveal(doneId)}>Abrir carpeta de la descarga</button>
      {:else}
        <button role="menuitem" onclick={start} disabled={downloads.busy || starting} title={downloads.busy ? 'Ya hay una descarga en curso' : ''}>{localOnly ? 'Copiar a descargas' : 'Descargar'}</button>
      {/if}
      {#if localId}<button role="menuitem" onclick={() => reveal(localId, true)}>Mostrar el archivo original</button>{/if}
      {#if downloads.dir}<p class="where muted" title={downloads.dir}>{downloads.qualityLabel}{downloads.ipod ? ' · iPod' : ''} · va a {dir()}</p>{/if}
    </div>
  {/if}
</span>

<style>
  .dlm { position: relative; display: inline-flex; align-items: center; gap: 6px; flex: none; }
  .ib { padding: 0; display: grid; place-items: center; border-radius: 50%; background: transparent; border: 1px solid var(--glass-line); color: var(--text); }
  .chip { border-radius: 999px; padding: 0 12px; height: 30px; font-size: 13px; white-space: nowrap; background: transparent; }
  .chip.done { color: #7cc7a3; border-color: color-mix(in srgb, #7cc7a3 45%, transparent); }
  .pct { font-size: 12.5px; color: var(--muted); min-width: 44px; text-align: center; }
  .err { color: var(--loop); font-size: 13px; }
  .menu { position: absolute; right: 0; top: calc(100% + 6px); z-index: 30; display: grid; gap: 2px; min-width: 220px; max-width: 320px; padding: 6px; border-radius: 12px; background: #16262a; border: 1px solid var(--glass-line); box-shadow: 0 18px 40px -12px rgba(0, 0, 0, 0.8); animation: rise 0.15s var(--ease) both; }
  .menu button { text-align: left; border: 0; background: transparent; border-radius: 8px; padding: 8px 10px; white-space: nowrap; }
  .menu button:hover:not(:disabled) { background: rgba(255, 255, 255, 0.09); }
  .where { margin: 2px 0 0; padding: 6px 10px 2px; font-size: 12px; border-top: 1px solid var(--glass-line); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  @container (max-width: 560px) { .chip.done { display: none; } }
</style>
