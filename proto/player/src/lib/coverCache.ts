// Portadas precargadas en memoria: al salir y volver a una pantalla la imagen ya está en la caché del navegador y no vuelve a pedir una conexión
// (el navegador permite pocas por servidor y el reproductor ocupa varias). Se guardan las últimas N para que no se liberen.
const kept = new Map<string, HTMLImageElement>();
const MAX = 80;

export function preloadCovers(urls: string[]) {
  if (typeof Image === 'undefined') return;
  for (const url of urls) {
    if (!url || kept.has(url)) continue;
    const img = new Image();
    img.decoding = 'async';
    img.src = url;
    kept.set(url, img);
    if (kept.size > MAX) kept.delete(kept.keys().next().value as string);
  }
}

/** Avisa al motor (solo local) cuando una portada falla o tarda: queda en <datos>/diag/covers.log para entender qué pasa en este navegador. */
export function reportCover(info: { src: string; kind: 'failed' | 'slow'; tries: number; ms: number }) {
  try {
    const conn = (performance.getEntriesByType('resource') as PerformanceResourceTiming[]).filter(e => e.responseEnd === 0).length; // pedidos todavía en curso
    const body = JSON.stringify({ ...info, online: navigator.onLine, visible: document.visibilityState === 'visible', connections: conn, screen: location.hash });
    navigator.sendBeacon?.('/engine/diag/cover', new Blob([body], { type: 'application/json' }));
  } catch { /* el diagnóstico nunca rompe la pantalla */ }
}
