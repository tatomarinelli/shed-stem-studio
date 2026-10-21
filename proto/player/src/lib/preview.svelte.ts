// Escucha previa de un tema sin separarlo: el motor pasa el audio y no guarda nada.
class Preview {
  id = $state('');
  title = $state('');
  state = $state<'idle' | 'loading' | 'playing' | 'paused' | 'error'>('idle');
  position = $state(0);
  duration = $state(0);
  #audio: HTMLAudioElement | null = null;

  #make(id: string) {
    this.stop();
    const a = new Audio(`/engine/play/${id}`);
    a.preload = 'metadata';
    a.addEventListener('loadedmetadata', () => (this.duration = a.duration));
    a.addEventListener('timeupdate', () => (this.position = a.currentTime));
    a.addEventListener('playing', () => (this.state = 'playing'));
    a.addEventListener('pause', () => { if (this.state === 'playing') this.state = 'paused'; });
    a.addEventListener('ended', () => this.stop());
    a.addEventListener('error', () => (this.state = 'error'));
    this.#audio = a;
    this.id = id;
  }

  async toggle(id: string, title: string) {
    if (this.id === id && this.#audio && this.state !== 'error') {
      if (this.state === 'playing') this.#audio.pause();
      else await this.#audio.play().catch(() => (this.state = 'error'));
      return;
    }
    this.#make(id);
    this.title = title;
    this.state = 'loading';
    await this.#audio!.play().catch(() => (this.state = 'error'));
  }

  seek(sec: number) { if (this.#audio) this.#audio.currentTime = sec; }

  stop() {
    this.#audio?.pause();
    this.#audio = null;
    this.id = ''; this.state = 'idle'; this.position = 0; this.duration = 0;
  }
}

export const preview = new Preview();
