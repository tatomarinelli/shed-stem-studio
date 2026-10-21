<script lang="ts">
  import { onMount } from 'svelte';
  import Spark from './Spark.svelte';
  import { resources, gb, mb, pct, WINDOW_MS } from '../lib/resources.svelte';

  onMount(() => resources.watch());

  const d = $derived(resources.data);
  const h = $derived(resources.hist);
  const now = $derived(d?.now ?? 0);
  // El gráfico abarca lo que se lleva medido (mínimo 30 s, máximo 5 min).
  const span = $derived(Math.min(WINDOW_MS, Math.max(30_000, h.t.length ? now - h.t[0] : 0)));
  const spanText = $derived(span >= 90_000 ? `${Math.round(span / 60_000)} min` : `${Math.round(span / 1000)} s`);
  const gpu = $derived(d?.gpus[0] ?? null);
  const peak = (xs: (number | null)[]) => xs.reduce<number | null>((m, v) => (v == null ? m : m == null || v > m ? v : m), null);
  const memPct = $derived(gpu?.memUsedBytes != null && gpu.memTotalBytes ? (100 * gpu.memUsedBytes) / gpu.memTotalBytes : 0);
  const procs = $derived([...(d?.processes ?? [])].sort((a, b) => Number(b.inApp) - Number(a.inApp) || (b.gpuMemBytes ?? 0) - (a.gpuMemBytes ?? 0) || (b.cpuPercent ?? 0) - (a.cpuPercent ?? 0)));
  const num = (v: number | null | undefined, unit: string) => (v == null ? '—' : `${Math.round(v)} ${unit}`);

  const C = { cpu: '#4fa3d9', ram: '#7cc7a3', util: '#f0a43c', vram: '#ff4d8d' };
</script>

<div class="mon">
  {#if resources.offline && !d}
    <p class="warn">No pude hablar con el motor.</p>
  {:else if !d}
    <p class="muted">Midiendo…</p>
  {:else}
    {#if d.jobs.length}
      <p class="jobs" role="status">
        {#each d.jobs as j, i (i)}<span class="chip">{j.kind}: {j.label}{j.percent != null ? ` ${j.percent} %` : ''}</span>{/each}
      </p>
    {/if}

    <div class="tiles">
      <div class="tile">
        <div class="top"><span class="muted">Procesador</span><b class="num">{pct(d.cpu?.percent)}</b></div>
        <Spark t={h.t} values={h.cpu} {now} {span} color={C.cpu} label="Procesador, últimos {spanText}, ahora {pct(d.cpu?.percent)}" />
        <span class="muted cap">{d.cpu?.cores ? `${d.cpu.cores} núcleos` : ''}{peak(h.cpu) != null ? ` · máx. ${pct(peak(h.cpu))} en ${spanText}` : ''}</span>
      </div>
      <div class="tile">
        <div class="top"><span class="muted">Memoria</span><b class="num">{d.ram ? `${gb(d.ram.usedBytes)} de ${gb(d.ram.totalBytes)}` : '—'}</b></div>
        <Spark t={h.t} values={h.ram} {now} {span} color={C.ram} label="Memoria, últimos {spanText}, ahora {pct(d.ram?.percent)}" />
        <span class="muted cap">{d.ram ? `${gb(d.ram.availableBytes)} disponibles` : ''}</span>
      </div>
      {#if gpu}
        <div class="tile">
          <div class="top"><span class="muted">Placa de video</span><b class="num">{pct(gpu.utilPercent)}</b></div>
          <Spark t={h.t} values={h.gpuUtil} {now} {span} color={C.util} label="Uso de la placa de video, últimos {spanText}, ahora {pct(gpu.utilPercent)}" />
          <span class="muted cap">{gpu.name}{peak(h.gpuUtil) != null ? ` · máx. ${pct(peak(h.gpuUtil))}` : ''}</span>
        </div>
        <div class="tile">
          <div class="top"><span class="muted">Memoria de video</span><b class="num">{gb(gpu.memUsedBytes)} de {gb(gpu.memTotalBytes)}</b></div>
          <Spark t={h.t} values={h.gpuMem} {now} {span} max={gpu.memTotalBytes ?? 1} color={C.vram} label="Memoria de video, últimos {spanText}, ahora {gb(gpu.memUsedBytes)}" />
          <span class="muted cap">máx. {gb(peak(h.gpuMem))} en {spanText}</span>
        </div>
      {/if}
    </div>

    {#if gpu}
      {#each d.gpus as g (g.index)}
        <div class="vram">
          <div class="bar" role="progressbar" aria-valuenow={g.memTotalBytes ? Math.round((100 * (g.memUsedBytes ?? 0)) / g.memTotalBytes) : 0} aria-valuemin="0" aria-valuemax="100" aria-label="Memoria de video de {g.name}"><i style="width:{g.memTotalBytes ? (100 * (g.memUsedBytes ?? 0)) / g.memTotalBytes : 0}%"></i></div>
          <span class="num">{gb(g.memUsedBytes)} / {gb(g.memTotalBytes)}</span>
          <span class="muted num">{num(g.tempC, '°C')} · {g.powerW == null ? 'potencia —' : `${Math.round(g.powerW)} W`}</span>
          {#if g.unverified}<span class="muted note">Lectura de AMD sin verificar en hardware real.</span>{/if}
        </div>
      {/each}
    {:else}
      <p class="muted">No se detectó una placa de video. {d.errors.includes('gpu') ? 'Falló la lectura.' : 'La separación y los modelos irían a CPU, mucho más lento.'}</p>
    {/if}

    <h4>Discos</h4>
    {#if d.disks.length}
      <ul class="disks">
        {#each d.disks as k (k.path)}
          <li>
            <span class="path" title={k.path}>{k.path}</span>
            <div class="bar thin" role="progressbar" aria-valuenow={Math.round(k.usedPercent ?? 0)} aria-valuemin="0" aria-valuemax="100" aria-label="Espacio usado en {k.path}"><i class:hot={(k.usedPercent ?? 0) >= 90} style="width:{k.usedPercent ?? 0}%"></i></div>
            <span class="num" class:warn={(k.usedPercent ?? 0) >= 90}>{gb(k.freeBytes, 0)} libres de {gb(k.totalBytes, 0)}</span>
          </li>
        {/each}
      </ul>
    {:else}
      <p class="muted">No pude leer los discos.</p>
    {/if}

    <h4>Procesos</h4>
    {#if procs.length}
      <div class="scroll">
        <table>
          <thead><tr><th>Proceso</th><th class="r" title="100 % es un núcleo completo">CPU</th><th class="r">Memoria</th><th class="r">Video</th></tr></thead>
          <tbody>
            {#each procs as p (p.pid)}
              <tr class:out={!p.inApp}>
                <td>{p.role}{p.inApp ? '' : ' (fuera de la app)'} <span class="muted">· {p.pid}</span></td>
                <td class="r num">{p.cpuPercent == null ? '—' : `${Math.round(p.cpuPercent)} %`}</td>
                <td class="r num">{mb(p.rssBytes)}</td>
                <td class="r num">{p.gpuMemBytes == null ? '—' : mb(p.gpuMemBytes)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <p class="muted cap">Se actualiza cada 2 s. 100 % de CPU es un núcleo completo.</p>
    {:else}
      <p class="muted">No hay procesos para mostrar{d.platform === 'linux' ? '' : ' en este sistema'}.</p>
    {/if}
  {/if}
</div>

<style>
  .mon { display: grid; gap: 10px; }
  p { margin: 0; }
  h4 { margin: 10px 0 0; font-size: 15px; color: var(--muted); font-weight: 600; }
  .warn { color: #f0a43c; }
  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; }
  .tile { display: grid; gap: 4px; padding: 10px 12px; border-radius: 12px; background: rgba(255, 255, 255, 0.04); min-width: 0; }
  .top { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
  .top b { font-size: 16px; font-weight: 600; white-space: nowrap; }
  .cap { font-size: 12.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .jobs { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip { font-size: 12.5px; padding: 2px 10px; border-radius: 999px; border: 1px solid rgba(79, 163, 217, 0.4); background: rgba(79, 163, 217, 0.12); }
  .vram { display: grid; grid-template-columns: minmax(120px, 1fr) auto auto; gap: 4px 14px; align-items: center; }
  .vram .note { grid-column: 1 / -1; font-size: 12.5px; }
  .bar { height: 8px; background: rgba(255, 255, 255, 0.1); border-radius: 4px; overflow: hidden; }
  .bar.thin { height: 6px; }
  .bar i { display: block; height: 100%; background: linear-gradient(90deg, #4fa3d9, #7cc7a3); border-radius: 4px; transition: width 0.5s var(--ease); }
  .vram .bar i { background: linear-gradient(90deg, #f0a43c, #ff4d8d); }
  .bar i.hot { background: #f0a43c; }
  .disks { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
  .disks li { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(80px, 1fr) auto; gap: 12px; align-items: center; padding: 8px 12px; border-radius: 12px; background: rgba(255, 255, 255, 0.04); }
  .path { color: var(--muted); font-size: 13.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .scroll { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th { text-align: left; font-weight: 600; color: var(--muted); font-size: 13px; padding: 4px 8px; }
  td { padding: 6px 8px; border-top: 1px solid rgba(255, 255, 255, 0.05); }
  .r { text-align: right; white-space: nowrap; }
  tr.out td { color: var(--muted); }
  @media (max-width: 760px) {
    .vram { grid-template-columns: 1fr; }
    .disks li { grid-template-columns: 1fr; gap: 4px; }
  }
</style>
