# Aplicación instalable para Windows

Estado: **plan** (2026-10-21), sin implementar. Desarrolla la Fase 6 de `PLAN.md` ("App de escritorio") para Windows. Hoy el proyecto está probado solo en Linux; en Windows no corre ni con Docker verificado (ver README, "Sistemas compatibles").

## 1. Objetivo

Un instalador (`.exe`) que un usuario sin conocimientos técnicos descarga, ejecuta y usa: se abre una ventana propia de Shed Stem Studio, el asistente de primeros pasos lo guía, y no hay que instalar Python, Docker, Node ni abrir una terminal.

Principios que se mantienen:
- **Local primero**: nada del audio ni de los gustos sale del equipo.
- **Nada se descarga solo**: el instalador es chico; el entorno de separación (≈ 8 GB) y los modelos se eligen y se bajan desde el asistente, a la carpeta que indique el usuario.
- **Sin administrador**: instalación por usuario.
- **Sin código ni credenciales de TIDAL en el instalador.**

## 2. Arquitectura propuesta

```
┌─ Instalador (NSIS o MSI) ─────────────────────────────────────────┐
│  Cáscara de escritorio  (ventana, bandeja, un solo proceso visible) │
│      │ lanza y supervisa                                           │
│      ▼                                                             │
│  Motor local (Python embebido + engine/)  ── sirve la interfaz     │
│      │ crea bajo demanda                       y la API en loopback │
│      ▼                                                             │
│  Entorno de separación (torch + CUDA, uv)   Servidor de modelos     │
│  en %LOCALAPPDATA%\ShedStemStudio\env       (Ollama para Windows)   │
└────────────────────────────────────────────────────────────────────┘
```

| Decisión | Propuesta | Alternativa | Por qué |
|---|---|---|---|
| **Cáscara** | **Tauri 2** (WebView2 del sistema, ≈ 10 MB) | Electron (Chromium propio, ≈ 150 MB) | Instalador chico. Riesgo: el reproductor necesita AudioWorklet, SharedArrayBuffer y aislamiento de origen (COOP/COEP) dentro de WebView2: **a verificar en la etapa 0**. Si falla, Electron. |
| **Dónde vive la interfaz** | La sirve el motor desde `127.0.0.1` con COOP/COEP (como hoy nginx en Docker); la ventana carga esa dirección | Empaquetarla en la cáscara | Mismo código y mismos encabezados que la web y Docker; un solo camino a probar. |
| **Motor** | Python embebido (distribución "standalone") con los `.py` de `engine/` a la vista, lanzado como proceso hijo | Congelarlo en un `.exe` (PyInstaller) | El motor usa solo la librería estándar: no hace falta congelarlo, y se evitan los falsos positivos del antivirus con ejecutables empaquetados. |
| **Entorno de separación** | Se crea la primera vez con **uv** (un solo ejecutable pequeño) desde el `requirements-env.txt` fijado; botón "Instalar" del asistente | Incluir torch en el instalador | Torch + CUDA son varios GB: no entran razonablemente en un instalador. Ya funciona así en Docker (`envsetup.py`). |
| **Servidor de modelos** | Ollama oficial para Windows, que el asistente ofrece instalar | Incluir `ollama.exe` + sus bibliotecas CUDA | Evita redistribuir bibliotecas de NVIDIA; Ollama gestiona su GPU. **Verificar**: instalación silenciosa y carpeta de modelos elegible. |
| **ffmpeg** | Descargarlo en el asistente (o incluir una build LGPL) | Incluirlo siempre | Pesa decenas de MB y tiene su propia licencia. |
| **Seguridad del motor** | La cáscara genera un token aleatorio por sesión y se lo pasa al motor y a la interfaz | Emparejamiento por código (el de la web) | En una app de escritorio no hace falta que el usuario lo escriba. |

## 3. Qué trae el instalador y qué se baja

| Trae (cifras a medir) | Se baja desde el asistente, con un clic |
|---|---|
| Cáscara Tauri | Entorno de separación (≈ 8 GB en disco) |
| Python embebido + `engine/` | Modelo de separación (≈ 700 MB) |
| La interfaz ya construida | Ollama + modelo de recomendación (varios GB) |
| `uv` | ffmpeg (si no se incluye) |
| Avisos de licencias | |

Tamaño objetivo del instalador: **del orden de 100 MB** (sin medir). Hay que decidir si además se ofrece un instalador "completo" sin conexión (decisión abierta).

## 4. Trabajo en el motor para que corra en Windows

El motor tiene supuestos de Linux. Los encontrados en el código:

| Qué | Dónde | Cambio |
|---|---|---|
| Rutas del entorno: `venv/bin/python`, `venv/bin/audio-separator`, `venv/bin/pip` | `stems.py`, `analysis.py`, `envsetup.py`, `settings.py` | En Windows son `venv\Scripts\python.exe`, `audio-separator.exe`, `pip.exe`. Una función única `env_bin(nombre)`. |
| Carpeta de configuración (`~/.config/stemshed`, `XDG_CONFIG_HOME`) | `settings.py`, `models.py`, `tidal_source.py` | `%APPDATA%\ShedStemStudio` (o el equivalente por plataforma); mantener la variable de entorno para pruebas. |
| Detección de hardware: `/proc/meminfo`, `/proc/cpuinfo` | `hardware.py` | `GlobalMemoryStatusEx` y el registro (con `ctypes`, sin dependencias); `nvidia-smi` ya sirve si está el controlador. |
| Lista de carpetas prohibidas con rutas Unix y selector de carpetas que parte de `/` | `settings.py` (`FORBIDDEN`, `list_dirs`) y `FolderPicker` | Rutas de Windows (`C:\Windows`, `C:\Program Files`), listar unidades, separador `\`. O usar el diálogo nativo de la cáscara. |
| Permisos `chmod 0o600/0o700` en archivos con secretos | `profile.py`, `memory.py`, `presets.py`, `library.py`, `tidal_source.py`, `destinations.py`, `recs.py`, `settings.py` | En Windows no hacen nada. La sesión de TIDAL debería guardarse con DPAPI / Administrador de credenciales, no solo en un archivo. |
| Prioridad baja del análisis | `analysis.py` | Clase de prioridad de Windows (`BELOW_NORMAL_PRIORITY_CLASS`) en `Popen`. |
| Procesos hijos | `stems.py`, `analysis.py`, `models.py`, `envsetup.py` | `CREATE_NO_WINDOW` para que no aparezcan consolas; terminar el árbol de procesos al apagar. |
| Ids de archivos locales y comparación de rutas | `library.py` | Windows no distingue mayúsculas y usa `\`: normalizar antes de calcular el id (si no, el mismo archivo tendría dos ids). |
| Caché de Numba y temporales | `analyze.py`, `stems.py` | Carpeta temporal dentro de los datos, no `/tmp`. |
| Pruebas con rutas Unix | `engine/tests` | Pasarlas a `pathlib` y a carpetas temporales. |
| Apagado desde Ajustes | `services.py` | Debe cerrar también el entorno hijo y Ollama si lo lanzó el motor. |

**Avance (etapa 1, parcial, 2026-10-21):** `engine/osenv.py` concentra rutas del venv (`Scripts\\*.exe`), carpeta de configuración (`%APPDATA%\\ShedStemStudio`), carpetas prohibidas de Windows, selector de unidades, `chmod` omitido, `CREATE_NO_WINDOW` y prioridad baja, `TEMP`/`TMP`, RAM y CPU por `ctypes`/registro, e ids de archivo sin distinguir mayúsculas. Probado **solo con simulaciones desde Linux** (`tests/test_osenv.py`); falta correr los tests en Windows de verdad. Pendiente de la tabla: DPAPI para la sesión de TIDAL, apagado del árbol de procesos, `services.py` y pruebas con rutas Unix.

## 5. Trabajo en la interfaz y la cáscara

- **Arranque**: pantalla de carga mientras el motor inicia; reintentos; mensaje si el puerto está ocupado (elegir uno libre y pasárselo a la ventana).
- **Una sola instancia**; ícono en la bandeja con "Abrir", "Apagar motor" y "Salir". Al cerrar la ventana, preguntar si se apaga el motor.
- **Diálogos nativos** de carpeta y archivo; arrastrar y soltar música a la ventana.
- **Asistente de primeros pasos**: pasos nuevos para Windows: comprobar el controlador de NVIDIA, instalar Ollama y ffmpeg.
- **Textos**: los que hoy mencionan Docker o `npm run engine` pasan a depender de la plataforma.
- **Identidad**: ícono de la app, nombre, versión, pantalla "Acerca de" con licencias.
- **Más adelante** (Fase 6 del plan): salida de audio exclusiva (WASAPI) con una capa `platform.*`.

## 6. GPU y compatibilidad

| Equipo | Qué pasa | Estado |
|---|---|---|
| **NVIDIA** (RTX 20 en adelante, probado en RTX 5080 en Linux) | Torch con CUDA 12.8; necesita un controlador reciente (**versión mínima a verificar**; el instalador debe comprobarla y avisar con un enlace) | Objetivo de la v1 |
| **Sin GPU compatible** | Separación en CPU, **mucho más lenta** (no medida): se avisa antes de instalar el entorno | v1, con advertencia |
| **AMD / Intel** | Torch no tiene aceleración para estas placas en Windows: la separación va a **CPU**. Para usar la placa habría que exportar el modelo a ONNX y usar DirectML (`onnxruntime-directml` existe para Python 3.11 a 3.14). La exportación de BS-Roformer-SW **no se hizo** (Fase 0.B) | CPU en la v1 (se mide en la notebook de prueba); DirectML, posterior |

## 7. Seguridad, datos y desinstalación

- Instalación **por usuario** en `%LOCALAPPDATA%\Programs\ShedStemStudio` (sin pedir administrador).
- Datos de la app (perfiles, memoria, sesión de TIDAL) en `%APPDATA%\ShedStemStudio`; entorno, stems y modelos en la carpeta que el usuario elija (con una sugerencia según el espacio libre).
- **Desinstalador**: borra el programa y **pregunta** si se borran también los datos y los modelos (decenas de GB), nunca lo hace solo.
- El motor escucha solo en `127.0.0.1`, con token por sesión y lista de orígenes permitidos; el Firewall de Windows no debería preguntar al ser solo loopback (**verificar**).
- **Firma de código**: sin firma, SmartScreen muestra una advertencia a los usuarios nuevos. Opciones: certificado de firma de código (OV/EV) o el servicio de firma de Microsoft. Tiene costo y trámite: decisión abierta.
- Sin telemetría. Registros solo locales.

## 8. Actualizaciones

- **La app** (cáscara + interfaz + motor): actualizador de Tauri con firma propia y publicación en GitHub Releases. Comprobar al iniciar, descargar con aviso, instalar al cerrar.
- **El entorno de separación**: versión fijada en `requirements-env.txt`; si una versión nueva de la app necesita otra, el asistente ofrece "Actualizar entorno" (otra descarga explícita).
- **Los modelos** no se actualizan solos.

## 9. Licencias y términos

- El proyecto es **GPL-3.0-or-later**: al distribuir el instalador hay que ofrecer el código fuente (ya está en el repo) y los avisos de terceros.
- **Rubber Band** (`rubberband-wasm`, GPL-2.0): la duda "solo v2 / o posterior" **sigue abierta** y hay que resolverla antes de publicar un instalador.
- **ffmpeg**: elegir una build compatible (LGPL, o GPL si se asume).
- **WebView2**: incluir el instalador "bootstrapper" de Microsoft en Windows 10 (en Windows 11 ya viene).
- **Ollama, uv, Python, torch, onnxruntime**: permisivas, solo requieren avisos.
- **Términos de TIDAL** para una versión pública: **sin verificar**; podrían obligar a dejar fuera la descarga de audio desde TIDAL en la versión pública.
- Modelos (BS-Roformer, Mistral Nemo, Gemma): licencias propias; no se distribuyen con el instalador.

## 10. Pruebas y CI

- **CI en GitHub Actions con runner de Windows**: construir el instalador, correr las pruebas del motor, instalar en silencio, arrancar la app y consultar `/engine/status`. No tiene GPU.
- **Pruebas manuales en una máquina Windows con NVIDIA**: instalar entorno, separar un tema, analizar, recomendar con Ollama, desinstalar. **Hoy no tengo acceso a una**: es el principal requisito para avanzar.
- Casos a cubrir: Windows 10 y 11, usuario con espacios y tildes en el nombre (`C:\Users\José Pérez`), disco secundario para datos, sin GPU, controlador viejo, sin internet en un paso, antivirus activo, instalación sobre una versión anterior.

## 10 bis. Lo ya verificado (2026-10-21, desde Linux, sin máquina Windows)

- **Ruedas (wheels) de las 83 dependencias fijadas** (`engine/requirements-env.txt`) para Windows x64 con Python 3.12, 3.13 y 3.14: todas existen **salvo `diffq`**, que solo se publica como código fuente y exigiría un compilador de C en el equipo del usuario. Cuatro son solo de Linux (`triton`, `nvidia-cufile-cu12`, `nvidia-nccl-cu12`, `nvidia-nvshmem-cu12`) y no aplican en Windows.
- **`diffq` no hace falta para separar:** probé BS-Roformer-SW sin `diffq` instalado (importación bloqueada) y separó un clip en 6 stems. En Windows se omite.
- **Torch en Windows:** existen `torch` y `torchaudio` 2.11.0 para `cu128` (NVIDIA) y para CPU (AMD, Intel o sin GPU), en Python 3.12, 3.13 y 3.14. En Windows las bibliotecas de CUDA vienen dentro de la rueda de torch, así que la lista de requisitos para Windows es distinta a la de Linux (sin los `nvidia-*`) y hay **dos variantes**: NVIDIA y CPU.
- **Sin verificar:** que la instalación completa funcione en Windows, que `numba`/`librosa`/`soxr` se comporten igual, y la velocidad en CPU.

## 10 ter. Máquina de prueba: notebook con Windows y placa AMD

Sirve para casi todo, menos para verificar la ruta NVIDIA.

| Se puede probar | No se puede probar |
|---|---|
| Ventana (WebView2): audio, AudioWorklet, aislamiento de origen | Separación con CUDA y su velocidad |
| Motor portable y sus pruebas | Controlador mínimo de NVIDIA y su mensaje de error |
| Instalador, desinstalador, accesos directos, SmartScreen | Rendimiento de Ollama con una GPU NVIDIA |
| Asistente de primeros pasos completo | |
| **Separación y análisis en CPU** (la ruta de AMD/Intel/sin GPU) | |
| Ollama en CPU o con la placa AMD (según el modelo: las integradas casi nunca se usan) | |
| Rutas con tildes y espacios, antivirus de Windows | |

Para la ruta NVIDIA hace falta otro equipo o un colaborador; mientras tanto se confía en la ruta de Linux, que es la misma de torch.

Primer paso: correr `tools/windows/diagnostico.ps1` en la notebook (no instala nada ni usa internet; genera un archivo con el hardware, el controlador de video, el espacio libre y si están WebView2, Python y ffmpeg) y pegar el resultado.

## 11. Etapas

| # | Etapa | Salida (criterio de aceptación) |
|---|---|---|
| 0 | **Prototipos de riesgo** (en una máquina Windows) | (a) La interfaz en WebView2 con audio, AudioWorklet y aislamiento de origen funcionando; (b) todas las dependencias del entorno instalan en Windows con la versión de Python elegida; (c) separar un tema en la GPU; (d) Ollama instalable en silencio con carpeta de modelos elegida. Decide Tauri vs Electron y la versión de Python. |
| 1 | **Motor portable** | Los 80+ tests pasan en Windows; el motor arranca, escanea una carpeta con tildes y espacios y responde `/engine/status`. |
| 2 | **Cáscara y motor empaquetado** | Una ventana que lanza el motor, muestra la interfaz y apaga todo al salir, sin dejar procesos huérfanos. |
| 3 | **Instalador por usuario** | `.exe` que instala, crea accesos directos y desinstala (con la pregunta de los datos). |
| 4 | **Asistente en Windows** | Del primer inicio a un "Disco de hoy" sin terminal: entorno, modelo de separación, Ollama, modelo de recomendación, perfil. |
| 5 | **Firma y actualizaciones** | Instalador firmado; actualización de una versión a otra probada. |
| 6 | **Versión beta pública** | Publicación en GitHub Releases con notas, licencias y guía de problemas comunes. |
| 7 | **Después** | Salida de audio nativa (WASAPI), AMD/Intel vía ONNX, winget/Microsoft Store, extensión de navegador. |

## 12. Riesgos

- **No hay máquina Windows con NVIDIA disponible** (solo una notebook con AMD): la ruta CUDA queda sin verificar en Windows.
- **Velocidad en CPU**: no medida; separar un tema podría tardar muchos minutos. Hay que medirlo en la notebook antes de prometer algo a usuarios sin NVIDIA.
- **WebView2 y el audio**: si el AudioWorklet o el aislamiento de origen se comportan distinto, cambia la decisión de cáscara.
- **Ruedas (wheels) de Python 3.14 en Windows**: alguna dependencia (`soxr`, `samplerate`, `numba`, `onnxruntime-gpu`) podría no tenerla; habría que fijar otra versión de Python y volver a medir el análisis.
- **Antivirus y SmartScreen** sobre un instalador nuevo y sin reputación.
- **Peso**: 8 GB de entorno + modelos: hay que decirlo claro en el instalador y comprobar el espacio antes.
- **Términos de TIDAL** y la duda de licencia de Rubber Band.
- **Mantener dos plataformas** con un equipo chico: conviene que el CI de Windows corra en cada cambio.

## 13. Decisiones abiertas

1. ¿Tauri (chico, a verificar) o Electron (pesado, más previsible)? Propuesta: probar Tauri en la etapa 0 y volver a Electron solo si falla el audio.
2. ¿Instalador chico que baja todo desde el asistente (propuesta) o también uno completo sin conexión?
3. ¿Solo NVIDIA en la v1, con CPU como respaldo? (propuesta: sí)
4. ¿Firma de código desde la beta, o primero beta sin firma y avisando de SmartScreen?
5. ~~¿Hay una máquina Windows para probar?~~ Hay una notebook con AMD (sin CUDA). Falta una máquina o colaborador con NVIDIA para verificar esa ruta.
6. ¿Ollama oficial instalado desde el asistente (propuesta) o incluido en el instalador?
7. ¿Canal de distribución: solo GitHub Releases al principio, y winget después?
