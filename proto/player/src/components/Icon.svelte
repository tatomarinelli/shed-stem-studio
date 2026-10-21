<script module lang="ts">
  // Íconos de línea, del mismo trazo que los del menú lateral.
  const PATHS = {
    fuentes: 'M4 6h16M4 12h16M4 18h10',
    musica: 'M9 18V6l11-2v12M9 18a3 3 0 11-6 0 3 3 0 016 0zM20 16a3 3 0 11-6 0 3 3 0 016 0z',
    estrella: 'M12 3l2.6 5.6 6.1.7-4.5 4.2 1.2 6L12 16.5 6.6 19.5l1.2-6L3.3 9.3l6.1-.7z',
    onda: 'M3 12h3l2-6 4 12 3-9 2 3h4',
    perfil: 'M12 12a4 4 0 100-8 4 4 0 000 8zM4 20c0-4 3.6-6 8-6s8 2 8 6',
    chip: 'M7 7h10v10H7zM10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4',
    carpeta: 'M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z',
    capas: 'M12 3l9 5-9 5-9-5 9-5zM3 13l9 5 9-5M3 17.5l9 5 9-5',
    volumen: 'M4 9v6h4l5 4V5L8 9H4zM16.5 8.5a5 5 0 010 7M19 6a8.5 8.5 0 010 12',
    silencio: 'M4 9v6h4l5 4V5L8 9H4zM17 9.5l5 5M22 9.5l-5 5',
    anterior: 'M18 5v14L8 12l10-7zM5 5v14',
    siguiente: 'M6 5v14l10-7L6 5zM19 5v14',
    cola: 'M4 6h12M4 11h12M4 16h7M16 14v6l5-3-5-3z',
    estudio: 'M5 20V11M10 20V4M15 20v-9M20 20V7',
    cerrar: 'M6 6l12 12M18 6L6 18',
    enlaces: 'M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1M14 10a4 4 0 00-5.7 0l-3 3a4 4 0 005.7 5.7l1-1',
  } as const;
  export type IconName = keyof typeof PATHS;
</script>

<script lang="ts">
  let { name, size = 20 }: { name: IconName; size?: number } = $props();
</script>

<svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d={PATHS[name]} /></svg>
