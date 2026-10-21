export interface Separated { id: string; title: string; artist: string; duration: number | null; bytes: number; writable: boolean; created: number | null }

class StemList {
  items = $state<Separated[]>([]);
  loaded = $state(false);
  error = $state('');

  async load() {
    try {
      this.items = await (await fetch('/engine/stems/list')).json();
      this.error = '';
    } catch {
      this.error = 'No pude leer la lista. ¿Está prendido el motor?';
    }
    this.loaded = true;
  }

  /** Borra los stems de un tema de la caché nueva. Devuelve el motivo si no se pudo. */
  async remove(id: string): Promise<string | null> {
    const res = await fetch(`/engine/stems/${id}/delete`, { method: 'POST' });
    const body = await res.json();
    if (!res.ok) return body.message ?? 'No se pudo borrar.';
    await this.load();
    return null;
  }

  get totals() {
    const w = this.items.filter(i => i.writable), r = this.items.filter(i => !i.writable);
    return { writable: w.reduce((a, i) => a + i.bytes, 0), readonly: r.reduce((a, i) => a + i.bytes, 0), count: this.items.length };
  }
}

export const stemlist = new StemList();
