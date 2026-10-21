export interface LocalTrack { id: string; title: string; artist: string; album: string; duration: number | null; folder: string; rel: string }

class Library {
  tracks = $state<LocalTrack[]>([]);
  folders = $state<string[]>([]);
  scanning = $state(false);
  scanned = $state(0);
  total = $state(0);
  available = $state(true);
  #timer = 0;

  async load() {
    try {
      const r = await (await fetch('/engine/library')).json();
      this.tracks = r.tracks; this.folders = r.folders; this.scanning = r.scanning; this.scanned = r.scanned; this.total = r.total;
      this.available = true;
    } catch {
      this.available = false;
      return;
    }
    window.clearTimeout(this.#timer);
    if (this.scanning) this.#timer = window.setTimeout(() => this.load(), 1500);
  }

  async rescan() {
    await fetch('/engine/library/rescan', { method: 'POST' });
    this.scanning = true;
    await this.load();
  }
}

export const library = new Library();
