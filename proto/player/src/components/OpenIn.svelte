<script lang="ts">
  import SourceLogo from './SourceLogo.svelte';

  let { links, size = 15 }: { links?: Record<string, string>; size?: number } = $props();
  const NAME: Record<string, string> = { tidal: 'TIDAL', spotify: 'Spotify', ytmusic: 'YouTube Music' };
  const list = $derived(['tidal', 'ytmusic', 'spotify'].filter(k => links?.[k]));
</script>

{#each list as k (k)}
  <a class="open" href={links![k]} target="_blank" rel="noopener noreferrer" title="Abrir en {NAME[k]}" aria-label="Abrir en {NAME[k]}"><SourceLogo id={k} size={size} /></a>
{/each}

<style>
  .open { display: inline-grid; place-items: center; width: 30px; height: 30px; border-radius: 50%; border: 1px solid var(--glass-line); color: var(--text); flex: none; opacity: 0.85; transition: opacity 0.15s, background 0.15s; }
  .open:hover, .open:focus-visible { opacity: 1; background: rgba(255, 255, 255, 0.08); }
</style>
