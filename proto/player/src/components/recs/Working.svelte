<script lang="ts">
  // Progreso de una búsqueda: etapa, avance real por candidato y botón para cortarla.
  let { title = '', step, done = 0, total = 0, found = 0, target = 4, cancelling = false, oncancel }:
    { title?: string; step: string; done?: number; total?: number; found?: number; target?: number; cancelling?: boolean; oncancel: () => void } = $props();
  const steps: Record<string, string> = {
    profile: 'Leyendo tus gustos…',
    model: 'Pensando discos con el modelo local…',
    verify: 'Verificando en MusicBrainz…',
    wait_mb: 'Esperando turno en MusicBrainz…',
    choose: 'Eligiendo un disco de cada artista…',
    review: 'El revisor lee lo elegido contra tu pedido…',
    context: 'Buscando el contexto de cada disco…',
  };
  const counted = $derived((step === 'verify' || step === 'context') && total > 0);
  const detail = $derived([counted ? `${Math.min(done + 1, total)} de ${total}` : '', step === 'verify' && found ? `${found} de ${target} encontrados` : ''].filter(Boolean).join(' · '));
</script>

<div class="working" role="status" aria-live="polite">
  {#if title}<b>{title}</b>{/if}
  <p>{cancelling ? 'Cancelando…' : (steps[step] ?? 'Trabajando…')}</p>
  <div class="bar" class:det={counted}><i style={counted ? `width:${Math.round((done / total) * 100)}%` : ''}></i></div>
  <div class="row">
    <span class="muted">{detail}</span>
    <span class="acts"><a class="link" href="#/agentes">Ver agentes</a><button class="ghost" onclick={oncancel} disabled={cancelling}>Cancelar</button></span>
  </div>
</div>

<style>
  .working { display: grid; gap: 8px; max-width: 520px; padding: 14px 0; }
  .working p { margin: 0; font-size: 18px; font-weight: 600; }
  .bar { height: 5px; border-radius: 3px; background: var(--line); overflow: hidden; }
  .bar i { display: block; height: 100%; width: 40%; border-radius: 3px; background: linear-gradient(90deg, #f0a43c, #ff4d8d, #4fa3d9); animation: slide 1.4s var(--ease) infinite; }
  .bar.det i { animation: none; transition: width 0.4s var(--ease); }
  .row { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 30px; font-size: 13.5px; }
  .acts { display: inline-flex; align-items: center; gap: 12px; }
  .link { color: var(--muted); font-size: 13px; text-decoration: underline; text-underline-offset: 3px; }
  .link:hover { color: var(--text); }
  .row button { padding: 3px 12px; font-size: 13.5px; }
  @keyframes slide { from { transform: translateX(-100%); } to { transform: translateX(250%); } }
</style>
