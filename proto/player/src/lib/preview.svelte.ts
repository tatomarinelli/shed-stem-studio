// Escucha normal de un tema sin separarlo: el motor pasa el audio y no guarda nada.
// Un único <audio> para toda la cola: así el navegador no bloquea el avance automático.
// Lo maneja la fachada de `playback.svelte.ts`; acá solo está el elemento y su estado.
class Preview {
  id = $state('');
  state = $state<'idle' | 'loading' | 'playing' | 'paused' | 'error'>('idle');
  position = $state(0);
  duration = $state(0);
  volume = 1; // ganancia ya con la curva aplicada
  onended: (() => void) | null = null;
  onfailed: (() => void) | null = null;
  onplaying: (() => void) | null = null;
  /** Se llama cuando alguien de afuera corta la escucha (por ejemplo, el Estudio empieza a sonar). */
  onstopped: (() => void) | null = null;
  #audio: HTMLAudioElement | null = null;

  #el() {
    if (this.#audio) return this.#audio;
    const a = new Audio();
    a.preload = 'metadata';
    a.volume = this.volume;
    const dur = () => { if (Number.isFinite(a.duration)) this.duration = a.duration; };
    a.addEventListener('loadedmetadata', dur);
    a.addEventListener('durationchange', dur);
    a.addEventListener('timeupdate', () => (this.position = a.currentTime));
    a.addEventListener('playing', () => { this.state = 'playing'; this.onplaying?.(); });
    a.addEventListener('pause', () => { if (this.state === 'playing') this.state = 'paused'; });
    a.addEventListener('ended', () => { this.state = 'paused'; this.onended?.(); });
    a.addEventListener('error', () => { if (this.id) this.#fail(); });
    return (this.#audio = a);
  }

  #fail() {
    if (this.state === 'error') return;
    this.state = 'error';
    this.onfailed?.();
  }

  async play(id: string) {
    const a = this.#el();
    this.id = id; this.state = 'loading'; this.position = 0; this.duration = 0;
    a.src = `/engine/play/${id}`;
    try { await a.play(); } catch (e) {
      if (this.id !== id || (e as DOMException).name === 'AbortError') return; // lo pisó otro tema
      this.#fail();
    }
  }

  pause() { this.#audio?.pause(); }
  async resume() {
    const a = this.#audio;
    if (!a || !this.id) return;
    if (this.duration && a.currentTime >= this.duration - 0.1) a.currentTime = 0;
    try { await a.play(); } catch (e) { if ((e as DOMException).name !== 'AbortError') this.#fail(); }
  }
  seek(sec: number) { if (this.#audio) this.#audio.currentTime = this.position = Math.max(0, sec); }
  setVolume(g: number) { this.volume = g; if (this.#audio) this.#audio.volume = g; }

  /** `silent`: lo corta la propia fachada (cambio de tema) y no avisa. */
  stop(silent = false) {
    const a = this.#audio;
    if (a && this.id) { a.pause(); a.removeAttribute('src'); a.load(); }
    this.id = ''; this.state = 'idle'; this.position = 0; this.duration = 0;
    if (!silent) this.onstopped?.();
  }
}

export const preview = new Preview();
