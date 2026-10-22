<script lang="ts">
  import { untrack } from 'svelte';
  import { tidal } from '../lib/tidal.svelte';
  import { library } from '../lib/library.svelte';
  import { settings } from '../lib/settings.svelte';
  import { music } from '../lib/music.svelte';
  import { toast } from '../lib/toast.svelte';
  import { providers } from '../lib/providers.svelte';
  import ProviderWizard from '../components/ProviderWizard.svelte';
  import SourceBlock from '../components/SourceBlock.svelte';
  import TidalLogin from '../components/TidalLogin.svelte';
  import FolderPicker from '../components/FolderPicker.svelte';

  let picking = $state(false);

  // untrack: connect() lee y escribe tidal.state; sin esto el efecto se reejecuta con cada cambio de estado.
  $effect(() => untrack(() => { library.load(); settings.load(); music.loadStatus(); tidal.connect(); providers.load(); }));

  const folders = $derived(settings.effective?.musicFolders ?? library.folders);
  const scanning = $derived(library.scanning || !!music.status?.local.scanning);
  const when = (t?: number) => (t ? new Date(t * 1000).toLocaleString('es-AR', { dateStyle: 'short', timeStyle: 'short' }) : '');

  async function add(path: string) {
    const ok = await settings.save({ musicFolders: [...(settings.config?.musicFolders ?? []), path] });
    if (!ok) { toast.show(settings.saveMessage?.text ?? 'No se pudo guardar.', 'warn'); return; }
    await library.rescan(); music.loadStatus();
  }
  async function remove(f: string) {
    const ok = await settings.save({ musicFolders: (settings.config?.musicFolders ?? []).filter(x => x !== f) });
    if (ok) { await library.rescan(); music.loadStatus(); }
  }
  async function rescan() { await library.rescan(); await music.refresh(); }
</script>

<h2>Fuentes</h2>

<div class="cards">
  <SourceBlock id="local" title="Archivos locales" ok={folders.length > 0} status={folders.length ? `${folders.length} ${folders.length === 1 ? 'carpeta' : 'carpetas'}` : 'sin carpetas'}>
    <div class="actions"><button onclick={() => (picking = true)}>Agregar carpeta</button></div>
    <ul class="paths">
      {#each folders as f (f)}
        <li><span class="path">{f}</span><button class="ghost" onclick={() => remove(f)} aria-label="Quitar {f}">Quitar</button></li>
      {:else}
        <li class="muted">Agregá la carpeta donde tenés tu música.</li>
      {/each}
    </ul>
    {#if settings.saveMessage && !settings.saveMessage.ok}<p class="err" role="alert">{settings.saveMessage.text}</p>{/if}
    <footer>
      <span class="muted num">
        {#if scanning}Leyendo {library.scanned || music.status?.local.scanned || 0} de {library.total || music.status?.local.total || 0}…
        {:else if folders.length}{library.total || music.sources.local} archivos{/if}
      </span>
      {#if folders.length}<button class="ghost" onclick={rescan} disabled={scanning}>Volver a leer</button>{/if}
    </footer>
  </SourceBlock>

  <SourceBlock id="tidal" title="TIDAL" ok={tidal.state === 'ready'} status={tidal.label}>
    {#if tidal.state === 'ready'}<div class="actions"><button class="ghost" onclick={() => tidal.logout()}>Desconectar</button></div>{/if}

    {#if tidal.state === 'idle' || tidal.state === 'connecting'}
      <p class="muted">Conectando…</p>
    {:else if tidal.state === 'logging_in'}
      <TidalLogin />
    {:else if tidal.state === 'no_engine'}
      <p>{tidal.message}</p>
      <div class="row"><button class="primary" onclick={() => { tidal.state = 'idle'; tidal.connect(); }}>Reintentar</button></div>
    {:else if tidal.state !== 'ready'}
      <p class="muted">{tidal.message || 'Conectá tu cuenta para ver tus favoritos y playlists en Música.'}</p>
      <div class="row"><button class="primary" onclick={() => tidal.login()}>Conectar TIDAL</button></div>
    {:else}
      <dl>
        <dt>Álbumes favoritos</dt><dd class="num">{music.status?.tidal.albums ?? tidal.library?.albums.length ?? 0}</dd>
        <dt>Temas favoritos</dt><dd class="num">{music.status?.tidal.tracks ?? tidal.library?.tracks.length ?? 0}</dd>
        <dt>Playlists</dt><dd class="num">{tidal.library?.playlists.length ?? 0}</dd>
      </dl>
      {#if music.status?.tidal.error}<p class="err" role="alert">{music.status.tidal.error}</p>{/if}
      <footer>
        <span class="muted">{music.status?.tidal.refreshing ? 'Actualizando…' : music.status?.tidal.fetchedAt ? `Actualizado ${when(music.status.tidal.fetchedAt)}` : ''}</span>
        <button class="ghost" onclick={() => music.refresh()} disabled={music.status?.tidal.refreshing}>Actualizar</button>
      </footer>
    {/if}
  </SourceBlock>

  {#each providers.accounts as p (p.id)}<ProviderWizard {p} />{/each}
</div>

<p class="muted foot">Tu música aparece en <a href="#/musica">Música</a>.</p>

{#if picking}
  <FolderPicker start={folders.at(-1) ?? '/'} title="Elegí una carpeta de música" onpick={add} onclose={() => (picking = false)} />
{/if}

<style>
  h2 { margin: 0; font-size: 28px; letter-spacing: -0.02em; }
  .cards { display: grid; gap: 12px; max-width: 760px; }
  .actions { display: flex; justify-content: flex-end; }
  footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  p { margin: 0; }
  .paths { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; }
  .paths li { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 6px 10px; border-radius: 10px; background: rgba(255,255,255,0.04); }
  .path { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 14px; }
  .ghost { background: transparent; }
  dl { display: grid; grid-template-columns: 1fr auto; gap: 6px 16px; margin: 0; }
  dt { color: var(--muted); } dd { margin: 0; font-weight: 600; text-align: right; }
  .err { color: var(--loop); font-size: 13.5px; }
  .row { display: flex; gap: 8px; }
  .primary { background: var(--text); color: var(--bg); border-color: var(--text); font-weight: 600; }
  .foot { margin: 0; font-size: 14px; }
  .foot a { color: var(--text); }
</style>
