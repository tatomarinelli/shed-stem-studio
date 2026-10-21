// Carga stems FLAC de la caché y los deja en SharedArrayBuffers planares (float32).
export const STEM_NAMES = ['guitar', 'bass', 'drums', 'piano', 'vocals', 'other'];

export async function loadStems(trackId, ctx, { skipSilent = true } = {}) {
  const t0 = performance.now();
  const manifest = await (await fetch(`/stems/${trackId}/manifest.json`)).json();
  const wanted = manifest.stems.filter(s => !(skipSilent && s.silent));
  const stems = [];
  let length = 0, bytesFlac = 0;
  for (const s of wanted) {
    const buf = await (await fetch(`/stems/${trackId}/${s.file}`)).arrayBuffer();
    bytesFlac += buf.byteLength;
    const ab = await ctx.decodeAudioData(buf);
    const mk = ch => { const sab = new SharedArrayBuffer(ab.length * 4); new Float32Array(sab).set(ab.getChannelData(ch)); return sab; };
    stems.push({ name: s.name, L: mk(0), R: mk(ab.numberOfChannels > 1 ? 1 : 0) });
    length = Math.max(length, ab.length);
  }
  return { manifest, stems, length, sampleRate: ctx.sampleRate, bytesFlac, loadMs: performance.now() - t0 };
}

export async function jsMemory() {
  const r = { heapMB: performance.memory ? performance.memory.usedJSHeapSize / 1e6 : null };
  try { const m = await performance.measureUserAgentSpecificMemory(); r.uaMB = m.bytes / 1e6; } catch (e) { r.uaErr = String(e); }
  return r;
}
