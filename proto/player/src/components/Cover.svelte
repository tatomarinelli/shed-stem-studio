<script lang="ts">
  import { untrack } from 'svelte';
  import { coverRetry } from '../lib/coverRetry.svelte';
  import { reportCover } from '../lib/coverCache';
  // Portada generada a partir del título: no se descarga ninguna imagen.
  let { title, artist = '', size = 64, radius = 10, src, eager = false, priority = false }: { title: string; artist?: string; size?: number; radius?: number; src?: string; eager?: boolean; priority?: boolean } = $props();
  const RETRY_MS = [1500, 5000, 20000, 45000];
  let failed = $state(false);
  let loaded = $state(false);
  // Un fallo suelto (red, motor ocupado) se reintenta con espera creciente (más larga que lo que el motor recuerda un fallo);
  // después queda la portada generada hasta que vuelva el foco o la red.
  let tries = $state(0);
  let timer = 0;
  let started = performance.now();
  let slowTimer = 0;
  let recoveries = $state(0); // cuántas veces se rescató por foco/red (tope: una 404 permanente no se pide en cada foco)
  $effect(() => {
    src; failed = false; loaded = false; tries = 0; recoveries = 0; window.clearTimeout(timer); started = performance.now();
    window.clearTimeout(slowTimer);
    // Si a los 6 s todavía no se vio, queda registrado (con cuántos pedidos había en curso) para entender por qué tarda.
    slowTimer = window.setTimeout(() => { if (src && !loaded && !failed) reportCover({ src, kind: 'slow', tries, ms: 6000 }); }, 6000);
    return () => { window.clearTimeout(timer); window.clearTimeout(slowTimer); };
  });
  // La imagen aparece cuando está lista, SIN depender del evento `load`: con la imagen en la caché del navegador y la pantalla montándose de nuevo (salir y volver
  // rápido) el evento se pierde y la portada quedaba cargada pero invisible para siempre (medido: 8 de 8 con opacity 0 y `complete` verdadero). Se mira `complete`,
  // se espera a `decode()` (se resuelve cuando está lista) y, de seguro, se vuelve a mirar unos segundos.
  let img = $state<HTMLImageElement>();
  $effect(() => {
    shown;
    const el = img;
    if (!el) return;
    let dead = false;
    const ready = () => el.complete && el.naturalWidth > 0;
    const show = () => { if (!dead && ready()) loaded = true; };
    show();
    el.decode?.().then(show, () => {});   // si no se puede decodificar, queda el error normal (reintento y portada generada)
    let n = 0;
    const poll = window.setInterval(() => { show(); if (dead || loaded || ++n >= 20) window.clearInterval(poll); }, 250);
    return () => { dead = true; window.clearInterval(poll); };
  });
  // Al volver la red o la ventana, una portada dada por perdida se vuelve a pedir.
  $effect(() => { coverRetry.epoch; untrack(() => { if (failed && recoveries < 2) { recoveries += 1; failed = false; loaded = false; tries = 0; } }); });
  // El número va en la URL: así el navegador no reutiliza el fallo guardado de un intento anterior.
  const shown = $derived(src && (tries || recoveries) ? `${src}${src.includes('?') ? '&' : '?'}r=${recoveries * 10 + tries}` : src);
  function broke() {
    if (tries >= RETRY_MS.length) { failed = true; if (src) reportCover({ src, kind: 'failed', tries, ms: Math.round(performance.now() - started) }); return; }
    timer = window.setTimeout(() => { tries += 1; }, RETRY_MS[tries]);
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
    <img bind:this={img} src={shown} alt="Portada de {title}" loading={eager ? 'eager' : 'lazy'} fetchpriority={priority ? 'high' : 'auto'} decoding="async" class:on={loaded} onload={() => (loaded = true)} onerror={broke} />
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
