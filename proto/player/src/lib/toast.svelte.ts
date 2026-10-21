class Toasts {
  text = $state('');
  kind = $state<'info' | 'warn'>('info');
  #timer = 0;
  show(text: string, kind: 'info' | 'warn' = 'info') {
    this.text = text; this.kind = kind;
    clearTimeout(this.#timer);
    this.#timer = window.setTimeout(() => (this.text = ''), 6000);
  }
  hide() { this.text = ''; }
}
export const toast = new Toasts();
