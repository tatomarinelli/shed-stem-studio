<script lang="ts">
  import { nav, SCREENS, type Screen } from '../lib/nav.svelte';
  import { player } from '../lib/player.svelte';
  import { ui } from '../lib/ui.svelte';
  import { settings } from '../lib/settings.svelte';

  const items: Record<Screen, { label: string; icon: string }> = {
    fuentes: { label: 'Fuentes', icon: 'M4 6h16M4 12h16M4 18h10' },
    musica: { label: 'Música', icon: 'M9 18V6l11-2v12M9 18a3 3 0 11-6 0 3 3 0 016 0zM20 16a3 3 0 11-6 0 3 3 0 016 0z' },
    recomendaciones: { label: 'Recomendaciones', icon: 'M12 3l2.6 5.6 6.1.7-4.5 4.2 1.2 6L12 16.5 6.6 19.5l1.2-6L3.3 9.3l6.1-.7z' },
    estudio: { label: 'Estudio', icon: 'M3 12h3l2-6 4 12 3-9 2 3h4' },
    ajustes: { label: 'Ajustes', icon: 'M4 7h10M18 7h2M4 17h2M10 17h10M14 5v4M8 15v4' },
  };
  const idx = $derived(SCREENS.indexOf(nav.screen));
  const downloads = $derived((settings.services?.jobs ?? []).filter(j => j.kind === 'descarga' || j.kind === 'instalación'));
</script>

<nav aria-label="Secciones" class:collapsed={ui.menuCollapsed}>
  <div class="brand">{ui.menuCollapsed ? 'S' : 'Shed Stem Studio'}</div>
  <ul style="--i:{idx}">
    <span class="pill" aria-hidden="true"></span>
    {#each SCREENS as s (s)}
      <li>
        <a href="#/{s}" class:active={nav.screen === s} aria-current={nav.screen === s ? 'page' : undefined} title={items[s].label} aria-label={items[s].label}>
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d={items[s].icon} /></svg>
          <span>{items[s].label}</span>
        </a>
      </li>
    {/each}
  </ul>
  {#if downloads.length}
    <a class="dl" href="#/ajustes" title={downloads.map(j => `${j.label} ${j.percent ?? 0} %`).join('\n')} aria-label="Descargas en curso, ir a Ajustes">
      <span class="pulse" aria-hidden="true"></span>
      {#if !ui.menuCollapsed}<span>{downloads.length === 1 ? `${downloads[0].label} ${downloads[0].percent ?? 0} %` : `${downloads.length} descargas`}</span>{/if}
    </a>
  {/if}
  {#if player.status === 'ready' && player.track && !ui.menuCollapsed}
    <div class="now">
      <span class="muted">Sonando</span>
      <b>{player.track.title}</b>
      <span class="muted">{player.track.artist}</span>
    </div>
  {/if}
  <button class="collapse" onclick={() => ui.toggleMenu()} aria-label={ui.menuCollapsed ? 'Expandir el menú' : 'Achicar el menú'} title={ui.menuCollapsed ? 'Expandir el menú' : 'Achicar el menú'}>
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="transform:rotate({ui.menuCollapsed ? 180 : 0}deg);transition:transform .3s var(--ease)"><path d="M15 6l-6 6 6 6" /></svg>
  </button>
</nav>

<style>
  nav { transition: width 0.3s var(--ease), padding 0.3s var(--ease); overflow: hidden; position: fixed; top: 12px; bottom: 12px; left: 12px; width: var(--menu-w); display: flex; flex-direction: column; gap: 22px; padding: 18px 12px; border-radius: 18px; background: var(--glass); border: 1px solid var(--glass-line); backdrop-filter: blur(20px) saturate(1.3); box-shadow: 0 24px 60px -28px rgba(0,0,0,0.8); z-index: 10; }
  .brand { font-weight: 700; font-size: 20px; letter-spacing: -0.02em; padding: 0 10px; font-variation-settings: 'wdth' 90; }
  .dl { height: auto; flex: none; display: flex; align-items: center; gap: 8px; margin: 10px 4px 0; padding: 8px 10px; border-radius: 10px; background: rgba(79, 163, 217, 0.12); border: 1px solid rgba(79, 163, 217, 0.35); color: inherit; text-decoration: none; font-size: 13px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  .pulse { width: 8px; height: 8px; border-radius: 50%; background: #4fa3d9; flex: none; animation: pulse 1.4s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: 0.3; } }
  @media (prefers-reduced-motion: reduce) { .pulse { animation: none; } }
  nav.collapsed .dl { justify-content: center; padding: 8px 0; }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; position: relative; }
  .pill { position: absolute; left: 0; right: 0; top: 0; height: 44px; border-radius: 12px; background: rgba(255, 255, 255, 0.1); border: 1px solid var(--glass-line); transform: translateY(calc(var(--i) * 48px)); transition: transform 0.4s var(--ease); }
  li { position: relative; height: 44px; }
  a { height: 100%; display: flex; align-items: center; gap: 12px; padding: 0 12px; border-radius: 12px; color: var(--muted); text-decoration: none; font-weight: 500; transition: color 0.2s; }
  a:hover, a.active { color: var(--text); }
  .collapse { margin-top: auto; align-self: flex-start; width: 36px; height: 36px; padding: 0; display: grid; place-items: center; border-radius: 10px; background: transparent; color: var(--muted); }
  .collapse:hover { color: var(--text); }
  .now { display: grid; padding: 12px; border-radius: 12px; background: rgba(255, 255, 255, 0.05); font-size: 13.5px; animation: rise 0.5s var(--ease) both; }
  .now b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 15px; }
  nav.collapsed { padding: 18px 8px; }
  nav.collapsed .brand { padding: 0; text-align: center; font-size: 22px; }
  nav.collapsed a { justify-content: center; padding: 0; }
  nav.collapsed a span { display: none; }
  nav.collapsed .collapse { align-self: center; }
  @media (max-width: 760px) {
    .collapse { display: none; }
    nav { top: auto; right: 12px; width: auto; bottom: 12px; flex-direction: row; padding: 8px; gap: 8px; z-index: 20; }
    .brand, .now { display: none; } ul { display: flex; flex: 1; } .pill { display: none; } li { flex: 1; } a { justify-content: center; } a span { display: none; } a.active { background: rgba(255,255,255,0.12); }
  }
</style>
