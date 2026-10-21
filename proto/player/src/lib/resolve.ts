import { toast } from './toast.svelte';

/** Lo mínimo para encontrar el audio de un tema: un id directo, un mapa de ids por fuente o artista + título. */
export interface Playable { title: string; artist: string; album?: string; ids?: { local?: string; tidal?: string }; sourceId?: string; resolve?: boolean }

/** Clave de un tema en la cola: sirve para saber qué fila es la que suena. */
export const playableKey = (p: Playable) =>
  p.ids ? `ids:${p.ids.local ?? ''}|${p.ids.tidal ?? ''}` : p.sourceId ? `id:${p.sourceId}` : `q:${p.artist}|${p.title}|${p.album ?? ''}`;

/**
 * Elige el id reproducible de un tema según el orden de fuentes de Ajustes (lo decide el motor).
 * Si no se puede, avisa con un aviso corto y devuelve null.
 */
export async function resolveId(p: Playable): Promise<string | null> {
  if (!p.resolve && !p.ids) return p.sourceId ?? null;
  try {
    if (p.ids) {
      const q = new URLSearchParams({ ...(p.ids.local ? { local: p.ids.local } : {}), ...(p.ids.tidal ? { tidal: p.ids.tidal } : {}) });
      const r = await (await fetch(`/engine/pick?${q}`)).json();
      if (!r.id) { toast.show(r.message ?? `No pude elegir una fuente para "${p.title}".`, 'warn'); return null; }
      return r.id;
    }
    const r = await (await fetch(`/engine/resolve?${new URLSearchParams({ artist: p.artist, title: p.title, album: p.album ?? '' })}`)).json();
    if (!r.id) { toast.show(`No encontré "${p.title}" en tus fuentes de audio. Revisá el orden y las carpetas en Ajustes.`, 'warn'); return null; }
    return r.id;
  } catch {
    toast.show('No pude hablar con el motor.', 'warn');
    return null;
  }
}

/** Portada de un tema por su id (local o de TIDAL). */
export const artFor = (id?: string) => (!id ? undefined : /^\d+$/.test(id) ? `/engine/albumart/${id}` : `/engine/art/${id}`);
