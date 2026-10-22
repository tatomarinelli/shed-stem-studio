<script lang="ts">
  import { onMount, type Snippet } from 'svelte';
  import { settings, type DetectedServer } from '../lib/settings.svelte';
  import Progress from './Progress.svelte';
  import JobNote from './JobNote.svelte';

  let { models }: { models?: Snippet } = $props();
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
    <span class="muted">Quién responde las recomendaciones</span>
    <button class="ghost" disabled={settings.detecting} onclick={() => settings.detectLlm()}>{settings.detecting ? 'Buscando…' : 'Buscar de nuevo'}</button>
  </div>
  {#if settings.detectError}<p class="warn" role="alert">{settings.detectError}</p>{/if}

  {#if det}
    <ul>
      {#each running as s (s.url)}
        <li>
          <div class="row">
            <div>
              <b>{KIND[s.kind]}</b> <code>{s.url.replace('http://', '')}</code>
              <span class="muted">{s.models.length ? `${s.models.length} ${s.models.length === 1 ? 'modelo' : 'modelos'}: ${s.models.slice(0, 3).join(', ')}${s.models.length > 3 ? '…' : ''}` : 'sin modelos'}</span>
            </div>
            <div class="act">
              {#if s.current}<span class="badge">En uso</span>
              {:else}<button class="ghost" onclick={() => (askUse = s)}>Usar</button>{/if}
              <label class="sw" title={s.own && s.kind === 'llamacpp' ? 'Apagar' : 'Lo prendió otra app: se apaga desde ahí'}>
                <input type="checkbox" role="switch" checked disabled={!(s.own && s.kind === 'llamacpp')} onchange={() => settings.stopLlamaCpp()} />
                <span>Encendido</span>
              </label>
            </div>
          </div>
          {#if s.current && s.kind === 'ollama' && models}<div class="inner">{@render models()}</div>{/if}
          {#if askUse?.url === s.url}
            <div class="ask" role="group" aria-label="Confirmar">
              <p>Las recomendaciones van a usar {KIND[s.kind]} en {s.url.replace('http://', '')}.
                {s.kind === 'ollama' ? 'Las descargas de modelos desde Ajustes van a esa instalación.' : 'Este servidor no baja modelos desde acá: usa el que tiene cargado.'}</p>
              <button class="primary" onclick={use}>Usar</button><button class="ghost" onclick={() => (askUse = null)}>Cancelar</button>
            </div>
          {/if}
        </li>
      {/each}

      {#if !running.some(s => s.own && s.kind === 'llamacpp')}
        <li>
          <div class="row">
            <div>
              <b>llama.cpp</b>
              {#if det.binaries.llamaServer && det.ggufs.length}
                <span class="muted">{det.ggufs.length} {det.ggufs.length === 1 ? 'modelo' : 'modelos'} .gguf</span>
              {:else if det.binaries.llamaServer}
                <span class="muted">Sin modelos .gguf en las carpetas habituales</span>
              {:else}
                <span class="muted">{det.ggufs.length ? `${det.ggufs.length} .gguf, pero falta llama-server` : 'No instalado'}</span>
              {/if}
            </div>
            <label class="sw">
              <input type="checkbox" role="switch" checked={loading} disabled={loading || !det.binaries.llamaServer || !chosen} onchange={() => (askStart = true)} />
              <span>{loading ? 'Encendiendo…' : 'Apagado'}</span>
            </label>
          </div>
          {#if det.binaries.llamaServer && det.ggufs.length}
            <select value={chosen?.path ?? ''} onchange={e => (model = e.currentTarget.value)} disabled={loading} aria-label="Modelo">
              {#each det.ggufs as g (g.path)}<option value={g.path}>{g.name} · {size(g.bytes)}</option>{/each}
            </select>
          {/if}
          {#if askStart && chosen}
            <div class="ask" role="group" aria-label="Confirmar">
              <p>Corre <code>llama-server</code> con <b>{chosen.name}</b> ({size(chosen.bytes)}) solo en esta computadora y lo usa para las recomendaciones.
                Se queda con la memoria de la placa hasta que lo apagues. No descarga nada.</p>
              <button class="primary" onclick={start}>Encender y usar</button><button class="ghost" onclick={() => (askStart = false)}>Cancelar</button>
            </div>
          {/if}
        </li>
      {/if}
    </ul>
    {#if !running.length && !det.binaries.llamaServer}<p class="muted">No encontré ningún servidor encendido.</p>{/if}

    {#if loading && own}
      <Progress job={own.job} verb="Cargando" oncancel={() => settings.stopLlamaCpp()} />
    {:else if own?.job.state === 'error' || own?.job.state === 'cancelled'}
      <JobNote job={own.job} />
    {/if}

    {#if det.binaries.ollama && !running.some(s => s.kind === 'ollama')}
      <p class="muted">Ollama está instalado pero apagado. El motor lo prende solo en su propio puerto al arrancar.</p>
    {/if}
  {/if}
</div>

<style>
  .det { display: grid; gap: 6px; margin: 6px 0 12px; }
  .top { display: flex; gap: 10px; align-items: center; justify-content: space-between; }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
  li { display: grid; gap: 6px; padding: 8px 10px; border: 1px solid var(--line, #3a332d); border-radius: 8px; }
  .inner { border-top: 1px solid var(--line, #3a332d); padding-top: 8px; display: grid; gap: 6px; }
  .row { display: flex; gap: 10px; align-items: center; justify-content: space-between; flex-wrap: wrap; }
  .sw { display: inline-flex; gap: 6px; align-items: center; font-size: 0.85rem; cursor: pointer; }
  .act { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .badge { font-size: 0.75em; padding: 1px 6px; border-radius: 10px; border: 1px solid currentColor; }
  .ask { display: grid; gap: 6px; padding: 8px 10px; border-radius: 8px; background: rgba(255, 255, 255, 0.05); }
  .ask p { margin: 0; font-size: 0.88rem; }
  .ask button { justify-self: start; }
  li select { max-width: 100%; }
  p { margin: 0; }
</style>
