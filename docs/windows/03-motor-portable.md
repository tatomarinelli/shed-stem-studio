# 03. Motor portable a Windows

Objetivo: que `engine/` corra en Windows **sin cambiar el comportamiento en Linux**. Se hace con ramas por plataforma y un módulo de ayuda; cada cambio va en su commit, con su prueba.

## Cómo trabajar
1. Partí de la lista de fallas de la etapa 0 (D).
2. Creá `engine/plat.py` con las funciones que dependen del sistema (ver abajo) y reemplazá los usos directos.
3. Para cada punto: escribí/ajustá la prueba, corré `python -m unittest discover -s tests` en Windows, y verificá que en Linux el resultado no cambia (las pruebas de Linux las corre quien tenga la otra máquina; mientras tanto, mantené el código de Linux **idéntico**, solo ramificá con `sys.platform == "win32"`).
4. No agregues dependencias: el motor usa solo la librería estándar (`ctypes` y `winreg` son estándar).

## `engine/plat.py` (propuesta)
```python
import os, sys
from pathlib import Path

WIN = sys.platform == "win32"

def config_dir() -> Path:
    """Linux: XDG_CONFIG_HOME o ~/.config; Windows: %APPDATA%. STEMSHED_CONFIG_DIR lo pisa en cualquier sistema (pruebas)."""
def env_bin(env_dir: Path, name: str) -> Path:
    """<env>/venv/bin/<name> en Linux; <env>\\venv\\Scripts\\<name>.exe en Windows."""
def secure_write(path: Path, data: bytes | str): ...   # chmod 600 en Linux; en Windows, archivo en una carpeta del usuario
def forbidden_roots() -> tuple[str, ...]: ...          # prefijos que nunca se aceptan como carpeta de datos
def popen_flags() -> dict: ...                         # Windows: creationflags=CREATE_NO_WINDOW; Linux: {}
```

## Cambios, archivo por archivo

| # | Qué | Archivo y lugar | Cambio | Prueba |
|---|---|---|---|---|
| 1 | Carpeta de configuración (`~/.config/stemshed`, `XDG_CONFIG_HOME`) | `settings.py` (`CONFIG_DIR`), `models.py`, `tidal_source.py` | Una sola función `plat.config_dir()`; en Windows `%APPDATA%\ShedStemStudio`. Mantener `XDG_CONFIG_HOME` para Linux y pruebas. | Con la variable de pruebas, `CONFIG_DIR` apunta a la carpeta temporal en ambos sistemas. |
| 2 | Binarios del entorno (`venv/bin/python`, `audio-separator`, `pip`) | `stems.py` (≈ l. 55 y 197), `analysis.py` (l. 44, 52), `envsetup.py` (l. 31, 57), `settings.py` (l. 81) | `plat.env_bin(env, "python")` etc. Mensajes de error con la ruta correcta. | `envsetup.present()` con un árbol falso de `Scripts\`. |
| 3 | Hardware: `/proc/meminfo`, `/proc/cpuinfo` | `hardware.py` (`_ram`, `_cpu`) | Windows: RAM con `ctypes` (`GlobalMemoryStatusEx`); nombre del CPU con `winreg` (`HKLM\HARDWARE\DESCRIPTION\System\CentralProcessor\0\ProcessorNameString`); hilos con `os.cpu_count()`. Si falla, valores vacíos, nunca una excepción. GPU: `nvidia-smi` ya sirve si está el controlador; si no, lista vacía. | Simular la falla de `ctypes`; la respuesta sigue siendo válida. |
| 4 | Discos | `hardware.py` (`_disks(["/", ...])`) | Usar la raíz de la unidad de cada carpeta configurada (`Path(p).anchor`); en Windows `"/"` es la unidad actual. | Carpetas en dos unidades. |
| 5 | Carpetas prohibidas y selector de carpetas | `settings.py` (`FORBIDDEN`, `list_dirs`, `_abs_dir`), `FolderPicker.svelte` | `plat.forbidden_roots()` (`%SystemRoot%`, `%ProgramFiles%`, `%ProgramFiles(x86)%`, `C:\Windows`); listar **unidades** (`os.listdrives()` en 3.12+) cuando la ruta es la raíz; separador `\`. Rechazar rutas relativas y UNC si no se quieren. La interfaz muestra rutas con `\`. | Rutas con tildes, espacios y unidades distintas. |
| 6 | Permisos `chmod 0o600/0o700` | `profile.py`, `memory.py`, `presets.py`, `library.py`, `tidal_source.py`, `destinations.py`, `recs.py`, `settings.py` | `plat.secure_write()`; en Windows `os.chmod` no protege: dejar el archivo en `%APPDATA%` (solo el usuario lo lee) y documentarlo. **Mejora**: guardar la sesión de TIDAL con DPAPI (`ctypes` + `CryptProtectData`) en vez de texto plano. | Que no falle en Windows y que en Linux siga siendo 600. |
| 7 | Prioridad baja del análisis | `analysis.py` (l. 133, `os.setpriority`) | Ya está dentro de `try/except AttributeError`; en Windows pasar `creationflags=BELOW_NORMAL_PRIORITY_CLASS` a `Popen`. | — |
| 8 | Procesos hijos sin consola | `stems.py`, `analysis.py`, `models.py` (`ollama serve`), `envsetup.py`, `art.py`, `hardware.py` | `**plat.popen_flags()` en cada `Popen`/`run`. Al apagar el motor, terminar el **árbol** de procesos (`taskkill /T /F /PID`). | El apagado no deja `audio-separator.exe` ni `ollama.exe` huérfanos (las pruebas de `services.shutdown` lo cubren con simulaciones). |
| 9 | Ids de archivos locales | `library.py` | Normalizar la ruta (`os.path.normcase`, `/` → `\` o al revés) **antes** de calcular el id, así el mismo archivo no tiene dos ids en Windows. | Misma ruta con distinta capitalización → mismo id. |
| 10 | Caché de Numba y temporales | `analyze.py` (l. 20), `stems.py`, `envsetup.py` | Carpeta temporal dentro de los datos (ya se hace con `STEMSHED_DATA`); no depender de `/tmp`. | — |
| 11 | `ffmpeg` y `ollama` | `stems.py`, `art.py`, `models.py` | Buscar con `shutil.which` (en Windows resuelve `.exe`); mensaje claro si falta ffmpeg ("Instalá ffmpeg desde Ajustes"). | — |
| 12 | Apagar y reiniciar el motor | `services.py` | `httpd.shutdown()` ya es portable; sumar la terminación del árbol (ítem 8). | — |
| 13 | Abrir carpeta en el explorador | `services.py` (`open_folder`) | Ya tiene la rama `os.startfile` (sin probar): probarla. | Sin pruebas automáticas: manual. |
| 14 | Pruebas con rutas Unix | `engine/tests/` | `pathlib` y `tempfile`; no asumir `/tmp`. Marcar con `unittest.skipIf` las que son solo de Linux. | La suite completa verde en Windows. |
| 15 | Scripts de la interfaz | `proto/player/package.json` (`worklet`: usa `cp`) | Reemplazar por un script de Node multiplataforma (`fs.copyFileSync`) para que `npm run dev/build` funcione en Windows. | `npm run build` en Windows. |
| 16 | `uicheck.py` | `proto/tools/uicheck.py` | Ruta del navegador configurable (`CHROME`); en Windows, `chrome.exe` o `msedge.exe`. | Una pasada de `uicheck` en Windows. |

## Lista de verificación del motor en Windows
- [ ] `python engine\server.py 8770` arranca y `/engine/status` responde.
- [ ] `GET /engine/hardware` devuelve CPU, RAM, discos y GPU (o lista vacía) sin errores.
- [ ] El selector de carpetas lista unidades y entra a carpetas con tildes y espacios.
- [ ] Agregar una carpeta de música con tildes: el escaneo lee los archivos y los ids son estables entre reinicios.
- [ ] `POST /engine/env/install` crea `venv\Scripts\...` (en una carpeta de prueba) o falla con un mensaje claro.
- [ ] Separar un clip corto desde el motor (no solo desde la línea de comandos) termina bien y deja los stems en `<datos>\cache`.
- [ ] `POST /engine/shutdown` no deja procesos hijos.

## Criterios de aceptación
- [ ] Todas las pruebas del motor pasan en Windows (las exclusivas de Linux marcadas como omitidas, con el motivo).
- [ ] La lista de verificación completa.
- [ ] Un commit por cambio y un resumen en `RESULTADOS.md` con lo que quedó sin resolver.
