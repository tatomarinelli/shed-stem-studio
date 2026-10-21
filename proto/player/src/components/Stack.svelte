<script lang="ts">
  import { player, STEM_LABELS, STEM_COLORS } from '../lib/player.svelte';
  import { view, MAX_PPS } from '../lib/view.svelte';
  import Wave from './Wave.svelte';
  import BeatGrid from './BeatGrid.svelte';
  import { analysis } from '../lib/analysis.svelte';

  let width = $state(800);
  let innerH = $state(900);
  let drag: { x0: number; t0: number; moved: boolean } | null = $state(null);
  let dragB = $state<number | null>(null);
  let area: HTMLDivElement;
  let editing = $state('');
  let thumbDrag: { x0: number; s0: number } | null = null;

  // Las pistas se estiran para llenar el alto libre de la ventana (entre 84 y 220 px).
  const rowH = $derived(Math.round(Math.max(84, Math.min(220, (innerH - 360) / Math.max(1, player.stems.length)))));
  const dur = $derived(player.duration || 1);
  $effect(() => { view.setViewport(width); });
  $effect(() => { view.dur = dur; });

  const timeAt = (clientX: number) => {
    return Math.max(0, Math.min(dur, view.t(clientX - area.getBoundingClientRect().left - area.clientLeft)));
  };

  // Ctrl + rueda: zoom bajo el cursor. Shift + rueda (o rueda horizontal): desplazar. La rueda sola sigue moviendo la página.
  $effect(() => {
    const el = area;
    const onWheel = (e: WheelEvent) => {
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        view.zoomWheel(e.clientX - el.getBoundingClientRect().left - el.clientLeft, e.deltaY); // sin el borde de 1 px
      } else if (e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
        e.preventDefault();
        view.scrollBy(e.deltaX || e.deltaY);
      }
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  });

  // Con zoom, el cabezal acompaña la reproducción.
  $effect(() => { if (view.follow && player.playing && view.zoomed) view.keepVisible(player.position); });

  // Marcas de la regla: el paso crece hasta que haya al menos 80 px entre marcas; solo las visibles.
  const ticks = $derived.by(() => {
    const steps = [0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300];
    const step = steps.find(s => s * view.pps >= 80) ?? 300;
    const out: { t: number; label: string }[] = [];
    const t0 = Math.max(0, Math.floor(view.t(0) / step) * step), t1 = Math.min(dur, view.t(view.viewW));
    for (let t = t0; t <= t1 + 1e-6; t += step) {
      const m = Math.floor(t / 60), s = t - m * 60;
      out.push({ t, label: step < 1 ? `${m}:${s.toFixed(1).padStart(4, '0')}` : `${m}:${String(Math.round(s)).padStart(2, '0')}` });
    }
    return out;
  });

  function rulerDown(e: PointerEvent) {
    player.selectedSection = '';
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    const t = timeAt(e.clientX);
    drag = { x0: e.clientX, t0: t, moved: false };
    dragB = t;
  }
  function rulerMove(e: PointerEvent) {
    if (!drag) return;
    if (Math.abs(e.clientX - drag.x0) > 4) drag.moved = true;
    dragB = timeAt(e.clientX);
  }
  function rulerUp(e: PointerEvent) {
    if (!drag) return;
    const t1 = timeAt(e.clientX);
    if (drag.moved && Math.abs(t1 - drag.t0) > 0.05) {
      const [a, b] = drag.t0 < t1 ? [drag.t0, t1] : [t1, drag.t0];
      player.setLoopA(a); player.setLoopB(b);
    } else player.seek(t1);
    drag = null; dragB = null;
  }

  const band = $derived.by(() => {
    if (drag?.moved && dragB != null) return { a: Math.min(drag.t0, dragB), b: Math.max(drag.t0, dragB), live: true };
    if (player.loopA != null) return { a: player.loopA, b: player.loopB ?? player.loopA, live: false };
    return null;
  });

  // Barra de desplazamiento (solo con zoom): el pulgar es la parte visible del tema.
  const thumb = $derived({ left: (view.scroll / view.totalW) * 100, width: Math.min(100, (view.viewW / view.totalW) * 100) });
  function thumbDown(e: PointerEvent) { (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId); thumbDrag = { x0: e.clientX, s0: view.scroll }; }
  function thumbMove(e: PointerEvent) {
    if (!thumbDrag) return;
    const track = (e.currentTarget as HTMLElement).parentElement!.getBoundingClientRect().width;
    view.scrollTo(thumbDrag.s0 + ((e.clientX - thumbDrag.x0) / track) * view.totalW);
  }
  const thumbUp = () => (thumbDrag = null);

  // Arrastrar el borde de una sección con el mouse.
  let edge: { id: string; which: 'start' | 'end' } | null = null;
  function edgeDown(e: PointerEvent, id: string, which: 'start' | 'end') {
    e.stopPropagation();
    try { (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId); } catch { /* sin captura: sigue funcionando dentro del borde */ }
    edge = { id, which };
    player.selectedSection = id;
  }
  function edgeMove(e: PointerEvent) { if (edge) player.setSectionEdge(edge.id, edge.which, timeAt(e.clientX)); }
  const edgeUp = () => (edge = null);

  const SEC_HUES = [38, 200, 150, 320, 10, 260];
  const secColor = (i: number) => `hsl(${SEC_HUES[i % SEC_HUES.length]} 70% 62%)`;
  function rename(id: string, e: Event) {
    const v = (e.currentTarget as HTMLInputElement).value;
    player.renameSection(id, v); editing = '';
  }
</script>

<svelte:window bind:innerHeight={innerH} />

<section class="stack" style="--rowh:{rowH}px">
  <div class="labels">
    <div class="corner">
      <button class="zb" onclick={() => view.zoomAt(view.viewW / 2, 1 / 1.4)} disabled={!view.zoomed} aria-label="Alejar" title="Alejar (Ctrl + rueda)">−</button>
      <button class="zb" onclick={() => view.zoomAt(view.viewW / 2, 1.4)} disabled={view.pps >= MAX_PPS} aria-label="Acercar" title="Acercar (Ctrl + rueda)">+</button>
      <button class="zb wide" onclick={() => view.fit()} disabled={!view.zoomed} title="Ver el tema entero">Ajustar</button>
      <button class="zb wide" class:on={view.follow} onclick={() => (view.follow = !view.follow)} aria-pressed={view.follow} title="El cabezal acompaña la reproducción">Seguir</button>
    </div>
    <div class="lane-lab"><button class="zb wide" onclick={() => player.addSection()} title="Marcar una sección en el cabezal (M)">+ Sección</button></div>
    {#if analysis.data && analysis.showChords}<div class="lane-lab chl muted">Acordes</div>{/if}
    {#each player.stems as s, i (s.name)}
      <div class="lab" class:off={s.mute} style="--c:{STEM_COLORS[s.name] ?? '#8ea4a7'}">
        <div class="name"><span class="dot"></span>{STEM_LABELS[s.name] ?? s.name}</div>
        <div class="ctl">
          <button class="ms" class:on={s.mute} onclick={() => player.toggleMute(i)} title="Silenciar" aria-pressed={s.mute}>M</button>
          <button class="ms" class:on={s.solo} onclick={() => player.toggleSolo(i)} title="Solo" aria-pressed={s.solo}>S</button>
          <input type="range" min="0" max="1.5" step="0.01" value={s.gain} style="--pct:{(s.gain / 1.5) * 100}%;--fill:{STEM_COLORS[s.name] ?? '#e7eeee'}" ondblclick={() => player.setGain(i, 1)} title="Doble clic: volumen 100 %" oninput={e => player.setGain(i, +e.currentTarget.value)} aria-label="Volumen de {STEM_LABELS[s.name] ?? s.name}" />
        </div>
      </div>
    {/each}
  </div>

  <div class="timeline" bind:this={area} bind:clientWidth={width}>
    <div class="ruler" onpointerdown={rulerDown} onpointermove={rulerMove} onpointerup={rulerUp} role="slider" tabindex="-1" aria-label="Regla de tiempo" aria-valuenow={player.position}>
      {#each ticks as k (k.t)}
        <span class="tick num" style="left:{view.x(k.t)}px">{k.label}</span>
      {/each}
    </div>
    <div class="lane">
      {#each player.sections as sec, i (sec.id)}
        {@const x0 = view.x(sec.start)}{@const x1 = view.x(sec.end)}
        {#if x1 > 0 && x0 < view.viewW}
          {@const looped = player.loopSectionId === sec.id && player.loopOn}
          <div class="sec" class:cur={player.currentSection === i} class:sel={player.selectedSection === sec.id} class:looped class:cut={x0 < 0}
            style="left:{Math.max(0, x0)}px;width:{Math.max(4, x1 - Math.max(0, x0))}px;--c:{secColor(i)}">
            {#if x0 >= 0}<!-- svelte-ignore a11y_no_static_element_interactions --><div class="h l" onpointerdown={e => edgeDown(e, sec.id, 'start')} onpointermove={edgeMove} onpointerup={edgeUp} onpointercancel={edgeUp}></div>{/if}
            {#if editing === sec.id}
              <input class="ren" value={sec.name} maxlength="12" onblur={e => rename(sec.id, e)} onkeydown={e => { if (e.key === 'Enter') e.currentTarget.blur(); if (e.key === 'Escape') editing = ''; }} />
            {:else}
              <button class="nm" onclick={() => player.goSection(i)} ondblclick={() => player.loopSection(i)} oncontextmenu={e => { e.preventDefault(); editing = sec.id; }}
                title="Clic: ir y seleccionar. Doble clic: repetir. Clic derecho: renombrar. Supr: borrar. Arrastrá los bordes para cambiar la duración">{#if looped}<span class="lp" aria-label="en loop">↻</span>{/if}{sec.name}</button>
              <button class="x" onclick={() => player.removeSection(sec.id)} aria-label="Quitar la sección {sec.name}">×</button>
            {/if}
            {#if x1 <= view.viewW}<!-- svelte-ignore a11y_no_static_element_interactions --><div class="h r" onpointerdown={e => edgeDown(e, sec.id, 'end')} onpointermove={edgeMove} onpointerup={edgeUp} onpointercancel={edgeUp}></div>{/if}
          </div>
        {/if}
      {/each}
    </div>
    {#if analysis.data && analysis.showChords}
      <div class="lane chords">
        {#each analysis.data.chords as c, i (i)}
          {@const x0 = view.x(c.start)}{@const x1 = view.x(c.end)}
          {#if x1 > 0 && x0 < view.viewW && c.label !== 'N'}
            <button class="ch" class:cur={analysis.chordAt(player.position) === c} style="left:{Math.max(0, x0)}px;width:{Math.max(2, x1 - Math.max(0, x0)) - 1}px;opacity:{0.45 + 0.55 * c.confidence}"
              onclick={() => player.seek(c.start)} title="{c.label} ({Math.round(c.confidence * 100)} %)">{x1 - x0 >= 26 ? c.label : ''}</button>
          {/if}
        {/each}
      </div>
    {/if}
    <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
    <div class="rows" onclick={e => { player.selectedSection = ''; player.seek(timeAt(e.clientX)); }}>
      {#each player.stems as s, i (s.name)}
        <div class="row" class:off={s.mute} style="--n:{i}"><Wave {i} h={rowH} /></div>
      {/each}
      <BeatGrid h={rowH * player.stems.length} />
    </div>
    {#if band}
      <div class="band" class:live={band.live} class:idle={!player.loopOn && !band.live} style="left:{view.x(band.a)}px;width:{Math.max(2, view.x(band.b) - view.x(band.a))}px"></div>
    {/if}
    <div class="head" style="transform:translateX({view.x(player.position)}px)"></div>
    {#if view.zoomed}
      <div class="scroller" aria-hidden="true">
        {#if band}<i class="mini-band" style="left:{(band.a / dur) * 100}%;width:{Math.max(0.4, ((band.b - band.a) / dur) * 100)}%"></i>{/if}
        <i class="mini-head" style="left:{(player.position / dur) * 100}%"></i>
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <div class="thumb" style="left:{thumb.left}%;width:{thumb.width}%" onpointerdown={thumbDown} onpointermove={thumbMove} onpointerup={thumbUp}></div>
      </div>
    {/if}
  </div>
</section>

<style>
  .stack { display: grid; grid-template-columns: 200px 1fr; background: var(--glass); backdrop-filter: blur(16px) saturate(1.3); border: 1px solid var(--glass-line); box-shadow: 0 1px 0 rgba(255,255,255,0.06) inset, 0 20px 50px -24px rgba(0,0,0,0.7); border-radius: var(--radius); overflow: hidden; }
  .corner { height: 30px; border-bottom: 1px solid var(--line); display: flex; align-items: center; gap: 4px; padding: 0 8px; }
  .lane-lab { height: 26px; border-bottom: 1px solid var(--line); display: flex; align-items: center; padding: 0 8px; }
  .zb { padding: 1px 8px; font-size: 12.5px; line-height: 1.5; border-radius: 6px; min-width: 24px; }
  .zb.wide { padding: 1px 9px; }
  .zb.on { background: var(--text); color: var(--bg); border-color: var(--text); }
  .lab { height: var(--rowh); border-bottom: 1px solid var(--line); padding: 8px 12px 8px 14px; display: grid; align-content: center; gap: 6px; border-left: 3px solid var(--c); }
  .lab:last-child { border-bottom: 0; }
  .name { display: flex; align-items: center; gap: 8px; font-weight: 600; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--c); }
  .ctl { display: flex; align-items: center; gap: 6px; }
  .ctl input { flex: 1; min-width: 0; width: 100%; }
  .ms { padding: 1px 0; width: 26px; font-size: 12px; font-weight: 700; border-radius: 6px; }
  .ms.on { background: var(--text); color: var(--bg); border-color: var(--text); }
  .lab, .row { transition: opacity 0.3s var(--ease); }
  .off { opacity: 0.35; }

  .timeline { position: relative; min-width: 0; border-left: 1px solid var(--line); overflow: hidden; }
  .rows { position: relative; }
  .lane.chords { background: rgba(0,0,0,0.12); }
  .chl { font-size: 12px; padding-left: 12px !important; }
  .ch { position: absolute; top: 3px; bottom: 3px; padding: 0 3px; border-radius: 4px; border: 0; background: rgba(255,255,255,0.09); color: var(--text); font-size: 12.5px; font-weight: 600; text-align: left; overflow: hidden; white-space: nowrap; transition: background 0.12s; }
  .ch:hover { background: rgba(255,255,255,0.2); }
  .ch.cur { background: color-mix(in srgb, var(--loop) 45%, transparent); box-shadow: 0 0 0 1.5px var(--loop); }
  .lane { position: relative; height: 26px; border-bottom: 1px solid var(--line); overflow: hidden; }
  .sec { position: absolute; top: 3px; bottom: 3px; display: flex; align-items: center; justify-content: space-between; padding: 0 4px 0 0; border-left: 2px solid var(--c); border-radius: 4px; background: color-mix(in srgb, var(--c) 16%, transparent); overflow: hidden; transition: background 0.2s; }
  .sec.sel { background: color-mix(in srgb, var(--c) 28%, transparent); box-shadow: 0 0 0 1.5px var(--c); }
  .sec.looped { box-shadow: 0 0 0 1.5px var(--loop); }
  .sec.looped .nm { color: var(--loop); }
  .sec .lp { margin-right: 4px; }
  .sec .h { position: absolute; top: 0; bottom: 0; width: 8px; cursor: ew-resize; touch-action: none; z-index: 2; }
  .sec .h.l { left: -2px; }
  .sec .h.r { right: -2px; }
  .sec .h:hover, .sec.sel .h { background: color-mix(in srgb, var(--c) 55%, transparent); }
  .sec.cut { border-left-color: transparent; border-top-left-radius: 0; border-bottom-left-radius: 0; }
  .sec.cur { background: color-mix(in srgb, var(--c) 34%, transparent); }
  .sec .nm { background: transparent; border: 0; padding: 0 8px; font-weight: 700; font-size: 12.5px; color: var(--c); min-width: 0; text-align: left; }
  .sec .x { background: transparent; border: 0; padding: 0 3px; font-size: 14px; line-height: 1; color: var(--muted); opacity: 0; transition: opacity 0.15s; }
  .sec:hover .x { opacity: 1; }
  .ren { width: 90%; margin-left: 6px; background: rgba(0,0,0,0.35); border: 1px solid var(--c); border-radius: 4px; color: var(--text); font: inherit; font-size: 12.5px; padding: 0 4px; }
  .scroller { position: absolute; left: 0; right: 0; bottom: 0; height: 14px; background: rgba(0,0,0,0.35); }
  .scroller .thumb { position: absolute; top: 2px; bottom: 2px; border-radius: 5px; background: rgba(255,255,255,0.3); cursor: grab; touch-action: none; }
  .scroller .thumb:active { cursor: grabbing; background: rgba(255,255,255,0.45); }
  .mini-band { position: absolute; top: 0; bottom: 0; background: color-mix(in srgb, var(--loop) 60%, transparent); }
  .mini-head { position: absolute; top: 0; bottom: 0; width: 2px; background: #fff; }
  .ruler { position: relative; height: 30px; border-bottom: 1px solid var(--line); cursor: col-resize; touch-action: none; user-select: none; }
  .tick { position: absolute; top: 0; height: 100%; padding: 6px 0 0 6px; font-size: 12px; color: var(--muted); border-left: 1px solid var(--line); pointer-events: none; }
  .rows { cursor: pointer; }
  .row { animation: reveal 0.9s var(--ease) both; animation-delay: calc(var(--n) * 90ms); height: var(--rowh); border-bottom: 1px solid var(--line); background: repeating-linear-gradient(90deg, transparent 0 79px, rgba(255,255,255,0.025) 79px 80px); }
  .row:last-child { border-bottom: 0; }

  .band { transition: background 0.25s, border-color 0.25s; animation: bandIn 0.35s var(--ease) both; transform-origin: left; position: absolute; top: 0; bottom: 0; background: color-mix(in srgb, var(--loop) 22%, transparent); border-left: 2px solid var(--loop); border-right: 2px solid var(--loop); pointer-events: none; }
  .band.idle { background: color-mix(in srgb, var(--muted) 14%, transparent); border-color: var(--muted); }
  .band.live { background: color-mix(in srgb, var(--loop) 14%, transparent); }
  .head { position: absolute; top: 0; bottom: 0; left: -1px; width: 2px; background: var(--head); pointer-events: none; box-shadow: 0 0 0 1px rgba(0,0,0,0.35), 0 0 14px rgba(255,255,255,0.55); }
  .head::before { content: ''; position: absolute; top: 0; left: -5px; border: 6px solid transparent; border-top-color: var(--head); border-bottom: 0; }

  @keyframes reveal { from { clip-path: inset(0 100% 0 0); opacity: 0; } to { clip-path: inset(0 0 0 0); opacity: 1; } }
  @keyframes bandIn { from { opacity: 0; transform: scaleX(0.6); } to { opacity: 1; transform: none; } }
  @media (max-width: 720px) { .stack { grid-template-columns: 120px 1fr; } .ctl input { display: none; } }
</style>
