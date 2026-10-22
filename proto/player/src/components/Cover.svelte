<script lang="ts">
  // Portada generada a partir del título: no se descarga ninguna imagen.
  let { title, artist = '', size = 64, radius = 10, src }: { title: string; artist?: string; size?: number; radius?: number; src?: string } = $props();
  let failed = $state(false);
  let loaded = $state(false);
  // Un fallo suelto (red, motor ocupado) se reintenta dos veces con espera; después queda la portada generada.
  let tries = $state(0);
  let timer = 0;
  $effect(() => { src; failed = false; loaded = false; tries = 0; window.clearTimeout(timer); return () => window.clearTimeout(timer); });
  const shown = $derived(src && tries ? `${src}${src.includes('?') ? '&' : '?'}r=${tries}` : src);
  function broke() {
    if (tries >= 2) { failed = true; return; }
    timer = window.setTimeout(() => { tries += 1; }, 1500 * (tries + 1));
  }
  const hash = (s: string) => { let h = 2166136261; for (const c of s) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); } return h >>> 0; };
  const p = $derived.by(() => {
    const h = hash(title + '|' + artist);
    const hue = h % 360;
    return { hue, hue2: (hue + 40 + ((h >> 8) % 80)) % 360, cx: 20 + ((h >> 4) % 60), cy: 20 + ((h >> 12) % 60), r: 22 + ((h >> 16) % 26), rot: (h >> 20) % 180 };
  });
</script>

{#if src && !failed}
  <!-- Mientras la imagen real llega se ve la portada generada; después se funde con ella. -->
  <span class="cv" style="width:{size}px;height:{size}px;border-radius:{radius}px">
    <svg viewBox="0 0 100 100" width="100%" height="100%" aria-hidden="true">
      <defs><linearGradient id="h{p.hue}{p.cx}{p.cy}" x1="0" y1="0" x2="1" y2="1" gradientTransform="rotate({p.rot} .5 .5)"><stop offset="0" stop-color="hsl({p.hue} 55% 38%)" /><stop offset="1" stop-color="hsl({p.hue2} 60% 22%)" /></linearGradient></defs>
      <rect width="100" height="100" fill="url(#h{p.hue}{p.cx}{p.cy})" /><circle cx={p.cx} cy={p.cy} r={p.r} fill="hsl({p.hue2} 70% 62%)" opacity="0.55" />
    </svg>
    <img src={shown} alt="Portada de {title}" loading="lazy" decoding="async" class:on={loaded} onload={() => (loaded = true)} onerror={broke} />
  </span>
{:else}
<svg viewBox="0 0 100 100" width={size} height={size} style="border-radius:{radius}px;flex:none" role="img" aria-label="Portada de {title}">
  <defs>
    <linearGradient id="g{p.hue}{p.cx}{p.cy}" x1="0" y1="0" x2="1" y2="1" gradientTransform="rotate({p.rot} .5 .5)">
      <stop offset="0" stop-color="hsl({p.hue} 55% 38%)" /><stop offset="1" stop-color="hsl({p.hue2} 60% 22%)" />
    </linearGradient>
  </defs>
  <rect width="100" height="100" fill="url(#g{p.hue}{p.cx}{p.cy})" />
  <circle cx={p.cx} cy={p.cy} r={p.r} fill="hsl({p.hue2} 70% 62%)" opacity="0.55" />
  <circle cx={100 - p.cx} cy={100 - p.cy} r={p.r / 2} fill="hsl({p.hue} 80% 75%)" opacity="0.35" />
</svg>
{/if}

<style>
  .cv { position: relative; display: inline-block; flex: none; overflow: hidden; }
  .cv svg, .cv img { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
  .cv img { object-fit: cover; opacity: 0; transition: opacity 0.35s ease; }
  .cv img.on { opacity: 1; }
  @media (prefers-reduced-motion: reduce) { .cv img { transition: none; } }
</style>
