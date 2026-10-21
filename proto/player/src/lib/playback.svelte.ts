// Fachada de reproducción: sabe qué está sonando ('estudio' = los stems del DAW, 'player' = escucha normal
// con cola) y deja manejarlo igual desde cualquier pantalla. También guarda el volumen general.
import { player } from './player.svelte';
import { preview } from './preview.svelte';
import { separation } from './separation.svelte';
import { toast } from './toast.svelte';
import { sendToStudio } from './studio';
import { artFor, playableKey, resolveId, type Playable } from './resolve';

export interface QItem extends Playable { key: string; art?: string; seconds?: number; pid?: string }
export type Mode = 'idle' | 'estudio' | 'player';

/** Arma un item de cola. */
export const queueItem = (p: Playable & { art?: string; seconds?: number }): QItem => ({ ...p, key: playableKey(p) });

const VOL_KEY = 'stemshed.volume';
/** Curva cuadrática: el recorrido fino queda en los volúmenes bajos. */
export const volumeCurve = (v: number) => v * v;

class Playback {
  queue = $state<QItem[]>([]);
  index = $state(-1);
  resolving = $state(false);
  volume = $state(1); // posición del fader, 0..1
  muted = $state(false);
  #token = 0;  // invalida una resolución pendiente cuando el usuario cambia de tema
  #fails = 0;  // temas seguidos que no se pudieron reproducir

  constructor() {
    try {
      const s = JSON.parse(localStorage.getItem(VOL_KEY) ?? 'null');
      if (s && typeof s.v === 'number' && s.v >= 0 && s.v <= 1) { this.volume = s.v; this.muted = !!s.m; }
    } catch { /* sin almacenamiento: queda el valor por defecto */ }
    this.#apply();
    preview.onended = () => this.#ended();
    preview.onfailed = () => this.#failed();
    preview.onplaying = () => (this.#fails = 0);
    preview.onstopped = () => this.#clear(); // otro cortó la escucha (el Estudio empezó a sonar)
    this.#session();
  }

  // ---- estado
  get mode(): Mode { return this.index >= 0 && this.queue.length ? 'player' : player.status === 'ready' ? 'estudio' : 'idle'; }
  get current(): QItem | null { return this.queue[this.index] ?? null; }
  get playing() { return this.mode === 'player' ? preview.state === 'playing' : this.mode === 'estudio' && player.playing; }
  get loading() { return this.mode === 'player' && (this.resolving || preview.state === 'loading'); }
  get failed() { return this.mode === 'player' && preview.state === 'error'; }
  get position() { return this.mode === 'player' ? preview.position : player.position; }
  get duration() { return this.mode === 'player' ? preview.duration || this.current?.seconds || 0 : player.duration; }
  get hasNext() { return this.index + 1 < this.queue.length; }
  /** Id reproducible del tema actual (ya resuelto). */
  get currentId() { return this.mode === 'player' ? (preview.id || this.current?.pid || '') : ''; }
  get currentArt() { return this.current?.art ?? artFor(this.currentId); }
  /** ¿Es esta fila la que suena (o la que está cargada en la escucha)? */
  isCurrent(key: string) { return this.mode === 'player' && this.current?.key === key; }

  // ---- cola
  /** Reproduce una lista desde el tema `start` hasta el final. */
  playFrom(items: QItem[], start = 0) {
    if (!items[start]) return;
    player.pause(); // el DAW queda cargado, pero en pausa
    this.queue = items;
    this.#fails = 0;
    void this.#go(start);
  }

  async #go(i: number) {
    const my = ++this.#token;
    this.index = i;
    this.resolving = true;
    preview.stop(true);
    const item = this.queue[i];
    // La fuente se elige recién cuando llega su turno, con el orden global de Ajustes.
    const id = item.pid ?? (await resolveId(item));
    if (my !== this.#token) return;
    this.resolving = false;
    if (!id) { this.#skip(); return; }
    item.pid = id;
    await preview.play(id);
  }

  #skip() {
    if (++this.#fails >= this.queue.length || !this.hasNext) { this.stop(); return; }
    void this.#go(this.index + 1);
  }
  #failed() {
    toast.show(`No pude reproducir "${this.current?.title ?? 'el tema'}".`, 'warn');
    this.#skip();
  }
  #ended() {
    if (this.hasNext) { this.#fails = 0; void this.#go(this.index + 1); } else this.stop();
  }
  #clear() { this.#token++; this.queue = []; this.index = -1; this.resolving = false; }

  jump(i: number) { if (this.queue[i]) { this.#fails = 0; void this.#go(i); } }
  next() {
    if (this.mode === 'player') { if (this.hasNext) this.jump(this.index + 1); }
    else if (this.mode === 'estudio') player.stepSection(1);
  }
  /** Pasados 3 s vuelve al principio del tema; antes, al anterior. */
  prev() {
    if (this.mode === 'player') {
      if (preview.position > 3 || this.index === 0) this.seek(0); else this.jump(this.index - 1);
    } else if (this.mode === 'estudio') player.stepSection(-1);
  }
  toggle() {
    if (this.mode === 'estudio') { void player.toggle(); return; }
    if (this.mode !== 'player' || this.resolving) return;
    if (preview.state === 'error' || preview.state === 'idle') this.jump(this.index);
    else if (preview.state === 'playing') preview.pause();
    else { player.pause(); void preview.resume(); }
  }
  seek(sec: number) { if (this.mode === 'player') preview.seek(sec); else if (this.mode === 'estudio') player.seek(sec); }
  /** Corta la escucha y vacía la cola; si hay un tema en el Estudio, vuelve a su skin. */
  stop() { this.#clear(); preview.stop(true); }

  // ---- Enviar al Estudio
  get separated() { return !!this.currentId && player.tracks.some(t => t.id === this.currentId); }
  get job() { return this.currentId ? separation.jobs[this.currentId] : undefined; }
  async toStudio() {
    const it = this.current, id = this.currentId;
    if (!it || !id) return;
    if (this.separated) { await sendToStudio({ title: it.title, artist: it.artist, localId: id }, { play: true }); return; }
    if (separation.busy) { toast.show('Ya hay una separación en curso.', 'warn'); return; }
    await separation.start(id);
  }

  // ---- volumen general
  get gain() { return this.muted ? 0 : volumeCurve(this.volume); }
  #apply() { const g = this.gain; preview.setVolume(g); player.setMaster(g); }
  #save() { try { localStorage.setItem(VOL_KEY, JSON.stringify({ v: this.volume, m: this.muted })); } catch { /* sin almacenamiento */ } }
  setVolume(v: number) { this.volume = Math.max(0, Math.min(1, v)); this.muted = false; this.#apply(); this.#save(); }
  toggleMute() { this.muted = !this.muted; this.#apply(); this.#save(); }
  resetVolume() { this.setVolume(1); }

  // ---- teclas de medios y notificación del sistema (Media Session)
  #session() {
    if (typeof navigator === 'undefined' || !('mediaSession' in navigator)) return;
    const ms = navigator.mediaSession;
    const on = (a: MediaSessionAction, f: MediaSessionActionHandler) => { try { ms.setActionHandler(a, f); } catch { /* acción no soportada */ } };
    on('play', () => { if (!this.playing) this.toggle(); });
    on('pause', () => { if (this.playing) this.toggle(); });
    on('nexttrack', () => this.next());
    on('previoustrack', () => this.prev());
    on('seekto', d => { if (d.seekTime != null) this.seek(d.seekTime); });
    on('seekbackward', d => this.seek(this.position - (d.seekOffset ?? 10)));
    on('seekforward', d => this.seek(this.position + (d.seekOffset ?? 10)));
    on('stop', () => { if (this.mode === 'player') this.stop(); else if (this.playing) this.toggle(); });
    $effect.root(() => {
      $effect(() => {
        const m = this.mode;
        let title = '', artist = '', album = '', art: string | undefined;
        const c = this.current;
        if (m === 'player' && c) { title = c.title; artist = c.artist; album = c.album ?? ''; art = this.currentArt; }
        else if (m === 'estudio' && player.track) { title = player.track.title; artist = player.track.artist; art = artFor(player.track.id); }
        ms.metadata = m === 'idle' ? null : new MediaMetadata({ title, artist, album, artwork: art ? [{ src: new URL(art, location.href).href }] : [] });
      });
      $effect(() => { ms.playbackState = this.mode === 'idle' ? 'none' : this.playing ? 'playing' : 'paused'; });
      $effect(() => {
        const d = this.duration, m = this.mode;
        // En el Estudio no se lee la posición (cambia en cada cuadro): el navegador la extrapola con la velocidad.
        const p = m === 'player' ? this.position : 0;
        if (m === 'idle' || !(d > 0)) return;
        try { ms.setPositionState({ duration: d, position: Math.min(p, d), playbackRate: m === 'estudio' ? player.speed : 1 }); } catch { /* valores fuera de rango */ }
      });
    });
  }
}

export const playback = new Playback();
