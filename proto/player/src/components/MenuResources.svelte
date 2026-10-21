<script lang="ts">
  import { resources, gb } from '../lib/resources.svelte';

  // Barra compacta del menú: solo mientras hay un trabajo activo. Usa el mismo sondeo que el panel de Ajustes.
  let { active, collapsed }: { active: boolean; collapsed: boolean } = $props();

  $effect(() => {
    if (!active) return;
    return resources.watch();
  });

  const d = $derived(active ? resources.data : null);
  const gpu = $derived(d?.gpus[0] ?? null);
  // Con placa de video: su memoria. Sin placa: la memoria del equipo.
  const used = $derived(gpu ? gpu.memUsedBytes : (d?.ram?.usedBytes ?? null));
  const total = $derived(gpu ? gpu.memTotalBytes : (d?.ram?.totalBytes ?? null));
  const title = $derived(gpu ? 'Memoria de video' : 'Memoria');
  const percent = $derived(used != null && total ? Math.min(100, (100 * used) / total) : 0);
  const text = $derived(`${title}: ${gb(used)} de ${gb(total)}`);
</script>

{#if d && used != null}
  <a class="res" class:collapsed href="#/ajustes" title="{text}. Ver recursos en Ajustes" aria-label="{text}. Ver recursos en Ajustes">
    {#if collapsed}
      <span class="tube" aria-hidden="true"><i style="height:{percent}%"></i></span>
    {:else}
      <span class="lbl muted">{title}</span>
      <span class="num">{gb(used)} / {gb(total)}</span>
      <span class="bar" aria-hidden="true"><i style="width:{percent}%"></i></span>
    {/if}
  </a>
{/if}

<style>
  .res { flex: none; display: grid; gap: 6px; margin: 10px 4px 0; padding: 8px 10px; border-radius: 10px; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--glass-line); color: inherit; text-decoration: none; font-size: 13px; height: auto; min-width: 0; overflow: hidden; white-space: nowrap; animation: rise 0.4s var(--ease) both; }
  .lbl { font-size: 12.5px; }
  .bar { height: 6px; border-radius: 3px; background: rgba(255, 255, 255, 0.1); overflow: hidden; }
  .bar i { display: block; height: 100%; background: linear-gradient(90deg, #f0a43c, #ff4d8d); border-radius: 3px; transition: width 0.5s var(--ease); }
  .res.collapsed { justify-items: center; padding: 8px 0; }
  .tube { width: 8px; height: 28px; border-radius: 4px; background: rgba(255, 255, 255, 0.1); overflow: hidden; display: flex; align-items: flex-end; }
  .tube i { display: block; width: 100%; background: linear-gradient(0deg, #f0a43c, #ff4d8d); transition: height 0.5s var(--ease); }
  @media (max-width: 760px) { .res { display: none; } }
</style>
