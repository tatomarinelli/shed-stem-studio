# Guía para agentes: trabajar en la versión de Windows

Para quien retome el trabajo (persona o agente de IA) sin el contexto de las sesiones anteriores. Léela junto con `CLAUDE.md`, `PLAN.md` (Fase 6) y `docs/windows-instalable.md` (el plan completo).

## Objetivo y prioridad
Una app nativa de Windows (instalador `.exe`, ventana propia, sin Docker). **Docker en Windows se probó y no sirve** (passthrough de GPU complejo, recursos mal asignados, interfaz lentísima): no invertir tiempo en arreglarlo, salvo que se pida.

## Principio central: un solo código
- La interfaz (`proto/player`, Svelte) y el motor (`engine/`, Python con librería estándar) son **los mismos** en Linux, Docker y Windows. Nada de ramas ni copias por plataforma.
- Todo lo que depende del sistema operativo vive en **`engine/osenv.py`**: rutas del venv (`venv/bin` vs `venv\Scripts\*.exe`), carpeta de configuración, carpetas prohibidas, `chmod`, flags de subprocesos, RAM/CPU, DPAPI y Job Object. **Si un módulo necesita saber en qué sistema corre, se agrega ahí**, nunca un `if sys.platform` suelto.
- Para cambios de UI, usabilidad o motor: se hacen una vez y llegan a Windows al reconstruir el instalador. Los textos que mencionan Docker o `npm run engine` hay que condicionarlos por plataforma (pendiente).

## Estado (2026-10-21)
| Hecho (probado solo con simulaciones desde Linux) | Pendiente |
|---|---|
| `osenv.py` y su uso en todos los módulos; `tests/test_osenv.py`; 136 tests pasan en Linux | **Correr los tests en Windows real** |
| Sesión de TIDAL cifrada con DPAPI (`protect_file`, `read_protected`) | Verificar DPAPI en Windows |
| Job Object que mata los hijos al terminar el motor (`kill_children_on_exit`) | Verificar que no quedan procesos huérfanos |
| `tools/windows/` : `diagnostico.ps1`, `serve-check.py`, `webview-check.html` | Correrlos y registrar resultados |
| | `services.open_folder` en Windows; entorno de separación (`requirements-env.win-*.txt`); cáscara; instalador; CI de Windows |

Lo marcado "SIN VERIFICAR EN WINDOWS" en el código lo está de verdad: **no afirmar que funciona hasta correrlo en Windows** y registrar el resultado en este archivo.

## Primer paso en una máquina Windows
1. Python 3.12 o 3.13 (no 3.14: es la versión con más riesgo de dependencias sin rueda).
2. `cd engine` y `python -m unittest discover -s tests`. `test_analysis` necesita el entorno de separación (numpy, librosa): se espera que falle sin él. Los demás fallos son el trabajo de la etapa 1: corregir en `osenv.py` o en el módulo, no con parches por prueba.
3. `tools\windows\diagnostico.ps1` (no instala nada ni usa internet) y `tools\windows\serve-check.py` con `webview-check.html` en Edge y en una ventana WebView2. Con eso se decide Tauri o Electron.
4. `python server.py` en `engine` y consultar `http://127.0.0.1:8770/engine/status`.

## Reglas específicas
- No instalar el entorno de separación (≈ 8 GB) ni modelos sin avisar y sin que el usuario elija la carpeta (fuera del disco del sistema si hay otro).
- Rutas con tildes y espacios (`C:\Users\José Pérez`) deben funcionar: probarlas.
- Cada cambio de plataforma lleva su prueba en `engine/tests` (simulando con `osenv.WINDOWS`) y se verifica también en Linux, donde no debe cambiar nada.
- Avisar antes de abrir ventanas visibles; las pruebas de interfaz usan Chromium sin ventana (`proto/tools/uicheck.py`).
- Windows con GPU AMD/Intel: separación en CPU (lenta, sin medir). NVIDIA: torch cu128; hace falta un equipo con NVIDIA para verificar esa ruta.
- Los datos de cada máquina (versión de Windows, GPU, Python, carpeta de datos) se anotan en el registro del final de este archivo, no en archivos locales: así los ve la próxima sesión.

## Equipos de prueba
(Una fila por equipo: Windows, GPU, RAM, Python, carpeta de datos.)

| Equipo | Windows | GPU | RAM | Python | Datos en |
|---|---|---|---|---|---|
| Notebook AMD (Ryzen 9 6900HS) | 11 Pro 10.0.26200 | AMD Radeon RX 6700S (4 GB según Windows) + gráficos integrados; sin NVIDIA | 15,2 GB | 3.14.6 (fuera de lo recomendado, 3.12/3.13) | por defecto (`%LOCALAPPDATA%\ShedStemStudio`); C: 94 GB libres de 930 |

Otros datos de ese equipo: WebView2 155.0.4283.62, Node y Git instalados, sin ffmpeg ni Ollama, Defender como antivirus, es-AR, usuario sin tildes ni espacios.

## Registro de verificaciones en Windows
Todo lo verificado en Windows real (2026-10-21, notebook AMD). **Pendiente re-correr la suite en Linux** tras estos cambios.

- **Tests del motor** (`python -m unittest discover -s tests`, Python 3.14.6): los 125 propios pasan; `test_analysis` falla solo por falta de `soundfile` (esperado, necesita el entorno de separación). Se corrigió:
  - Tests con `0o600`: los modos Unix no existen en Windows; ahora usan `tests/perms.py::assert_private`, que los exige solo fuera de Windows.
  - `test_missing_separation_model_blocks_separation` dependía de que la máquina tuviera un entorno de separación real; ahora arma uno falso.
  - Placas AMD: `resources.py` filtraba con un `sys.platform` suelto; ahora `amd_gpus` simplemente no encuentra nada si no existe `/sys/class/drm`.
  - Husos horarios: Windows no trae la base IANA y `ZoneInfo` falla. Centralizado en `osenv.tzinfo(nombre)` (devuelve `None` y se cae a la hora local, como antes pero en un solo lugar). **El instalador debería incluir el paquete `tzdata`**, si no la hora del contexto usa la del equipo en vez de la de la ciudad del perfil.
- **Job Object** (`kill_children_on_exit`): fallaba al arrancar (el motor no levantaba) con `OverflowError` porque `GetCurrentProcess` devuelve el handle de 64 bits y faltaban los `argtypes`. Corregido; verificado que un hijo muere cuando matan al motor de golpe.
- **DPAPI** (`protect_file`/`read_protected`): cifra, descifra y es idempotente; el texto plano no queda en disco; probado con ruta con tildes y espacios.
- **Motor**: `python server.py` y `GET /engine/status` responden `engine: ok`; al cerrarlo no quedan procesos de Python.
- `tools\windows\diagnostico.ps1`: corrido, datos en la tabla de arriba.
- **Interfaz servida por el motor** (`engine/webui.py`, `tests/test_webui.py`): `GET /` y los archivos de `proto/player/dist` con COOP/COEP, `.wasm` con su tipo y sin salir de la carpeta. Verificado con el motor real. `npm run worklet` usaba `cp` (no existe en Windows): ahora copia con `node`. La interfaz compila en Windows.
- **Carpeta `windows/`** (ver su README): cáscara Tauri 2 (Rust 1.99, VS 2022 con C++) y `build/build.ps1`, que arma `runtime/` (Python 3.13.12 embebible + `tzdata` + motor + interfaz), compila y genera `ShedStemStudio-portable-0.0.1.zip` (12,7 MB) y el instalador NSIS por usuario (10,5 MB). El runtime del zip, descomprimido en una ruta con tildes y espacios, arranca el motor y sirve la interfaz (sin ventana). **El `.exe` con ventana todavía no se abrió.**
- **Placas de video** (`osenv.gpu_adapters`, DXGI; `resources.WindowsGpuCounters`, contadores PDH en inglés; `hardware._gpus`): detecta NVIDIA, AMD e Intel y mide uso y VRAM en vivo. Verificado en la Radeon RX 6700S: **8 GB reales** (Windows informaba 4 GB) y uso/VRAM en vivo. NVIDIA e Intel por DXGI: sin verificar en hardware real. Solo NVIDIA/CUDA cuenta como aceleración (`accel`); AMD/Intel se muestran pero se asume CPU hasta que se compruebe otra cosa (ROCm/Vulkan en Ollama, DirectML), y las recomendaciones lo dicen. Temperatura y potencia quedan en null en Windows.
- **Discos**: la carpeta de datos que todavía no existe ya no da "quedan 0 GB" (se usa el disco donde se creará); la raíz es la unidad (`C:\`), no `\`.
- **Motores de separación según el hardware** (`engine/backends.py`, `GET /engine/backends`, `BackendPicker` en el asistente y Ajustes; análisis en `docs/backends-separacion.md`): recomienda CUDA con NVIDIA y CPU en el resto; DirectML y ROCm figuran "Próximamente" y no se pueden instalar. `POST /engine/env/install` acepta `{"backend": id}`. Probado en el motor real solo el rechazo de motores en estudio y de ids inválidos. **No probar el POST con un motor instalable contra el motor real: arranca la descarga de ~8 GB** (me pasó una vez; se cortó a los 12 MB y se borró).
- **Linux verificado (2026-10-21, Ubuntu 22.04 en WSL, Python 3.10):** los mismos 163 tests pasan y solo falla `test_analysis` (falta numpy). Eso destapó un f-string con barra invertida en `settings.py` que no compila antes de Python 3.12: corregido. Docker usa Python 3.14.
- **Entorno CPU en Windows** (`backends`: `cpu`, vía el asistente): instala y funciona (torch 2.11+cpu, onnxruntime 1.31, audio-separator 0.47.1, Python 3.14.6). Ocupa **1,06 GB**. Falló la primera descarga del modelo por falta de ffmpeg (que `audio-separator` pide hasta para bajar el modelo): se instaló con winget (Gyan.FFmpeg 9.0.2) y `osenv.ensure_ffmpeg_on_path` lo busca donde lo deja winget. Modelo BS-Roformer-SW (699 MB) descargado por el asistente.
- **Separación en CPU, medición parcial:** clip sintético de 90 s con BS-Roformer-SW en el Ryzen 9 6900HS (8 núcleos): **≈ 16 s por trozo, 19 trozos**; se vieron 10 de 19 y la medición no se vio terminar (la sesión se cortó), así que el total de ≈ 5 min por 90 s y ≈ 19 min por un tema de 5:26 (70 trozos) es una estimación. Uso de RAM ≈ 2,7 GB. Pendiente repetirlo completo.
- **TIDAL** en Windows necesita `tidalapi` (`engine/requirements-engine.txt`, la misma 0.8.11 de Docker): `build.ps1` ahora lo incluye en el runtime. En desarrollo hay que `pip install tidalapi==0.8.11`. Sin verificar el inicio de sesión de TIDAL en Windows.
- **Pendiente de empaquetado:** `envsetup` crea el entorno con `sys.executable -m venv`; el Python embebible no trae `venv` ni `pip`, así que en el zip/instalador el botón de instalar el entorno no va a funcionar hasta usar `uv` (como prevé `docs/windows-instalable.md`). ffmpeg también hay que ofrecerlo en el asistente.
- Modo desarrollo en caliente: `python windows/dev.py` (ver `windows/README.md`).
- Sin correr todavía: la ventana (WebView2: audio, AudioWorklet, aislamiento), el instalador, `serve-check.py` con `webview-check.html` (abre Edge y una ventana WebView2, hay que avisar), `services.open_folder`, entorno de separación, cáscara, instalador, CI.
