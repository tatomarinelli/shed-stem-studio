# Motores de IA según el hardware (separación y recomendaciones)

Estado: **análisis** (2026-10-21) y primera implementación. Código: `engine/backends.py`, `GET /engine/backends`, `components/BackendPicker.svelte` (paso "Separar en instrumentos" del asistente y Ajustes).

Hay **dos cargas de IA distintas** y cada una tiene sus propias opciones:

| Carga | Qué corre | Cómo se ejecuta hoy |
|---|---|---|
| Separación en instrumentos | BS-Roformer-SW (667 MB) o Demucs, modelos de PyTorch | `audio-separator` dentro del entorno de separación (≈ 8 GB) |
| Recomendaciones | Un modelo de lenguaje (Mistral Nemo 12B, Gemma 3…) | Ollama, por su API (`/api/chat`, `/api/tags`, `/api/pull`, `/api/ps`) |

## 1. Separación

| Motor | Hardware | Estado en el proyecto | Evidencia / límites |
|---|---|---|---|
| **PyTorch + CUDA** | NVIDIA | **Instalable.** Verificado de punta a punta en Linux (RTX 5080); en Windows sin verificar (no hay NVIDIA para probar) | Ruedas `torch 2.11 cu128` existen para Windows |
| **PyTorch CPU** | Cualquiera | **Instalable**, sin medir la velocidad | Es el respaldo de AMD, Intel y sin placa |
| **ONNX Runtime + DirectML** | Cualquier placa DirectX 12 (AMD, Intel, NVIDIA) en Windows | **Próximamente (no instalable)** | No requiere ROCm. Hay ONNX públicos de Demucs; **no hay de BS-Roformer-SW** y no se halló nada sobre exportarlo. Habría que exportarlo, comprobar que DirectML soporta sus operaciones y escribir ese camino de separación. Calidad de Demucs < RoFormer |
| **PyTorch + ROCm (Windows)** | AMD recientes | **No instalable** | Según un proyecto de terceros, las ruedas oficiales para Windows soportan RDNA3/RDNA4 (RX 7000/9000); RDNA2 (RX 6000, como la RX 6700S) no. Existen builds de la comunidad con `HSA_OVERRIDE_GFX_VERSION`, experimentales: no para un producto |
| **Ollama / llama.cpp** | — | **No sirve para separar** | Ejecutan modelos de lenguaje en formato GGUF. BS-Roformer y Demucs no son modelos de lenguaje: no hay forma de cargarlos ahí |

Regla del asistente: solo se ofrece instalar lo que existe de verdad y está probado; lo demás se muestra "Próximamente" con el motivo. Nunca se descarga nada sin un clic y sin carpeta elegida.

Recomendación hoy: NVIDIA con CUDA → `cuda`; todo lo demás → `cpu`, y el texto lo dice con el nombre de la placa.

## 2. Recomendaciones (modelo de lenguaje)

| Motor | Hardware | Estado | Notas |
|---|---|---|---|
| **Ollama + CUDA** | NVIDIA | Funciona (Linux, RTX 5080) | Camino actual |
| **Ollama + ROCm** | AMD en la lista de ROCm | Sin verificar | La documentación de Ollama advierte que algunas RDNA2 pueden no exponer ROCm v7 en Windows |
| **Ollama + Vulkan** | AMD fuera de la lista, Intel | **Verificado en la RX 6700S** (Windows 11, Ollama 0.40.7) | Vulkan viene activado por defecto. Ollama detecta la placa (`library=Vulkan`), descarta la integrada y deja ROCm de lado. llama3.2:3b (2,39 GB) entero en la placa: **88,8 tokens/s contra 20,9 en CPU** (4,2×); prompt 4.042 contra 977 tokens/s. El monitor del motor ve la VRAM ocupada y el modelo cargado |
| **llama.cpp (llama-server)** | NVIDIA (CUDA), AMD/Intel (Vulkan), CPU | **Soportado para recomendaciones, sin verificar contra un llama-server real** (2026-10-22). Se detecta, se prende con un clic sobre un `.gguf` ya descargado y se usa con `llmProvider: "llamacpp"` | Ollama está construido sobre llama.cpp. `llama-server` habla la API compatible con OpenAI (`/v1/chat/completions`, `/v1/models`), no la de Ollama: `models.chat()` y `models.ollama_tags()` son el único punto que traduce. Sin descargas (consistente con «nada se descarga solo»), sin `/api/ps` ni `/api/embed` (los embeddings de géneros caen al cruce por palabras). Mantiene la VRAM tomada hasta que se lo apaga; Ollama la libera solo (`keep_alive`) |
| **CPU** | Cualquiera | Siempre disponible | Mucho más lento con modelos de 12B |

Medición (2026-10-21, `/api/generate`, 200 tokens, temperatura 0, modelo ya cargado): Vulkan 88,8 tok/s, CPU (`OLLAMA_VULKAN=0`) 20,9 tok/s. Falta medir un modelo de 12B, que con 8 GB de VRAM entra apenas o parcialmente (Ollama reparte capas entre placa y CPU), y comprobar la velocidad de ese reparto.

Consecuencia en el código: `hardware._gpus` distingue `accel` (separación) de `llmAccel` (modelos de recomendación: `cuda`, `vulkan` en AMD/Intel dedicadas, nada en integradas). Con una Radeon dedicada las recomendaciones usan la placa aunque la separación vaya por CPU, y como no compiten por la VRAM `withSeparation` queda en verdadero.

## 3. Qué hace el asistente hoy

1. `GET /engine/backends` junto con la detección de placas (`hardware._gpus`, DXGI en Windows).
2. Muestra el motor recomendado con el motivo y las alternativas (instalables o "Próximamente", con "Sin verificar en este sistema" donde corresponde).
3. Con el clic de **Instalar**, `POST /engine/env/install {"backend": id}` instala el archivo de requisitos de ese motor en la carpeta elegida; deja `backend.txt` junto al entorno para saber cuál es.

## 3b. Servidores de modelos que el usuario ya tiene (2026-10-22)

`engine/llmdetect.py`, `GET /engine/llm/detect`, `components/LlmDetect.svelte` (Ajustes y asistente). Solo mira, nunca descarga ni instala:

- **Puertos locales** (127.0.0.1): 11434 (Ollama), 11500 (Ollama propio), 8080/8081 (llama-server), 1234 (LM Studio) y el de `llmUrl`. Se reconoce por la forma de la respuesta (`/api/version`, `/props`, `/v1/models`), no por el puerto.
- **Binarios**: `ollama` y `llama-server` en el PATH o en carpetas conocidas de cada sistema (`osenv.find_llama_server`, `STEMSHED_LLAMA_SERVER`).
- **Modelos**: `.gguf` en `LLAMA_CACHE`, `~/.cache/llama.cpp` (Linux) o `%LOCALAPPDATA%\llama.cpp` (Windows), LM Studio y Hugging Face (`osenv.gguf_roots`); manifiestos de Ollama (`osenv.ollama_model_roots`). Acotado a 200 archivos, sin los `mmproj` ni los menores de 50 MB.
- **Orden en la UI**: «Ya prendidos» (Usar este) → «Instalado, sin prender» (llama-server + modelo + Prender…) → instalar Ollama (`LlmServer`). Cada acción pide confirmación con el resumen de lo que va a pasar.
- **Levantar llama-server**: `POST /engine/llm/llamacpp/start {model}`; el modelo tiene que estar en lo detectado, escucha en 127.0.0.1 (puerto libre de 8081 a 8089), `-c 8192 --jinja -ngl 99`. Se espera a `/health`; cancelar o apagar lo mata (`osenv.kill_tree`) y el apagado del motor también. Al cargar queda en uso (`llmUrl` + `llmProvider`); «Apagar» vuelve a Ollama.
- **Decisión**: no se adopta la carpeta de modelos de un Ollama ajeno; se usa su servidor (ve sus modelos por `/api/tags`). Dos Ollama compartiendo carpeta es frágil y la carpeta del servicio suele no ser escribible.
- **Separación**: sin cambios. llama.cpp/Ollama no sirven para BS-Roformer ni Demucs. En el selector las opciones salen agrupadas: «Para instalar ahora» (el recomendado primero), «No son para tu equipo», «Próximamente».

## 4. Pendiente

- Medir la separación en CPU en esta notebook (línea base).
- Medir un modelo de 12B (Mistral Nemo) con reparto parcial entre placa y CPU.
- Evaluar exportar BS-Roformer-SW a ONNX y correrlo con DirectML; mientras tanto, Demucs ONNX + DirectML como camino AMD de menor calidad.
- Verificar CUDA en Windows con una máquina NVIDIA.
- Probar un llama-server real (Linux y Windows): `response_format` json_schema en la versión instalada, tiempo de carga, `/props`. Hasta entonces la prueba fue con un servidor falso y tests simulados.
- Windows: rutas de `osenv.llama_server_dirs`/`gguf_roots` sin verificar en un equipo real.

## Fuentes
- ROCm en Windows, requisitos: https://rocm.docs.amd.com/projects/install-on-windows/en/latest/reference/system-requirements.html
- Ruedas de PyTorch oficiales solo RDNA3/4 (tercero): https://github.com/ssubedir/RCOm-windows-gfx1030
- Ollama en Windows: https://docs.ollama.com/windows
- DirectML en ONNX Runtime: https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html
