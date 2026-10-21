# Estado de la versión de Windows

Actualizado: 2026-10-21, notebook con Windows 11 Pro (build 26200), Ryzen 9 6900HS, 15,2 GB de RAM, Radeon RX 6700S (8 GB) y gráficos integrados. Detalle de cada prueba: `docs/windows-agentes.md` (registro). Plan completo: `docs/windows-instalable.md`.

## Qué hay

| Entregable | Tamaño | Dónde |
|---|---|---|
| Zip portable (`ShedStemStudio.exe` + `runtime/`) | 28,8 MB | `windows/build/out/ShedStemStudio-portable-0.0.1.zip` (no se versiona) |
| Instalador NSIS por usuario, sin administrador | 21,9 MB | `windows/build/out/Shed Stem Studio_0.0.1_x64-setup.exe` |

Se arman con `powershell -ExecutionPolicy Bypass -File windows\build\build.ps1`. Sin firma de código: SmartScreen avisa.

**Publicado** como pre-lanzamiento (los archivos se suben como `ShedStemStudio_<versión>_x64-setup.exe`, porque GitHub cambia los espacios por puntos):

| Versión | Fecha | Commit | Enlace | SHA-256 (instalador / zip) |
|---|---|---|---|---|
| 0.0.3 | 2026-10-21 | `9ed8abf` | https://github.com/tatomarinelli/shed-stem-studio/releases/tag/v0.0.3 | `71e844a7…f41d` / `8add727d…d155` |
| 0.0.2 | 2026-10-21 | `9ed1ab3` | https://github.com/tatomarinelli/shed-stem-studio/releases/tag/v0.0.2 | `6cc6d911…55bf` / `e2c260fe…46db` |
| 0.0.1 | 2026-10-21 | `9029abd` | https://github.com/tatomarinelli/shed-stem-studio/releases/tag/v0.0.1 | `5621ac0a…2485` / `91208a6d…3b5a` |

Los hashes coinciden con los que calcula el servidor. **Usar la 0.0.3**: la 0.0.1 no reproduce audio de TIDAL y la 0.0.2 no puede separar temas de TIDAL en una PC recién instalada.

### Lo que apareció al probar la 0.0.2 en una PC limpia (corregido en la 0.0.3)

- **Separar un tema de TIDAL: "Error I/O"** (502). `fetch_source` le pasaba la URL https de TIDAL a `ffmpeg`, que está construido con GnuTLS y en Windows solo confía en el almacén del sistema (el mismo defecto que Python, ya corregido en la 0.0.2 para el audio). Reproducido con un servidor https de certificado no confiable: `[tls] Peer certificate failed verification` y `Error opening input: I/O error`; con `-ca_file` funciona. Ahora Python baja el audio con `certifi` y `ffmpeg` solo convierte un archivo local (reintentos, progreso, cancelación); si falla, queda el camino viejo con `-ca_file` para las URL https directas.
- El log de esa PC (`engine.log`, 120 bytes) no traía el error porque los fallos del trabajo de separación no se registraban: ahora sí (`Separación <id> falló: …`) y el error de `ffmpeg` incluye las dos últimas líneas.
- **Confirmado por el usuario en una PC limpia con la 0.0.3: "funciona"** (separar un tema de TIDAL). No se sabe si ese tema llegó por el formato directo (BTS) o por DASH; el camino DASH (segmentos concatenados en un MP4 fragmentado) sigue sin probarse por separado contra TIDAL, y si no convierte cae al camino viejo.

### Lo que apareció al probar la 0.0.1 en una PC limpia (corregido en la 0.0.2)

- **Audio sin reproducción, 502 `URLError`**: Python en Windows solo confía en el almacén de certificados del sistema, y una PC recién instalada todavía no tiene las raíces de la CDN de TIDAL. El inicio de sesión andaba porque `requests` trae `certifi`. Simulado con el almacén vacío (el error es idéntico al reportado): falla sin el arreglo y valida con `SSL_CERT_FILE` apuntando a `certifi`. **Confirmado por el usuario en una PC limpia con la 0.0.2: ya reproduce.**
- **El enlace de TIDAL no se abría**: dentro de WebView2 los `target="_blank"` no abren nada. La cáscara ahora manda los enlaces externos al navegador del sistema (verificado en su registro `shell.log`) y la interfaz muestra el enlace debajo del botón con un botón para copiarlo.
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

- **TIDAL en Windows**: el inicio de sesión funciona (probado por el usuario en la 0.0.1); la reproducción en una PC limpia con la 0.0.2 está por confirmar. Nunca se probó desde acá con una cuenta real.
- **Botones de Cancelar y el paso de ffmpeg en pantalla**: el motor está probado, la interfaz compila y pasa `svelte-check`, pero no se vieron renderizados con un trabajo en curso.
- **Instalar ffmpeg y Ollama con winget desde el asistente**: el código está probado con procesos simulados; no se ejecutó la instalación real (en esta PC ya estaban).
- **Una PC limpia, parcialmente**: el usuario confirmó en una PC limpia con la 0.0.3 que reproduce y separa un tema de TIDAL. Cómo se instalaron ffmpeg y Ollama ahí (el asistente con winget, a mano, o ya estaban) y el resto del recorrido no están registrados; en esta notebook ya estaban instalados.
- **NVIDIA/CUDA e Intel en Windows**: no hay hardware para probar. DXGI y los contadores solo se vieron con AMD.
- **Desinstalador interactivo**: en modo silencioso no toca los datos; no se probó la casilla de borrar datos del modo con pantalla.
- **Linux real y Docker**: solo los tests unitarios en WSL; no se levantó Docker ni se probó la RTX 5080.

## Limitaciones conocidas

- Con AMD e Intel la separación va por CPU: ~24 min por tema. Aceleración con ONNX + DirectML: `docs/plan-directml.md` (sin empezar). DirectML y ROCm figuran "Próximamente" en el asistente.
- Los modelos que no entran enteros en la VRAM solo corren repartidos con Vulkan (medido); con CUDA siguen bloqueados como antes.
- Cancelar la descarga de un modelo de Ollama no existe todavía (sí la de separación).
- ffmpeg es obligatorio para separar y hay que instalarlo antes (el asistente lo ofrece con winget).

## Para retomar

1. **Release**: ya está publicado como pre-lanzamiento. Falta probarlo en una PC limpia (una VM o una cuenta nueva) y decidir la firma antes de una versión estable. Los archivos del release no se versionan: se reconstruyen con `build.ps1`.
2. **Firma de código** (decisión abierta) y **actualizaciones**.
3. **Verificar CUDA en Windows** con la RTX 5080 (hace falta Windows en esa PC) y TIDAL.
4. **DirectML**: etapas 0 a 4 de `docs/plan-directml.md`.
5. Licencias antes de distribuir: Rubber Band (GPL v2 o posterior), pesos de modelos, build de ffmpeg.

## Notas de trabajo

- `docker/compose.yml` tiene un cambio local sin commitear (saca el acceso a la GPU NVIDIA de los contenedores): rompería la RTX 5080 en Linux. No se incluyó en ningún commit.
- Modo desarrollo en caliente: `python windows/dev.py` y abrir http://127.0.0.1:5173/.
- No editar archivos de `engine/` mientras corre un trabajo largo con `dev.py`: reinicia el motor y lo corta.
- Los datos de la app: `%LOCALAPPDATA%\ShedStemStudio`; configuración: `%APPDATA%\ShedStemStudio`; registro del motor: `%LOCALAPPDATA%\ShedStemStudio\logs\engine.log`.
