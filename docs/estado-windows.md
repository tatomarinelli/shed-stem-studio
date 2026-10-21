# Estado de la versión de Windows

Actualizado: 2026-10-21, notebook con Windows 11 Pro (build 26200), Ryzen 9 6900HS, 15,2 GB de RAM, Radeon RX 6700S (8 GB) y gráficos integrados. Detalle de cada prueba: `docs/windows-agentes.md` (registro). Plan completo: `docs/windows-instalable.md`.

## Qué hay

| Entregable | Tamaño | Dónde |
|---|---|---|
| Zip portable (`ShedStemStudio.exe` + `runtime/`) | 28,8 MB | `windows/build/out/ShedStemStudio-portable-0.0.1.zip` (no se versiona) |
| Instalador NSIS por usuario, sin administrador | 21,9 MB | `windows/build/out/Shed Stem Studio_0.0.1_x64-setup.exe` |

Se arman con `powershell -ExecutionPolicy Bypass -File windows\build\build.ps1`. Sin firma de código: SmartScreen avisa. **No se publicó ninguna release en GitHub.**
El `runtime/` trae Python 3.13.12 embebido, el motor, la interfaz compilada, `tzdata`, `tidalapi` y `uv` 0.13.4 (hash verificado contra el `.sha256` del release). No trae el entorno de separación, ni modelos, ni ffmpeg, ni Ollama: se instalan desde el asistente con un clic.

## Verificado (con datos)

- **Zip desde cero**, en una ruta con tildes y espacios, con el PATH reducido: el motor arranca con el Python embebido y sirve la interfaz con COOP/COEP.
- **Entorno de separación (CPU) con `uv`**: instala en 1,3 min, 0,90 GB, con su propio Python 3.13.16; la caché se limpia sola. Modelo BS-Roformer-SW (699 MB) descargado por el asistente.
- **Separación en CPU**: clip de 90 s con BS-Roformer-SW en 401 s (6,7 min), unas 4,5 veces el tiempo real; para un tema de 5:26 son unos 24 min (estimado a partir de ese clip). RAM ≈ 2,7 GB. El audio era sintético: sirve para el tiempo, no para juzgar la calidad.
- **Cancelar**: la instalación del entorno y la separación se cortan en segundos, el trabajo queda `cancelled` (no es un error), se borra lo parcial y no queda ningún proceso vivo.
- **Ventana (WebView2)** con el `.exe` real y también instalado: carga la interfaz, `crossOriginIsolated` verdadero, `SharedArrayBuffer` y `AudioWorklet` disponibles, el audio corre, el worklet y el `.wasm` cargan, sin excepciones.
- **Cierre limpio**: al cerrar la ventana no queda Python, Ollama ni nada; el puerto se libera (Job Object).
- **Instalar y desinstalar en silencio**: 4,4 s, `runtime/` queda junto al `.exe`, acceso directo y entrada de desinstalación; al desinstalar se borra todo y los datos del usuario quedan intactos (34.032 archivos antes y después).
- **GPU AMD**: detección con sus 8 GB reales, uso y VRAM en vivo. **Ollama con Vulkan** usa la RX 6700S: llama3.2:3b 88,8 tokens/s contra 20,9 en CPU; Mistral Nemo 12B 19,8 contra 6,5 (82 % del modelo en la placa).
- **Tests del motor**: 176 de 177 pasan en Windows (Python 3.14) y en Linux (Ubuntu 22.04 en WSL, Python 3.10); falla `test_analysis` por falta de numpy en ambos (necesita el entorno de separación). `svelte-check`: 0 errores.

## No verificado

- **TIDAL en Windows**: el inicio de sesión no se probó (la librería ya está en el runtime).
- **Botones de Cancelar y el paso de ffmpeg en pantalla**: el motor está probado, la interfaz compila y pasa `svelte-check`, pero no se vieron renderizados con un trabajo en curso.
- **Instalar ffmpeg y Ollama con winget desde el asistente**: el código está probado con procesos simulados; no se ejecutó la instalación real (en esta PC ya estaban).
- **Una PC limpia**: esta notebook tiene ffmpeg y Ollama de winget; el comportamiento sin ellos solo se probó con tests.
- **NVIDIA/CUDA e Intel en Windows**: no hay hardware para probar. DXGI y los contadores solo se vieron con AMD.
- **Desinstalador interactivo**: en modo silencioso no toca los datos; no se probó la casilla de borrar datos del modo con pantalla.
- **Linux real y Docker**: solo los tests unitarios en WSL; no se levantó Docker ni se probó la RTX 5080.

## Limitaciones conocidas

- Con AMD e Intel la separación va por CPU: ~24 min por tema. Aceleración con ONNX + DirectML: `docs/plan-directml.md` (sin empezar). DirectML y ROCm figuran "Próximamente" en el asistente.
- Los modelos que no entran enteros en la VRAM solo corren repartidos con Vulkan (medido); con CUDA siguen bloqueados como antes.
- Cancelar la descarga de un modelo de Ollama no existe todavía (sí la de separación).
- ffmpeg es obligatorio para separar y hay que instalarlo antes (el asistente lo ofrece con winget).

## Para retomar

1. **Release**: decidir si se publica en GitHub Releases (el zip y el instalador están listos; sin firma). Antes, probar una PC limpia (una VM o una cuenta nueva).
2. **Firma de código** (decisión abierta) y **actualizaciones**.
3. **Verificar CUDA en Windows** con la RTX 5080 (hace falta Windows en esa PC) y TIDAL.
4. **DirectML**: etapas 0 a 4 de `docs/plan-directml.md`.
5. Licencias antes de distribuir: Rubber Band (GPL v2 o posterior), pesos de modelos, build de ffmpeg.

## Notas de trabajo

- `docker/compose.yml` tiene un cambio local sin commitear (saca el acceso a la GPU NVIDIA de los contenedores): rompería la RTX 5080 en Linux. No se incluyó en ningún commit.
- Modo desarrollo en caliente: `python windows/dev.py` y abrir http://127.0.0.1:5173/.
- No editar archivos de `engine/` mientras corre un trabajo largo con `dev.py`: reinicia el motor y lo corta.
- Los datos de la app: `%LOCALAPPDATA%\ShedStemStudio`; configuración: `%APPDATA%\ShedStemStudio`; registro del motor: `%LOCALAPPDATA%\ShedStemStudio\logs\engine.log`.
