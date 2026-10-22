<script lang="ts">
  let { id, size = 28 }: { id: string; size?: number } = $props();
</script>

<!-- Marcas simplificadas de cada fuente (no son los logos oficiales). -->
<svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" class="logo">
  {#if id === 'spotify'}
    <circle cx="16" cy="16" r="15" fill="#1db954" />
    <path d="M8.5 12c5-1.4 11-1 15.5 1.6" stroke="#0b0b0b" stroke-width="2.2" stroke-linecap="round" fill="none" />
    <path d="M9.4 16.4c4.2-1.1 8.8-.7 12.5 1.4" stroke="#0b0b0b" stroke-width="1.9" stroke-linecap="round" fill="none" />
    <path d="M10.3 20.4c3.4-.8 6.8-.5 9.8 1.1" stroke="#0b0b0b" stroke-width="1.6" stroke-linecap="round" fill="none" />
  {:else if id === 'ytmusic'}
    <circle cx="16" cy="16" r="15" fill="#ff0033" />
    <circle cx="16" cy="16" r="9" fill="none" stroke="#fff" stroke-width="1.8" />
    <path d="M13.4 11.9v8.2L20.6 16z" fill="#fff" />
  {:else if id === 'tidal'}
    <g fill="currentColor">
      <path d="M16 3.5l5.5 5.5L16 14.5 10.5 9z" /><path d="M7.5 12l5.5 5.5L7.5 23 2 17.5z" /><path d="M24.5 12l5.5 5.5-5.5 5.5-5.5-5.5z" /><path d="M16 20.5l5.5 5.5L16 31.5 10.5 26z" />
    </g>
  {:else}
    <path d="M3 9.5a2.5 2.5 0 0 1 2.5-2.5h6l2.5 3h12.5A2.5 2.5 0 0 1 29 12.5v12A2.5 2.5 0 0 1 26.5 27h-21A2.5 2.5 0 0 1 3 24.5z" fill="currentColor" opacity="0.85" />
  {/if}
</svg>

<style>
  .logo { flex: none; display: block; }
</style>
