import { player } from './player.svelte';
import { nav } from './nav.svelte';
import { toast } from './toast.svelte';

const norm = (s: string) => s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, ' ').trim();

/** Busca un tema en la biblioteca local (por título y artista) y lo manda al Estudio. */
export async function sendToStudio(item: { title: string; artist: string; localId?: string }, opts: { play?: boolean } = {}) {
  const hit = player.tracks.find(t => t.id === item.localId) ??
    player.tracks.find(t => norm(t.title) === norm(item.title) && norm(t.artist) === norm(item.artist));
  if (!hit) {
    toast.show(`No encontramos "${item.title}" en tus archivos. Arrastralo a Fuentes o conseguilo, por ejemplo en Bandcamp.`, 'warn');
    return;
  }
  nav.go('estudio');
  if (player.track?.id !== hit.id || player.status !== 'ready') await player.load(hit.id);
  if (opts.play && player.status === 'ready' && !player.playing) await player.play();
}
