<script lang="ts">
  import { onMount } from 'svelte';
  import { settings } from '../lib/settings.svelte';
  import Progress from './Progress.svelte';
  import JobNote from './JobNote.svelte';

  onMount(() => { void settings.loadLlm(); });

  const llm = $derived(settings.llm);
  const job = $derived(llm?.job);
  const via = $derived(!llm ? '' : llm.accel === 'cpu' ? 'CPU' : `${llm.accel === 'cuda' ? 'CUDA' : 'Vulkan'} · ${llm.gpu}`);
</script>

{#if llm}
  <div class="llm">
    <span>Modelos de <b>Ollama</b></span>
    {#if llm.installed}
      <span class="muted">{via}</span>
    {:else if job?.state === 'running'}<Progress job={job} verb="Instalando" oncancel={() => settings.cancelLlmInstall()} />
    {:else if llm.canInstall}
      <span class="muted">≈ {llm.approxGb.toLocaleString('es-AR')} GB</span>
      <button class="primary" onclick={() => settings.installLlm()}>Instalar</button>
      <JobNote job={job} />
    {:else}<span class="warn">Falta instalarlo (ollama.com)</span>{/if}
  </div>
{/if}

<style>
  .llm { display: flex; gap: 10px; align-items: center; margin: 6px 0 10px; }
</style>
