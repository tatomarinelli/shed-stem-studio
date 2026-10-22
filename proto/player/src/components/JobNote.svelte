<script lang="ts">
  import type { Pull } from '../lib/settings.svelte';

  let { job }: { job: Pull | undefined } = $props();
</script>

{#if job?.state === 'error'}<span class="warn" role="alert">{job.message || 'Falló, sin más datos.'}</span>
{:else if job?.state === 'cancelled'}<span class="muted" role="status">Cancelado.</span>{/if}
