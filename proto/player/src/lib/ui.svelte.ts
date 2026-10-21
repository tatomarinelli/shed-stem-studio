// Preferencias de interfaz que se recuerdan en este navegador.
const KEY = 'stemshed.menuCollapsed';
const read = () => { try { return localStorage.getItem(KEY) === '1'; } catch { return false; } };

class Ui {
  menuCollapsed = $state(read());

  constructor() { this.#apply(); }

  toggleMenu() {
    this.menuCollapsed = !this.menuCollapsed;
    try { localStorage.setItem(KEY, this.menuCollapsed ? '1' : '0'); } catch { /* sin almacenamiento: no se recuerda */ }
    this.#apply();
  }

  #apply() { document.documentElement.style.setProperty('--menu-w', this.menuCollapsed ? '64px' : '220px'); }
}

export const ui = new Ui();
