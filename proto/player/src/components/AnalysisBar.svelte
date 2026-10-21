<script lang="ts">
  import { analysis } from '../lib/analysis.svelte';
  import { player } from '../lib/player.svelte';

  const d = $derived(analysis.data);
  const chord = $derived(d ? analysis.chordAt(player.position) : null);
  const bpm = $derived(d ? Math.round(d.tempo.bpm) : 0);
  const keyHint = $derived(d ? `Confianza ${Math.round(d.key.confidence * 100)} %. Otras opciones: ${d.key.alternatives.map(a => `${a.tonic} ${a.mode}`).join(', ')}. Es una estimación.` : '');
  const bpmHint = $derived(d ? `Confianza ${Math.round(d.tempo.confidence * 100)} %.${d.tempo.stable ? '' : ' El tempo varía en el tema.'} ${d.tempo.alternatives.map(a => `Podría ser ${Math.round(a.bpm)} (${a.relation}).`).join(' ')}` : '');
  const stageLabel: Record<string, string> = { load: 'Leyendo stems', tempo: 'Tempo', chroma: 'Armonía', chords: 'Acordes', key: 'Tonalidad', done: 'Listo' };
</script>

<div class="bar" role="group" aria-label="Análisis del tema">
  {#if analysis.state === 'ready' && d}
    <span class="chip" title={keyHint}><span class="k">Tonalidad</span><b>{d.key.label}</b>{#if d.key.confidence < 0.5}<i class="low" aria-label="poco seguro">?</i>{/if}</span>
    <span class="chip" title={bpmHint}><span class="k">Tempo</span><b class="num">{d.tempo.stable ? '' : '~'}{bpm}</b><span class="u">BPM</span></span>
    <span class="chord" aria-live="off" title="Acorde que suena ahora (estimado)">{chord && chord.label !== 'N' ? chord.label : '·'}</span>
    <span class="grow"></span>
    <button class:on={analysis.showGrid} onclick={() => (analysis.showGrid = !analysis.showGrid)} aria-pressed={analysis.showGrid}>Compases</button>
    <button class:on={analysis.showChords} onclick={() => (analysis.showChords = !analysis.showChords)} aria-pressed={analysis.showChords}>Acordes</button>
    <button class:on={player.clickOn} onclick={() => player.toggleClick()} disabled={!player.hasBeats} aria-pressed={player.clickOn} title="Click en los pulsos del tema (K)">Click</button>
    {#if player.clickOn}
      <input type="range" min="0" max="1" step="0.01" value={player.clickGain} style="--pct:{player.clickGain * 100}%;--fill:var(--text)" oninput={e => player.setClickGain(+e.currentTarget.value)} aria-label="Volumen del click" />
    {/if}
    <button class="ghost" onclick={() => analysis.start(true)} title="Volver a analizar">↻</button>
  {:else if analysis.state === 'running'}
    <span class="muted" role="status">Analizando{analysis.stage ? `: ${stageLabel[analysis.stage] ?? analysis.stage}` : ''}… <span class="num">{Math.round(analysis.percent)} %</span></span>
    <span class="prog"><i style="width:{analysis.percent}%"></i></span>
  {:else if analysis.state === 'checking'}
    <span class="muted">Buscando el análisis…</span>
  {:else}
    <button class="primary" onclick={() => analysis.start()}>Analizar tonalidad, tempo y acordes</button>
    {#if analysis.message}<span class="warn" role="alert">{analysis.message}</span>{/if}
  {/if}
</div>

<style>
  .bar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 8px 12px; border-radius: var(--radius); background: var(--glass); backdrop-filter: blur(16px) saturate(1.3); border: 1px solid var(--glass-line); min-height: 52px; animation: rise 0.4s var(--ease) both; }
  .chip { display: inline-flex; align-items: baseline; gap: 6px; padding: 4px 11px; border-radius: 999px; background: rgba(255,255,255,0.07); border: 1px solid var(--glass-line); }
  .chip .k { font-size: 12.5px; color: var(--muted); }
  .chip b { font-size: 16px; letter-spacing: -0.01em; }
  .chip .u { font-size: 12.5px; color: var(--muted); }
  .low { font-style: normal; font-size: 12px; color: #f0a43c; border: 1px solid #f0a43c; border-radius: 50%; width: 16px; height: 16px; display: inline-grid; place-items: center; }
  .chord { min-width: 70px; text-align: center; font-size: 23px; font-weight: 700; letter-spacing: -0.02em; padding: 0 10px; border-radius: 12px; background: color-mix(in srgb, var(--loop) 14%, transparent); border: 1px solid color-mix(in srgb, var(--loop) 45%, transparent); transition: background 0.15s; }
  .grow { flex: 1; min-width: 0; }
  button { padding: 4px 11px; border-radius: 999px; }
  .ghost { padding: 4px 9px; }
  button.on { background: var(--text); color: var(--bg); border-color: var(--text); }
  .ghost { background: transparent; }
  .primary { background: var(--text); color: var(--bg); border-color: var(--text); font-weight: 600; }
  input[type='range'] { width: 90px; }
  .warn { color: #f0a43c; }
  .prog { flex: 1; min-width: 120px; max-width: 320px; height: 6px; border-radius: 3px; background: var(--line); overflow: hidden; }
  .prog i { display: block; height: 100%; background: linear-gradient(90deg, #f0a43c, #ff4d8d, #4fa3d9); transition: width 0.4s var(--ease); }
</style>
