<script lang="ts">
  import Cover from './Cover.svelte';
  import { sendToStudio } from '../lib/studio';
  import { toast } from '../lib/toast.svelte';
  import { player } from '../lib/player.svelte';
  import { separation } from '../lib/separation.svelte';
  import { playback, queueItem, type QItem } from '../lib/playback.svelte';
  import { resolveId } from '../lib/resolve';
  import { seed } from '../lib/seed.svelte';
  import { nav } from '../lib/nav.svelte';
  import OpenIn from './OpenIn.svelte';

  let { title, artist, meta = '', duration = '', localId, origin = false, badge = '', sourceId, resolve = false, album = '', ids, art, links, compact = false, n = 0, queue, qi = 0 }:
    { compact?: boolean; n?: number; queue?: QItem[]; qi?: number; title: string; artist: string; meta?: string; duration?: string; localId?: string; origin?: boolean; badge?: string; sourceId?: string; resolve?: boolean; album?: string; ids?: { local?: string; tidal?: string }; art?: string; links?: Record<string, string> } = $props();

  // Un tema "referencia" (de favoritos, playlists...) no trae su audio: se busca con el orden de fuentes de Ajustes.
  let resolved = $state<string | null>(null);
  let resolving = $state(false);
  // Con `ids` (mapa por fuente) el motor elige el id según el orden global; "separado" es cualquiera de los ids.
  const idList = $derived(ids ? Object.values(ids).filter((x): x is string => !!x) : []);
  const sepId = $derived(idList.find(i => player.tracks.some(t => t.id === i)));
  const self = $derived(queueItem({ title, artist, album, ids, sourceId, resolve, art }));
  // El motor puede haber elegido ya la fuente al reproducir (la cola la guarda en el item).
  const here = $derived(playback.isCurrent(self.key));
  const queued = $derived(here ? playback.current?.pid : undefined);
  const pid = $derived(ids ? (sepId ?? resolved ?? queued ?? idList[0]) : (resolved ?? queued ?? sourceId));
  const separated = $derived(ids ? !!sepId : resolve ? !!pid && player.tracks.some(t => t.id === pid) : !sourceId || player.tracks.some(t => t.id === sourceId));
  const job = $derived(pid ? separation.jobs[pid] : undefined);
  const going = $derived(here && playback.playing);

  async function ensure(): Promise<string | null> {
    if (resolved) return resolved;
    if (!resolve && !ids) return sourceId ?? null;
    resolving = true;
    try {
      const id = await resolveId(self);
      if (id) resolved = id;
      return id;
    } finally { resolving = false; }
  }
  // Va a la cola de la fachada (la lista de su álbum, o solo este tema); la fuente se elige cuando le toca.
  function listen() {
    if (here) { playback.toggle(); return; }
    const list = queue?.length ? queue : [self];
    playback.playFrom(list, queue?.length ? qi : 0);
  }
  async function separate() { const id = await ensure(); if (id) separation.start(id); }
</script>

<li class="trk"><div class="track" class:here class:going class:compact class:numbered={compact && n > 0}>
  {#if compact && n > 0}
    <span class="n muted num">{n}</span>
  {:else}
    <Cover {title} {artist} size={compact ? 44 : 48} radius={8} src={art ?? (pid ? `/engine/art/${pid}` : undefined)} />
  {/if}
  <div class="txt">
    <b>{#if here}<span class="eq" class:still={!going} aria-hidden="true"><i></i><i></i><i></i></span>{/if}{title}{#if badge && !compact} <span class="badge">{badge}</span>{/if}</b>
    {#if !(compact && n > 0)}<span class="muted">{artist}{meta ? `, ${meta}` : ''}</span>{/if}
  </div>
  <span class="muted num dur">{duration}</span>
  {#if compact}
  <div class="acts ic">
    <!-- Dentro de una cola (álbum) ▶ siempre escucha; un tema suelto ya separado se abre en el Estudio. -->
    {#if separated && !queue?.length}
      <button class="ib primary" onclick={() => sendToStudio({ title, artist, localId: pid ?? localId }, { play: true })} title="Reproducir en el Estudio" aria-label="Reproducir en el Estudio">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true"><path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.5-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5Z"/></svg>
      </button>
    {:else}
      <button class="ib primary" onclick={listen} aria-pressed={going} title={going ? 'Pausar' : 'Escuchar'} aria-label={going ? 'Pausar' : 'Escuchar'}>
        {#if going}
          <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>
        {:else if (here && playback.loading) || resolving}
          <span class="spin" aria-hidden="true"></span>
        {:else}
          <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true"><path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.5-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5Z"/></svg>
        {/if}
      </button>
    {/if}
    {#if separated}
      <button class="ib" onclick={() => sendToStudio({ title, artist, localId: pid ?? localId })} title="Abrir en el Estudio" aria-label="Abrir en el Estudio">
        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 17L17 7M9 7h8v8"/></svg>
      </button>
    {:else if job?.state === 'running'}
      <span class="pct num" role="status" title={separation.label(pid!)}>{job.percent ?? 0} %</span>
      <button class="ib sep" onclick={() => separation.cancel(pid!)} title="Cancelar la separación">Cancelar</button>
    {:else}
      <button class="ib sep" disabled={separation.busy || resolving} onclick={separate} title={separation.busy ? 'Ya hay una separación en curso' : 'Separar en instrumentos para estudiar'}>Separar</button>
    {/if}
    {#if ids}
      <button class="ib" onclick={() => { seed.set({ artist, album: album || undefined, title }); nav.go('recomendaciones'); }} title="Recomendar parecidos" aria-label="Recomendar parecidos">
        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l2 5.5 5.5 2-5.5 2L12 18l-2-5.5L4.5 10.5l5.5-2zM19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/></svg>
      </button>
    {/if}
    <OpenIn {links} size={14} />
    {#if job?.state === 'error'}<span class="err" role="alert" title={job.message}>!</span>{/if}
  </div>
  {:else}
  <div class="acts">
    {#if separated}
      <button class="primary" onclick={() => sendToStudio({ title, artist, localId: pid ?? localId }, { play: true })}>Reproducir</button>
      <button class="ghost" onclick={() => sendToStudio({ title, artist, localId: pid ?? localId })}>Enviar al estudio</button>
    {:else if job?.state === 'running'}
      <button class="primary" disabled>{separation.label(pid!)}</button>
    {:else}
      <button class="primary" disabled={separation.busy || resolving} onclick={separate} title={separation.busy ? 'Ya hay una separación en curso' : ''}>{resolving ? 'Buscando…' : 'Separar para estudiar'}</button>
    {/if}
    {#if (sourceId || resolve || ids) && !separated}
      <button class="ghost" onclick={listen} aria-pressed={going}>{going ? 'Pausar' : here && playback.loading ? 'Cargando…' : 'Escuchar'}</button>
    {/if}
    {#if job?.state === 'error'}<span class="err" role="alert">{job.message}</span>{/if}
    {#if ids}
      <button class="ghost" onclick={() => { seed.set({ artist, album: album || undefined, title }); nav.go('recomendaciones'); }}>Recomendar parecidos</button>
    {:else}
      <button class="ghost" onclick={() => toast.show('Esto funciona cuando haya un modelo de recomendación conectado (Fase 4).')}>Más como este</button>
    {/if}
    {#if origin}<button class="ghost" onclick={() => toast.show('Se abrirá en la app de origen cuando la fuente esté conectada.')}>Abrir en el origen</button>{/if}
  </div>
  {/if}
</div></li>

<style>
  .trk { container-type: inline-size; list-style: none; }
  .track { display: grid; grid-template-columns: 48px 1fr auto auto; align-items: center; gap: 14px; padding: 8px 12px; border-radius: 12px; transition: background 0.2s; }
  .track:hover { background: rgba(255, 255, 255, 0.05); }
  .txt { display: grid; min-width: 0; }
  .txt b, .txt span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .dur { font-size: 13px; }
  .badge { font-size: 11.5px; font-weight: 600; color: #7cc7a3; border: 1px solid color-mix(in srgb, #7cc7a3 50%, transparent); border-radius: 999px; padding: 0 8px; margin-left: 6px; vertical-align: 1px; }
  .track.compact { grid-template-columns: 44px 1fr auto auto; gap: 10px; padding: 5px 8px; }
  .track.compact.numbered { grid-template-columns: 22px 1fr auto auto; }
  .n { text-align: right; font-size: 13px; }
  .acts.ic { opacity: 1; align-items: center; gap: 4px; }
  .ib { min-width: 30px; height: 30px; padding: 0; display: grid; place-items: center; border-radius: 50%; background: transparent; border: 1px solid var(--glass-line); color: var(--text); }
  .ib.primary { background: var(--text); color: var(--bg); border-color: var(--text); }
  .ib.sep { border-radius: 999px; padding: 0 12px; font-size: 13px; }
  .pct { font-size: 12.5px; color: var(--muted); min-width: 44px; text-align: center; }
  .spin { width: 12px; height: 12px; border-radius: 50%; border: 2px solid currentColor; border-right-color: transparent; animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .acts { display: flex; gap: 6px; opacity: 0.55; transition: opacity 0.2s; }
  .track:hover .acts, .track:focus-within .acts { opacity: 1; }
  .acts button { white-space: nowrap; }
  .primary { background: var(--text); color: var(--bg); border-color: var(--text); font-weight: 600; }
  .ghost { background: transparent; }
  .track.here { background: rgba(255, 255, 255, 0.09); }
  .eq { display: inline-flex; align-items: flex-end; gap: 2px; height: 11px; margin-right: 7px; vertical-align: -1px; }
  .eq i { width: 3px; height: 100%; background: var(--loop); border-radius: 1px; transform-origin: bottom; animation: eq 0.9s ease-in-out infinite; }
  .eq i:nth-child(2) { animation-delay: -0.3s; } .eq i:nth-child(3) { animation-delay: -0.6s; }
  .eq.still i { animation: none; transform: scaleY(0.35); }
  @keyframes eq { 0%, 100% { transform: scaleY(0.3); } 50% { transform: scaleY(1); } }
  .err { color: var(--loop); font-size: 13px; align-self: center; }
  @container (max-width: 640px) { .track:not(.compact) { grid-template-columns: 48px 1fr; } .track:not(.compact) .acts { grid-column: 1 / -1; opacity: 1; flex-wrap: wrap; } .track:not(.compact) .dur { display: none; } }
  @container (max-width: 380px) { .track.compact .dur { display: none; } }
</style>
