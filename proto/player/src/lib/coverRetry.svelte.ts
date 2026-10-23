// Las portadas que fallaron se reintentan solas cuando vuelve la red o la ventana (p. ej. tras tocar la notificación de medios).
class CoverRetry { epoch = $state(0); }
export const coverRetry = new CoverRetry();

if (typeof window !== 'undefined') {
  let timer = 0;
  const bump = () => { window.clearTimeout(timer); timer = window.setTimeout(() => { coverRetry.epoch += 1; }, 500); };
  window.addEventListener('online', bump);
  window.addEventListener('focus', bump);
  window.addEventListener('pageshow', bump);
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') bump(); });
}
