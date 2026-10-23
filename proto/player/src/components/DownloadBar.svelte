<script lang="ts">
  import { untrack } from 'svelte';
  import { downloads, type Estimate, type Pick } from '../lib/downloads.svelte';

  // Barra de acción de una lista con selección: "N temas · ≈ X MB · calidad · Descargar", y el avance del lote.
  let { picks, total, onall, onnone, onclose, inline = false }: { picks: Pick[]; total: number; onall: () => void | Promise<void>; onnone: () => void; onclose: () => void; inline?: boolean } = $props();

  let est = $state<Estimate | null>(null);
  let starting = $state(false);
  let error = $state('');
  let loadingAll = $state(false);

  const opts = $derived(downloads.options);
  const b = $derived(downloads.batch);
  const running = $derived(b?.state === 'running');
  const qualities = $derived((opts?.qualities ?? []).filter(q => !downloads.ipod || opts?.ipod.qualities.includes(q.id)));
  const blocked = $derived((opts?.qualities ?? []).filter(q => !q.available));
  const unavailable = $derived([...new Set(blocked.map(q => q.reason))]);
  const cur = $derived(opts?.qualities.find(q => q.id === downloads.q));

  const size = (n: number) => (n >= 1e9 ? `${(n / 1e9).toFixed(1)} GB` : `${Math.max(1, Math.round(n / 1e6))} MB`);
  const approx = $derived(!(est && !est.approx && downloads.q === 'original'));

  $effect(() => { downloads.ensure(); });

  // Se vuelve a estimar al cambiar la selección o la calidad (con una pausa corta para no pedir en cada tilde).
  $effect(() => {
    const p = picks, key = downloads.key;
    void key;
    if (!p.length) { est = null; return; }
    const t = window.setTimeout(async () => { const r = await untrack(() => downloads.estimate(p)); est = r; }, 250);
    return () => window.clearTimeout(t);
  });

  async function go() {
    error = '';
    starting = true;
    error = await downloads.startBatch(picks);
    starting = false;
  }
  async function all() { loadingAll = true; try { await onall(); } finally { loadingAll = false; } }
  const fails = $derived(b?.items.filter(i => i.state === 'error') ?? []);
</script>

<section class="dlb" class:inline aria-label="Descargar lo elegido">
  {#if b}
    <div class="batch" aria-live="polite">
      {#if running}
        <div class="line"><b class="num">{b.done} de {b.total}</b>
          <span class="muted cur">{b.currentJob ? `${b.currentJob.artist ? b.currentJob.artist + ' - ' : ''}${b.currentJob.title} · ${b.currentJob.percent} %` : 'Preparando…'}</span></div>
        <div class="pbar" role="progressbar" aria-valuenow={b.total ? Math.round(100 * b.done / b.total) : 0} aria-valuemin="0" aria-valuemax="100"><i style="width:{Math.max(3, b.total ? 100 * (b.done + (b.currentJob?.percent ?? 0) / 100) / b.total : 0)}%"></i></div>
        {#if b.currentJob?.step}<span class="muted small">{b.currentJob.step}</span>{/if}
        <div class="row"><button onclick={() => downloads.cancelBatch('current')}>Cancelar este tema</button><button class="danger" onclick={() => downloads.cancelBatch('all')}>Cancelar todo</button></div>
      {:else}
        <div class="line"><b>{b.state === 'cancelled' ? 'Cancelado' : 'Listo'}</b><span class="muted cur">{b.summary}</span></div>
        {#if fails.length > 1}<ul class="fails">{#each fails.slice(0, 4) as f (f.id + f.title)}<li class="small">{f.title || f.id}: {f.message}</li>{/each}</ul>{/if}
        <span class="muted small" title={b.dir}>Los archivos están en {b.dir}</span>
        <div class="row"><button class="primary" onclick={() => downloads.reveal({ path: b!.dir })}>Abrir carpeta</button><button class="ghost" onclick={() => downloads.dismissBatch()}>Cerrar</button></div>
      {/if}
    </div>
  {:else}
    <div class="line">
      <b class="num" role="status">{picks.length} {picks.length === 1 ? 'tema' : 'temas'}</b>
      {#if est}<span class="num" title="Duración x tasa de bits. Sin pérdida: ≈ 850 kbps (FLAC típico); MP3: tasa fija.">{approx ? '≈ ' : ''}{size(est.bytes)}</span>{/if}
      <span class="sp"></span>
      <button class="ghost" onclick={all} disabled={loadingAll}>{loadingAll ? 'Cargando…' : `Todos${total ? ` (${total})` : ''}`}</button>
      <button class="ghost" onclick={onnone} disabled={!picks.length}>Ninguno</button>
      <button class="ghost" onclick={onclose} aria-label="Salir de la selección">Salir</button>
    </div>
    <div class="line">
      <label class="q">Calidad
        <select value={downloads.q} onchange={e => downloads.setQuality(e.currentTarget.value)} aria-label="Calidad">
          {#each qualities as q (q.id)}<option value={q.id} disabled={!q.available}>{q.label}{q.available ? '' : ' (no disponible)'}</option>{/each}
        </select>
      </label>
      <button class="primary go" onclick={go} disabled={!picks.length || starting || (est !== null && !est.enough) || cur?.available === false}>{starting ? 'Empezando…' : 'Descargar'}</button>
    </div>
    <div class="opts">
      <label><input type="checkbox" checked={downloads.ipod} onchange={e => downloads.setIpod(e.currentTarget.checked)} /> iPod / dispositivo viejo <span class="muted small">MP3 128 o 192, ID3v2.3, 44,1 kHz</span></label>
      <label><input type="checkbox" checked={downloads.folders} onchange={e => downloads.setFolders(e.currentTarget.checked)} /> Carpeta por álbum <span class="muted small">Artista/Álbum/NN - Título</span></label>
    </div>
    <div class="notes small">
      {#if est && !est.enough}<span class="warn" role="alert">No alcanza: hacen falta ≈ {size(est.bytes)} y hay {size(est.free)} libres.</span>
      {:else if est}<span class="muted" title={est.dir}>Libres {size(est.free)} en {est.dir}</span>{:else if opts}<span class="muted" title={opts.dir}>Va a {opts.dir}</span>{/if}
      {#if est && est.unknown}<span class="muted">{est.unknown} sin dato, no {est.unknown === 1 ? 'cuenta' : 'cuentan'}.</span>{/if}
      {#each unavailable as r (r)}<span class="muted">{r}</span>{/each}
      {#if error}<span class="warn" role="alert">{error}</span>{/if}
    </div>
  {/if}
</section>

<style>
  .dlb { position: sticky; bottom: 12px; z-index: 20; display: grid; gap: 8px; padding: 12px 14px; border-radius: 16px; background: rgba(18, 32, 36, 0.96); border: 1px solid var(--glass-line); box-shadow: 0 18px 44px -14px rgba(0, 0, 0, 0.85); backdrop-filter: blur(14px); animation: rise 0.25s var(--ease) both; }
  .dlb.inline { position: static; box-shadow: none; }
  .batch { display: grid; gap: 8px; }
  .line { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; min-width: 0; }
  .sp { flex: 1; }
  .row { display: flex; gap: 8px; flex-wrap: wrap; }
  .cur { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; flex: 1; }
  .small { font-size: 12.5px; }
  .q { display: flex; align-items: center; gap: 8px; color: var(--muted); font-size: 13.5px; }
  .q select { background: rgba(255, 255, 255, 0.06); color: var(--text); border: 1px solid var(--glass-line); border-radius: 9px; padding: 6px 8px; }
  .go { margin-left: auto; }
  .primary { background: var(--text); color: var(--bg); border-color: var(--text); font-weight: 600; }
  .ghost { background: transparent; padding: 4px 11px; }
  .danger { color: var(--loop); border-color: color-mix(in srgb, var(--loop) 50%, transparent); }
  .opts { display: flex; gap: 6px 18px; flex-wrap: wrap; font-size: 13.5px; }
  .opts label { display: inline-flex; align-items: center; gap: 6px; }
  .notes { display: flex; gap: 4px 14px; flex-wrap: wrap; }
  .warn { color: #f0a43c; }
  .pbar { height: 6px; border-radius: 3px; background: rgba(255, 255, 255, 0.1); overflow: hidden; }
  .pbar i { display: block; height: 100%; border-radius: 3px; background: linear-gradient(90deg, #4fa3d9, #7cc7a3); transition: width 0.6s var(--ease); }
  .fails { margin: 0; padding-left: 18px; color: var(--muted); }
  button:disabled { opacity: 0.5; }
</style>
