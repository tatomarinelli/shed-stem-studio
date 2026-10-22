<script lang="ts">
  import { onMount } from 'svelte';
  import { settings, type DetectedServer } from '../lib/settings.svelte';
  import Progress from './Progress.svelte';
  import JobNote from './JobNote.svelte';

  onMount(() => { void settings.detectLlm(); });

  const det = $derived(settings.detected);
  const own = $derived(det?.own);
  const KIND: Record<string, string> = { ollama: 'Ollama', llamacpp: 'llama.cpp', openai: 'Compatible con OpenAI' };
  const size = (b: number) => (b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : `${Math.round(b / 1e6)} MB`);

  // Nada cambia sin confirmar: el clic abre un resumen de lo que va a pasar.
  let askUse = $state<DetectedServer | null>(null);
  let model = $state('');
  let askStart = $state(false);
  const chosen = $derived(det?.ggufs.find(g => g.path === model) ?? det?.ggufs[0] ?? null);
  const running = $derived(det?.servers ?? []);
  const loading = $derived(own?.job.state === 'running');
  const offline = $derived(!!det?.binaries.llamaServer && !own?.running && !loading);

  async function use() {
    if (!askUse) return;
    const s = askUse;
    askUse = null;
    await settings.useServer(s);
  }
  async function start() {
    if (!chosen) return;
    askStart = false;
    await settings.startLlamaCpp(chosen.path);
  }
</script>

<div class="det">
  <div class="top">
    <b>Servidor de modelos</b>
    <button class="ghost" disabled={settings.detecting} onclick={() => settings.detectLlm()}>{settings.detecting ? 'Buscando…' : 'Buscar de nuevo'}</button>
  </div>
  <p class="muted note">Solo para las recomendaciones: separar en instrumentos no usa modelos de lenguaje. Acá no se descarga nada.</p>
  {#if settings.detectError}<p class="warn" role="alert">{settings.detectError}</p>{/if}

  {#if det}
    <h5>Ya prendidos en tu equipo</h5>
    {#if running.length}
      <ul>
        {#each running as s (s.url)}
          <li>
            <div>
              <b>{KIND[s.kind]}</b> <code>{s.url.replace('http://', '')}</code>
              {#if s.own}<span class="tag">Prendido por la app</span>{/if}
              <span class="muted">{s.models.length ? `${s.models.length} ${s.models.length === 1 ? 'modelo' : 'modelos'}: ${s.models.slice(0, 3).join(', ')}${s.models.length > 3 ? '…' : ''}` : 'sin modelos'}</span>
            </div>
            <div class="act">
              {#if s.current}<span class="badge">En uso</span>
              {:else}<button onclick={() => (askUse = s)}>Usar este</button>{/if}
              {#if s.own && s.kind === 'llamacpp'}<button class="ghost" onclick={() => settings.stopLlamaCpp()}>Apagar</button>{/if}
            </div>
            {#if askUse?.url === s.url}
              <div class="ask" role="group" aria-label="Confirmar">
                <p>Las recomendaciones van a usar {KIND[s.kind]} en {s.url.replace('http://', '')}.
                  {s.kind === 'ollama' ? 'Las descargas de modelos desde Ajustes van a esa instalación, en la carpeta que ella use.' : 'Este servidor no baja modelos desde acá: usa el que tiene cargado.'}</p>
                <button class="primary" onclick={use}>Usar</button><button class="ghost" onclick={() => (askUse = null)}>Cancelar</button>
              </div>
            {/if}
          </li>
        {/each}
      </ul>
    {:else}<p class="muted">No encontré ninguno prendido.</p>{/if}

    {#if loading && own}
      <h5>Prendiendo llama-server</h5>
      <Progress job={own.job} verb="Cargando" oncancel={() => settings.stopLlamaCpp()} />
    {:else if own?.job.state === 'error' || own?.job.state === 'cancelled'}
      <JobNote job={own.job} />
    {/if}

    {#if offline || det.ggufs.length}
      <h5>Instalado, sin prender</h5>
      {#if det.binaries.llamaServer && det.ggufs.length}
        <div class="llama">
          <div><b>llama.cpp</b> <code title={det.binaries.llamaServer}>llama-server</code> <span class="muted">{det.ggufs.length} {det.ggufs.length === 1 ? 'modelo' : 'modelos'} .gguf</span></div>
          <label>Modelo
            <select value={chosen?.path ?? ''} onchange={e => (model = e.currentTarget.value)} disabled={loading || !!own?.running}>
              {#each det.ggufs as g (g.path)}<option value={g.path}>{g.name} · {size(g.bytes)}</option>{/each}
            </select>
          </label>
          <button disabled={loading || !!own?.running} onclick={() => (askStart = true)}>Prender…</button>
          {#if askStart && chosen}
            <div class="ask" role="group" aria-label="Confirmar">
              <p>Va a correr <code>llama-server</code> con <b>{chosen.name}</b> ({size(chosen.bytes)}) en 127.0.0.1, solo en esta computadora, y después lo usa para las recomendaciones.
                Se queda con la memoria de la placa hasta que lo apagues (Ollama la libera solo), así que no conviene separar mientras tanto en una placa chica. No descarga nada.</p>
              <button class="primary" onclick={start}>Prender y usar</button><button class="ghost" onclick={() => (askStart = false)}>Cancelar</button>
            </div>
          {/if}
        </div>
      {:else if det.binaries.llamaServer}
        <p class="muted">llama-server está instalado pero no encontré modelos .gguf en las carpetas habituales.</p>
      {:else}
        <p class="muted">Encontré {det.ggufs.length} {det.ggufs.length === 1 ? 'modelo' : 'modelos'} .gguf, pero falta llama-server (llama.cpp) para usarlos.</p>
      {/if}
    {/if}

    {#if det.binaries.ollama && !running.some(s => s.kind === 'ollama')}
      <p class="muted">Ollama está instalado pero apagado. El motor lo prende solo en su propio puerto al arrancar.</p>
    {/if}
    {#each det.ollamaFolders as f (f.path)}
      <p class="muted">Modelos de Ollama en <code>{f.path}</code>: {f.models}.</p>
    {/each}
  {/if}
</div>

<style>
  .det { display: grid; gap: 6px; margin: 6px 0 12px; }
  .top { display: flex; gap: 10px; align-items: center; justify-content: space-between; }
  h5 { margin: 8px 0 0; font-size: 0.82rem; opacity: 0.8; font-weight: 600; }
  .note { margin: 0; font-size: 0.82rem; }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
  li { display: grid; gap: 6px; padding: 8px 10px; border: 1px solid var(--line, #3a332d); border-radius: 8px; }
  .act { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .tag, .badge { font-size: 0.75em; padding: 1px 6px; border-radius: 10px; border: 1px solid currentColor; }
  .ask { display: grid; gap: 6px; padding: 8px 10px; border-radius: 8px; background: rgba(255, 255, 255, 0.05); }
  .ask p { margin: 0; font-size: 0.88rem; }
  .ask button { justify-self: start; }
  .llama { display: grid; gap: 6px; padding: 8px 10px; border: 1px solid var(--line, #3a332d); border-radius: 8px; }
  .llama label { display: grid; gap: 2px; font-size: 0.85rem; }
  .llama select { max-width: 100%; }
  .llama > button { justify-self: start; }
  p { margin: 0; }
</style>
