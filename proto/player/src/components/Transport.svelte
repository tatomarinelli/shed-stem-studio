<script lang="ts">
  import { player, ENGINES, type EngineName } from '../lib/player.svelte';

  const clock = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, '0')}`;
  const presets = [0.25, 0.5, 0.75, 1];
</script>

<footer>
  <div class="bar">
    <div class="play-group">
      <button class="play" class:live={player.playing} onclick={() => player.toggle()} aria-label={player.playing ? 'Pausar' : 'Reproducir'}>
        {#if player.playing}
          <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>
        {:else}
          <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.5-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5Z"/></svg>
        {/if}
      </button>
      <button class="ghost" onclick={() => player.seek(player.loopActive ? player.loopA! : 0)} aria-label="Volver al principio">⏮</button>
      <div class="clock num">{clock(player.position)}<span class="muted"> de {clock(player.duration)}</span></div>
    </div>

    <div class="speed">
      <div class="readout num" style="--k:{player.speed >= 1 ? 1 : 0.3 + 0.7 * player.speed}">{Math.round(player.speed * 100)}<small>%</small></div>
      <div class="speed-ctl">
        <input type="range" min="0.25" max="1.25" step="0.01" value={player.speed} style="--pct:{((player.speed - 0.25) / 1) * 100}%;--fill:var(--loop)" oninput={e => player.setSpeed(+e.currentTarget.value)} aria-label="Velocidad" />
        <div class="seg">
          {#each presets as p (p)}
            <button class:on={Math.abs(player.speed - p) < 0.005} onclick={() => player.setSpeed(p)}>{p * 100}</button>
          {/each}
        </div>
      </div>
    </div>

    <div class="loop">
      <button class="toggle" class:on={player.loopOn} onclick={() => player.toggleLoop()} disabled={player.loopA == null || player.loopB == null}>
        {player.loopOn ? 'Loop activo' : 'Loop apagado'}
      </button>
      <button class="ghost" onclick={() => player.clearLoop()} disabled={player.loopA == null && player.loopB == null}>Borrar loop</button>
      <label class="engine"><span class="muted">Estirador</span>
        <select value={player.engine} onchange={e => player.setEngine(e.currentTarget.value as EngineName)}>
          {#each ENGINES as en (en.id)}<option value={en.id}>{en.label}</option>{/each}
        </select>
      </label>
    </div>
  </div>
  <p class="hint muted">Regla: arrastrá para un loop. Ctrl + rueda: zoom. M: marcar sección. N y P: saltar. S: repetir sección. Espacio: play.</p>
</footer>

<style>
  footer { transition: left 0.3s var(--ease); position: fixed; left: calc(var(--menu-w) + 24px); right: 12px; bottom: 12px; background: rgba(15, 26, 29, 0.62); border: 1px solid var(--glass-line); border-radius: 18px; backdrop-filter: blur(22px) saturate(1.4); box-shadow: 0 -1px 0 rgba(255,255,255,0.05) inset, 0 24px 60px -20px rgba(0,0,0,0.8); padding: 12px 22px 8px; animation: rise 0.6s var(--ease) 0.5s both; }
  .bar { max-width: 2200px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; gap: 20px 32px; flex-wrap: wrap; }
  .play-group { display: flex; align-items: center; gap: 12px; }
  .play { width: 52px; height: 52px; border-radius: 50%; padding: 0; display: grid; place-items: center; background: var(--text); color: var(--bg); border-color: var(--text); }
  .play:hover:not(:disabled) { background: #fff; border-color: #fff; }
  .play { position: relative; transition: transform 0.15s var(--ease), box-shadow 0.4s; }
  .play.live { box-shadow: 0 0 0 0 rgba(255,255,255,0.45); animation: ring 2.2s ease-out infinite; }
  .play svg { fill: currentColor; }
  @keyframes ring { to { box-shadow: 0 0 0 16px rgba(255,255,255,0); } }
  .ghost { background: transparent; }
  .clock { font-size: 22px; font-weight: 600; min-width: 190px; }
  .clock .muted { font-size: 14px; font-weight: 400; }

  .speed { display: flex; align-items: center; gap: 16px; }
  .readout { transition: color 0.3s; color: color-mix(in srgb, var(--text) calc(60% + 40% * var(--k)), var(--loop)); font-size: 44px; font-weight: 700; line-height: 1; letter-spacing: -0.03em; min-width: 104px; text-align: right; font-variation-settings: 'wdth' 85; }
  .readout small { font-size: 18px; font-weight: 500; margin-left: 2px; color: var(--muted); }
  .speed-ctl { display: grid; gap: 4px; }
  .speed-ctl input { width: 240px; }
  .seg { display: flex; gap: 4px; }
  .seg button { flex: 1; padding: 2px 0; font-size: 13px; border-radius: 6px; }
  .seg button.on, .toggle.on { background: var(--loop); border-color: var(--loop); color: #14040a; font-weight: 600; }
  .seg button.on { background: var(--text); border-color: var(--text); color: var(--bg); }

  .loop { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .engine { display: flex; align-items: center; gap: 8px; margin-left: 8px; }
  .hint { margin: 4px 0 0; opacity: 0.8; text-align: center; font-size: 12.5px; }
  @media (max-width: 760px) { footer { left: 12px; bottom: 76px; } }
  @media (max-width: 720px) { .hint { display: none; } .speed-ctl input { width: 160px; } }
</style>
