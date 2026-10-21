<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { setup, PAGES, TITLES, SKIPPABLE, PAGE_OF, type Page } from '../lib/setup.svelte';
  import { settings, type Config } from '../lib/settings.svelte';
  import { tidal } from '../lib/tidal.svelte';
  import { recs } from '../lib/recs.svelte';
  import { nav } from '../lib/nav.svelte';
  import Progress from '../components/Progress.svelte';
  import Icon from '../components/Icon.svelte';
  import TidalLogin from '../components/TidalLogin.svelte';
  import FolderPicker from '../components/FolderPicker.svelte';
  import ProfileForm from '../components/recs/ProfileForm.svelte';
  import PresetWizard from '../components/recs/PresetWizard.svelte';
  import BackendPicker from '../components/BackendPicker.svelte';
  import LlmServer from '../components/LlmServer.svelte';

  const hw = $derived(settings.hardware);
  const eff = $derived(settings.effective);
  const st = $derived(settings.storage);
  const stepOf = (id: string) => setup.step(id)?.state ?? 'pending';
  const mark = (p: Page) => (p === 'carpetas' ? '' : setup.pageState(p));

  onMount(() => {
    void settings.load();
    void recs.load();
    untrack(() => tidal.connect());
    settings.watchServices(true);
    const t = window.setInterval(() => void settings.syncJobs(['mistral-nemo']), 2500);
    return () => { settings.watchServices(false); window.clearInterval(t); };
  });

  // ---- carpetas
  type PathKey = 'dataDir' | 'ollamaModelsDir' | 'separationModelsDir' | 'separationEnvDir';
  let picking = $state<null | { key: PathKey | 'musicFolders'; title: string; start: string }>(null);
  const rows: { key: PathKey; label: string }[] = [
    { key: 'dataDir', label: 'Datos (stems y análisis)' },
    { key: 'separationEnvDir', label: 'Entorno de separación' },
    { key: 'separationModelsDir', label: 'Modelo de separación' },
    { key: 'ollamaModelsDir', label: 'Modelos de recomendaciones' },
  ];
  async function picked(path: string) {
    if (!picking) return;
    if (picking.key === 'musicFolders') await settings.save({ musicFolders: [...(settings.config?.musicFolders ?? []), path] });
    else await settings.save({ [picking.key]: path } as Partial<Config>);
  }
  const removeFolder = (f: string) => settings.save({ musicFolders: settings.config!.musicFolders.filter(x => x !== f) });
  // Rutas de Linux ("/mnt/x") y de Windows ("C:\Users\x", sin distinguir mayúsculas): se comparan con "/" como separador.
  const norm = (p: string) => { const q = p.replace(/\\/g, '/').replace(/\/+$/, ''); return /^[a-z]:/i.test(q) ? q.toLowerCase() : q; };
  const freeFor = (path?: string) => {
    if (!path || !hw) return null;
    const p = norm(path);
    const d = [...hw.disks].filter(x => { const r = norm(x.path); return p === r || p.startsWith(r + '/'); }).sort((a, b) => b.path.length - a.path.length)[0];
    return d ? d.freeGB : null;
  };
  const envFree = $derived(freeFor(eff?.separationEnvDir));
  const envBlocked = $derived(envFree !== null && envFree < 10);

  // ---- dónde quedó cada cosa
  type DirKey = 'dataDir' | 'separationEnvDir' | 'separationModelsDir' | 'ollamaModelsDir';
  const inDocker = $derived(!!settings.services?.engine.docker);
  const pathOf = (key: DirKey) => settings.services?.engine.hostPaths[key]?.path ?? eff?.[key] ?? '';
  let openError = $state('');
  async function openDir(key: DirKey) { openError = await settings.openFolder(key); }

  // ---- modelo de recomendaciones
  let customModel = $state('');
  const candidate = $derived(hw?.models.find(m => m.module === 'recomendaciones'));
  const chat = $derived(setup.step('modelo')?.detail as { serverUp?: boolean; installed?: string[] } | undefined);

  // ---- perfil
  type Stage = 'loading' | 'form' | 'preset' | 'wizard' | 'done';
  let stage = $state<Stage>('loading');
  let prefill = $state<{ loves: string[]; essentials: string[] } | null>(null);
  let profileLoaded = $state(false);
  $effect(() => {
    if (setup.page !== 'perfil' || profileLoaded) return;
    profileLoaded = true;
    void (async () => {
      await recs.load();
      if (recs.profileFilled) { stage = 'done'; return; }
      try {
        const r = await fetch('/engine/recs/profile/suggested?refresh=1');
        const s = await r.json();
        prefill = s.from === 'none' ? null : { loves: s.loves, essentials: s.essentials };
      } catch { prefill = null; }
      stage = 'form';
    })();
  });

  async function firstDisc() {
    await setup.finish();
    nav.go('recomendaciones');
    await recs.generate('daily');
  }
  const canDisc = $derived(stepOf('modelo') === 'done' && stepOf('perfil') === 'done');
  const label = (s: string) => ({ done: 'Listo', pending: 'Pendiente', running: 'En curso', error: 'Con error', skipped: 'Para más tarde' }[s] ?? s);
</script>

<div class="wiz" role="dialog" aria-modal="true" aria-label="Primeros pasos">
  <header>
    <b class="brand">Primeros pasos</b>
    <ol class="steps">
      {#each PAGES as p, i (p)}
        <li>
          <button class="dot {mark(p)}" class:cur={setup.page === p} aria-current={setup.page === p ? 'step' : undefined} onclick={() => setup.go(p)} title={TITLES[p]}>
            <span class="n">{i + 1}</span><span class="t">{TITLES[p]}</span>
          </button>
        </li>
      {/each}
    </ol>
    <button class="ghost out" onclick={() => setup.finish()}>Salir</button>
  </header>

  <div class="scroll"><section class="body">
    {#if setup.page === 'bienvenida'}
      <h2>Vamos a dejar todo listo</h2>
      {#if setup.engine === 'off'}
        <p class="warn" role="alert">El motor local no responde.</p>
        <p>Iniciálo y volvé a intentar. Con Docker: <code>docker compose -f docker/compose.yml up -d</code>. Sin Docker: <code>npm run engine</code> en proto/player.</p>
        <div class="row"><button class="primary" onclick={() => setup.load()}>Reintentar</button></div>
      {:else}
        <ul class="feat">
          <li><Icon name="capas" size={22} /><div><b>Separación en instrumentos</b><span>Guitarra, bajo, batería, piano y voz por separado.</span></div></li>
          <li><Icon name="enlaces" size={22} /><div><b>Multifuente</b><span>Archivos locales y TIDAL en un solo lugar.</span></div></li>
          <li><Icon name="estrella" size={22} /><div><b>Recomendación basada en contexto y memoria del usuario</b><span>Un disco por período, según tus gustos, la hora y lo que ya escuchaste.</span></div></li>
          <li><Icon name="perfil" size={22} /><div><b>Perfil de gustos</b><span>Para afinar cada recomendación.</span></div></li>
        </ul>
        <p class="muted">Nada se descarga sin que lo pidas, y cada paso se puede dejar para más tarde.</p>
      {/if}

    {:else if setup.page === 'carpetas'}
      <h2>Dónde guardar</h2>
      <p class="muted">Lo pesado (entorno, modelos y stems) va a estas carpetas. Elegí un disco con espacio.</p>
      {#each rows as r (r.key)}
        {@const host = settings.services?.engine.hostPaths[r.key]}
        <div class="field">
          <div><b>{r.label}</b> <span class="muted num">{freeFor(eff?.[r.key]) ?? '?'} GB libres</span></div>
          <p class="path">{host ? host.path : eff?.[r.key]}</p>
          {#if host}<p class="muted">Con Docker se cambia en <code>docker/.env</code> (<code>{host.var}</code>) y se vuelve a levantar.</p>
          {:else}<button onclick={() => (picking = { key: r.key, title: `Elegí: ${r.label.toLowerCase()}`, start: eff?.[r.key] ?? '/' })}>Cambiar</button>{/if}
        </div>
      {/each}
      {#if settings.saveMessage && !settings.saveMessage.ok}<p class="warn" role="alert">{settings.saveMessage.text}</p>{/if}

    {:else if setup.page === 'modelos'}
      <h2>Modelos</h2>

      <div class="equip" aria-label="Tu equipo">
        <b>Tu equipo</b>
        {#if hw}
          <span class="spec">
            <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="7" width="16" height="10" rx="2" /><path d="M8 17v2M12 17v2M16 17v2M7 11h4M15 11h2" /></svg>
            {hw.gpus.length ? `${hw.gpus[0].name}, ${hw.gpus[0].vramGB} GB de memoria de video` : 'Sin placa de video'}
          </span>
          <span class="spec muted">
            <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="8" width="18" height="8" rx="1.5" /><path d="M7 8v8M11 8v8M15 8v8M6 16v2M18 16v2" /></svg>
            {hw.ram.totalGB} GB de RAM
          </span>
          <span class="spec muted">
            <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="5" width="16" height="14" rx="2" /><path d="M4 14h16M8 17h.01" /></svg>
            Disco: {envFree ?? '?'} GB libres
          </span>
        {:else}<span class="muted">Midiendo tu equipo…</span>{/if}
        {#if hw && !hw.gpus.length}<span class="warn" role="alert">Sin placa de video: todo va por CPU, lento.</span>
        {:else if hw && !hw.gpus.some(g => g.accel)}<span class="warn" role="alert">Separación por CPU: lenta.</span>{/if}
      </div>

      {#if openError}<p class="warn" role="alert">{openError}</p>{/if}
      <div class="job col">
        <div class="ttl"><Icon name="chip" /><b>Entorno de separación</b> <span class="muted">≈ 8 GB en disco</span></div>
        <p class="info">Lo que hace correr la IA. Se instala una vez; es lo más pesado.</p>
        <p class="where"><Icon name="carpeta" size={16} /><span class="path">{pathOf('separationEnvDir')}</span>
          {#if !inDocker}<button class="ghost" onclick={() => openDir('separationEnvDir')}>Abrir carpeta</button>{/if}</p>
        {#if st?.env.present}<span class="ok">Instalado{st.env.backend ? ` · ${st.env.backend === 'cuda' ? 'NVIDIA (CUDA)' : st.env.backend === 'cpu' ? 'procesador' : st.env.backend}` : ''}</span>
        {:else if settings.envPull.state === 'running'}<Progress job={settings.envPull} verb="Instalando" />
        {:else}
          <BackendPicker />
          <button class="primary" disabled={envBlocked} onclick={() => settings.installEnv()}>Instalar</button>
          {#if envBlocked}<span class="warn" role="alert">Necesita unos 10 GB y quedan {envFree} GB acá. Cambiá la carpeta en el paso anterior.</span>{/if}
          {#if settings.envPull.state === 'error'}<span class="warn" role="alert">{settings.envPull.message}</span>{/if}
        {/if}
      </div>

      <div class="job col">
        <div class="ttl"><Icon name="onda" /><b>Modelo de separación</b> <span class="muted">≈ 700 MB en disco · ≈ 3 GB de placa de video al separar</span></div>
        <p class="info">La red neuronal que separa un tema en guitarra, bajo, batería, piano, voz y otros. Es un solo archivo; necesita el entorno.</p>
        <p class="where"><Icon name="carpeta" size={16} /><span class="path">{pathOf('separationModelsDir')}</span>
          {#if !inDocker}<button class="ghost" onclick={() => openDir('separationModelsDir')}>Abrir carpeta</button>{/if}</p>
        {#if st?.separation[0]?.present}<span class="ok">Descargado</span>
        {:else if settings.sepPull.state === 'running'}<Progress job={settings.sepPull} />
        {:else}
          <button class="primary" disabled={!st?.env.present} onclick={() => settings.pullSeparation()}>Descargar</button>
          {#if !st?.env.present}<span class="muted">Primero el entorno.</span>{/if}
          {#if settings.sepPull.state === 'error'}<span class="warn" role="alert">{settings.sepPull.message}</span>{/if}
        {/if}
      </div>

      <div class="job col">
        <LlmServer />
        {#if chat?.installed?.length}
          <div class="ttl"><Icon name="estrella" /><b>Modelo de recomendaciones</b> <span class="muted">{chat.installed[0]}</span></div>
          <p class="info">El modelo de lenguaje que propone discos según tus gustos. Corre en tu equipo.</p>
          <p class="where"><Icon name="carpeta" size={16} /><span class="path">{pathOf('ollamaModelsDir')}</span>
            {#if !inDocker}<button class="ghost" onclick={() => openDir('ollamaModelsDir')}>Abrir carpeta</button>{/if}</p>
          <span class="ok">Instalado</span>
        {:else}
          <div class="ttl"><Icon name="estrella" /><b>Modelo de recomendaciones</b>
            {#if candidate}<span class="muted">{candidate.label} · {candidate.gb ? `≈ ${candidate.gb} GB en disco · ≈ ${Math.ceil(candidate.gb + 2)} GB de placa de video` : ''}</span> <span class="reco">Recomendado</span>{#if candidate.partial} <span class="muted">· parte en CPU</span>{/if}{/if}</div>
          <p class="info">Propone discos según tus gustos. Corre en tu equipo.</p>
          <p class="where"><Icon name="carpeta" size={16} /><span class="path">{pathOf('ollamaModelsDir')}</span></p>
          {#if candidate}
            {#if settings.pulls[candidate.id]?.state === 'running'}<Progress job={settings.pulls[candidate.id]} />
            {:else}
              <button class="primary" disabled={!candidate.fits} onclick={() => settings.pull(candidate.id)}>Descargar</button>
              {#each candidate.reasons as r (r)}<span class="warn" role="alert">{r}</span>{/each}
              {#if settings.pulls[candidate.id]?.state === 'error'}<span class="warn" role="alert">{settings.pulls[candidate.id].message}</span>{/if}
            {/if}
          {/if}
          {#if candidate && hw?.gpus.some(g => g.accel) && !candidate.withSeparation}
            <p class="info">Con tu placa de video no entran a la vez: la separación y las recomendaciones se turnan solas.</p>
          {/if}
          <details class="other">
            <summary>Elegir otro modelo</summary>
            <form onsubmit={e => { e.preventDefault(); const n = customModel.trim(); if (n) settings.pull(n); }}>
              <label>Nombre en Ollama, por ejemplo qwen3:8b
                <input bind:value={customModel} placeholder="nombre:etiqueta" autocomplete="off" spellcheck="false" />
              </label>
              {#if customModel.trim() && settings.pulls[customModel.trim()]?.state === 'running'}<Progress job={settings.pulls[customModel.trim()]} />
              {:else}<button type="submit" disabled={!customModel.trim()}>Descargar</button>{/if}
            </form>
          </details>
          {#if chat && !chat.serverUp}
            <p class="warn" role="alert">El servidor de modelos no responde todavía. Si recién arrancó, esperá unos segundos.</p>
          {/if}
        {/if}
      </div>

    {:else if setup.page === 'musica'}
      <h2>Fuentes</h2>
      <p class="muted">Con una alcanza. Podés sumar la otra después.</p>
      <div class="job col">
        <div class="head"><span class="ttl"><Icon name="musica" /><b>Archivos locales</b></span><button onclick={() => (picking = { key: 'musicFolders', title: 'Elegí una carpeta de música', start: settings.config?.musicFolders.at(-1) ?? '/' })}>Agregar carpeta</button></div>
        {#each settings.config?.musicFolders ?? [] as f (f)}
          <div class="folder"><span class="path">{f}</span><button class="ghost" onclick={() => removeFolder(f)}>Quitar</button></div>
        {:else}<span class="muted">Ninguna carpeta todavía.</span>{/each}
      </div>
      <div class="job col">
        <div class="head"><span class="ttl"><Icon name="enlaces" /><b>TIDAL</b></span><span class={tidal.state === 'ready' ? 'ok' : 'muted'}>{tidal.label}</span></div>
        {#if tidal.state === 'logging_in'}
          <TidalLogin />
        {:else if tidal.state === 'ready'}<span class="muted">Conectado. Tus favoritos ya se pueden usar para armar tu perfil.</span>
        {:else if tidal.state === 'connecting'}<span class="muted">Conectando…</span>
        {:else}
          {#if tidal.message}<p class="muted">{tidal.message}</p>{/if}
          <div class="row"><button class="primary" onclick={() => tidal.login()}>Conectar TIDAL</button></div>
        {/if}
      </div>

    {:else if setup.page === 'perfil'}
      <h2>Perfil de gustos</h2>
      {#if stage === 'loading'}<p class="muted">Leyendo tus favoritos…</p>
      {:else if stage === 'form' && recs.profile}
        <ProfileForm prefill={prefill} onclose={() => (stage = 'preset')} />
      {:else if stage === 'preset'}
        <p>Perfil guardado. ¿Querés crear ahora un perfil por horario (por ejemplo "Trabajo de lunes a viernes")?</p>
        <div class="row"><button class="primary" onclick={() => (stage = 'wizard')}>Crear uno ahora</button><button onclick={() => (stage = 'done')}>Usar el de por defecto</button></div>
      {:else if stage === 'wizard'}
        <PresetWizard onclose={() => (stage = 'done')} />
      {:else}
        <p class="ok">Tu perfil está listo.</p>
        <div class="row"><button onclick={() => (stage = 'form')}>Editarlo</button></div>
      {/if}

    {:else}
      <h2>Listo</h2>
      <ul class="sum">
        {#each setup.status?.steps.filter(s => ['separacion', 'musica', 'modelo', 'perfil'].includes(s.id)) ?? [] as s (s.id)}
          <li class={s.state}>
            <span>{s.label}</span><span class="tag">{label(s.state)}</span>
            {#if s.state !== 'done'}<button class="ghost" onclick={() => setup.go(PAGE_OF[s.id])}>Ir al paso</button>{/if}
          </li>
        {/each}
      </ul>
      {#if canDisc}
        <div class="row"><button class="primary" onclick={firstDisc}>Armar mi primer disco</button><button onclick={() => setup.finish()}>Terminar</button></div>
      {:else}
        {#if stepOf('modelo') !== 'done'}<p class="muted">Para armar tu primer disco falta el modelo de recomendaciones.</p>{/if}
        <div class="row">
          {#if stepOf('modelo') !== 'done'}<button class="primary" onclick={() => setup.go('modelos')}>Ir al modelo</button>{/if}
          <button onclick={() => setup.finish()}>Terminar igual</button>
        </div>
      {/if}
    {/if}

    <div class="actions">
      <button onclick={() => setup.back()} disabled={setup.index === 0}>Atrás</button>
      <span class="sp"></span>
      {#if SKIPPABLE.includes(setup.page) && setup.pageState(setup.page) !== 'done'}
        <button class="ghost" onclick={() => setup.skip(setup.page)}>Más tarde</button>
      {/if}
      {#if setup.page !== 'listo'}
        <button class="primary" disabled={setup.page === 'bienvenida' && setup.engine === 'off'} onclick={() => setup.next()}>Siguiente</button>
      {/if}
    </div>
  </section></div>
</div>

{#if picking}
  <FolderPicker start={picking.start} title={picking.title} onpick={picked} onclose={() => (picking = null)} />
{/if}

<style>
  .wiz { position: fixed; inset: 0; z-index: 60; display: grid; grid-template-rows: auto 1fr; background: var(--bg); animation: rise 0.35s var(--ease) both; }
  header { display: flex; align-items: center; gap: 18px; padding: 14px 22px; border-bottom: 1px solid var(--glass-line); }
  .brand { font-size: 18px; white-space: nowrap; }
  .steps { display: flex; gap: 6px; list-style: none; margin: 0; padding: 0; flex: 1; overflow-x: auto; }
  .dot { display: flex; align-items: center; gap: 8px; padding: 5px 11px; border-radius: 999px; background: transparent; border-color: transparent; white-space: nowrap; }
  .dot .n { display: grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; font-size: 12px; background: rgba(255,255,255,0.08); }
  .dot .t { font-size: 13px; color: var(--muted); }
  .dot.cur { background: rgba(255,255,255,0.08); border-color: var(--glass-line); }
  .dot.cur .t { color: inherit; }
  .dot.done .n { background: #7cc7a3; color: var(--bg); }
  .dot.skipped .n { background: #f0a43c; color: var(--bg); }
  .dot.running .n { background: #4fa3d9; color: var(--bg); }
  .dot.error .n { background: #ff8a8a; color: var(--bg); }
  .out { white-space: nowrap; }
  .scroll { overflow: auto; }
  .body { padding: 28px 22px 0; max-width: 760px; width: 100%; margin: 0 auto; display: grid; gap: 14px; align-content: start; }
  h2 { margin: 0; font-size: 28px; font-weight: 700; letter-spacing: -0.02em; }
  /* Pegados a la columna de contenido (no a los bordes de la ventana) y siempre a la vista aunque la página sea larga. */
  .actions { display: flex; gap: 10px; align-items: center; margin-top: 10px; padding: 14px 0; border-top: 1px solid var(--glass-line); position: sticky; bottom: 0; background: var(--bg); }
  .equip { display: grid; gap: 3px; padding: 12px 14px; border-radius: 12px; background: rgba(255,255,255,0.04); border: 1px solid var(--glass-line); }
  .spec { display: flex; align-items: center; gap: 9px; }
  .spec svg { width: 18px; height: 18px; flex: none; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
  .feat { list-style: none; margin: 4px 0 0; padding: 0; display: grid; gap: 10px; }
  .feat li { display: flex; gap: 14px; align-items: flex-start; padding: 14px 16px; border-radius: 14px; background: rgba(255,255,255,0.04); border: 1px solid var(--glass-line); }
  .feat li :global(svg) { flex: none; margin-top: 2px; color: #7cc7a3; }
  .feat div { display: grid; gap: 2px; }
  .feat span { color: var(--muted); font-size: 0.92rem; }
  .ttl { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; }
  .ttl :global(svg) { flex: none; color: #7cc7a3; }
  .where { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin: 0; color: var(--muted); font-size: 0.88rem; }
  .where :global(svg) { flex: none; }
  .where .path { flex: 1; min-width: 0; }
  .info { margin: 0; color: var(--muted); font-size: 0.92rem; line-height: 1.45; }
  .other { width: 100%; }
  .other summary { cursor: pointer; color: var(--muted); font-size: 0.9rem; }
  .other form { display: grid; gap: 8px; margin-top: 8px; justify-items: start; }
  .sp { flex: 1; }
  .list { margin: 0; padding-left: 20px; display: grid; gap: 4px; }
  .field, .job { display: grid; gap: 6px; padding: 12px 14px; border-radius: 12px; background: rgba(255,255,255,0.04); justify-items: start; }
  .job .head, .folder { display: flex; justify-content: space-between; align-items: center; gap: 12px; width: 100%; }
  .path { font-family: ui-monospace, monospace; font-size: 0.88em; overflow-wrap: anywhere; margin: 0; }
  .row { display: flex; gap: 10px; flex-wrap: wrap; }
  .btn { display: inline-block; padding: 7px 13px; border-radius: 9px; border: 1px solid var(--glass-line); background: rgba(255,255,255,0.06); text-decoration: none; color: inherit; }
  .ok { color: #7cc7a3; } .warn { color: #f0a43c; }
  .reco { font-size: 12px; font-weight: 600; color: var(--bg); background: #7cc7a3; border-radius: 999px; padding: 1px 10px; margin-left: 6px; white-space: nowrap; }
  label { display: grid; gap: 4px; color: var(--muted); font-size: 0.85rem; width: 100%; }
  .sum { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
  .sum li { display: flex; align-items: center; gap: 12px; padding: 10px 14px; border-radius: 12px; background: rgba(255,255,255,0.04); }
  .sum li span:first-child { flex: 1; }
  .sum .tag { font-size: 13px; color: var(--muted); }
  .sum .done .tag { color: #7cc7a3; } .sum .skipped .tag { color: #f0a43c; }
  code { font-family: ui-monospace, monospace; font-size: 0.9em; }
  @media (max-width: 760px) { .dot .t { display: none; } header { gap: 8px; padding: 10px 12px; } }
</style>
