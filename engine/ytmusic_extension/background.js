// Si hay un emparejamiento pendiente, toma los encabezados de la primera petición a /youtubei/v1/browse que ya traiga la sesión
// y se los entrega al motor local con el token de un solo uso. Sin emparejamiento pendiente no hace nada.
const api = globalThis.browser ?? globalThis.chrome;
const KEY = 'pair';
const TTL = 10 * 60 * 1000;
let busy = false;

api.runtime.onMessage.addListener(msg => {
  if (msg?.type === 'pair') api.storage.local.set({ [KEY]: { token: msg.token, port: msg.port, at: Date.now() } });
});

async function deliver(details) {
  const { [KEY]: pair } = await api.storage.local.get(KEY);
  if (!pair || Date.now() - pair.at > TTL || busy) return;
  const headers = {};
  for (const h of details.requestHeaders ?? []) headers[h.name] = h.value;
  const get = n => Object.entries(headers).find(([k]) => k.toLowerCase() === n)?.[1] ?? '';
  if (!get('cookie') || !get('authorization').includes('SAPISIDHASH')) return; // todavía no es una petición con sesión
  busy = true;
  try {
    const res = await fetch(`http://127.0.0.1:${pair.port}/engine/pair/ytmusic`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Stemshed-Token': pair.token },
      body: JSON.stringify({ headers })
    });
    if (res.ok || res.status === 403) await api.storage.local.remove(KEY); // entregado, o el token ya no vale
    await api.action.setBadgeText({ text: res.ok ? 'OK' : '!' });
  } catch {
    await api.action.setBadgeText({ text: '!' }); // el motor no responde: el token queda por si vuelve
  } finally { busy = false; }
}

const filter = { urls: ['https://music.youtube.com/youtubei/v1/browse*'], types: ['xmlhttprequest'] };
try { api.webRequest.onSendHeaders.addListener(deliver, filter, ['requestHeaders', 'extraHeaders']); }
catch { api.webRequest.onSendHeaders.addListener(deliver, filter, ['requestHeaders']); } // Firefox no conoce extraHeaders
