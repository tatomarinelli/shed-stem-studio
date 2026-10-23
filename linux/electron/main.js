// Cáscara de escritorio para Linux: lanza el motor (Python), espera a que responda y muestra la interfaz que él sirve en una ventana propia.
// Sin lógica de producto: la interfaz y el motor son los mismos que en Windows y Docker.
const { app, BrowserWindow, Menu, dialog, shell } = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const http = require('node:http');
const net = require('node:net');
const path = require('node:path');

const PREFERRED_PORT = 8770; // el origen (puerto) guarda el estado de la interfaz: conviene que no cambie entre sesiones
const START_TIMEOUT_MS = 90_000;

app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
app.setName('Shed Stem Studio');

let engine = null;
let win = null;

function logFile() {
  const dir = path.join(process.env.XDG_STATE_HOME || path.join(process.env.HOME, '.local', 'state'), 'shedstemstudio');
  fs.mkdirSync(dir, { recursive: true });
  return path.join(dir, 'engine.log');
}

function layout() {
  const root = app.isPackaged ? process.resourcesPath : path.join(__dirname, '..', 'build', 'payload');
  return { engine: path.join(root, 'engine'), ui: path.join(root, 'ui'), lib: path.join(root, 'lib') };
}

const get = (port) => new Promise((resolve) => {
  const req = http.get({ host: '127.0.0.1', port, path: '/engine/status', timeout: 1000 }, (res) => { res.resume(); resolve(res.statusCode === 200); });
  req.on('error', () => resolve(false));
  req.on('timeout', () => { req.destroy(); resolve(false); });
});

const portFree = (port) => new Promise((resolve) => {
  const s = net.createServer().once('error', () => resolve(false)).once('listening', () => s.close(() => resolve(true)));
  s.listen(port, '127.0.0.1');
});

async function pickPort() {
  if (await portFree(PREFERRED_PORT)) return PREFERRED_PORT;
  return new Promise((resolve) => {
    const s = net.createServer().listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => resolve(p)); });
  });
}

function fail(msg) {
  dialog.showErrorBox('Shed Stem Studio', msg);
  app.exit(1);
}

async function startEngine() {
  if (await get(PREFERRED_PORT)) return PREFERRED_PORT; // ya hay un motor propio corriendo: solo se abre la ventana
  const l = layout();
  const port = await pickPort();
  const log = fs.openSync(logFile(), 'a');
  engine = spawn('python3', ['-u', path.join(l.engine, 'server.py'), String(port)], {
    cwd: l.engine,
    detached: true, // grupo propio: al cerrar se mata el árbol (Ollama, separación, ffmpeg)
    stdio: ['ignore', log, log],
    env: {
      ...process.env,
      STEMSHED_HOST: '127.0.0.1',
      STEMSHED_ORIGINS: `http://127.0.0.1:${port}`,
      STEMSHED_UI: l.ui,
      STEMSHED_SCHEDULER: '1',
      PYTHONUTF8: '1',
      PYTHONPATH: [l.lib, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
    },
  });
  let exited = false;
  engine.on('exit', () => { exited = true; });
  engine.on('error', (e) => fail(`No pude lanzar Python (python3): ${e.message}`));
  const t0 = Date.now();
  while (!(await get(port))) {
    if (exited) return fail(`El motor se cerró al arrancar.\nRegistro: ${logFile()}`);
    if (Date.now() - t0 > START_TIMEOUT_MS) return fail(`El motor no respondió a tiempo.\nRegistro: ${logFile()}`);
    await new Promise((r) => setTimeout(r, 300));
  }
  return port;
}

function stopEngine() {
  if (engine && engine.exitCode === null) {
    try { process.kill(-engine.pid, 'SIGTERM'); } catch { /* ya terminó */ }
    setTimeout(() => { try { process.kill(-engine.pid, 'SIGKILL'); } catch { /* ya terminó */ } }, 8000).unref();
  }
}

const isInternal = (url) => /^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?\//.test(url);

function openExternal(url) {
  if (/^https?:\/\//.test(url)) void shell.openExternal(url); // solo http y https
}

if (!app.requestSingleInstanceLock()) {
  app.exit(0);
} else {
  app.on('second-instance', () => { if (win) { if (win.isMinimized()) win.restore(); win.focus(); } });
  app.whenReady().then(async () => {
    Menu.setApplicationMenu(null);
    const port = await startEngine();
    if (port === undefined) return;
    win = new BrowserWindow({
      width: 1280, height: 820, minWidth: 900, minHeight: 600,
      title: 'Shed Stem Studio', backgroundColor: '#14110f',
      icon: path.join(app.isPackaged ? process.resourcesPath : path.join(__dirname, '..'), 'app-icon.png'),
      webPreferences: { contextIsolation: true, sandbox: true },
    });
    win.webContents.setWindowOpenHandler(({ url }) => { openExternal(url); return { action: 'deny' }; });
    win.webContents.on('will-navigate', (e, url) => { if (!isInternal(url)) { e.preventDefault(); openExternal(url); } });
    win.webContents.on('page-title-updated', (e) => e.preventDefault()); // el título fijo
    await win.loadURL(`http://127.0.0.1:${port}/`);
  });
  app.on('window-all-closed', () => app.quit());
  app.on('before-quit', stopEngine);
  process.on('exit', stopEngine); // último recurso: cualquier salida del proceso apaga el motor
  for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, () => { stopEngine(); app.exit(0); });
}
