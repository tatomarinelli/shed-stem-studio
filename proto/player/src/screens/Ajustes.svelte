<script lang="ts">
  import { onMount } from 'svelte';
  import { settings, type Config } from '../lib/settings.svelte';
  import FolderPicker from '../components/FolderPicker.svelte';
  import Progress from '../components/Progress.svelte';
  import JobNote from '../components/JobNote.svelte';
  import LlmDetect from '../components/LlmDetect.svelte';
  import BackendPicker from '../components/BackendPicker.svelte';
  import LlmServer from '../components/LlmServer.svelte';
  import { setup } from '../lib/setup.svelte';
  import Icon from '../components/Icon.svelte';
  import ResourceMonitor from '../components/ResourceMonitor.svelte';

  let resOpen = $state(true); // "Recursos" arranca abierto; cerrado, no se sondea
  onMount(() => {
    void settings.load().then(() => settings.syncJobs());
    settings.watchServices(true);
    return () => settings.watchServices(false);
  });
  let confirmOff = $state(false);
  const svc = $derived(settings.services);
  const uptime = (sec: number) => (sec < 90 ? `${sec} s` : sec < 5400 ? `${Math.round(sec / 60)} min` : `${(sec / 3600).toFixed(1)} h`);
  const MB = (b: number) => (b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : `${Math.round(b / 1e6)} MB`);

  const size = (b: number) => (b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : b >= 1e6 ? `${Math.round(b / 1e6)} MB` : `${Math.round(b / 1e3)} KB`);
  const hw = $derived(settings.hardware);
  const st = $derived(settings.storage);
  const eff = $derived(settings.effective);
  const base = (label: string) => label.split(':')[0];
  // Un modelo es "recomendado" si está en el catálogo de Shed Stem Studio y entra en este equipo.
  const recommended = (label: string) => hw?.models.some(c => c.fits && c.id === base(label)) ?? false;
  // Recomendados que todavía no están instalados: se ofrecen como una fila más del módulo.
  const toInstall = $derived(hw?.models.filter(c => c.fits && !st?.recommendations.models.some(m => base(m.label) === c.id)) ?? []);
  // Separación: RoFormer si la GPU tiene al menos 8 GB (estimación del uso con RoFormer, sin medir con precisión); si no, Demucs.
  const sepRecommended = $derived((hw?.gpus.find(g => g.accel)?.vramGB ?? 0) >= 8 ? 'RoFormer (BS-Roformer-SW)' : 'Demucs 6 stems (htdemucs_6s)');

  // Selector de carpetas: qué ajuste se está eligiendo.
  type PathKey = 'dataDir' | 'ollamaModelsDir' | 'separationModelsDir' | 'separationEnvDir';
  let picking = $state<null | { key: PathKey | 'musicFolders'; title: string; start: string }>(null);
  let urlDraft = $state('');
  let customModel = $state('');
  $effect(() => { if (eff) urlDraft = eff.llmUrl; });

  function pick(key: PathKey | 'musicFolders', title: string, start: string) { picking = { key, title, start }; }
  async function picked(path: string) {
    if (!picking || !settings.config) return;
    if (picking.key === 'musicFolders') await settings.save({ musicFolders: [...settings.config.musicFolders, path] });
    else await settings.save({ [picking.key]: path } as Partial<Config>);
  }
  const removeFolder = (f: string) => settings.save({ musicFolders: settings.config!.musicFolders.filter(x => x !== f) });

  const rows: { key: PathKey; label: string; help: string }[] = [
    { key: 'dataDir', label: 'Datos de Shed Stem Studio', help: 'Stems nuevos y archivos temporales. Lo que ya está guardado no se mueve solo.' },
    { key: 'ollamaModelsDir', label: 'Modelos de recomendaciones', help: 'Donde se descargan. Los ya descargados no se mueven solos.' },
    { key: 'separationModelsDir', label: 'Modelos de separación', help: 'Donde se descarga el modelo. Los ya descargados no se mueven solos.' },
    { key: 'separationEnvDir', label: 'Entorno de separación', help: 'Tiene que tener venv/bin/audio-separator.' },
  ];
</script>

<h2>Ajustes</h2>

{#if settings.state === 'loading'}
  <p class="muted">Midiendo tu equipo…</p>
{:else if settings.state === 'no_engine' || !hw || !st || !eff}
  <div class="card">
    <h3>El motor local está apagado</h3>
    <p>Sin el motor no puedo ver qué modelos hay instalados. Iniciálo de nuevo: con Docker, <code>docker compose -f docker/compose.yml up -d</code>; sin Docker, <code>npm run engine</code> en proto/player.</p>
    <button class="primary" onclick={() => settings.load()}>Reintentar</button>
  </div>
{:else}
  <section class="card">
    <h3>Configuración inicial</h3>
    <p class="muted">Repasá paso a paso el entorno, los modelos, tu música y tu perfil.</p>
    <div class="off"><button onclick={() => setup.restart()}>Repetir configuración inicial</button></div>
  </section>

  {#if svc}
    <section class="card">
      <h3>Qué está corriendo</h3>
      <ul class="svc">
        <li><b>Motor</b> <code>{svc.engine.host}:{svc.engine.port}</code>
          <span class="muted">{svc.engine.docker ? 'en Docker, ' : ''}activo hace {uptime(svc.engine.uptimeSec)}, proceso {svc.engine.pid}</span></li>
        <li><b>Interfaz</b> <code>{location.host}</code> <span class="muted">la página que estás viendo</span></li>
        <li><b>Servidor de modelos</b> <code>{svc.llm.url.replace(/^https?:\/\//, '')}</code>
          {#if svc.llm.running}
            <span class="ok">prendido</span>
            <span class="muted">{svc.llm.installed} instalados{svc.llm.loaded.length ? `, en memoria: ${svc.llm.loaded.map(m => `${m.name} (${MB(m.bytes)})`).join(', ')}` : ', ninguno en memoria'}</span>
          {:else}<span class="warn">apagado</span>{/if}</li>
        <li><b>Disco de hoy automático</b> <span class="muted">{svc.scheduler.auto ? `cada ${svc.scheduler.cadenceHours} h` : 'apagado'}</span></li>
      </ul>
      {#if svc.jobs.length}
        <h4>En curso</h4>
        <ul class="svc">
          {#each svc.jobs as j (j.kind + j.label)}
            <li><b>{j.kind}</b> {j.label} {#if j.percent != null}<span class="muted num">{j.percent} %</span>{/if} {#if j.step}<span class="muted">{j.step}</span>{/if}</li>
          {/each}
        </ul>
      {/if}
      <div class="off">
        {#if !confirmOff}
          <button class="ghost danger" disabled={svc.jobs.length > 0} onclick={() => (confirmOff = true)}>Apagar el motor</button>
          {#if svc.jobs.length}<span class="muted">Esperá a que termine lo que está en curso.</span>{/if}
        {:else}
          <span>¿Apagar el motor? Para volver a prenderlo hay que iniciarlo desde afuera (Docker o el instalador).</span>
          <button class="danger" onclick={() => { confirmOff = false; void settings.shutdown(); }}>Apagar</button>
          <button class="ghost" onclick={() => (confirmOff = false)}>Cancelar</button>
        {/if}
        {#if settings.shutdownMessage}<span class="warn" role="alert">{settings.shutdownMessage}</span>{/if}
      </div>
    </section>
  {/if}

  <section class="card">
    <h3>Modelos</h3>

    <div class="module">
      <h4>Separación en instrumentos</h4>
      {#if !st.env.present}
        <div class="env">
          <div><b>Falta el entorno de separación</b> <span class="muted">unos {st.env.approxGb} GB, se instala en {st.env.path}</span></div>
          <div class="act">
            {#if settings.envPull.state === 'running'}
              <Progress job={settings.envPull} verb="Instalando" oncancel={() => settings.cancelEnv()} />
            {:else}
              <BackendPicker />
              <button class="primary" onclick={() => settings.installEnv()}>Instalar</button>
              <JobNote job={settings.envPull} />
            {/if}
          </div>
        </div>
      {/if}
      <ul class="models">
        {#each st.separation as m (m.label)}
          {@const inUse = m.label === st.separationInUse}
          <li class:use={inUse}>
            <div><b>{m.label}</b> <span class="muted">{size(m.bytes)}</span>{#if m.label === sepRecommended} <span class="reco">Recomendado</span>{/if}</div>
            {#if !m.present && m.label === st.separationInUse}
              <div class="act">
                {#if settings.sepPull.state === 'running'}
                  <Progress job={settings.sepPull} oncancel={() => settings.cancelSepModel()} />
                {:else}
                  <button class="primary" onclick={() => settings.pullSeparation()}>Descargar</button>
                  <JobNote job={settings.sepPull} />
                {/if}
              </div>
            {:else if !m.present}<span class="warn">Falta instalar</span>
            {:else if inUse}<span class="badge">En uso</span>
            {:else}<span class="muted">Instalado, sin usar</span>{/if}
          </li>
        {/each}
      </ul>
    </div>

    <div class="module">
      <h4>Recomendaciones</h4>
      <h5>1 · Servidor</h5>
      <LlmDetect />
      <h5>2 · Modelo</h5>
      <LlmServer />
      <ul class="models">
        {#each st.recommendations.models as m (m.label)}
          {@const inUse = m.label === st.recommendations.inUse}
          <li class:use={inUse}>
            <div><b>{m.label}</b> <span class="muted">{size(m.bytes)}</span>{#if recommended(m.label)} <span class="reco">Recomendado</span>{/if}</div>
            {#if inUse}<span class="badge">En uso</span>
            {:else}<button onclick={() => settings.save({ llmModel: m.label })}>Usar este</button>{/if}
          </li>
        {/each}
        {#each toInstall as c (c.id)}
          {@const pull = settings.pulls[c.id]}
          <li>
            <div><b>{c.label}</b> <span class="muted">{c.gb ? `${c.gb} GB` : ''}</span> <span class="reco">Recomendado</span></div>
            <div class="act">
              {#if pull?.state === 'running'}
                <Progress job={pull} oncancel={() => settings.cancelPull(c.id)} />
              {:else}
                <button class="primary" disabled={!!settings.pullingNow} onclick={() => settings.pull(c.id)}>Descargar</button>
                {#if settings.pullingNow}<span class="muted">Esperá a que termine {settings.pullingNow}.</span>{/if}
                <JobNote job={pull} />
              {/if}
            </div>
          </li>
        {/each}
        <li>
          <form class="custom" onsubmit={e => { e.preventDefault(); const n = customModel.trim(); if (n) settings.pull(n); }}>
            <label>Otro: nombre de Ollama, ej. qwen3:8b
              <input bind:value={customModel} placeholder="nombre:etiqueta" autocomplete="off" spellcheck="false" />
            </label>
            {#if customModel.trim() && settings.pulls[customModel.trim()]?.state === 'running'}
              <Progress job={settings.pulls[customModel.trim()]} oncancel={() => settings.cancelPull(customModel.trim())} />
            {:else}
              <button type="submit" disabled={!customModel.trim() || !!settings.pullingNow}>Descargar</button>
              {#if settings.pullingNow}<span class="muted">Esperá a que termine {settings.pullingNow}.</span>{/if}
            {/if}
            {#if customModel.trim()}<JobNote job={settings.pulls[customModel.trim()]} />{/if}
          </form>
        </li>
        {#if !st.recommendations.models.length && !toInstall.length}
          <li><div class="warn">No hay un modelo instalado. {st.recommendations.running ? 'Ninguno del catálogo entra en tu equipo.' : 'El servidor de modelos está apagado.'}</div></li>
        {/if}
      </ul>
    </div>
  </section>

  <section class="card">
    <h3>Tu equipo</h3>
    <dl class="hw">
      {#each hw.gpus as g (g.name)}
        <dt>Placa de video</dt><dd>{g.name}, {g.vramGB} GB de memoria{#if g.accel === null}<span class="muted"> · separación por CPU</span>{/if}</dd>
      {:else}
        <dt>Placa de video</dt><dd class="warn">No se detectó una placa de video: la separación y los modelos irían a CPU, mucho más lento.</dd>
      {/each}
      <dt>Procesador</dt><dd>{hw.cpu.name}, {hw.cpu.threads} hilos</dd>
      <dt>Memoria</dt><dd>{hw.ram.totalGB} GB ({hw.ram.availableGB} GB libres)</dd>
      {#each hw.disks as d (d.path)}
        <dt>Disco {d.path}</dt><dd class:warn={d.usedPct >= 90}>{d.freeGB} GB libres de {d.totalGB} GB{d.usedPct >= 90 ? ', casi lleno' : ''}</dd>
      {/each}
    </dl>
  </section>

  <details class="card adv" open ontoggle={e => (resOpen = e.currentTarget.open)}>
    <summary><Icon name="medidor" size={18} /> Recursos</summary>
    {#if resOpen}<ResourceMonitor />{/if}
  </details>

  <details class="card adv">
    <summary>Carpetas y ubicaciones</summary>

    <div class="field">
      <div class="head"><b>Carpetas de música</b><button onclick={() => pick('musicFolders', 'Elegí una carpeta de música', settings.config?.musicFolders.at(-1) ?? '/')}>Agregar carpeta</button></div>
      <p class="muted">Shed Stem Studio las recorre para mostrarlas en Fuentes → Archivos.</p>
      <ul class="paths">
        {#each eff.musicFolders as f (f)}
          <li><span class="path">{f}</span><button class="ghost" onclick={() => removeFolder(f)} aria-label="Quitar {f}">Quitar</button></li>
        {:else}
          <li class="muted">Todavía no agregaste ninguna.</li>
        {/each}
      </ul>
    </div>

    {#each rows as r (r.key)}
      {@const host = svc?.engine.hostPaths[r.key]}
      <div class="field">
        {#if host}
          <div class="head"><b>{r.label}</b></div>
          <p class="path">{host.path}</p>
          <p class="muted">Con Docker esta carpeta se define al levantar: cambiá <code>{host.var}</code> en <code>docker/.env</code> y volvé a levantar.</p>
        {:else}
          <div class="head"><b>{r.label}</b><span class="btns"><button class="ghost" onclick={() => settings.openFolder(r.key)}>Abrir carpeta</button><button onclick={() => pick(r.key, `Elegí: ${r.label.toLowerCase()}`, eff[r.key])}>Cambiar</button></span></div>
          <p class="path">{eff[r.key]}</p>
          <p class="muted">{r.help}</p>
        {/if}
      </div>
    {/each}

    <form class="field" onsubmit={e => { e.preventDefault(); settings.save({ llmUrl: urlDraft }); }}>
      <div class="head"><b>Servidor de modelos (Ollama o LM Studio)</b><button type="submit" disabled={urlDraft === eff.llmUrl}>Guardar</button></div>
      <input type="text" bind:value={urlDraft} aria-label="Dirección del servidor de modelos" spellcheck="false" />
      <p class="muted">Tiene que ser de esta computadora. Con la dirección por defecto, Shed Stem Studio lo levanta solo.</p>
    </form>

    {#if settings.saveMessage}<p class={settings.saveMessage.ok ? 'ok' : 'warn'} role="status">{settings.saveMessage.text}</p>{/if}

    <h4>Espacio que ocupa cada cosa</h4>
    <table>
      <tbody>
        {#each st.storage as s (s.label)}
          <tr><td>{s.label}</td><td class="r num">{size(s.bytes)}</td><td class="path">{s.path}</td><td class="muted">{s.writable ? '' : 'Solo lectura'}</td></tr>
        {/each}
      </tbody>
    </table>
  </details>

  {#if picking}
    <FolderPicker start={picking.start} title={picking.title} onpick={picked} onclose={() => (picking = null)} />
  {/if}
{/if}

<style>
  h2 { margin: 0; font-size: 28px; letter-spacing: -0.02em; }
  h3 { margin: 0 0 10px; font-size: 19px; letter-spacing: -0.01em; }
  h4 { margin: 14px 0 6px; font-size: 15px; color: var(--muted); font-weight: 600; }
  .card { background: var(--glass); backdrop-filter: blur(16px) saturate(1.3); border: 1px solid var(--glass-line); border-radius: var(--radius); padding: 16px 18px; box-shadow: 0 20px 50px -24px rgba(0,0,0,0.7); animation: rise 0.45s var(--ease) both; }
  .card p { margin: 4px 0; }
  .module + .module { margin-top: 6px; }
  h5 { margin: 12px 0 2px; font-size: 13px; color: var(--muted); font-weight: 600; }
  .models, .paths { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
  .models li { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 10px 12px; border-radius: 12px; background: rgba(255,255,255,0.04); border: 1px solid transparent; transition: border-color 0.3s, background 0.3s; }
  .models li.use { border-color: color-mix(in srgb, #7cc7a3 55%, transparent); background: rgba(124, 199, 163, 0.08); }
  .hw { display: grid; grid-template-columns: minmax(0, max-content) 1fr; gap: 6px 20px; margin: 0; }
  .hw dt { color: var(--muted); overflow-wrap: anywhere; } .hw dd { margin: 0; overflow-wrap: anywhere; }
  .reco { font-size: 12px; font-weight: 600; color: var(--bg); background: #7cc7a3; border-radius: 999px; padding: 1px 10px; margin-left: 6px; white-space: nowrap; vertical-align: 1px; }
  .ok { color: #7cc7a3; } .warn { color: #f0a43c; }
  .badge { font-size: 12.5px; font-weight: 600; color: #7cc7a3; border: 1px solid color-mix(in srgb, #7cc7a3 50%, transparent); border-radius: 999px; padding: 2px 12px; white-space: nowrap; }
  .primary { background: var(--text); color: var(--bg); border-color: var(--text); font-weight: 600; }
  .ghost { background: transparent; padding: 2px 10px; }
  .svc { list-style: none; margin: 0 0 10px; padding: 0; display: grid; gap: 6px; }
  .svc li { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; padding: 8px 12px; border-radius: 12px; background: rgba(255,255,255,0.04); }
  .svc code { font-family: ui-monospace, monospace; font-size: 0.9em; }
  .off { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-top: 10px; }
  .danger { color: #ff8a8a; border-color: color-mix(in srgb, #ff8a8a 45%, transparent); }
  .env { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 10px; }
  .btns { display: flex; gap: 8px; }
  .custom { display: flex; flex-wrap: wrap; gap: 10px; align-items: end; width: 100%; }
  .custom label { display: grid; gap: 4px; flex: 1; min-width: 220px; color: var(--muted); font-size: 0.85rem; }
  .act { display: grid; gap: 6px; justify-items: end; min-width: 190px; }
  .adv summary { cursor: pointer; font-weight: 600; font-size: 17px; }
  .adv summary :global(svg) { vertical-align: -3px; margin-right: 4px; }
  .adv[open] summary { margin-bottom: 10px; }
  .field { display: grid; gap: 2px; padding: 10px 0; border-top: 1px solid var(--glass-line); }
  .head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
  .path { color: var(--muted); font-size: 13.5px; word-break: break-all; margin: 0; }
  .paths li { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
  .field input[type='text'] { background: rgba(255,255,255,0.06); border: 1px solid var(--glass-line); border-radius: 9px; padding: 7px 10px; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  td { padding: 6px 8px; border-bottom: 1px solid rgba(255,255,255,0.05); vertical-align: top; }
  .r { text-align: right; white-space: nowrap; }
  @media (max-width: 760px) { .models li { flex-direction: column; align-items: stretch; } .act { justify-items: start; } }
</style>
