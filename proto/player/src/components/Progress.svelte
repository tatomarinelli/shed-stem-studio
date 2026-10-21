<script lang="ts">
  import type { Pull } from '../lib/settings.svelte';

  let { job, verb = 'Descargando', oncancel }: { job: Pull; verb?: string; oncancel?: () => void } = $props();

  const mb = (b: number) => (b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : `${Math.round(b / 1e6)} MB`);
  const detail = $derived.by(() => {
    const parts: string[] = [];
    if (job.total) parts.push(`${job.approx ? '≈ ' : ''}${mb(job.done ?? 0)} de ${mb(job.total)}`);
    if (job.rate) parts.push(`${(job.rate / 1e6).toFixed(1)} MB/s`);
    if (job.total && job.rate && job.done != null) {
      const left = Math.max(0, job.total - job.done) / job.rate;
      if (left > 5 && left < 36000) parts.push(left >= 90 ? `faltan ${Math.round(left / 60)} min` : `faltan ${Math.round(left)} s`);
    }
    return parts.join(' · ');
  });
</script>

<div class="progress" role="progressbar" aria-valuenow={job.percent ?? 0} aria-valuemin="0" aria-valuemax="100" aria-label={verb}>
  <div class="bar"><i style="width:{job.percent ?? 0}%"></i></div>
  <span class="muted num">{verb} {job.percent ?? 0} %{detail ? ` · ${detail}` : ''}</span>
  {#if job.step}<span class="muted step">{job.step}</span>{/if}
  {#if oncancel}<button class="ghost cancel" onclick={oncancel}>Cancelar</button>{/if}
</div>

<style>
  .progress { display: grid; gap: 4px; width: 100%; }
  .bar { height: 8px; background: rgba(255,255,255,0.1); border-radius: 4px; overflow: hidden; }
  .bar i { display: block; height: 100%; background: linear-gradient(90deg, #4fa3d9, #7cc7a3); border-radius: 4px; transition: width 0.5s var(--ease); }
  .num { font-variant-numeric: tabular-nums; font-size: 0.85rem; }
  .step { font-size: 0.78rem; overflow-wrap: anywhere; }
  .cancel { justify-self: start; }
</style>
