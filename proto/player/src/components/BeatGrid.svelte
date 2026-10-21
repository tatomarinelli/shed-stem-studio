<script lang="ts">
  import { analysis } from '../lib/analysis.svelte';
  import { view } from '../lib/view.svelte';

  let { h }: { h: number } = $props();
  let canvas: HTMLCanvasElement;

  // Líneas de pulso y de compás sobre las ondas; solo las visibles y solo si no quedan apelotonadas.
  $effect(() => {
    const d = analysis.data;
    const w = Math.max(1, Math.floor(view.viewW)), dpr = window.devicePixelRatio || 1;
    canvas.width = w * dpr; canvas.height = h * dpr;
    const g = canvas.getContext('2d')!;
    g.scale(dpr, dpr);
    if (!d || !analysis.showGrid) return;
    const beats = d.tempo.beats, down = new Set(d.tempo.downbeats.map(t => Math.round(t * 1000)));
    const t0 = view.t(0), t1 = view.t(w);
    const beatPx = (60 / d.tempo.bpm) * view.pps, barPx = beatPx * 4;
    if (barPx < 6) return;
    let lo = 0, hi = beats.length;
    while (lo < hi) { const m = (lo + hi) >> 1; if (beats[m] < t0) lo = m + 1; else hi = m; }
    let bar = d.tempo.downbeats.findIndex(t => t >= t0 - 1e-6);
    if (bar < 0) bar = d.tempo.downbeats.length;
    g.font = '11px system-ui, sans-serif'; g.textBaseline = 'top';
    for (let i = lo; i < beats.length && beats[i] <= t1; i++) {
      const isDown = [...[Math.round(beats[i] * 1000)]].some(v => down.has(v) || down.has(v - 1) || down.has(v + 1));
      const x = Math.round(view.x(beats[i])) + 0.5;
      if (!isDown && beatPx < 7) continue;
      g.strokeStyle = isDown ? 'rgba(255,255,255,0.30)' : 'rgba(255,255,255,0.10)';
      g.beginPath(); g.moveTo(x, 0); g.lineTo(x, h); g.stroke();
      if (isDown) {
        const n = d.tempo.downbeats.findIndex(t => Math.abs(t - beats[i]) < 0.04) + 1;
        if (barPx >= 38 && n > 0) { g.fillStyle = 'rgba(255,255,255,0.55)'; g.fillText(String(n), x + 4, 3); }
      }
    }
  });
</script>

<canvas bind:this={canvas} style="width:{view.viewW}px;height:{h}px" aria-hidden="true"></canvas>

<style>
  canvas { position: absolute; left: 0; top: 0; pointer-events: none; }
</style>
