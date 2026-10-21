<script lang="ts">
  import { toast } from '../lib/toast.svelte';
</script>

{#if toast.text}
  <div class="toast" class:warn={toast.kind === 'warn'} role="status">
    <span>{toast.text}</span>
    <button onclick={() => toast.hide()} aria-label="Cerrar">×</button>
  </div>
{/if}

<style>
  .toast { position: fixed; right: 20px; bottom: 120px; max-width: 420px; display: flex; gap: 12px; align-items: flex-start; padding: 12px 14px; border-radius: 14px; background: rgba(23, 38, 42, 0.8); backdrop-filter: blur(18px); border: 1px solid var(--glass-line); box-shadow: 0 18px 40px -16px rgba(0,0,0,0.8); animation: rise 0.35s var(--ease) both; z-index: 30; }
  .toast.warn { border-color: color-mix(in srgb, var(--loop) 60%, transparent); }
  button { background: transparent; border: 0; padding: 0 4px; font-size: 20px; line-height: 1; }
</style>
