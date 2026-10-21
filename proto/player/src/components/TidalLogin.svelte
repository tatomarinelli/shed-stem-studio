<script lang="ts">
  import { tidal } from '../lib/tidal.svelte';

  const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;

  let copied = $state(false);
  async function copy() {
    try { await navigator.clipboard.writeText(tidal.loginUrl); copied = true; window.setTimeout(() => (copied = false), 2000); } catch { /* queda el campo para copiar a mano */ }
  }
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
<div class="link">
  <span class="muted">Si no se abre:</span>
  <input readonly value={tidal.loginUrl} aria-label="Enlace de TIDAL" onfocus={e => e.currentTarget.select()} />
  <button onclick={copy}>{copied ? 'Copiado' : 'Copiar'}</button>
</div>

<style>
  p { margin: 0; }
  .code { font-size: 38px; font-weight: 700; letter-spacing: 0.12em; }
  .left { font-size: 13.5px; }
  .notice { color: #7cc7a3; font-size: 13.5px; }
  .row { display: flex; gap: 8px; flex-wrap: wrap; margin: 6px 0; }
  .link { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin: 4px 0; }
  .link input { flex: 1 1 18rem; min-width: 0; font: inherit; font-size: 13px; padding: 6px 8px; border-radius: 8px; border: 1px solid var(--line, #3a332d); background: transparent; color: inherit; }
  .ghost { background: transparent; }
  .btn { display: inline-block; padding: 7px 14px; border-radius: 9px; border: 1px solid var(--text); background: var(--text); color: var(--bg); font-weight: 600; text-decoration: none; }
</style>
