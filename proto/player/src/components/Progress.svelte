<script lang="ts">
  import { onMount } from 'svelte';
  import type { Pull } from '../lib/settings.svelte';

  let { job, verb = 'Descargando', oncancel }: { job: Pull; verb?: string; oncancel?: () => void } = $props();

  // Reloj para el tiempo transcurrido y para detectar que no hay novedades (el motor sella `updated` solo cuando avanza algo).
  let now = $state(Date.now());
  onMount(() => {
    const t = window.setInterval(() => (now = Date.now()), 1000);
    return () => window.clearInterval(t);
  });

  const mb = (b: number) => (b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : `${Math.round(b / 1e6)} MB`);
  const clock = (s: number) => (s >= 3600 ? `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min` : `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`);
  const PHASES = ['Preparando', 'Descargando', 'Verificando', 'Instalando', 'Terminando', 'Cargando', 'Creando'];

  const cancelling = $derived(!!job.cancelling);
  const phase = $derived(PHASES.find(p => job.step?.startsWith(p)) ?? verb);
  const indeterminate = $derived(!job.total && !(job.percent ?? 0));
  const pct = $derived(job.percent ?? 0);
  const label = $derived(cancelling ? 'Cancelando…' : indeterminate ? `${phase}…` : `${phase} ${job.approx ? '≈ ' : ''}${pct} %`);
  const elapsed = $derived(job.startedAt ? Math.max(0, Math.round(now / 1000 - job.startedAt)) : null);
  const quiet = $derived(job.updated ? Math.round(now / 1000 - job.updated) : 0);
  const stalled = $derived(!cancelling && quiet >= 30);
  const detail = $derived.by(() => {
    const parts: string[] = [];
    if (job.total) parts.push(`${job.approx ? '≈ ' : ''}${mb(job.done ?? 0)} de ${mb(job.total)}`);
    if (job.rate) parts.push(`${(job.rate / 1e6).toFixed(1)} MB/s`);
    if (job.total && job.rate && job.done != null) {
      const left = Math.max(0, job.total - job.done) / job.rate;
      if (left > 5 && left < 36000) parts.push(left >= 90 ? `faltan ${Math.round(left / 60)} min` : `faltan ${Math.round(left)} s`);
    }
    if (elapsed != null) parts.push(`lleva ${clock(elapsed)}`);
    return parts.join(' · ');
  });
</script>

<div class="progress" role="progressbar" aria-busy="true" aria-valuemin="0" aria-valuemax="100"
  aria-valuenow={indeterminate ? undefined : pct} aria-valuetext={label} aria-label={verb}>
  <div class="bar" class:indet={indeterminate || cancelling}><i style={indeterminate || cancelling ? '' : `width:${pct}%`}></i></div>
  <span class="muted num">{label}{detail ? ` · ${detail}` : ''}</span>
  {#if job.step && job.step !== phase}<span class="muted step">{job.step}</span>{/if}
  {#if stalled}<span class="warn step" role="status">Sin novedades hace {quiet} s. Puede estar trabajando; si sigue igual, cancelá y probá de nuevo.</span>{/if}
  {#if job.notice}<span class="warn step" role="alert">{job.notice}</span>{/if}
  {#if oncancel}
    {#if job.cancelable === false}<span class="muted step">Ya no se puede cortar sin dejarlo a medias.</span>
    {:else}<button class="ghost cancel" disabled={cancelling} onclick={oncancel}>{cancelling ? 'Cancelando…' : 'Cancelar'}</button>{/if}
  {/if}
</div>

<style>
  .progress { display: grid; gap: 4px; width: 100%; }
  .bar { height: 8px; background: rgba(255,255,255,0.1); border-radius: 4px; overflow: hidden; position: relative; }
  .bar i { display: block; height: 100%; background: linear-gradient(90deg, #4fa3d9, #7cc7a3); border-radius: 4px; transition: width 0.5s var(--ease); }
  .bar.indet i { position: absolute; width: 35%; animation: slide 1.4s ease-in-out infinite; }
  @keyframes slide { from { left: -35%; } to { left: 100%; } }
  @media (prefers-reduced-motion: reduce) { .bar.indet i { animation: none; width: 100%; opacity: 0.5; } }
  .num { font-variant-numeric: tabular-nums; font-size: 0.85rem; }
  .step { font-size: 0.78rem; overflow-wrap: anywhere; }
  .cancel { justify-self: start; }
</style>
