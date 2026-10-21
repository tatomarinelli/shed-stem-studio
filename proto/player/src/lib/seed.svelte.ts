// Puente entre Música y Recomendaciones: "recomendar a partir de esto". Lo escribe Música, lo consume Recomendaciones.
export interface Seed { artist: string; album?: string; title?: string }

class SeedStore {
  value = $state<Seed | null>(null);
  set(seed: Seed) { this.value = seed; }
  clear() { this.value = null; }
}

export const seed = new SeedStore();
