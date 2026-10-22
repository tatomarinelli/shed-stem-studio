<script lang="ts">
  import { onMount } from 'svelte';
  import { settings } from '../lib/settings.svelte';

  onMount(() => { void settings.loadBackends(); });

  const rep = $derived(settings.backends);
  const chosen = $derived(settings.backend ?? rep?.recommended ?? null);
  const TITLES: Record<string, string> = { available: 'Para instalar ahora', incompatible: 'No son para tu equipo', soon: 'Próximamente' };
</script>

{#if rep}
  <fieldset class="backends">
    <legend>Motor de separación · {rep.reason}</legend>
    {#each rep.options as o, i (o.id)}
      {#if o.group && o.group !== rep.options[i - 1]?.group}<span class="grp">{TITLES[o.group]}</span>{/if}
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
  .grp { font-size: 0.75rem; opacity: 0.65; text-transform: uppercase; letter-spacing: 0.04em; margin-top: 4px; }
  legend { padding: 0 6px; font-size: 0.85em; opacity: 0.8; }
  label { display: flex; gap: 8px; align-items: center; cursor: pointer; }
  label.off { opacity: 0.55; cursor: not-allowed; }
  .reco, .tag { font-size: 0.78em; padding: 1px 6px; border-radius: 10px; border: 1px solid currentColor; }
  .reco { color: var(--accent, #d9a441); }
  .tag { opacity: 0.75; }
</style>
