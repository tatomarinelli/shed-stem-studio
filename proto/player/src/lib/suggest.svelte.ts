// Sugerencias para los campos de estilos y artistas: primero lo que ya está en la biblioteca del usuario
// (GET /engine/music, facetas con conteos), después una lista fija. Se cargan una vez.
import { recs } from './recs.svelte';
export const STYLES = ['jazz', 'jazz modal', 'hard bop', 'bebop', 'cool jazz', 'jazz fusión', 'soul jazz', 'bossa nova', 'soul', 'neo soul', 'funk',
  'blues', 'rock', 'reggae', 'electrónica', 'organic house', 'deep house', 'ambient', 'hip hop', 'mpb', 'folk', 'clásica'];

export interface Sugg { name: string; mine?: boolean }

class Suggest {
  genres = $state<string[]>([]);
  artists = $state<string[]>([]);
  #loaded = false;

  async load() {
    if (this.#loaded) return;
    this.#loaded = true;
    try {
      const f = (await (await fetch('/engine/music?kind=albums&limit=1')).json()).facets;
      this.genres = f.genres.map((g: { name: string }) => g.name);
      this.artists = f.artists.map((a: { name: string }) => a.name).filter((n: string) => !(recs.profile?.ownArtists ?? []).some(o => o.toLowerCase() === n.toLowerCase()));
    } catch { this.#loaded = false; /* sin biblioteca: quedan las fijas */ }
  }

  /** Los 6 estilos más frecuentes tuyos, después la lista fija y al final el resto tuyo (todo aparece al escribir). */
  get styles(): Sugg[] {
    const mine = this.genres;
    return [...mine.slice(0, 6).map(name => ({ name, mine: true })),
      ...STYLES.filter(s => !mine.some(g => g.toLowerCase() === s)).map(name => ({ name })),
      ...mine.slice(6).map(name => ({ name, mine: true }))];
  }
  get artistList(): Sugg[] { return this.artists.map(name => ({ name, mine: true })); }
}

export const suggest = new Suggest();
