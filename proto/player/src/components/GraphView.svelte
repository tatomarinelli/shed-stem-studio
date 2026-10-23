<script lang="ts">
  // El lienzo del mapa (graphology + sigma 4, WebGL). Aislado acá: el resto de la app no conoce sigma.
  // Animaciones propias (sigma no interpola los reducers): un valor `focus` 0..1 que se mueve con rAF y que usan los reducers.
  import { onMount } from 'svelte';
  import Graph from 'graphology';
  import Sigma from 'sigma';
  import { communityColor, type GraphData, type Kind } from '../lib/graph.svelte';

  let { data, selected = '', kinds, colorBy = 'type', communities = [], onselect }: { data: GraphData; selected?: string; kinds: Kind[]; colorBy?: 'type' | 'community'; communities?: number[]; onselect: (id: string) => void } = $props();

  const COLOR: Record<Kind, string> = { artist: '#4fa3d9', genre: '#c58bf0', album: '#7cc7a3', rec: '#f0a43c' };
  const DIM = '#1d2b30';
  const SAME = '#7cc7a3', OTHER = '#f08fb0';   // discos de la misma banda / de otras bandas
  // sentido de los colores de las aristas: verde = misma banda, rosa = parecido con discos de otras bandas, violeta = género, ámbar = recomendado
  const EDGE: Record<string, { rest: string | null; lit: string }> = {
    by: { rest: 'rgba(124,199,163,0.55)', lit: '#7cc7a3' },
    similar: { rest: 'rgba(240,143,176,0.17)', lit: '#f08fb0' },
    'similar-to': { rest: 'rgba(240,164,60,0.45)', lit: '#f0a43c' },
    'subgenre-of': { rest: 'rgba(197,139,240,0.30)', lit: '#c58bf0' },
    related: { rest: null, lit: '#f08fb0' },
    'has-genre': { rest: null, lit: '#b58ae0' },
  };
  const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

  let box = $state<HTMLElement>();
  let rings = $state<HTMLCanvasElement>();
  let sigma: Sigma | null = null;
  let g: Graph | null = null;
  let drawn = $state(0);

  // --- estado animado (se lee desde los reducers) ---
  let focus = 0;      // 0 = nada elegido, 1 = hay selección o comunidad
  let intro = 0;      // 0..1: aparición en onda desde el centro
  let hover = '';
  const glows: { u: string; v: string; col: string; a: number }[] = [];
  let raf = 0;
  const ease = (t: number) => 1 - (1 - t) ** 3;

  // --- colores ---
  const rgb = (c: string): [number, number, number] => {
    const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(c);
    return m ? [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)] : [127, 140, 145];
  };
  const mix = (a: string, b: string, t: number) => { const x = rgb(a), y = rgb(b); return `rgb(${x.map((v, i) => Math.round(v + (y[i] - v) * t)).join(',')})`; };
  const alpha = (c: string, a: number) => { const [r, gg, b] = rgb(c); return `rgba(${r},${gg},${b},${a})`; };

  let meId = '', meAttrs: Record<string, unknown> = {};
  const meOf = (id: string) => (meId === id ? meAttrs : ((meId = id), (meAttrs = g!.getNodeAttributes(id))));
  const sel = () => selected;
  let commSet: Set<number> | null = null;   // comunidades en foco (null = ninguna); se rearma solo cuando cambian
  const comm = () => commSet;
  let shownSet = new Set<string>();   // se rearma solo cuando cambian los tipos, no en cada nodo
  const shown = () => shownSet;
  let adj = new Map<string, Set<string>>();   // vecinos de cada nodo, calculados una sola vez al armar el grafo (nunca en hover)
  const EMPTY = new Set<string>();
  const near = (id: string) => adj.get(id) ?? EMPTY;

  function build() {
    const wmax = Math.max(0.0001, ...data.nodes.filter(n => n.type !== 'rec').map(n => n.w));
    const gr = new Graph({ multi: true, type: 'undirected' });
    for (const n of data.nodes) {
      const size = n.type === 'rec' ? 6 : 2.5 + 9 * Math.sqrt(n.w / wmax);
      gr.addNode(n.id, { x: n.x, y: n.y, size, label: n.label, kind: n.type, color: COLOR[n.type], artist: n.type === 'artist' ? n.label : n.artist ?? '', community: n.community, radius: n.radius });
    }
    data.edges.forEach((e, i) => {
      if (!gr.hasNode(e.from) || !gr.hasNode(e.to)) return;
      const a = { kind: e.type, scope: e.scope ?? '', size: 0.6 + 0.8 * e.w, color: '#3b4f55' };
      gr.addEdgeWithKey(`e${i}`, e.from, e.to, a);
    });
    adj = new Map(gr.mapNodes(n => [n, new Set(gr.neighbors(n))] as const));
    return gr;
  }

  const fit = (ids: string[], ratioMin = 0.13) => {  // encuadra un grupo de nodos con margen, con animación
    if (!sigma || !ids.length) return;
    const pts = ids.map(i => sigma!.getNodeDisplayData(i)).filter(Boolean) as { x: number; y: number }[];
    if (!pts.length) return;
    const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
    const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys), 0.02);
    void sigma.getCamera().animate({ x: (Math.min(...xs) + Math.max(...xs)) / 2, y: (Math.min(...ys) + Math.max(...ys)) / 2, ratio: Math.min(1, Math.max(ratioMin, span * 1.7 + 0.04)) },
      { duration: reduced() ? 0 : 750, easing: 'cubicInOut' });
  };

  const tickRing = () => {  // anillos de referencia: dónde pesa más y dónde menos
    const c = rings, s = sigma;
    if (!c || !s) return;
    const { width, height } = s.getDimensions();
    const dpr = devicePixelRatio || 1;
    if (c.width !== width * dpr || c.height !== height * dpr) { c.width = width * dpr; c.height = height * dpr; }
    const x = c.getContext('2d')!;
    x.setTransform(dpr, 0, 0, dpr, 0, 0);
    x.clearRect(0, 0, width, height);
    const o = s.graphToViewport({ x: 0, y: 0 });
    const edge = Math.abs(s.graphToViewport({ x: 0.85, y: 0 }).x - o.x);
    const grad = x.createRadialGradient(o.x, o.y, 0, o.x, o.y, edge);
    grad.addColorStop(0, 'rgba(124,199,163,0.07)'); grad.addColorStop(1, 'rgba(124,199,163,0)');
    x.fillStyle = grad; x.beginPath(); x.arc(o.x, o.y, edge, 0, Math.PI * 2); x.fill();
    for (const r of [0.28, 0.56, 0.85]) {
      x.beginPath(); x.arc(o.x, o.y, Math.abs(s.graphToViewport({ x: r, y: 0 }).x - o.x), 0, Math.PI * 2);
      x.strokeStyle = 'rgba(160,200,210,0.07)'; x.lineWidth = 1; x.setLineDash([2, 7]); x.stroke();
    }
    x.setLineDash([]);
    x.globalCompositeOperation = 'lighter';  // luz aditiva: los resplandores se suman sin tapar
    x.lineCap = 'round';
    for (const gl of glows) {  // resplandor de las líneas conectadas: tres pasadas de ancho creciente y luz tenue, más una línea suave
      if (!g?.hasNode(gl.u) || !g.hasNode(gl.v)) continue;
      const A = g.getNodeAttributes(gl.u), B = g.getNodeAttributes(gl.v);
      const p = s.graphToViewport({ x: A.x as number, y: A.y as number }), q = s.graphToViewport({ x: B.x as number, y: B.y as number });
      for (const [w, al] of [[14, 0.05], [8, 0.09], [4, 0.16]] as const) {
        x.beginPath(); x.moveTo(p.x, p.y); x.lineTo(q.x, q.y);
        x.strokeStyle = alpha(gl.col, al * gl.a); x.lineWidth = w; x.stroke();
      }
    }
    x.globalCompositeOperation = 'source-over';
  };

  // un solo bucle de animación: mueve focus/intro hacia su objetivo y refresca mientras haya algo que mover
  let target = 0, introStart = 0, last = 0;
  const loop = (now: number) => {
    raf = 0;
    if (!sigma) return;
    const dt = Math.min(64, now - (last || now)); last = now;
    const k = reduced() ? 1 : Math.min(1, dt / 260);
    focus += (target - focus) * k;
    if (Math.abs(target - focus) < 0.004) focus = target;
    let busy = focus !== target;
    if (intro < 1) { intro = reduced() ? 1 : Math.min(1, (now - introStart) / 1500); busy = true; }
    redraw();
    if (busy) raf = requestAnimationFrame(loop); else last = 0;
  };
  const redraw = () => { glows.length = 0; sigma?.refresh({ skipIndexation: true }); };
  const kick = () => { if (!raf && sigma) raf = requestAnimationFrame(loop); };

  onMount(() => {
    if (!box) return;
    g = build();
    drawn = g.order;
    introStart = performance.now();
    sigma = new Sigma(g, box, {
      settings: { itemSizesReference: 'screen', labelRenderedSizeThreshold: 6, labelDensity: 0.5, labelGridCellSize: 110, stagePadding: 70, enableEdgeEvents: false, antiAliasingFeather: 1.4 },
      // sigma 4: los estilos son declarativos y se leen de los atributos del nodo; los reducers retocan el resultado
      styles: {
        nodes: { x: { attribute: 'x' }, y: { attribute: 'y' }, size: { attribute: 'size' }, color: { attribute: 'color' }, label: { attribute: 'label' }, labelColor: '#e7eeee', labelSize: 13, labelFont: 'Bricolage Grotesque Variable, system-ui, sans-serif' },
        edges: { size: { attribute: 'size' }, color: { attribute: 'color' } },
        stage: { background: 'transparent' },
      },
      nodeReducer: (id, d, attrs) => {
        const s = sel(), c = comm(), k = attrs.kind as Kind;
        if (!shown().has(k)) return { ...d, hidden: true, visibility: 'hidden' as const };
        const rippled = ease(Math.max(0, Math.min(1, (intro * 1.7 - (attrs.radius as number)) / 0.7)));   // aparece de adentro hacia afuera
        const baseColor = colorBy === 'community' ? communityColor(attrs.community as number) : (d.color as string);
        const size = (d.size as number) * rippled;
        const hov = hover && !s ? hover : '';
        if (s) {
          if (id === s) return { ...d, size: size * 1.25, color: baseColor, zIndex: 4, highlighted: true, labelVisibility: 'visible' as const, labelSize: 15 };
          if (!near(s).has(id)) {  // lo que no está conectado se apaga y se achica: queda de fondo, desenfocado
            const t = focus;
            return { ...d, size: size * (1 - 0.35 * t), color: mix(baseColor, DIM, t * 0.9), label: t > 0.5 ? '' : d.label, zIndex: 0,
              };
          }
          const me = meOf(s);
          let col = baseColor;
          if (colorBy === 'type' && k === 'album' && (me.kind === 'album' || me.kind === 'artist')) col = attrs.artist === me.artist ? SAME : OTHER;
          if (colorBy === 'type' && k === 'artist' && me.kind === 'artist') col = OTHER;   // artista parecido: otra banda
          const left = (attrs.x as number) < (me.x as number);  // la etiqueta mira hacia afuera de la flor
          return { ...d, size: size * (1 + 0.15 * focus), color: col, zIndex: 3, labelVisibility: near(s).size <= 14 || (d.size as number) > 6 ? ('visible' as const) : ('auto' as const), labelSize: 13, labelPosition: left ? ('left' as const) : ('right' as const) };
        }
        if (c) {
          if (!c.has(attrs.community as number)) return { ...d, size: size * (1 - 0.3 * focus), color: mix(baseColor, DIM, focus * 0.9), label: focus > 0.5 ? '' : d.label, zIndex: 0 };
          return { ...d, size, color: baseColor, zIndex: 2 };
        }
        if (hov) {
          if (id === hov) return { ...d, size: size * 1.2, color: baseColor, zIndex: 4, labelVisibility: 'visible' as const };
          if (near(hov).has(id)) return { ...d, size, color: baseColor, zIndex: 3, labelVisibility: 'visible' as const };
        }
        return { ...d, size, color: baseColor };
      },
      edgeReducer: (e, d, attrs) => {
        const s = sel(), [u, v] = g!.extremities(e), c = comm();
        const hide = { ...d, hidden: true, visibility: 'hidden' as const };
        if (!shown().has(g!.getNodeAttribute(u, 'kind')) || !shown().has(g!.getNodeAttribute(v, 'kind'))) return hide;
        const kind = (attrs.kind as string) ?? '', st = EDGE[kind] ?? { rest: null, lit: '#9fd8bf' };
        const lit = (x: string) => (kind === 'similar' && attrs.scope === 'same-artist' ? SAME : x);
        const hov = hover && !s ? hover : '';
        const active = s || hov;
        if (active) {
          if (u !== active && v !== active) return hide;
          const col = lit(st.lit), t = s ? focus : 1;
          glows.push({ u, v, col, a: t });   // el resplandor de la línea lo dibuja el lienzo 2D (tickRing)
          return { ...d, color: col, size: 1.2 + 0.9 * t, zIndex: 1 };
        }
        if (c) return c.has(g!.getNodeAttribute(u, 'community')) && c.has(g!.getNodeAttribute(v, 'community')) && st.rest ? { ...d, color: st.rest } : hide;
        if (!st.rest || (kind === 'similar' && attrs.scope === 'same-artist')) return hide;
        return { ...d, color: st.rest };
      },
    });
    sigma.on('clickNode', ({ node }) => onselect(node));
    sigma.on('clickStage', () => onselect(''));
    sigma.on('enterNode', ({ node }) => { box!.style.cursor = 'pointer'; if (selected || commSet) return; hover = node; kick(); });
    sigma.on('leaveNode', () => { box!.style.cursor = ''; if (!hover) return; hover = ''; kick(); });
    sigma.on('afterRender', tickRing);
    kick();
    return () => { cancelAnimationFrame(raf); sigma?.kill(); sigma = null; g = null; };
  });

  $effect(() => { colorBy; shownSet = new Set<string>(kinds); redraw(); });
  $effect(() => {  // al elegir algo (clic, búsqueda, lista) o una comunidad: se apaga el resto y la cámara encuadra lo conectado
    const id = selected, list = communities;
    if (!sigma || !g) return;
    commSet = list.length ? new Set(list) : null;
    target = id || commSet ? 1 : 0;
    focus = id || commSet ? Math.min(focus, 0.15) : focus;
    kick();
    if (id && g.hasNode(id)) fit([id, ...[...near(id)].filter(n => shown().has(g!.getNodeAttribute(n, 'kind')))]);
    else if (commSet) fit(g.filterNodes((_, a) => commSet!.has(a.community as number)));
    else void sigma.getCamera().animate({ x: 0.5, y: 0.5, ratio: 1 }, { duration: reduced() ? 0 : 650, easing: 'cubicInOut' });
  });
</script>

<div class="wrap">
  <div class="canvas" bind:this={box} data-drawn={drawn} role="img" aria-label="Mapa de tu música: {drawn} nodos. La vista de lista tiene lo mismo, navegable con el teclado."></div>
  <canvas class="rings" bind:this={rings} aria-hidden="true"></canvas>
</div>

<style>
  .wrap { position: relative; width: 100%; height: 100%; min-height: 420px; border-radius: var(--radius); border: 1px solid var(--glass-line); overflow: hidden;
    background: radial-gradient(ellipse at 50% 48%, rgba(124, 199, 163, 0.10), transparent 58%), radial-gradient(ellipse at 20% 90%, rgba(79, 163, 217, 0.07), transparent 50%), var(--panel); }
  .wrap::after { content: ''; position: absolute; inset: 0; pointer-events: none; box-shadow: inset 0 0 90px rgba(0, 0, 0, 0.45); border-radius: inherit; }
  .canvas { position: absolute; inset: 0; }
  .rings { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
</style>
