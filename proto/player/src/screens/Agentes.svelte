<script lang="ts">
  // Los agentes de la recomendación trabajando: planificador → buscador → revisor → clasificador, una etapa a la vez, con lo que fueron decidiendo.
  import { onMount, tick } from 'svelte';
  import { recs, type Agent } from '../lib/recs.svelte';
  import { settings } from '../lib/settings.svelte';

  onMount(() => { void recs.load(); void settings.load(); });

  const running = $derived(recs.state === 'running');
  // En vivo mientras se busca (o si el motor ya trae el registro en memoria); si no, la última búsqueda guardada.
  const live = $derived(recs.agents.length > 0);
  const agents = $derived<Agent[]>(live ? recs.agents : (recs.lastRun?.agents ?? []));
  const log = $derived(live ? recs.log : (recs.lastRun?.log ?? []));
  const inputs = $derived(live ? recs.inputs : (recs.lastRun?.inputs ?? null));
  const MODE: Record<string, string> = { estudiar: 'Estudiar', concentrarme: 'Concentrarme', sorprenderme: 'Sorprenderme' };
  const TYPE: Record<string, string> = { album: 'Álbum', ep: 'EP', live: 'En vivo' };
  const HOW: Record<string, string> = { horario: 'por horario', defecto: 'por defecto', elegido: 'elegido por vos' };
  const DISC: Record<string, string> = { nada: 'se queda en tu zona', algo: 'algo de música nueva', mucho: 'mucha música nueva' };
  const LISTEN: Record<string, string> = { discos: 'escucha discos enteros', temas: 'escucha temas sueltos', ambos: 'discos y temas sueltos' };
  const names = (xs: { name: string; w: number }[]) => xs.map(x => x.name).join(', ');
  const lastWhen = $derived(!live && recs.lastRun ? new Date(recs.lastRun.createdAt * 1000).toLocaleString('es-AR', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '');
  const STATE: Record<Agent['state'], string> = { idle: 'Esperando', running: 'Trabajando', done: 'Listo', skipped: 'Apagado', cancelled: 'Cortado' };
  const WHO: Record<string, string> = { planificador: 'Planificador', buscador: 'Buscador', revisor: 'Revisor', clasificador: 'Clasificador' };
  const KIND: Record<string, string> = { ok: 'ok', discard: 'descarte', warn: 'duda', skip: 'omitido', info: '' };

  // Prender o apagar el revisor y el clasificador sin ir a Ajustes (no se puede cambiar mientras se busca).
  const planner = $derived((settings.config as { recsPlanner?: string } | null)?.recsPlanner ?? 'off');
  const toggles: Record<string, { on: () => boolean; patch: (on: boolean) => Record<string, string> } | undefined> = {
    planificador: { on: () => planner !== 'off', patch: on => ({ recsPlanner: on ? 'off' : 'same' }) },
    revisor: { on: () => (settings.config?.recsReviewer ?? 'off') !== 'off', patch: on => ({ recsReviewer: on ? 'off' : 'same' }) },
    clasificador: { on: () => (settings.config?.classifier ?? 'off') !== 'off', patch: on => ({ classifier: on ? 'off' : 'llm' }) },
  };

  let feed = $state<HTMLElement>();
  $effect(() => { log.length; if (running) void tick().then(() => feed?.scrollTo({ top: feed.scrollHeight })); });
</script>

<div class="head">
  <h2>Agentes</h2>
  {#if running}<span class="live" role="status"><i aria-hidden="true"></i> Buscando ahora</span>
  {:else if lastWhen}<span class="muted small">Última búsqueda: {lastWhen}</span>{/if}
</div>
<p class="muted intro">Cada búsqueda pasa por hasta cuatro agentes, <b>una etapa a la vez</b>: el planificador lee tu pedido, el buscador trae discos reales, el revisor los lee contra lo que pediste y el clasificador verifica lo que quedó en duda. Cada uno puede usar un modelo distinto.</p>

{#if inputs}
  {@const i = inputs}
  <details class="vars" open>
    <summary>Con qué variables corre</summary>
    <p class="muted small lead">Lo que se entendió de tu pedido y de tu perfil para esta búsqueda, no el texto que ve el modelo.</p>
    <div class="groups">
      <div class="g">
        <h5>Qué pediste</h5>
        <ul>
          <li>{#if i.request.genres.length}<b>Género:</b> {i.request.genres.join(', ')} · {i.request.strict ? 'solo ese género' : 'flexible'}{i.request.genresDetected ? ' (lo detecté en tu texto)' : ''}{:else if !i.request.countries.length}<b>Sin género:</b> por tus gustos{:else}<b>Género:</b> el que sea de ese país{/if}</li>
          {#if i.request.countries.length}<li><b>País:</b> {i.request.countryNames.join(', ')} · {i.request.strict ? 'solo artistas de ahí (lo verifica MusicBrainz)' : 'flexible'}{i.request.countriesDetected ? ' (lo detecté en tu texto)' : ''}</li>{/if}
          {#if i.request.era}<li><b>Época:</b> {i.request.era.from}–{i.request.era.to} · {i.request.era.source === 'reglas' ? 'la escribiste vos' : 'la entendió el modelo'} · {i.request.era.strict ? 'se exige con el año de MusicBrainz' : 'solo orienta (pedido flexible)'}</li>{/if}
          {#if i.request.canon}<li><b>Busca:</b> lo fundamental, los imprescindibles</li>{/if}
          <li><b>Tipo:</b> {i.request.type ? TYPE[i.request.type] : 'cualquiera (de estudio)'}</li>
          <li><b>Modo:</b> {i.request.mode ? `${MODE[i.request.mode]} (${i.request.modeFrom === 'pedido' ? 'lo pediste' : 'del perfil activo'})` : 'ninguno'}</li>
          {#if i.request.hasText}<li><b>Tu texto:</b> “{i.request.text}”</li>{/if}
          {#if i.request.seed}<li><b>Parecido a:</b> {i.request.seed}</li>{/if}
        </ul>
      </div>
      <div class="g">
        <h5>Qué entendí de vos</h5>
        {#if i.profile.filled}
          <ul>
            {#if i.profile.instrument}<li>Toca <b>{i.profile.instrument}</b>{i.profile.level ? `, nivel ${i.profile.level}` : ''}</li>{/if}
            <li><b>Quiere mejorar:</b> {i.profile.focus.length ? i.profile.focus.join(', ') : i.profile.focusSkipped ? 'no se usa en este modo' : '—'}</li>
            <li><b>Descubrimiento:</b> {i.profile.discovery ? DISC[i.profile.discovery] : '—'}</li>
            {#if i.profile.loves.length}<li><b>Le gusta:</b> {i.profile.loves.join(', ')}</li>{/if}
            {#if i.profile.listening}<li>{LISTEN[i.profile.listening]}</li>{/if}
          </ul>
        {:else}<p class="muted small">Perfil sin completar: se usan tus fuentes y reacciones.</p>{/if}
      </div>
      <div class="g">
        <h5>Perfil de sugerencia</h5>
        <ul>
          <li><b>{i.preset.name ?? '—'}</b>{i.preset.how ? ` · ${HOW[i.preset.how]}` : ''}</li>
          {#if i.preset.intent && i.preset.intent !== 'libre'}<li>Intención: {i.preset.intent}</li>{/if}
          {#if i.preset.instrumental}<li>Mayormente instrumental</li>{/if}
          {#if i.preset.favor.length}<li>Favorece: {i.preset.favor.join(', ')}</li>{/if}
        </ul>
      </div>
      <div class="g">
        <h5>Cómo se decide</h5>
        <div class="bar2" title="Cercanía a tus gustos frente a novedad"><i style="width:{i.scoring.tastePct}%"></i></div>
        <ul>
          <li><b>Tipo de pedido:</b> {i.plan.label}</li>
          <li>Cercanía a tus gustos <b>{i.scoring.tastePct} %</b> · novedad {100 - i.scoring.tastePct} %</li>
          {#each i.plan.why as w (w)}<li class="muted">{w}</li>{/each}
          {#if i.scoring.genreWeightPct}<li>El género pesa <b>{i.scoring.genreWeightPct} %</b> en el puntaje</li>{/if}
          {#if i.scoring.textWeightPct}<li>Tu texto pesa <b>{i.scoring.textWeightPct} %</b> sobre tus gustos</li>{/if}
        </ul>
      </div>
      <div class="g wide">
        <h5>Tus gustos hoy</h5>
        <ul>
          <li><b>Artistas:</b> {names(i.taste.artists) || '—'}</li>
          <li><b>Géneros:</b> {names(i.taste.genres) || '—'}{i.taste.decades.length ? ` · décadas: ${names(i.taste.decades)}` : ''}</li>
        </ul>
        <p class="muted small">Armado con {i.taste.favorites} favoritos y {i.taste.reactions} reacciones; lo viejo pesa menos (la mitad a los {i.taste.halfLifeDays} días).</p>
      </div>
      <div class="g">
        <h5>Qué se deja afuera</h5>
        <ul>
          <li>{i.exclusions.known} discos que ya tenés o clasificaste</li>
          {#if i.exclusions.shownRecently}<li>{i.exclusions.shownRecently} mostrados hace poco</li>{/if}
          {#if i.profile.avoids.length}<li><b>Estilos que evitás:</b> {i.profile.avoids.join(', ')}</li>{/if}
          {#if i.profile.ownArtists.length}<li><b>Tu banda:</b> {i.profile.ownArtists.join(', ')} (nunca se recomienda)</li>{/if}
        </ul>
      </div>
      <div class="g">
        <h5>Contexto</h5>
        <p class="small">{i.context ?? 'No se usa la hora ni el clima.'}</p>
      </div>
      {#if i.planner?.enabled}
        {@const pl = i.planner}
        <div class="g wide">
          <h5>Cómo lo entendió el planificador <span class="op">opinión del modelo</span></h5>
          {#if !pl.ran}
            <p class="muted small">Sin texto que interpretar: se usaron solo las reglas.</p>
          {:else if !pl.ok}
            <p class="muted small">No pudo armar el plan: se siguió con las reglas.</p>
          {:else}
            <ul>
              <li><b>Época:</b> {pl.era ? `${pl.era.from}–${pl.era.to} · ${pl.era.source === 'reglas' ? 'la escribiste vos' : 'la entendió el modelo'}${pl.era.strict ? ' · se exige con el año de MusicBrainz' : ' · solo orienta (pedido flexible)'}` : 'no pediste una'}</li>
              <li><b>Ánimo:</b> {pl.mood ?? 'no dijiste uno'}{pl.instrumental === true ? ' · instrumental' : pl.instrumental === false ? ' · con voz' : ''}{pl.language ? ` · en ${pl.language}` : ''}</li>
              {#if pl.refs.length}<li><b>Referencias que nombraste:</b> {pl.refs.join(', ')}</li>{/if}
              {#if pl.brief}<li><b>Brief para el buscador:</b> <i>“{pl.brief}”</i></li>{/if}
            </ul>
            <p class="muted small">El ánimo, el idioma y el brief son opinión del modelo: orientan al buscador, no se verifican. Solo la época se comprueba con datos.{pl.dropped ? ` Descartó ${pl.dropped} ${pl.dropped === 1 ? 'valor inválido' : 'valores inválidos'}.` : ''}</p>
          {/if}
        </div>
      {/if}
      <div class="g wide">
        <h5>Cómo trabajan los agentes</h5>
        <ul>
          <li><b>Planificador:</b> {i.engine.planner ?? 'apagado'}</li>
          <li><b>Buscador:</b> {i.engine.model} · {i.engine.method === 'artistas' ? 'propone artistas y los discos salen de MusicBrainz' : 'propone discos'} · hasta {i.engine.maxRounds} rondas, objetivo {i.engine.target} discos</li>
          <li><b>Revisor:</b> {i.engine.reviewer ?? (i.engine.reviewerSkipped ? 'prendido, pero omitido: pediste solo un género y ya se verificó' : 'apagado')}</li>
          <li><b>Clasificador:</b> {i.engine.classifier ?? 'apagado'}</li>
          <li><b>Diversidad:</b> {Math.round(i.engine.diversity * 100)} % relevancia, {100 - Math.round(i.engine.diversity * 100)} % no repetirse</li>
        </ul>
      </div>
    </div>
  </details>
{/if}

{#if !agents.length}
  <section class="empty">
    <p>Todavía no hay una búsqueda para mostrar.</p>
    <a class="go" href="#/recomendaciones">Pedir una recomendación</a>
  </section>
{:else}
  <ol class="flow">
    {#each agents as a, i (a.id)}
      {@const t = toggles[a.id]}
      <li class="agent {a.state}">
        <div class="top">
          <span class="num" aria-hidden="true">{i + 1}</span>
          <h3>{a.label}</h3>
          <span class="pill"><i aria-hidden="true"></i>{STATE[a.state]}</span>
        </div>
        <p class="role">{a.role}</p>
        <dl>
          <dt>Modelo</dt><dd>{a.model ?? '—'}</dd>
          <dt>{a.state === 'running' ? 'Ahora' : 'Resumen'}</dt><dd>{a.detail || '—'}</dd>
          <dt>Tiempo</dt><dd>{a.seconds ? `${a.seconds} s` : '—'}{a.calls ? ` · ${a.calls} ${a.calls === 1 ? 'consulta' : 'consultas'}` : ''}</dd>
        </dl>
        {#if t}
          <button class="ghost" disabled={running || !settings.config} onclick={() => settings.save(t.patch(t.on()))}>{t.on() ? 'Apagar' : 'Prender'}</button>
        {/if}
      </li>
    {/each}
  </ol>

  <section class="feed-box">
    <h4>Qué fueron decidiendo</h4>
    {#if log.length}
      <ul class="feed" bind:this={feed} aria-live="polite">
        {#each log as e, i (i)}
          <li class={e.kind}>
            <span class="t">{e.t.toFixed(1)} s</span>
            <span class="who {e.agent}">{WHO[e.agent] ?? e.agent}</span>
            <span class="txt">{e.text}</span>
            {#if KIND[e.kind]}<span class="kind">{KIND[e.kind]}</span>{/if}
          </li>
        {/each}
      </ul>
    {:else}
      <p class="muted small">Sin movimientos todavía.</p>
    {/if}
    <p class="muted small">Cada línea sale de datos del motor (MusicBrainz, la barrera de género, los veredictos). La opinión del revisor y del clasificador se muestra como tal, no como un hecho verificado.</p>
  </section>
{/if}

<style>
  .head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
  h2 { margin: 0; font-size: 28px; letter-spacing: -0.02em; }
  h3 { margin: 0; font-size: 17px; flex: 1; }
  h4 { margin: 0 0 8px; font-size: 14px; letter-spacing: 0.04em; text-transform: uppercase; color: var(--muted); }
  .small { font-size: 13px; margin: 0; }
  .intro { margin: 0; max-width: 78ch; }
  .live { display: inline-flex; align-items: center; gap: 8px; color: #7cc7a3; font-size: 14px; }
  .live i, .pill i { width: 8px; height: 8px; border-radius: 50%; background: currentColor; display: inline-block; }
  .live i, .agent.running .pill i { animation: pulse 1.2s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: 0.25; transform: scale(0.8); } }
  .vars { border-radius: var(--radius); background: var(--glass); border: 1px solid var(--glass-line); padding: 12px 16px; }
  .vars summary { cursor: pointer; font-weight: 600; }
  .lead { margin: 6px 0 12px; }
  .groups { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 16px 22px; }
  .g { min-width: 0; }
  .g.wide { grid-column: span 2; }
  @media (max-width: 700px) { .g.wide { grid-column: auto; } }
  .g h5 { margin: 0 0 6px; font-size: 12.5px; letter-spacing: 0.05em; text-transform: uppercase; color: var(--muted); }
  .g ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; font-size: 14px; }
  .g li { overflow-wrap: anywhere; }
  .g b { font-weight: 600; }
  .op { margin-left: 6px; font-size: 11px; letter-spacing: 0; text-transform: none; border: 1px solid var(--glass-line); border-radius: 999px; padding: 0 8px; }
  .bar2 { height: 5px; border-radius: 3px; background: var(--line); overflow: hidden; margin-bottom: 8px; }
  .bar2 i { display: block; height: 100%; border-radius: 3px; background: linear-gradient(90deg, #4fa3d9, #7cc7a3); }
  .flow { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; }
  .agent { position: relative; display: grid; gap: 10px; align-content: start; padding: 16px; border-radius: var(--radius); background: var(--glass); border: 1px solid var(--glass-line); transition: border-color 0.3s, box-shadow 0.3s, opacity 0.3s; }
  .agent.running { border-color: rgba(124, 199, 163, 0.6); box-shadow: 0 0 28px -8px rgba(124, 199, 163, 0.45); }
  .agent.skipped { opacity: 0.6; }
  @media (min-width: 900px) { .agent:not(:last-child)::after { content: '→'; position: absolute; right: -14px; top: 22px; width: 14px; text-align: center; color: var(--muted); } }
  .top { display: flex; align-items: center; gap: 10px; }
  .num { width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center; font-size: 13px; font-weight: 600; border: 1px solid var(--glass-line); color: var(--muted); }
  .pill { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; padding: 2px 10px; border-radius: 999px; border: 1px solid var(--glass-line); color: var(--muted); }
  .agent.running .pill { color: #7cc7a3; border-color: rgba(124, 199, 163, 0.5); }
  .agent.done .pill { color: var(--text); }
  .agent.cancelled .pill { color: #f0a43c; border-color: rgba(240, 164, 60, 0.5); }
  .role { margin: 0; color: var(--muted); font-size: 14px; }
  dl { margin: 0; display: grid; grid-template-columns: max-content 1fr; gap: 4px 14px; font-size: 14px; }
  dt { color: var(--muted); }
  dd { margin: 0; min-width: 0; overflow-wrap: anywhere; }
  .agent button { justify-self: start; padding: 4px 12px; font-size: 13.5px; }
  .feed-box { display: grid; gap: 6px; padding: 14px 16px; border-radius: var(--radius); background: var(--glass); border: 1px solid var(--glass-line); }
  .feed { list-style: none; margin: 0; padding: 0; max-height: 360px; overflow: auto; display: grid; gap: 2px; font-size: 14px; }
  .feed li { display: grid; grid-template-columns: 52px 96px 1fr auto; gap: 10px; align-items: baseline; padding: 4px 0; border-bottom: 1px solid rgba(255, 255, 255, 0.04); }
  .t { color: var(--muted); font-variant-numeric: tabular-nums; font-size: 12.5px; }
  .who { font-size: 12.5px; font-weight: 600; }
  .who.planificador { color: #7cc7a3; }
  .who.buscador { color: #4fa3d9; }
  .who.revisor { color: #f0a43c; }
  .who.clasificador { color: #c58bf0; }
  .txt { min-width: 0; overflow-wrap: anywhere; }
  .kind { font-size: 11.5px; color: var(--muted); border: 1px solid var(--glass-line); border-radius: 999px; padding: 0 8px; }
  li.discard .txt { color: var(--muted); }
  li.warn .kind { color: #f0a43c; border-color: rgba(240, 164, 60, 0.45); }
  li.ok .kind { color: #7cc7a3; border-color: rgba(124, 199, 163, 0.4); }
  .empty { padding: 28px 8px; display: grid; gap: 12px; justify-items: start; }
  .empty p { margin: 0; font-size: 18px; }
  .go { padding: 8px 16px; border-radius: 10px; background: var(--text); color: var(--bg); font-weight: 600; text-decoration: none; }
  @media (max-width: 700px) { .feed li { grid-template-columns: 44px 1fr; } .who { grid-column: 2; } .txt { grid-column: 1 / -1; } .kind { display: none; } }
  @media (prefers-reduced-motion: reduce) { .live i, .agent.running .pill i { animation: none; } }
</style>
