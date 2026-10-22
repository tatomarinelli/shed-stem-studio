<script lang="ts">
  import { providers, type ProviderStatus } from '../lib/providers.svelte';

  let { p }: { p: ProviderStatus } = $props();
  let clientId = $state('');
  let clientSecret = $state('');
  let editing = $state(false);

  const label = $derived(p.connected ? 'conectado' : providers.waiting === p.id ? 'esperando autorización' : p.configured ? 'sin conectar' : 'falta configurar');
  const showForm = $derived(!p.configured || editing);
  const prot = $derived({ dpapi: 'Sesión cifrada con Windows.', keyring: 'Sesión en el llavero del sistema.', 'file-600': 'Sesión en un archivo solo legible por tu usuario (sin llavero, no está cifrada).' }[p.protection ?? 'file-600']);

  async function save() {
    if (await providers.saveApp(p.id, clientId, clientSecret)) { clientId = clientSecret = ''; editing = false; }
  }
</script>

<li class="prov" data-provider={p.id}>
  <div class="head">
    <b>{p.label}</b>
    <span class={p.connected ? 'ok' : 'muted'} role="status">{label}</span>
    <span class="grow"></span>
    {#if p.connected}
      <button class="ghost" disabled={providers.busy === p.id} onclick={() => providers.logout(p.id)}>Desconectar</button>
    {:else if providers.waiting === p.id}
      <button class="ghost" onclick={() => providers.cancelWait()}>Cancelar</button>
    {:else if p.configured}
      <button class="primary" disabled={providers.busy === p.id} onclick={() => providers.connect(p.id)}>Conectar</button>
    {/if}
  </div>
  <p class="muted">{p.note}</p>
  {#if p.connected}<p class="muted">{prot} Desconectar solo borra la sesión de esta computadora; para revocar el permiso, hacelo desde tu cuenta de {p.label}.</p>{/if}

  {#if showForm && !p.connected}
    <div class="form">
      <p>Creá tu propia app en {p.id === 'spotify' ? 'developer.spotify.com' : 'Google Cloud (cliente de escritorio, con la YouTube Data API activada)'} y registrá esta dirección de redirección:</p>
      <input readonly value={p.redirectUri} aria-label="Dirección de redirección" onfocus={e => e.currentTarget.select()} />
      <input bind:value={clientId} placeholder="Client ID" aria-label="Client ID de {p.label}" autocomplete="off" spellcheck="false" />
      {#if p.needsSecret}<input bind:value={clientSecret} type="password" placeholder="Client Secret" aria-label="Client Secret de {p.label}" autocomplete="off" />{/if}
      <div class="row">
        <button class="primary" disabled={!clientId.trim() || (p.needsSecret && !clientSecret.trim()) || providers.busy === p.id} onclick={save}>Guardar</button>
        {#if editing}<button class="ghost" onclick={() => (editing = false)}>Cancelar</button>{/if}
      </div>
    </div>
  {:else if p.configured && !p.connected}
    <button class="ghost link" onclick={() => (editing = true)}>Cambiar Client ID</button>
  {/if}
  {#if providers.messages[p.id]}<p class="err" role="alert">{providers.messages[p.id]}</p>{/if}
</li>

<style>
  .prov { list-style: none; display: grid; gap: 6px; padding: 10px 12px; border-radius: 12px; background: rgba(255,255,255,0.04); }
  .head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .grow { flex: 1; }
  p { margin: 0; font-size: 13.5px; }
  .form { display: grid; gap: 6px; }
  .form input { font: inherit; font-size: 13px; padding: 6px 8px; border-radius: 8px; border: 1px solid var(--line, #3a332d); background: transparent; color: inherit; min-width: 0; }
  .row { display: flex; gap: 8px; }
  .ok { color: #7cc7a3; }
  .err { color: var(--loop); }
  .ghost { background: transparent; }
  .link { justify-self: start; padding: 0 4px; font-size: 13px; }
  .primary { background: var(--text); color: var(--bg); border-color: var(--text); font-weight: 600; }
</style>
