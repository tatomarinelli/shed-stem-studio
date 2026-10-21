// Carga stems FLAC de la caché y los deja en SharedArrayBuffers planares (float32) para el worklet.
export interface TrackInfo { id: string; title: string; artist: string; duration: number; stems: string[] }
export interface LoadedStem { name: string; L: SharedArrayBuffer; R: SharedArrayBuffer; peaks: Uint8Array }
export interface LoadedTrack { stems: LoadedStem[]; length: number; sampleRate: number; flacBytes: number; loadMs: number }

export const PEAKS_PER_SEC = 100;

function computePeaks(L: Float32Array, R: Float32Array, sr: number): Uint8Array {
  const win = Math.floor(sr / PEAKS_PER_SEC);
  const out = new Uint8Array(Math.ceil(L.length / win));
  let max = 1e-9;
  for (let i = 0; i < out.length; i++) {
    let m = 0;
    const end = Math.min(L.length, (i + 1) * win);
    for (let j = i * win; j < end; j += 2) { const a = Math.max(Math.abs(L[j]), Math.abs(R[j])); if (a > m) m = a; }
    out[i] = Math.min(255, Math.round(Math.sqrt(m) * 255));
    if (m > max) max = m;
  }
  return out;
}

export async function loadTrack(
  id: string, ctx: AudioContext, onProgress: (done: number, total: number, name: string) => void,
): Promise<LoadedTrack> {
  const t0 = performance.now();
  const manifest = await (await fetch(`/engine/files/${id}/manifest.json`)).json();
  const wanted = manifest.stems.filter((s: { silent: boolean }) => !s.silent);
  const stems: LoadedStem[] = [];
  let length = 0, flacBytes = 0;
  for (const [i, s] of wanted.entries()) {
    onProgress(i, wanted.length, s.name);
    const buf = await (await fetch(`/engine/files/${id}/${s.file}`)).arrayBuffer();
    flacBytes += buf.byteLength;
    const ab = await ctx.decodeAudioData(buf);
    const copy = (ch: number) => { const sab = new SharedArrayBuffer(ab.length * 4); new Float32Array(sab).set(ab.getChannelData(ch)); return sab; };
    const L = copy(0), R = ab.numberOfChannels > 1 ? copy(1) : L;
    stems.push({ name: s.name, L, R, peaks: computePeaks(new Float32Array(L), new Float32Array(R), ctx.sampleRate) });
    length = Math.max(length, ab.length);
  }
  onProgress(wanted.length, wanted.length, '');
  return { stems, length, sampleRate: ctx.sampleRate, flacBytes, loadMs: performance.now() - t0 };
}
