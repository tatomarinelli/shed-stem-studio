<script lang="ts">
  import { tidal } from '../lib/tidal.svelte';

  const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
</script>

<p>Abrí el enlace, iniciá sesión y confirmá este código:</p>
<p class="code num" aria-label="Código de TIDAL">{tidal.loginCode}</p>
<p class="muted left num" role="timer">Vence en {mmss(tidal.loginLeft)}</p>
{#if tidal.loginNotice}<p class="notice" role="status">{tidal.loginNotice}</p>{/if}
<div class="row">
  <a class="btn" href={tidal.loginUrl} target="_blank" rel="noopener noreferrer">Abrir TIDAL</a>
  <button onclick={() => tidal.renew()}>Pedir otro código</button>
  <button class="ghost" onclick={() => tidal.cancelLogin()}>Cancelar</button>
</div>
<p class="muted">El enlace ya lleva el código. Se actualiza solo al autorizar.</p>

<style>
  p { margin: 0; }
  .code { font-size: 38px; font-weight: 700; letter-spacing: 0.12em; }
  .left { font-size: 13.5px; }
  .notice { color: #7cc7a3; font-size: 13.5px; }
  .row { display: flex; gap: 8px; flex-wrap: wrap; margin: 6px 0; }
  .ghost { background: transparent; }
  .btn { display: inline-block; padding: 7px 14px; border-radius: 9px; border: 1px solid var(--text); background: var(--text); color: var(--bg); font-weight: 600; text-decoration: none; }
</style>
