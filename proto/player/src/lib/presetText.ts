// Horarios de los perfiles de sugerencia en lenguaje natural y detección de solapes (misma regla que engine/presets.py:
// un rango que termina antes de empezar cruza la medianoche y pertenece al día en que empieza).
import type { Preset, Range } from './recs.svelte';

const SHORT = ['lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom'];
const LONG = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábados', 'domingos'];

const hm = (s: string) => { const [h, m] = s.split(':').map(Number); return h * 60 + m; };
const fmt = (min: number) => `${Math.floor(min / 60)}:${String(min % 60).padStart(2, '0')}`;

export function days(ds: number[]): string {
  const d = [...ds].sort();
  if (d.length === 7) return 'todos los días';
  if (d.join() === '0,1,2,3,4') return 'lun a vie';
  if (d.join() === '5,6') return 'sáb y dom';
  // tramos consecutivos: "lun a mié, vie"
  const parts: string[] = [];
  for (let i = 0; i < d.length; i++) {
    let j = i;
    while (j + 1 < d.length && d[j + 1] === d[j] + 1) j++;
    parts.push(j - i >= 2 ? `${SHORT[d[i]]} a ${SHORT[d[j]]}` : d.slice(i, j + 1).map(x => SHORT[x]).join(', '));
    i = j;
  }
  return parts.join(', ');
}

export function range(r: Range): string {
  if (r.start === '00:00' && r.end === '24:00') return `${days(r.days)}, todo el día`;
  return `${days(r.days)}, ${fmt(hm(r.start))} a ${fmt(hm(r.end) % 1440 || (r.end === '24:00' ? 1440 : 0))}`.replace(' a 24:00', ' a 0:00');
}

export const schedule = (p: Preset) => (p.schedule.length ? p.schedule.map(range).join(' · ') : 'a demanda');

/** Minutos de la semana (0..10079) que cubre un rango, como intervalos [a, b). */
function weekly(r: Range): [number, number][] {
  const a = hm(r.start), b = hm(r.end), len = b > a ? b - a : 1440 - a + b;
  const out: [number, number][] = [];
  for (const d of r.days) {
    const s = d * 1440 + a, e = s + len;
    if (e <= 10080) out.push([s, e]); else { out.push([s, 10080]); out.push([0, e - 10080]); }
  }
  return out;
}

/** Primer solape entre dos perfiles, en palabras ("los lunes de 9:00 a 18:00"), o null. */
export function overlap(a: Preset, b: Preset): string | null {
  for (const ra of a.schedule) for (const rb of b.schedule) {
    for (const [s1, e1] of weekly(ra)) for (const [s2, e2] of weekly(rb)) {
      const s = Math.max(s1, s2), e = Math.min(e1, e2);
      if (s < e) {
        const day = Math.floor(s / 1440), from = s % 1440, to = e - day * 1440;
        return `los ${LONG[day]} de ${fmt(from)} a ${to >= 1440 ? fmt(to - 1440) + ' (del día siguiente)' : fmt(to)}`;
      }
    }
  }
  return null;
}
