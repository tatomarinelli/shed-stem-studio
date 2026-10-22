<script lang="ts">
  import { providers, type ProviderStatus } from '../lib/providers.svelte';
  import { music } from '../lib/music.svelte';

  let { p }: { p: ProviderStatus } = $props();
  let clientId = $state('');
  let clientSecret = $state('');
  let editing = $state(false);
  let copied = $state(false);
  let headers = $state('');
  let askInstall = $state(false);

  const spotify = $derived(p.id === 'spotify');
  const waiting = $derived(providers.waiting === p.id);
  const busy = $derived(providers.busy === p.id);
  const stat = $derived(music.status?.providers?.[p.id]);
  const when = (t?: number | null) => (t ? new Date(t * 1000).toLocaleString('es-AR', { dateStyle: 'short', timeStyle: 'short' }) : '');
  const prot = $derived({ dpapi: 'Sesión cifrada con Windows.', keyring: 'Sesión en el llavero del sistema.', 'file-600': 'Sesión en un archivo solo legible por tu usuario (sin llavero, no está cifrada).' }[p.protection ?? 'file-600']);
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

<section class="card" data-provider={p.id}>
  <header>
    <div>
      <h3>{p.label}</h3>
      <span class="state" class:ok={p.connected} role="status">{p.connected ? 'conectado' : waiting ? 'esperando autorización' : p.configured ? 'listo para conectar' : 'sin conectar'}</span>
    </div>
    {#if p.connected}<button class="ghost" disabled={busy} onclick={disconnect}>Desconectar</button>{/if}
  </header>

  {#if p.connected}
    <dl>
      {#if spotify}<dt>Álbumes guardados</dt><dd class="num">{stat?.albums ?? 0}</dd>{/if}
      <dt>Temas guardados</dt><dd class="num">{stat?.tracks ?? 0}</dd>
    </dl>
    {#if stat?.error}<p class="err" role="alert">{stat.error}</p>{/if}
    <footer>
      <span class="muted">{stat?.refreshing ? 'Actualizando…' : stat?.fetchedAt ? `Actualizado ${when(stat.fetchedAt)}` : ''}</span>
      <button class="ghost" onclick={() => music.refresh()} disabled={stat?.refreshing}>Actualizar</button>
    </footer>
    {#if un?.connected}<p class="muted small">Biblioteca completa por ytmusicapi (no oficial). Si deja de actualizar, pegá los encabezados de nuevo. <button class="ghost link" onclick={() => providers.ytAction('headers/clear')}>Quitar</button></p>{/if}
    <p class="muted small">{prot} Solo lectura: no escribimos en tu cuenta. Desconectar borra la sesión y la copia de tu biblioteca en esta computadora; para revocar el permiso, hacelo desde tu cuenta de {p.label}.</p>
  {:else}
    <p class="muted">{spotify ? 'Trae tus álbumes y temas guardados.' : 'Trae tus playlists y los temas con “Me gusta”.'} Solo lectura. {p.note}</p>
    {#if un}
      <div class="unof">
        <b>Biblioteca completa (recomendado)</b>
        <p class="muted small">Con tu sesión de music.youtube.com trae álbumes guardados, temas y playlists. Usa <b>ytmusicapi</b>, una librería no oficial: puede dejar de andar si YouTube cambia algo. Solo lectura.</p>
        {#if !un.installed}
          {#if installing}<p class="muted" role="status">Instalando ytmusicapi…</p>
          {:else if askInstall}
            <div class="ask" role="group" aria-label="Confirmar">
              <p>Va a instalar <b>ytmusicapi</b> con pip en una carpeta propia de la app (unos pocos MB, desde PyPI). No toca nada más.</p>
              <div class="row"><button class="primary" onclick={install}>Instalar</button><button class="ghost" onclick={() => (askInstall = false)}>Cancelar</button></div>
            </div>
          {:else}<button class="primary" onclick={() => (askInstall = true)}>Instalar ytmusicapi…</button>{/if}
          {#if un.install.state === 'error'}<p class="err" role="alert">{un.install.error}</p>{/if}
        {:else}
          <ol class="mini">
            <li>Abrí <a href="https://music.youtube.com" target="_blank" rel="noopener noreferrer">music.youtube.com</a> con tu cuenta y las herramientas del navegador (F12) → pestaña <i>Red</i>.</li>
            <li>Escribí <i>browse</i> en el filtro, tocá cualquier sección de YouTube Music y buscá una petición <i>POST</i> a <code>/youtubei/v1/browse</code>.</li>
            <li>Copiá los encabezados de esa petición. Firefox: clic derecho → <i>Copiar valor</i> → <i>Copiar encabezados de la petición</i>. Chrome o Edge: en <i>Encabezados</i>, seleccioná todo <i>Request Headers</i> y copialo. Pegalos acá:</li>
          </ol>
          <textarea bind:value={headers} rows="4" placeholder="Host: music.youtube.com&#10;Cookie: …&#10;Authorization: SAPISIDHASH …" aria-label="Encabezados de la petición" spellcheck="false" autocomplete="off"></textarea>
          <div class="row"><button class="primary" disabled={!headers.trim() || busy} onclick={saveHeaders}>{busy ? 'Probando…' : 'Conectar'}</button>
            <span class="muted small">Se prueba leyendo tu biblioteca y se guarda cifrado. Se hace una sola vez.</span></div>
        {/if}
      </div>
      <details class="off-api"><summary>Alternativa oficial (Google Cloud): solo playlists y “Me gusta”</summary>
        {@render stepsList()}
      </details>
    {:else}
      {@render stepsList()}
    {/if}
  {/if}
  {#if providers.messages[p.id]}<p class="err" role="alert">{providers.messages[p.id]}</p>{/if}
</section>

{#snippet stepsList()}
    <ol class="steps">
      <li class:done={step === 3}>
        <div><b>Creá tu app en {spotify ? 'Spotify' : 'Google'}</b> <span class="muted">(una sola vez)</span></div>
        {#if step <= 2}
          <div class="how">
            {#if spotify}
              <p><a href="https://developer.spotify.com/dashboard" target="_blank" rel="noopener noreferrer">Abrir el panel de Spotify</a> → <i>Create app</i>. Poné el nombre que quieras, marcá <i>Web API</i> y pegá esta dirección en <i>Redirect URIs</i>:</p>
            {:else}
              <p>En Google Cloud: <a href="https://console.cloud.google.com/projectcreate" target="_blank" rel="noopener noreferrer">creá un proyecto</a>, <a href="https://console.cloud.google.com/apis/library/youtube.googleapis.com" target="_blank" rel="noopener noreferrer">activá la YouTube Data API v3</a>, configurá la <a href="https://console.cloud.google.com/apis/credentials/consent" target="_blank" rel="noopener noreferrer">pantalla de consentimiento</a> (tipo Externo, y agregá tu mail como usuario de prueba) y en <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noopener noreferrer">Credenciales</a> creá un <i>ID de cliente OAuth</i> de tipo <i>Aplicación de escritorio</i>.</p>
            {/if}
            <div class="copy">
              <input readonly value={p.redirectUri} aria-label="Dirección de redirección" onfocus={e => e.currentTarget.select()} />
              <button class="ghost" onclick={copy}>{copied ? 'Copiada' : 'Copiar'}</button>
            </div>
            {#if spotify}<p class="muted small">Si Spotify te deja la app en modo desarrollo, agregá tu mail en <i>User Management</i>. Hace falta Premium en la cuenta dueña de la app.</p>{/if}
          </div>
        {/if}
      </li>
      <li class:done={step === 3} class:off={step < 2}>
        <b>Pegá los datos de tu app</b>
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
        <b>Autorizá el acceso</b>
        {#if step === 3}
          <div class="row">
            {#if waiting}
              <span class="muted">Esperando que autorices en el navegador…</span>
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
  .card { background: var(--glass); backdrop-filter: blur(16px) saturate(1.3); border: 1px solid var(--glass-line); border-radius: var(--radius); padding: 16px; display: grid; gap: 12px; box-shadow: 0 20px 50px -24px rgba(0,0,0,0.7); animation: rise 0.45s var(--ease) both; }
  header, footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  h3 { margin: 0; font-size: 20px; }
  .state { font-size: 12.5px; color: var(--muted); }
  .state.ok { color: #7cc7a3; }
  p { margin: 0; font-size: 13.5px; }
  .small { font-size: 12.5px; }
  dl { display: grid; grid-template-columns: 1fr auto; gap: 6px 16px; margin: 0; }
  dt { color: var(--muted); } dd { margin: 0; font-weight: 600; text-align: right; }
  .steps { margin: 0; padding: 0; list-style: none; counter-reset: s; display: grid; gap: 10px; }
  .steps li { counter-increment: s; display: grid; gap: 6px; padding-left: 30px; position: relative; }
  .steps li::before { content: counter(s); position: absolute; left: 0; top: 0; width: 20px; height: 20px; border-radius: 50%; border: 1px solid var(--muted); display: grid; place-items: center; font-size: 12px; }
  .steps li.done::before { content: '✓'; color: #7cc7a3; border-color: #7cc7a3; }
  .steps li.off { opacity: 0.5; }
  .unof { display: grid; gap: 8px; padding: 10px 12px; border-radius: 10px; background: rgba(255,255,255,0.04); }
  .unof textarea { font: inherit; font-size: 12px; padding: 6px 8px; border-radius: 8px; border: 1px solid var(--line, #3a332d); background: transparent; color: inherit; resize: vertical; min-width: 0; }
  .mini { margin: 0; padding-left: 18px; display: grid; gap: 4px; font-size: 13px; }
  .ask { display: grid; gap: 6px; padding: 8px 10px; border-radius: 8px; background: rgba(255,255,255,0.05); }
  .off-api summary { cursor: pointer; font-size: 13px; color: var(--muted); margin: 4px 0 8px; }
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
