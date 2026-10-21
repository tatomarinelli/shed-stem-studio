<script lang="ts">
  import Icon from './Icon.svelte';
  import { playback } from '../lib/playback.svelte';

  const shown = $derived(playback.muted ? 0 : playback.volume);
  const off = $derived(playback.muted || playback.volume === 0);
</script>

<div class="vol">
  <button class="ib" class:off onclick={() => playback.toggleMute()} aria-pressed={off} aria-label={off ? 'Quitar el silencio' : 'Silenciar'} title={off ? 'Quitar el silencio' : 'Silenciar'}>
    <Icon name={off ? 'silencio' : 'volumen'} size={18} />
  </button>
  <input type="range" min="0" max="1" step="0.01" value={shown} style="--pct:{shown * 100}%" oninput={e => playback.setVolume(+e.currentTarget.value)} ondblclick={() => playback.resetVolume()}
    title="Doble clic: volumen 100 %" aria-label="Volumen general" aria-valuetext="{Math.round(shown * 100)} %" />
  <span class="num pct muted">{Math.round(shown * 100)}</span>
</div>

<style>
  .vol { display: flex; align-items: center; gap: 6px; }
  .vol input { width: 110px; }
  .pct { font-size: 12.5px; min-width: 24px; text-align: right; }
  .ib { width: 34px; height: 34px; padding: 0; display: grid; place-items: center; border-radius: 50%; background: transparent; border-color: transparent; }
  .ib.off { color: var(--loop); }
  @media (max-width: 520px) { .vol input { width: 84px; } .pct { display: none; } }
</style>
