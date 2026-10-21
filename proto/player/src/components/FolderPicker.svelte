<script lang="ts">
  let { start, title, onpick, onclose }: { start: string; title: string; onpick: (path: string) => void; onclose: () => void } = $props();

  let dialog: HTMLDialogElement;
  let current = $state({ path: '', parent: null as string | null, dirs: [] as string[], freeGB: 0 });
  let typed = $state('');
  let error = $state('');

  async function go(path: string) {
    error = '';
    try {
      const res = await fetch(`/engine/fs?path=${encodeURIComponent(path)}`);
      const body = await res.json();
      if (!res.ok) { error = body.message; return; }
      current = body;
      typed = body.path;
    } catch {
      error = 'No pude hablar con el motor.';
    }
  }

  $effect(() => { dialog.showModal(); go(start || '/'); });
  const child = (name: string) => (current.path === '/' ? '' : current.path) + '/' + name;
</script>

<dialog bind:this={dialog} onclose={onclose} aria-label={title}>
  <h3>{title}</h3>
  <form class="path" onsubmit={e => { e.preventDefault(); go(typed); }}>
    <input type="text" bind:value={typed} aria-label="Ruta de la carpeta" spellcheck="false" />
    <button type="submit">Ir</button>
  </form>
  {#if error}<p class="err" role="alert">{error}</p>{/if}
  <ul>
    {#if current.parent}<li><button onclick={() => go(current.parent!)}>.. (carpeta de arriba)</button></li>{/if}
    {#each current.dirs as d (d)}<li><button onclick={() => go(child(d))}>{d}</button></li>{:else}
      <li class="muted empty">No hay subcarpetas.</li>
    {/each}
  </ul>
  <div class="foot">
    <span class="muted num">{current.freeGB} GB libres acá</span>
    <span class="grow"></span>
    <button onclick={() => dialog.close()}>Cancelar</button>
    <button class="primary" disabled={!current.path} onclick={() => { onpick(current.path); dialog.close(); }}>Elegir esta carpeta</button>
  </div>
</dialog>

<style>
  dialog { width: min(560px, 92vw); max-height: 80vh; padding: 18px; border: 1px solid var(--glass-line); border-radius: 18px; background: rgba(18, 30, 33, 0.92); backdrop-filter: blur(22px); color: var(--text); box-shadow: 0 30px 80px -20px rgba(0, 0, 0, 0.9); }
  dialog[open] { display: grid; gap: 10px; animation: rise 0.25s var(--ease) both; }
  dialog::backdrop { background: rgba(0, 0, 0, 0.5); backdrop-filter: blur(3px); }
  h3 { margin: 0; font-size: 19px; }
  .path { display: flex; gap: 6px; }
  .path input { flex: 1; min-width: 0; background: rgba(255,255,255,0.06); border: 1px solid var(--glass-line); border-radius: 9px; padding: 7px 10px; }
  ul { list-style: none; margin: 0; padding: 0; overflow: auto; max-height: 40vh; display: grid; gap: 2px; border: 1px solid var(--glass-line); border-radius: 12px; padding: 4px; }
  li button { width: 100%; text-align: left; background: transparent; border: 0; border-radius: 8px; padding: 6px 10px; }
  li button:hover { background: rgba(255,255,255,0.08); }
  .empty { padding: 8px 10px; }
  .foot { display: flex; align-items: center; gap: 8px; }
  .grow { flex: 1; }
  .primary { background: var(--text); color: var(--bg); border-color: var(--text); font-weight: 600; }
  .err { color: var(--loop); margin: 0; }
</style>
