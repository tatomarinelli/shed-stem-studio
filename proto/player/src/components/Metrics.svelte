<script lang="ts">
  import { player } from '../lib/player.svelte';
  const m = $derived(player.metrics);
</script>

<details class="metrics">
  <summary>Rendimiento</summary>
  <dl>
    <dt>Motor</dt><dd>{m.engineReady ? 'listo' : 'iniciando…'}</dd>
    <dt>Cortes (underruns)</dt><dd class:bad={player.underruns > 0}>{player.underruns}</dd>
    <dt>Stems en memoria (float32)</dt><dd>{m.f32MB.toFixed(0)} MB</dd>
    <dt>Heap JS</dt><dd>{m.heapMB.toFixed(0)} MB</dd>
    <dt>FLAC leído / tiempo de carga</dt><dd>{m.flacMB.toFixed(0)} MB / {(m.loadMs / 1000).toFixed(1)} s</dd>
    <dt>Latencia base / de salida</dt><dd>{m.baseLatencyMs.toFixed(0)} ms / {m.outLatencyMs.toFixed(0)} ms</dd>
  </dl>
</details>

<style>
  .metrics { background: var(--glass); backdrop-filter: blur(12px); border: 1px solid var(--glass-line); border-radius: 12px; padding: 8px 14px; color: var(--muted); font-size: 13.5px; }
  dl { display: grid; grid-template-columns: max-content 1fr; gap: 2px 16px; margin: 8px 0 2px; }
  dt { color: var(--muted); }
  dd { margin: 0; color: var(--text); font-variant-numeric: tabular-nums; }
  .bad { color: var(--danger); font-weight: 600; }
</style>
