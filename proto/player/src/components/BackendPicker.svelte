<script lang="ts">
  import { onMount } from 'svelte';
  import { settings } from '../lib/settings.svelte';

  onMount(() => { void settings.loadBackends(); });

  const rep = $derived(settings.backends);
  const chosen = $derived(settings.backend ?? rep?.recommended ?? null);
</script>

{#if rep}
  <fieldset class="backends">
    <legend>Motor de separación · {rep.reason}</legend>
    {#each rep.options as o (o.id)}
      {@const usable = o.installable && o.compatible}
      <label class:off={!usable} title={o.note}>
        <input type="radio" name="backend" value={o.id} disabled={!usable} checked={chosen === o.id} onchange={() => (settings.backend = o.id)} />
        <b>{o.label}</b>
        {#if o.recommended}<span class="reco">Recomendado</span>{/if}
        {#if !o.compatible}<span class="tag">{o.requires ?? 'No compatible'}</span>
        {:else if !o.installable}<span class="tag">Próximamente</span>
        {:else if !o.verified}<span class="tag">Sin verificar</span>{/if}
      </label>
    {/each}
  </fieldset>
{/if}

<style>
  .backends { border: 1px solid var(--line, #3a332d); border-radius: 8px; padding: 8px 12px; margin: 8px 0; display: grid; gap: 6px; }
  legend { padding: 0 6px; font-size: 0.85em; opacity: 0.8; }
  label { display: flex; gap: 8px; align-items: center; cursor: pointer; }
  label.off { opacity: 0.55; cursor: not-allowed; }
  .reco, .tag { font-size: 0.78em; padding: 1px 6px; border-radius: 10px; border: 1px solid currentColor; }
  .reco { color: var(--accent, #d9a441); }
  .tag { opacity: 0.75; }
</style>
