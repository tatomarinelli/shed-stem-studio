// AudioWorklet: lee los stems por posición (SharedArrayBuffer), los mezcla y estira UNA sola mezcla.
import { RubberBandInterface, RubberBandOption as O } from 'rubberband-wasm';
import { SoundTouch } from 'soundtouchjs';

const BLOCK = 128;
// Demora de cada estirador respecto del tiempo de la fuente (medida con _clicktest.html, ver docs/phase0-results.md).
// Rubber Band: el audio se adelanta X ms * (1/velocidad - 1) respecto de un mapeo lineal, con X constante por modo; dispersión ~1 ms.
// SoundTouch no sigue una ley simple y tiene ±15 ms de dispersión: tabla por velocidad (ms; negativo = el audio va adelantado).
const LAT_X = { 'rb-fast': 33.5, 'rb-finer': 52.7 };
const LAT_ST = [[0.25, -300], [0.4, -146.6], [0.5, -91.8], [0.6, -57.2], [0.75, -24], [0.9, -7.5], [1, 0], [1.25, 0]];
const interp = (tab, x) => { if (x <= tab[0][0]) return tab[0][1]; for (let i = 1; i < tab.length; i++) if (x <= tab[i][0]) { const [x0, y0] = tab[i - 1], [x1, y1] = tab[i]; return y0 + ((y1 - y0) * (x - x0)) / (x1 - x0); } return tab[tab.length - 1][1]; };
const MAXN = 4096;

class StemEngine extends AudioWorkletProcessor {
  constructor({ processorOptions: o }) {
    super();
    this.stems = o.stems.map(s => ({ L: new Float32Array(s.L), R: new Float32Array(s.R) }));
    this.length = o.length;
    this.n = this.stems.length;
    this.cur = new Float32Array(o.gains || new Array(this.n).fill(1));
    this.tgt = new Float32Array(this.cur);
    this.pos = o.pos || 0;
    this.loop = null;
    this.speed = 1;
    this.playing = false;
    this.schedule = (o.schedule || []).slice().sort((a, b) => a.t - b.t);
    this.engineName = o.engine;
    this.sr = sampleRate;
    this.mixL = new Float32Array(MAXN);
    this.mixR = new Float32Array(MAXN);
    this.seekT = null;
    // Click: suena en los pulsos detectados, DESPUÉS del estirador, así no se estira ni se corre con la velocidad.
    this.beats = o.beats ? new Float64Array(o.beats.frames) : null;   // pulsos en cuadros de la fuente
    this.beatDown = o.beats ? new Uint8Array(o.beats.down) : null;     // 1 si el pulso es el 1 del compás
    this.clickOn = !!o.clickOn;
    this.clickGain = o.clickGain ?? 0.5;
    this.clicks = [];
    this.outN = 0;           // muestras de salida producidas
    this.stLatency = 0;      // demora del estirador SoundTouch (se calibra con la prueba de sincronía)
    this.stats = { blocks: 0, underruns: 0 };
    this.port.onmessage = e => this.onMsg(e.data);
    if (o.speed) this.speed = o.speed;
    if (o.loop) this.loop = o.loop;
    if (o.autoplay) this.playing = true;
    this.anchor(this.pos);
    this.initEngine(o);
  }

  async initEngine(o) {
    if (this.engineName.startsWith('rb')) {
      const rb = await RubberBandInterface.initialize(o.wasmModule);
      const opts = O.RubberBandOptionProcessRealTime | O.RubberBandOptionChannelsTogether |
        (this.engineName === 'rb-finer' ? O.RubberBandOptionEngineFiner : 0);
      this.rb = rb;
      this.st_ = rb.rubberband_new(this.sr, 2, opts, 1 / this.speed, 1);
      this.inBufs = [rb.malloc(MAXN * 4), rb.malloc(MAXN * 4)];
      this.outBufs = [rb.malloc(BLOCK * 4), rb.malloc(BLOCK * 4)];
      this.inPtrs = rb.malloc(8);
      this.outPtrs = rb.malloc(8);
      rb.memWrite(this.inPtrs, new Uint8Array(new Uint32Array(this.inBufs).buffer));
      rb.memWrite(this.outPtrs, new Uint8Array(new Uint32Array(this.outBufs).buffer));
      this.rbLatency = rb.rubberband_get_latency(this.st_);
    } else {
      this.soundtouch = new SoundTouch();
      this.soundtouch.tempo = this.speed;
      this.tmpIn = new Float32Array(MAXN * 2);
      this.tmpOut = new Float32Array(BLOCK * 2);
    }
    this.ready = true;
    this.port.postMessage({ type: 'ready' });
  }

  onMsg(m) {
    switch (m.type) {
      case 'play': this.playing = true; break;
      case 'pause': this.playing = false; break;
      case 'seek': this.seek(m.frame); break;
      case 'speed': this.anchor(this.heardAt(this.outN)); this.setSpeed(m.value); break;
      case 'loop': { const h = this.heardAt(this.outN); this.loop = m.a == null ? null : { a: m.a, b: m.b }; this.anchor(h); break; }
      case 'gain': this.tgt[m.i] = m.g; break;
      case 'beats': this.beats = m.frames ? new Float64Array(m.frames) : null; this.beatDown = m.down ? new Uint8Array(m.down) : null; break;
      case 'click': this.clickOn = !!m.on; if (m.gain != null) this.clickGain = m.gain; break;
    }
  }

  seek(frame) {
    this.pos = Math.max(0, Math.min(this.length - 1, frame | 0));
    if (this.rb) this.rb.rubberband_reset(this.st_);
    if (this.soundtouch) this.soundtouch.clear();
    this.seekT = currentTime;
    this.anchor(this.pos);
  }

  setSpeed(v) {
    this.speed = v;
    if (this.rb) this.rb.rubberband_set_time_ratio(this.st_, 1 / v);
    if (this.soundtouch) this.soundtouch.tempo = v;
  }

  // Mezcla n cuadros desde this.pos (con vuelta del loop) en mixL/mixR. Devuelve false si se acabó el tema.
  readMix(n) {
    const L = this.mixL, R = this.mixR;
    L.fill(0, 0, n); R.fill(0, 0, n);
    const g0 = this.cur.slice(), step = new Float32Array(this.n);
    for (let i = 0; i < this.n; i++) step[i] = (this.tgt[i] - g0[i]) / n;
    let k = 0, left = n;
    while (left > 0) {
      const end = this.loop ? this.loop.b : this.length;
      if (this.pos >= end) {
        if (!this.loop) return false;
        this.pos = this.loop.a; continue;
      }
      const seg = Math.min(left, end - this.pos);
      for (let i = 0; i < this.n; i++) {
        if (g0[i] === 0 && this.tgt[i] === 0) continue;
        const sL = this.stems[i].L, sR = this.stems[i].R;
        let g = g0[i] + step[i] * k;
        const gs = step[i];
        for (let j = 0, p = this.pos; j < seg; j++, p++, g += gs) { L[k + j] += sL[p] * g; R[k + j] += sR[p] * g; }
      }
      this.pos += seg; k += seg; left -= seg;
    }
    this.cur.set(this.tgt);
    return true;
  }

  process(_, outputs) {
    const out = outputs[0];
    while (this.schedule.length && currentTime >= this.schedule[0].t) this.onMsg(this.schedule.shift().msg);
    if (!this.ready || !this.playing) return true;
    this.stats.blocks++;
    const ok = this.rb ? this.pullRB(out) : this.pullST(out);
    if (ok) { if (this.clickOn && this.beats) this.mixClick(out); this.outN += BLOCK; }
    if (!ok) { this.stats.underruns++; }
    else if (this.seekT != null && (Math.abs(out[0][0]) > 1e-7 || Math.abs(out[0][BLOCK - 1]) > 1e-7)) {
      this.port.postMessage({ type: 'seeked', ms: (currentTime - this.seekT) * 1000 });
      this.seekT = null;
    }
    if (this.stats.blocks % 16 === 0) this.port.postMessage({ type: 'pos', pos: this.audiblePos(), t: currentTime, underruns: this.stats.underruns });
    return true;
  }

  // Posición que se está escuchando: lo leído menos lo que todavía espera en la salida del estirador.
  // ---- Tiempo de la fuente que se OYE, de forma determinista: una ancla (posición de la fuente en una muestra de salida)
  // más la velocidad. No depende de cuánto tenga pendiente el estirador, que cambia a tirones.
  anchor(pos) { this.anchorPos = this.loop && pos >= this.loop.b ? this.loop.a : pos; this.anchorOut = this.outN; }

  heardAt(k) {
    const ms = this.engineName in LAT_X ? -LAT_X[this.engineName] * (1 / this.speed - 1) : interp(LAT_ST, this.speed);
    const lat = (ms * this.sr) / 1000;
    let x = this.anchorPos + Math.max(0, k - this.anchorOut - lat) * this.speed;
    if (this.loop && this.anchorPos < this.loop.b && x >= this.loop.b) x = this.loop.a + ((x - this.loop.a) % (this.loop.b - this.loop.a));
    return x;
  }

  mixClick(out) {
    const b = this.beats, h0 = this.heardAt(this.outN), h1 = this.heardAt(this.outN + BLOCK);
    const first = (x) => { let lo = 0, hi = b.length; while (lo < hi) { const m = (lo + hi) >> 1; if (b[m] > x) hi = m; else lo = m + 1; } return lo; };
    const emit = (i, offset) => this.clicks.push({ delay: Math.max(0, Math.min(BLOCK - 1, offset)), t: 0, f: this.beatDown[i] ? 1500 : 1000, g: this.beatDown[i] ? 0.9 : 0.55 });
    if (h1 >= h0) {
      const span = h1 - h0 || 1;
      for (let i = first(h0); i < b.length && b[i] <= h1; i++) emit(i, Math.floor(((b[i] - h0) / span) * BLOCK));
    } else if (this.loop) { // la vuelta del loop cae dentro de este bloque
      const { a: la, b: lb } = this.loop, s1 = Math.max(0, lb - h0), s2 = Math.max(0, h1 - la), tot = s1 + s2 || 1;
      for (let i = first(h0); i < b.length && b[i] <= lb; i++) emit(i, Math.floor(((b[i] - h0) / tot) * BLOCK));
      for (let i = first(la - 1); i < b.length && b[i] <= h1; i++) if (b[i] >= la) emit(i, Math.floor(((s1 + b[i] - la) / tot) * BLOCK));
    }
    const LEN = Math.floor(this.sr * 0.04), tau = this.sr * 0.006;
    for (const c of this.clicks) {
      for (let i = c.delay; i < BLOCK && c.t < LEN; i++, c.t++) {
        const v = Math.sin((2 * Math.PI * c.f * c.t) / this.sr) * Math.exp(-c.t / tau) * c.g * this.clickGain;
        out[0][i] += v; if (out[1]) out[1][i] += v;
      }
      c.delay = 0;
    }
    this.clicks = this.clicks.filter(c => c.t < LEN);
  }

  audiblePos() {
    const pending = this.rb ? this.rb.rubberband_available(this.st_) : this.soundtouch.outputBuffer.frameCount;
    let p = this.pos - pending * this.speed;
    if (this.loop && p < this.loop.a && this.pos >= this.loop.a) p += this.loop.b - this.loop.a;
    return Math.max(0, p);
  }

  pullRB(out) {
    const rb = this.rb, s = this.st_;
    let guard = 0;
    while (rb.rubberband_available(s) < BLOCK && guard++ < 64) {
      const n = Math.max(256, Math.min(MAXN, rb.rubberband_get_samples_required(s)));
      if (!this.readMix(n)) { this.playing = false; this.port.postMessage({ type: 'ended' }); return false; }
      rb.memWrite(this.inBufs[0], this.mixL.subarray(0, n));
      rb.memWrite(this.inBufs[1], this.mixR.subarray(0, n));
      rb.rubberband_process(s, this.inPtrs, n, 0);
    }
    if (rb.rubberband_available(s) < BLOCK) return false;
    rb.rubberband_retrieve(s, this.outPtrs, BLOCK);
    out[0].set(rb.memReadF32(this.outBufs[0], BLOCK));
    if (out[1]) out[1].set(rb.memReadF32(this.outBufs[1], BLOCK));
    return true;
  }

  pullST(out) {
    const st = this.soundtouch;
    let guard = 0;
    while (st.outputBuffer.frameCount < BLOCK && guard++ < 64) {
      const n = 256;
      if (!this.readMix(n)) { this.playing = false; this.port.postMessage({ type: 'ended' }); return false; }
      for (let i = 0; i < n; i++) { this.tmpIn[2 * i] = this.mixL[i]; this.tmpIn[2 * i + 1] = this.mixR[i]; }
      st.inputBuffer.putSamples(this.tmpIn, 0, n);
      st.process();
    }
    if (st.outputBuffer.frameCount < BLOCK) return false;
    st.outputBuffer.receiveSamples(this.tmpOut, BLOCK);
    for (let i = 0; i < BLOCK; i++) { out[0][i] = this.tmpOut[2 * i]; if (out[1]) out[1][i] = this.tmpOut[2 * i + 1]; }
    return true;
  }
}
registerProcessor('stem-engine', StemEngine);
