<script lang="ts">
  import { providers, type ProviderStatus } from '../lib/providers.svelte';
  import { music } from '../lib/music.svelte';
  import SourceBlock from './SourceBlock.svelte';

  let { p }: { p: ProviderStatus } = $props();
  let clientId = $state('');
  let clientSecret = $state('');
  let editing = $state(false);
  let copied = $state(false);
  let headers = $state('');
  let askInstall = $state(false);
  let method = $state<'own' | 'ext' | 'paste' | 'official'>('own');
  const methods = [
    { id: 'own', title: 'Ventana propia', hint: 'Recomendado · 1 clic', needsLib: true },
    { id: 'ext', title: 'Mi navegador', hint: 'Con extensión', needsLib: true },
    { id: 'paste', title: 'A mano', hint: 'Pegar encabezados', needsLib: true },
    { id: 'official', title: 'Oficial', hint: 'Google Cloud', needsLib: false }
  ] as const;

  const spotify = $derived(p.id === 'spotify');
  const waiting = $derived(providers.waiting === p.id);
  const busy = $derived(providers.busy === p.id);
  const stat = $derived(music.status?.providers?.[p.id]);
  const when = (t?: number | null) => (t ? new Date(t * 1000).toLocaleString('es-AR', { dateStyle: 'short', timeStyle: 'short' }) : '');
  const prot = $derived({ dpapi: 'cifrada con Windows', keyring: 'en el llavero', 'file-600': 'en un archivo privado, sin cifrar' }[p.protection ?? 'file-600']);
  // El paso activo es el primero que falta: 1 crear la app, 2 pegar los datos, 3 autorizar.
  const step = $derived(p.connected ? 4 : p.configured && !editing ? 3 : 2);
  const canSave = $derived(!!clientId.trim() && (!p.needsSecret || !!clientSecret.trim()) && !busy);

  async function copy() {
    try { await navigator.clipboard.writeText(p.redirectUri); copied = true; window.setTimeout(() => (copied = false), 1800); } catch { /* sin portapapeles: queda seleccionada para copiar a mano */ }
  }
  async function save() {
    if (await providers.saveApp(p.id, clientId, clientSecret)) { clientId = clientSecret = ''; editing = false; }
  }
  const un = $derived(p.unofficial);
  const installing = $derived(un?.install.state === 'running');
  async function install() { askInstall = false; await providers.ytAction('install'); }
  async function saveHeaders() { if (await providers.ytAction('headers', { headers })) { headers = ''; await music.refresh(); } }
  async function disconnect() {
    await providers.logout(p.id);
    await music.loadStatus();
  }
</script>

<SourceBlock id={p.id} title={p.label} ok={p.connected} status={p.connected ? 'conectado' : waiting ? 'esperando…' : p.configured ? 'listo para conectar' : 'sin conectar'}>
  <div data-provider={p.id} class="wiz">
  {#if p.connected}
    <dl>
      {#if spotify || un?.connected}<dt>Álbumes</dt><dd class="num">{stat?.albums ?? 0}</dd>{/if}
      <dt>Temas</dt><dd class="num">{stat?.tracks ?? 0}</dd>
    </dl>
    {#if stat?.error}<p class="err" role="alert">{stat.error}</p>{/if}
    <footer>
      <span class="muted small">{stat?.refreshing ? 'Actualizando…' : stat?.fetchedAt ? `Actualizado ${when(stat.fetchedAt)}` : ''}</span>
      <span class="row">
        <button class="ghost" onclick={() => music.refresh()} disabled={stat?.refreshing}>Actualizar</button>
        <button class="ghost" disabled={busy} onclick={disconnect}>Desconectar</button>
      </span>
    </footer>
    <p class="muted small">Solo lectura · {prot}{un?.connected ? ' · Si deja de actualizar, volvé a conectar' : ''}</p>
  {:else if un}
    {#if !un.installed}
      <div class="need">
        <span>Falta <b>ytmusicapi</b> <span class="muted">(~1 MB, pip, carpeta de la app)</span></span>
        {#if installing}<span class="muted" role="status">Instalando…</span>
        {:else if askInstall}<span class="row"><button class="primary" onclick={install}>Instalar</button><button class="ghost" onclick={() => (askInstall = false)}>Cancelar</button></span>
        {:else}<button class="primary" onclick={() => (askInstall = true)}>Instalar</button>{/if}
      </div>
      {#if un.install.state === 'error'}<p class="err" role="alert">{un.install.error}</p>{/if}
    {/if}

    <div class="methods" role="radiogroup" aria-label="Cómo conectar">
      {#each methods as m (m.id)}
        <button role="radio" aria-checked={method === m.id} class:on={method === m.id} class:dis={m.needsLib && !un.installed} onclick={() => (method = m.id)}>
          <b>{m.title}</b><span class="muted">{m.hint}</span>
        </button>
      {/each}
    </div>

    {#if method === 'own'}
      <div class="how">
        <p>{un.browser ? `Abre ${un.browser} aparte: iniciás sesión y entrás a Biblioteca.` : 'No encontré Chromium, Chrome, Edge ni Brave.'}</p>
        {@render pairRow(true, !un.installed || !un.browser)}
      </div>
    {:else if method === 'ext'}
      <div class="how">
        <p>1. <a href="/engine/ytmusic-extension.zip" download>Bajar extensión</a> y cargarla (modo desarrollador).<br />2. Conectar y entrar a Biblioteca.</p>
        {@render pairRow(false, !un.installed)}
      </div>
    {:else if method === 'paste'}
      <div class="how">
        <p>En <a href="https://music.youtube.com" target="_blank" rel="noopener noreferrer">music.youtube.com</a>: F12 → Red → filtrá <code>browse</code> → petición POST → copiá los <i>Request Headers</i>.</p>
        <textarea bind:value={headers} rows="3" placeholder="Host: music.youtube.com&#10;Cookie: …&#10;Authorization: SAPISIDHASH …" aria-label="Encabezados de la petición" spellcheck="false" autocomplete="off"></textarea>
        <div class="row"><button class="primary" disabled={!headers.trim() || busy || !un.installed} onclick={saveHeaders}>{busy ? 'Probando…' : 'Conectar'}</button></div>
      </div>
    {:else}
      <p class="muted small">Solo playlists y “Me gusta”, sin álbumes.</p>
      {@render stepsList()}
    {/if}
  {:else}
    <p class="muted small">Álbumes y temas guardados · solo lectura · sin audio</p>
    {@render stepsList()}
  {/if}
  {#if providers.messages[p.id]}<p class="err" role="alert">{providers.messages[p.id]}</p>{/if}
  </div>
</SourceBlock>

{#snippet pairRow(launch: boolean, disabled: boolean)}
  <div class="row">
    {#if waiting}
      <span class="spin" aria-hidden="true"></span>
      <span class="muted" role="status">Esperando la sesión… {launch ? 'iniciá sesión y entrá a Biblioteca' : 'entrá a Biblioteca'}</span>
      <button class="ghost" onclick={() => providers.cancelPairYt()}>Cancelar</button>
    {:else}
      <button class="primary" disabled={busy || disabled} onclick={() => providers.pairYt(launch)}>Conectar</button>
    {/if}
  </div>
{/snippet}

{#snippet stepsList()}
    <ol class="steps">
      <li class:done={step === 3}>
        <div><b>Creá tu app</b> <span class="muted">(una vez)</span></div>
        {#if step <= 2}
          <div class="how">
            {#if spotify}
              <p><a href="https://developer.spotify.com/dashboard" target="_blank" rel="noopener noreferrer">Panel de Spotify</a> → <i>Create app</i> → <i>Web API</i>. Pegá esta dirección en <i>Redirect URIs</i>:</p>
            {:else}
              <p>Google Cloud: <a href="https://console.cloud.google.com/projectcreate" target="_blank" rel="noopener noreferrer">proyecto</a> → <a href="https://console.cloud.google.com/apis/library/youtube.googleapis.com" target="_blank" rel="noopener noreferrer">activar YouTube Data API</a> → <a href="https://console.cloud.google.com/apis/credentials/consent" target="_blank" rel="noopener noreferrer">consentimiento</a> (Externo, tu mail de prueba) → <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noopener noreferrer">credencial</a> de escritorio. Redirección:</p>
            {/if}
            <div class="copy">
              <input readonly value={p.redirectUri} aria-label="Dirección de redirección" onfocus={e => e.currentTarget.select()} />
              <button class="ghost" onclick={copy}>{copied ? 'Copiada' : 'Copiar'}</button>
            </div>
            {#if spotify}<p class="muted small">Modo desarrollo: sumá tu mail en <i>User Management</i> (la cuenta dueña necesita Premium).</p>{/if}
          </div>
        {/if}
      </li>
      <li class:done={step === 3} class:off={step < 2}>
        <b>Pegá los datos</b>
        {#if step === 2}
          <div class="form">
            <input bind:value={clientId} placeholder="Client ID" aria-label="Client ID de {p.label}" autocomplete="off" spellcheck="false" />
            {#if p.needsSecret}<input bind:value={clientSecret} type="password" placeholder="Client Secret" aria-label="Client Secret de {p.label}" autocomplete="off" />{/if}
            <div class="row">
              <button class="primary" disabled={!canSave} onclick={save}>Guardar</button>
              {#if editing}<button class="ghost" onclick={() => (editing = false)}>Cancelar</button>{/if}
            </div>
          </div>
        {:else if step === 3}<button class="ghost link" onclick={() => (editing = true)}>Cambiar Client ID</button>{/if}
      </li>
      <li class:off={step < 3}>
        <b>Autorizá</b>
        {#if step === 3}
          <div class="row">
            {#if waiting}
              <span class="muted">Esperando que autorices…</span>
              <button class="ghost" onclick={() => providers.cancelWait()}>Cancelar</button>
            {:else}
              <button class="primary" disabled={busy} onclick={() => providers.connect(p.id)}>Conectar {p.label}</button>
            {/if}
          </div>
        {/if}
      </li>
    </ol>
{/snippet}

<style>
  .wiz { display: grid; gap: 12px; }
  footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  p { margin: 0; font-size: 13.5px; }
  .small { font-size: 12.5px; }
  dl { display: grid; grid-template-columns: 1fr auto; gap: 6px 16px; margin: 0; }
  dt { color: var(--muted); } dd { margin: 0; font-weight: 600; text-align: right; }
  .steps { margin: 0; padding: 0; list-style: none; counter-reset: s; display: grid; gap: 10px; }
  .steps li { counter-increment: s; display: grid; gap: 6px; padding-left: 30px; position: relative; }
  .steps li::before { content: counter(s); position: absolute; left: 0; top: 0; width: 20px; height: 20px; border-radius: 50%; border: 1px solid var(--muted); display: grid; place-items: center; font-size: 12px; }
  .steps li.done::before { content: '✓'; color: #7cc7a3; border-color: #7cc7a3; }
  .steps li.off { opacity: 0.5; }
  .methods { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 8px; }
  .methods button { display: grid; gap: 2px; text-align: left; padding: 8px 10px; border-radius: 10px; background: rgba(255,255,255,0.04); border: 1px solid transparent; font-size: 13px; }
  .methods button.on { border-color: var(--text); background: rgba(255,255,255,0.09); }
  .methods button.dis { opacity: 0.55; }
  .methods .muted { font-size: 11.5px; }
  .need { display: flex; gap: 10px; align-items: center; justify-content: space-between; flex-wrap: wrap; padding: 8px 10px; border-radius: 10px; background: rgba(255,255,255,0.06); font-size: 13px; }
  .spin { width: 14px; height: 14px; border-radius: 50%; border: 2px solid var(--muted); border-top-color: var(--text); animation: spin 0.9s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .how textarea { font: inherit; font-size: 12px; padding: 6px 8px; border-radius: 8px; border: 1px solid var(--line, #3a332d); background: transparent; color: inherit; resize: vertical; min-width: 0; }
  .how { display: grid; gap: 8px; }
  .how a { color: var(--text); }
  .copy { display: flex; gap: 8px; }
  .copy input, .form input { font: inherit; font-size: 13px; padding: 6px 8px; border-radius: 8px; border: 1px solid var(--line, #3a332d); background: transparent; color: inherit; min-width: 0; flex: 1; }
  .form { display: grid; gap: 6px; }
  .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .err { color: var(--loop); }
  .ghost { background: transparent; }
  .link { justify-self: start; padding: 0 4px; font-size: 13px; }
  .primary { background: var(--text); color: var(--bg); border-color: var(--text); font-weight: 600; }
</style>
