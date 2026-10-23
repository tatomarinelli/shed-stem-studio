<script lang="ts">
  // "Lo que sé de vos": observaciones con evidencia para confirmar o rechazar, y un resumen de la memoria por temas.
  import { recs, REACTION_LABELS } from '../../lib/recs.svelte';
  const f = $derived(recs.facets);
  const names = (xs: { name: string; w: number }[], n = 8) => xs.slice(0, n).map(x => x.name).join(', ') || '—';
  const open = $derived(f?.observations.items.filter(o => o.status === 'proposed') ?? []);
  const decided = $derived(f?.observations.items.filter(o => o.status !== 'proposed') ?? []);
</script>

<details class="fold" ontoggle={e => { if ((e.currentTarget as HTMLDetailsElement).open) recs.loadMemory(); }}>
  <summary>Lo que sé de vos</summary>
  {#if !f}
    <p class="muted small">Leyendo tu memoria…</p>
  {:else}
    <div class="obs">
      <h5>Conclusiones para revisar</h5>
      {#each open as o (o.id)}
        <div class="o">
          <p>{o.text} <span class="muted small">{o.evidence.length} discos de evidencia · confianza {Math.round(o.confidence * 100)} %</span></p>
          <p class="muted small">{o.effect}</p>
          <div class="acts"><button onclick={() => recs.setObservation(o.id, 'confirmed')}>Es así</button><button class="ghost" onclick={() => recs.setObservation(o.id, 'rejected')}>No es así</button></div>
        </div>
      {:else}
        <p class="muted small">Todavía no hay suficientes reacciones para sacar conclusiones. Con 3 discos de un mismo género ya aparece alguna.</p>
      {/each}
      {#each decided as o (o.id)}
        <p class="done"><span class="tag">{o.status === 'confirmed' ? 'Confirmado' : 'Rechazado'}</span> {o.text}
          <button class="ghost" onclick={() => recs.setObservation(o.id, 'proposed')}>Deshacer</button></p>
      {/each}
    </div>
    <dl class="data">
      <dt>Te gusta</dt><dd>{names(f.taste.artists)}<br /><span class="muted">{names(f.taste.genres)}</span></dd>
      <dt>Evitás</dt><dd>{[...f.avoid.styles, ...f.avoid.confirmedStyles].join(', ') || '—'}</dd>
      <dt>Reacciones</dt><dd>{Object.entries(f.habits.reactions).map(([k, n]) => `${REACTION_LABELS[k as keyof typeof REACTION_LABELS] ?? k}: ${n}`).join(' · ') || '—'}</dd>
      <dt>Querés mejorar</dt><dd>{f.learning.focus.join('; ') || '—'}</dd>
    </dl>
    <p class="muted small">Se arma sola con tus favoritos, tus reacciones y tu perfil. Cada conclusión cita los discos que la sostienen; no cambia lo que se te recomienda hasta que la confirmás.</p>
  {/if}
</details>

<style>
  .fold { background: var(--glass); border: 1px solid var(--glass-line); border-radius: var(--radius); padding: 10px 16px; }
  summary { cursor: pointer; font-weight: 600; }
  h5 { margin: 10px 0 6px; font-size: 14px; }
  .o { padding: 8px 0; border-bottom: 1px solid var(--glass-line); }
  .o p { margin: 0 0 4px; }
  .acts { display: flex; gap: 6px; margin-top: 6px; }
  .acts button { padding: 3px 12px; font-size: 13.5px; }
  .done { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; font-size: 13.5px; color: var(--muted); margin: 6px 0; }
  .tag { font-size: 12px; border-radius: 999px; padding: 1px 9px; border: 1px solid var(--glass-line); }
  .data { display: grid; grid-template-columns: max-content 1fr; gap: 6px 16px; margin: 14px 0 8px; font-size: 14px; }
  .data dt { color: var(--muted); }
  .data dd { margin: 0; min-width: 0; }
</style>
