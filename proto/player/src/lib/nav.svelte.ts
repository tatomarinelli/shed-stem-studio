export type Screen = 'fuentes' | 'musica' | 'recomendaciones' | 'agentes' | 'mapa' | 'estudio' | 'ajustes';
export const SCREENS: Screen[] = ['fuentes', 'musica', 'recomendaciones', 'agentes', 'mapa', 'estudio', 'ajustes'];

const fromHash = (): Screen => {
  const h = location.hash.replace('#/', '') as Screen;
  return SCREENS.includes(h) ? h : 'estudio';
};

class Nav {
  screen = $state<Screen>(fromHash());
  constructor() { addEventListener('hashchange', () => (this.screen = fromHash())); }
  go(s: Screen) { location.hash = `#/${s}`; }
}
export const nav = new Nav();
