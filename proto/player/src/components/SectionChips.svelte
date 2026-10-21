<script lang="ts">
  import { player } from '../lib/player.svelte';
  const SEC_HUES = [38, 200, 150, 320, 10, 260];
  const color = (i: number) => `hsl(${SEC_HUES[i % SEC_HUES.length]} 70% 62%)`;
  const mm = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
</script>

{#if player.sections.length}
  <div class="chips" role="group" aria-label="Secciones">
    {#each player.sections as s, i (s.id)}
      <button class:cur={player.currentSection === i} class:looped={player.loopSectionId === s.id && player.loopOn} style="--c:{color(i)}" onclick={() => player.goSection(i)} ondblclick={() => player.loopSection(i)}
        title="{s.name}, {mm(s.start)} a {mm(s.end)}. Clic: ir ({i + 1}). Doble clic: repetir">
        <b>{player.loopSectionId === s.id && player.loopOn ? '↻ ' : ''}{s.name}</b><span class="num">{mm(s.start)}</span>
      </button>
    {/each}
    <button class="ghost" onclick={() => player.stepSection(-1)} aria-label="Sección anterior" title="Sección anterior (P)">‹</button>
    <button class="ghost" onclick={() => player.stepSection(1)} aria-label="Sección siguiente" title="Sección siguiente (N)">›</button>
  </div>
{/if}

<style>
  .chips { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-left: auto; }
  .chips button { display: flex; align-items: baseline; gap: 6px; padding: 4px 12px; border-radius: 999px; border: 1px solid color-mix(in srgb, var(--c, var(--muted)) 55%, transparent); background: color-mix(in srgb, var(--c, transparent) 12%, transparent); }
  .chips button b { color: var(--c); }
  .chips button span { font-size: 12px; color: var(--muted); }
  .chips button.cur { background: color-mix(in srgb, var(--c) 36%, transparent); border-color: var(--c); }
  .chips button.looped { box-shadow: 0 0 0 1.5px var(--loop); }
  .chips .ghost { background: transparent; border-color: var(--glass-line); padding: 4px 10px; }
</style>
