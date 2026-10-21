<script lang="ts">
  import Cover from './Cover.svelte';
  import Icon from './Icon.svelte';
  import Volume from './Volume.svelte';
  import { playback } from '../lib/playback.svelte';
  import { separation } from '../lib/separation.svelte';

  let queueOpen = $state(false);
  let panel = $state<HTMLElement>();
  const mm = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
  const cur = $derived(playback.current);
  const dur = $derived(playback.duration);
  const many = $derived(playback.queue.length > 1);
  const job = $derived(playback.job);
  const running = $derived(job?.state === 'running');

  // Mientras el panel está abierto, el tema actual queda a la vista; Escape lo cierra.
  $effect(() => { if (queueOpen && panel) panel.querySelector('[aria-current="true"]')?.scrollIntoView({ block: 'nearest' }); });
</script>

<svelte:window onkeydown={e => { if (e.key === 'Escape' && queueOpen) queueOpen = false; }} />

<div class="ps">
  <div class="meta">
    <Cover title={cur?.album || cur?.title || ''} artist={cur?.artist ?? ''} size={56} radius={10} src={playback.currentArt} />
    <div class="txt">
      <b title={cur?.title}>{cur?.title}</b>
      <span class="muted">{cur?.artist}</span>
      {#if many}<span class="muted num n">{playback.index + 1} de {playback.queue.length}</span>{/if}
    </div>
  </div>

  <div class="ctl">
    <div class="btns">
      <button class="ib" onclick={() => playback.prev()} aria-label="Anterior" title="Anterior (después de 3 s vuelve al principio)"><Icon name="anterior" size={20} /></button>
      <button class="play" class:live={playback.playing} onclick={() => playback.toggle()} aria-label={playback.playing ? 'Pausar' : 'Reproducir'}>
        {#if playback.loading}
          <span class="spin" aria-hidden="true"></span>
        {:else if playback.playing}
          <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>
        {:else}
          <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.5-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5Z"/></svg>
        {/if}
      </button>
      <button class="ib" onclick={() => playback.next()} disabled={!playback.hasNext} aria-label="Siguiente" title="Siguiente"><Icon name="siguiente" size={20} /></button>
    </div>
    <div class="prog">
      <span class="num muted t">{mm(playback.position)}</span>
      <input type="range" min="0" max={dur || 1} step="0.5" value={Math.min(playback.position, dur || 1)} style="--pct:{dur ? (playback.position / dur) * 100 : 0}%"
        oninput={e => playback.seek(+e.currentTarget.value)} disabled={!dur} aria-label="Posición" />
      <span class="num muted t">{dur ? mm(dur) : '--:--'}</span>
    </div>
    {#if playback.failed}<span class="err" role="alert">No se pudo reproducir. Probá de nuevo con play.</span>{/if}
  </div>

  <div class="side">
    {#if running}
      <span class="sep num" role="status" title="Separando en instrumentos"><span class="spin s" aria-hidden="true"></span>{separation.label(playback.currentId)}</span>
    {:else if playback.separated}
      <button class="studio" onclick={() => playback.toStudio()} aria-label="Abrir en el Estudio" title="Este tema ya está separado: abrirlo en el Estudio"><Icon name="estudio" size={16} /><span class="lbl">Abrir en el Estudio</span></button>
    {:else}
      <button class="studio" onclick={() => playback.toStudio()} disabled={!playback.currentId || separation.busy} aria-label="Enviar al Estudio" title={separation.busy ? 'Ya hay una separación en curso' : 'Separar en instrumentos para estudiar'}>
        <Icon name="estudio" size={16} /><span class="lbl">{job?.state === 'error' ? 'Reintentar la separación' : 'Enviar al Estudio'}</span>
      </button>
    {/if}
    <Volume />
    <button class="ib q" class:on={queueOpen} onclick={() => (queueOpen = !queueOpen)} aria-expanded={queueOpen} aria-label="Cola" title="Cola"><Icon name="cola" size={19} /></button>
    <button class="ib" onclick={() => playback.stop()} aria-label="Cerrar el reproductor" title="Detener y cerrar (vuelve al Estudio si hay un tema cargado)"><Icon name="cerrar" size={18} /></button>
  </div>

  {#if job?.state === 'error'}<p class="err full" role="alert">{job.message}</p>{/if}

  {#if queueOpen}
    <div class="queue" bind:this={panel} role="dialog" aria-label="Cola de reproducción">
      <div class="qh"><b>En cola</b><span class="muted num">{playback.queue.length}</span></div>
      <ol>
        {#each playback.queue as it, i (i + it.key)}
          <li><button class:cur={i === playback.index} aria-current={i === playback.index ? 'true' : undefined} onclick={() => playback.jump(i)}>
            <span class="qn num muted">{i === playback.index && playback.playing ? '▶' : i + 1}</span>
            <span class="qt"><b>{it.title}</b><span class="muted">{it.artist}</span></span>
          </button></li>
        {/each}
      </ol>
    </div>
  {/if}
</div>

<style>
  .ps { position: relative; max-width: 2200px; margin: 0 auto; display: flex; align-items: center; flex-wrap: wrap; gap: 10px 28px; }
  .meta { flex: 1 1 230px; min-width: 0; display: flex; align-items: center; gap: 12px; }
  .meta :global(.cv), .meta :global(svg) { flex: none; }
  .txt { display: grid; min-width: 0; line-height: 1.25; }
  .txt b, .txt span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .txt b { font-weight: 600; }
  .n { font-size: 12.5px; }
  .ctl { flex: 2 1 320px; min-width: 0; display: grid; gap: 2px; justify-items: center; }
  .btns { display: flex; align-items: center; gap: 10px; }
  .ib { width: 36px; height: 36px; padding: 0; display: grid; place-items: center; border-radius: 50%; background: transparent; border-color: transparent; }
  .ib.on { background: rgba(255, 255, 255, 0.14); }
  .play { width: 46px; height: 46px; border-radius: 50%; padding: 0; display: grid; place-items: center; background: var(--text); color: var(--bg); border-color: var(--text); position: relative; transition: transform 0.15s var(--ease), box-shadow 0.4s; }
  .play:hover:not(:disabled) { background: #fff; border-color: #fff; }
  .play svg { fill: currentColor; }
  .play.live { box-shadow: 0 0 0 0 rgba(255, 255, 255, 0.45); animation: ring 2.2s ease-out infinite; }
  @keyframes ring { to { box-shadow: 0 0 0 14px rgba(255, 255, 255, 0); } }
  .prog { display: flex; align-items: center; gap: 10px; width: 100%; max-width: 640px; }
  .prog input { flex: 1; min-width: 0; }
  .t { font-size: 12.5px; min-width: 38px; }
  .t:first-child { text-align: right; }
  .side { flex: 1 1 430px; display: flex; align-items: center; justify-content: flex-end; gap: 6px; flex-wrap: wrap; }
  .studio { display: inline-flex; align-items: center; gap: 7px; border-radius: 999px; padding: 6px 13px; font-size: 13.5px; white-space: nowrap; margin-right: 4px; }
  .sep { display: inline-flex; align-items: center; gap: 8px; font-size: 13.5px; color: var(--muted); padding: 0 6px; white-space: nowrap; }
  .spin { width: 14px; height: 14px; border-radius: 50%; border: 2px solid currentColor; border-right-color: transparent; animation: spin 0.8s linear infinite; }
  .spin.s { width: 12px; height: 12px; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .err { color: var(--loop); font-size: 13px; margin: 0; }
  .full { flex: 1 1 100%; text-align: right; }
  .queue { position: absolute; right: 0; bottom: calc(100% + 18px); width: min(430px, 100%); max-height: min(46vh, 380px); overflow: auto; padding: 8px; border-radius: 16px; background: rgba(15, 26, 29, 0.97); border: 1px solid var(--glass-line); box-shadow: 0 24px 60px -20px rgba(0, 0, 0, 0.85); animation: rise 0.25s var(--ease) both; }
  .qh { display: flex; gap: 8px; align-items: baseline; padding: 4px 8px 8px; }
  ol { list-style: none; margin: 0; padding: 0; display: grid; gap: 1px; }
  ol button { width: 100%; display: grid; grid-template-columns: 26px 1fr; gap: 8px; align-items: center; text-align: left; background: transparent; border-color: transparent; padding: 6px 8px; border-radius: 10px; }
  ol button:hover { background: rgba(255, 255, 255, 0.07); }
  ol button.cur { background: rgba(255, 255, 255, 0.12); }
  .qn { text-align: right; font-size: 12.5px; }
  .qt { display: grid; min-width: 0; line-height: 1.25; }
  .qt b, .qt span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .qt b { font-weight: 600; font-size: 14px; }
  .qt span { font-size: 12.5px; }
  @media (max-width: 760px) {
    .ps { gap: 6px 12px; }
    .meta { flex-basis: 100%; }
    .ctl { flex-basis: 100%; }
    .side { flex-basis: 100%; justify-content: space-between; flex-wrap: nowrap; }
    .studio { margin-right: 0; }
    .studio .lbl { display: none; }
    .studio { padding: 8px; }
  }
</style>
