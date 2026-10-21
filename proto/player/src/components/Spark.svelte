<script lang="ts">
  import { WINDOW_MS } from '../lib/resources.svelte';

  // Gráfico de línea chico (hasta 5 minutos: `span` es lo que abarca). El eje X es el tiempo real: si hubo un corte, la línea se corta.
  let { t, values, now, span = WINDOW_MS, max = 100, color, label }: {
    t: number[]; values: (number | null)[]; now: number; span?: number; max?: number; color: string; label: string;
  } = $props();

  const W = 300, H = 48, GAP = 3500;
  const paths = $derived.by(() => {
    const top = Math.max(max, 1e-9);
    const segs: [number, number][][] = [];
    let cur: [number, number][] = [];
    let prevT = -Infinity;
    for (let i = 0; i < t.length; i++) {
      const v = values[i];
      if (v == null || t[i] - prevT > GAP) { if (cur.length) segs.push(cur); cur = []; }
      prevT = t[i];
      if (v == null) continue;
      cur.push([((t[i] - (now - span)) / span) * W, H - 2 - Math.min(1, Math.max(0, v / top)) * (H - 4)]);
    }
    if (cur.length) segs.push(cur);
    const f = (n: number) => n.toFixed(1);
    const line = segs.map(s => (s.length === 1 ? `M${f(s[0][0])} ${f(s[0][1])}h0.1` : 'M' + s.map(p => `${f(p[0])} ${f(p[1])}`).join('L'))).join('');
    const area = segs.filter(s => s.length > 1).map(s => `M${f(s[0][0])} ${H}L` + s.map(p => `${f(p[0])} ${f(p[1])}`).join('L') + `L${f(s[s.length - 1][0])} ${H}Z`).join('');
    return { line, area };
  });
</script>

<svg viewBox="0 0 {W} {H}" preserveAspectRatio="none" role="img" aria-label={label} style="--c:{color}">
  <path class="grid" d="M0 {H / 2}H{W}" />
  {#if paths.area}<path class="area" d={paths.area} />{/if}
  {#if paths.line}<path class="line" d={paths.line} />{/if}
</svg>

<style>
  svg { width: 100%; height: 48px; display: block; overflow: visible; }
  .grid { stroke: rgba(255, 255, 255, 0.08); stroke-width: 1; stroke-dasharray: 3 4; vector-effect: non-scaling-stroke; fill: none; }
  .area { fill: var(--c); opacity: 0.16; }
  .line { fill: none; stroke: var(--c); stroke-width: 1.6; stroke-linejoin: round; stroke-linecap: round; vector-effect: non-scaling-stroke; }
</style>
