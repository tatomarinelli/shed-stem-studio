<script lang="ts">
  import { onMount } from 'svelte';
  import { settings } from '../lib/settings.svelte';
  import Progress from './Progress.svelte';

  onMount(() => { void settings.loadFfmpeg(); });

  const ff = $derived(settings.ffmpeg);
</script>

{#if ff && !ff.installed}
  <div class="ff">
    <b>ffmpeg</b>
    {#if ff.job.state === 'running'}<Progress job={ff.job} verb="Instalando" />
    {:else if ff.canInstall}
      <span class="muted">Hace falta para separar</span>
      <button class="primary" onclick={() => settings.installFfmpeg()}>Instalar</button>
      {#if ff.job.state === 'error'}<span class="warn" role="alert">{ff.job.message}</span>{/if}
    {:else}<span class="warn">Falta instalarlo (ffmpeg.org)</span>{/if}
  </div>
{/if}

<style>
  .ff { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin: 6px 0; }
</style>
