<script lang="ts">
  import { onMount } from 'svelte';
  import { player } from './lib/player.svelte';
  import { playback } from './lib/playback.svelte';
  import { nav } from './lib/nav.svelte';
  import SideMenu from './components/SideMenu.svelte';
  import { ui } from './lib/ui.svelte';
  import Transport from './components/Transport.svelte';
  import Toast from './components/Toast.svelte';
  import Estudio from './screens/Estudio.svelte';
  import Fuentes from './screens/Fuentes.svelte';
  import Musica from './screens/Musica.svelte';
  import Recomendaciones from './screens/Recomendaciones.svelte';
  import Agentes from './screens/Agentes.svelte';
  import Mapa from './screens/Mapa.svelte';
  import Ajustes from './screens/Ajustes.svelte';
  import Inicio from './screens/Inicio.svelte';
  import { setup } from './lib/setup.svelte';
  import { settings } from './lib/settings.svelte';
  import { separation } from './lib/separation.svelte';

  onMount(() => {
    void player.init();
    void setup.init();
    settings.watchServices(true);
    separation.watch(true);
    return () => { settings.watchServices(false); separation.watch(false); };
  });

  function onKey(e: KeyboardEvent) {
    const t = e.target instanceof HTMLElement ? e.target : document.body;
    if (t.matches('select, input, textarea') || e.ctrlKey || e.metaKey || e.altKey) return;
    const k = e.key;
    if (playback.mode === 'player') {  // escucha normal: Espacio y flechas manejan la cola; los atajos del DAW no aplican
      if (k === ' ' && !t.matches('button, a')) playback.toggle();
      else if (k === 'ArrowLeft') playback.seek(playback.position - 5);
      else if (k === 'ArrowRight') playback.seek(playback.position + 5);
      else return;
      e.preventDefault();
      return;
    }
    if (player.status !== 'ready') return;
    if (k === '\\') ui.toggleMenu();
    else if ((k === 'Delete' || k === 'Backspace') && player.selectedSection) player.removeSection(player.selectedSection);
    else if (k === 'Escape' && player.selectedSection) player.selectedSection = '';
    else if (k === ' ' && !t.matches('button, a')) player.toggle();
    else if (k.toLowerCase() === 'm') player.addSection();
    else if (k.toLowerCase() === 'k') player.toggleClick();
    else if (k.toLowerCase() === 'n') player.stepSection(1);
    else if (k.toLowerCase() === 'p') player.stepSection(-1);
    else if (k.toLowerCase() === 's' && player.currentSection >= 0) player.loopSection(player.currentSection);
    else if (/^[1-9]$/.test(k)) player.goSection(+k - 1);
    else if (k === '[') player.setLoopA();
    else if (k === ']') player.setLoopB();
    else if (k.toLowerCase() === 'l') player.toggleLoop();
    else if (k === 'ArrowLeft') player.seek(player.position - (e.shiftKey ? 1 : 5));
    else if (k === 'ArrowRight') player.seek(player.position + (e.shiftKey ? 1 : 5));
    else if (k === ',') player.setSpeed(Math.max(0.25, +(player.speed - 0.05).toFixed(2)));
    else if (k === '.') player.setSpeed(Math.min(1.25, +(player.speed + 0.05).toFixed(2)));
    else return;
    e.preventDefault();
  }
</script>

<svelte:window onkeydown={onKey} />

{#if setup.open}
  <Inicio />
{/if}

<SideMenu />

<main>
  {#if setup.status?.notice && !setup.open && !setup.noticeHidden}
    <div class="notice" role="status">
      <span>Falta terminar la configuración: {setup.status.missing.map(id => setup.step(id)?.label.toLowerCase()).join(', ')}.</span>
      <button class="primary" onclick={() => setup.start()}>Completar</button>
      <button class="ghost" onclick={() => (setup.noticeHidden = true)}>Ahora no</button>
    </div>
  {/if}
  {#key nav.screen}
    <div class="screen">
      {#if nav.screen === 'estudio'}<Estudio />
      {:else if nav.screen === 'fuentes'}<Fuentes />
      {:else if nav.screen === 'musica'}<Musica />
      {:else if nav.screen === 'ajustes'}<Ajustes />
      {:else if nav.screen === 'agentes'}<Agentes />
      {:else if nav.screen === 'mapa'}<Mapa />
      {:else}<Recomendaciones />{/if}
    </div>
  {/key}
</main>

<Transport />
<Toast />

<style>
  main { transition: margin-left 0.3s var(--ease); margin-left: calc(var(--menu-w) + 24px); padding: 16px 20px max(140px, calc(var(--bar-h, 0px) + 36px)) 8px; min-height: 100vh; }
  .screen { max-width: 2200px; display: grid; grid-template-columns: minmax(0, 1fr); gap: 16px; align-content: start; animation: rise 0.4s var(--ease) both; }
  .notice { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 10px 14px; margin-bottom: 12px; border-radius: 12px; background: rgba(240, 164, 60, 0.1); border: 1px solid rgba(240, 164, 60, 0.35); max-width: 2200px; }
  .notice span { flex: 1; min-width: 200px; }
  @media (max-width: 760px) { main { margin-left: 0; padding: 12px 12px max(170px, calc(var(--bar-h, 0px) + 120px)); } }
</style>
