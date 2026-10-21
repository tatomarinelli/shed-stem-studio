<script lang="ts">
  import { player, STEM_COLORS } from '../lib/player.svelte';
  import { view } from '../lib/view.svelte';
  import { PEAKS_PER_SEC } from '../lib/stems';

  let { i, h: H }: { i: number; h: number } = $props();
  let canvas: HTMLCanvasElement;
  const peaks = $derived(player.stems[i].peaks);
  const color = $derived(STEM_COLORS[player.stems[i].name] ?? '#8ea4a7');

  // Solo se dibuja la parte visible: con zoom alto el tema entero no cabe en un canvas.
  $effect(() => {
    const w = Math.max(1, Math.floor(view.viewW));
    const pps = view.pps, scroll = view.scroll;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = w * dpr; canvas.height = H * dpr;
    const g = canvas.getContext('2d')!;
    g.scale(dpr, dpr);
    g.fillStyle = color;
    const perPx = PEAKS_PER_SEC / pps; // picos por píxel
    for (let x = 0; x < w; x++) {
      const k0 = Math.floor((scroll + x) * perPx), k1 = Math.max(k0 + 1, Math.ceil((scroll + x + 1) * perPx));
      if (k0 >= peaks.length) break;
      let m = 0;
      for (let k = k0; k < Math.min(peaks.length, k1); k++) if (peaks[k] > m) m = peaks[k];
      const bh = Math.max(1, (m / 255) * (H - 8));
      g.fillRect(x, (H - bh) / 2, 1, bh);
    }
  });
</script>

<canvas bind:this={canvas} style="width:{view.viewW}px;height:{H}px" aria-hidden="true"></canvas>

<style>
  canvas { display: block; }
</style>
