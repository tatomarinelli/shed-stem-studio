// Lee el token de emparejamiento que Fuentes puso en la dirección (#stemshed=TOKEN&port=PUERTO), lo guarda y limpia la dirección.
const api = globalThis.browser ?? globalThis.chrome;
const m = /[#&]stemshed=([\w-]{16,64})&port=(\d{4,5})/.exec(location.hash);
if (m && +m[2] >= 1024 && +m[2] <= 65535) {
  api.runtime.sendMessage({ type: 'pair', token: m[1], port: +m[2] });
  history.replaceState(null, '', location.pathname + location.search);
}
