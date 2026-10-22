# Shed Stem Studio: plan de trabajo

Arquitectura de referencia: `docs/architecture.md` (v2). Este archivo es el plan operativo; se actualiza a medida que se avanza.

## Visión

1. **Webapp** local-first: fuentes (Spotify, TIDAL, YouTube, archivos), recomendación diaria con cuestionario, estudio con stems, botón "Enviar al estudio".
2. **App de escritorio** (wrapper del mismo código web) con lo que el navegador no puede: salida de audio HiFi (exclusiva / bit-perfect, 24 bit, 96-192 kHz), separación con GPU nativa sin límites, acceso a archivos sin permisos, integración con el sistema. Mismo código de interfaz; lo nativo entra por una capa de plataforma (`platform.*`) con implementación web y nativa.
3. Separación: nivel A en navegador, B motor local, C proveedor (pendiente).

## Decisiones tomadas

- Nombre: **Shed Stem Studio** (antes StemShed; renombrado el 2026-10-21). Los identificadores técnicos no cambian por compatibilidad: carpeta del proyecto, `~/.config/stemshed/`, `/mnt/plexdata/stemshed`, variables `STEMSHED_*` y claves de almacenamiento del navegador `stemshed.*`. Proyecto independiente: no copia código del cliente de TIDAL.
- UI en TypeScript + Vite (Svelte recomendado, a confirmar en fase 1).
- Interfaz de usuario en español rioplatense.
- Reacciones por ítem, nunca por género. La banda o proyecto propio del usuario (`ownArtists` del perfil) nunca se recomienda ni cuenta como gusto.

## Hechos medidos (2026-10-20)

- Electron 43 / Chrome 150 sin ventana: `navigator.gpu` **ausente** y `crossOriginIsolated` falso. Inconcluyente: repetir en Chromium/Firefox reales (`/usr/bin/chromium`, `/usr/bin/firefox`) con GPU (RTX 5080, Vulkan).
- npm: `onnxruntime-web` 1.30.0 (MIT). Estiradores: `rubberband-web` 0.2.1 y `rubberband-wasm` 3.3.0 (**GPL**), `soundtouchjs` 0.3.0 (LGPL, calidad menor al estirar mucho).
- Hay exportaciones ONNX públicas de **Demucs** (p. ej. `timcsy/demucs-web-onnx`, `MrCitron/demucs-v4-onnx`); **no** hay de BS-Roformer-SW: habría que exportarlo.
- Modelo de referencia: `BS-Roformer-SW.ckpt` 667 MB (6 stems), 70 trozos por tema de ~5:26. Demucs `htdemucs_6s` 52 MB.
- Datos de prueba reales: `/mnt/plexdata/tidal-stems/cache/<trackId>/` (stems FLAC por modelo, `peaks.json`), temas 209514765, 633713, 77611327. Solo lectura; no escribir ahí.
- Referencia de calidad: salida de PyTorch del mismo tema (en `/mnt/plexdata/tidal-stems/out/` hay resultados de RoFormer y Demucs).

## Fase 0: prototipo y mediciones (máx. ~1-2 días)

Objetivo: decidir con datos qué corre en el navegador. Carpeta `proto/`, sin código de producto.

**0.A Reproducción (Web Audio)**
- Cargar 4-6 stems FLAC reales, mezcla con volumen/mute/solo, loop A-B, velocidad 25-125 % con AudioWorklet + Rubber Band WASM (y SoundTouch como comparación).
- Medir: memoria (decodificación completa vs. por tramos), latencia de seek, exactitud del loop (error en ms al repetir 50 vueltas), carga de CPU, y calidad auditiva a 25/50/75 % con la voz y la guitarra (el usuario escucha y valora).
- Servir con cabeceras COOP/COEP para hilos WASM.

**0.B Separación en el navegador**
- Entorno: confirmar WebGPU en Chromium real (`chrome://gpu`, `navigator.gpu.requestAdapter()`); si falla, probar flags de Vulkan; si sigue sin, registrar y pasar a WASM-CPU como piso.
- Demucs: bajar un ONNX público de htdemucs, correr con ONNX Runtime Web (WebGPU y WASM) sobre un tema, comparar con la salida de PyTorch (SDR/correlación por stem) y medir tiempo y memoria.
- BS-Roformer-SW: intentar `torch.onnx.export` desde el checkpoint (STFT/iSTFT fuera del grafo si hace falta); tope de tiempo de 3-4 horas. Si exporta: correr en WebGPU y comparar. Si no: documentar el bloqueo exacto.
- Criterio de salida: tabla con tiempo, memoria y diferencia contra PyTorch por modelo y backend.

**Decisión al cierre de la fase 0** (se escribe en `docs/phase0-results.md`):
- ¿El nivel A puede ofrecer el modelo grande? Si sí, es el camino principal; si no, el nivel A usa Demucs y el B ofrece RoFormer.
- Estirador elegido y su implicación de licencia (GPL → el proyecto es GPL/abierto).
- Estrategia de memoria para el estudio.

## Fase 1: Estudio local

Motor Python (FastAPI) + UI web. Arrastrar archivos, separación nivel B con los modelos actuales, ondas, loops, velocidad, entrenador, loops guardados, almacenamiento. Reutiliza `tidalrecs/stems*.py` y la lógica de `studyPanel/` (copiar y adaptar, no enlazar). Pruebas del núcleo migradas.

## Fase 2: Separación en el navegador (nivel A)

Según los resultados de la fase 0. Descarga y caché del modelo en OPFS, progreso por trozos, cancelar, reanudar.

## Fase 3: Fuentes y "Enviar al estudio"

Archivos locales (File System Access), MusicBrainz, Spotify (OAuth PKCE). Antes de construir: verificar cuotas del modo desarrollo de Spotify y Google, y el alcance de la API oficial de TIDAL. Coincidencia tema ↔ archivo local por etiquetas, artista, título y duración.

## Fase 4: Cuestionario y recomendación

Cuestionario inicial → perfil editable. Proveedores de LLM: local (Ollama / LM Studio, probar con un modelo medio en 16 GB de VRAM), clave propia, motor local. Verificación contra MusicBrainz. Memoria por reacciones. Reutiliza `daily.py`, `memory.py`, `context.py`, `llm.py`.

## Fase 5: TIDAL y YouTube

Vías oficiales primero; `tidalapi` / `ytmusicapi` solo como complemento aparte, nunca en la versión pública.

## Fase 6: App de escritorio

Wrapper (Electron o Tauri, decidir con datos) sobre la misma UI. Capa `platform.*`: salida HiFi (exclusiva / bit-perfect, selección de dispositivo, muestra nativa), separación nativa con GPU, archivos sin permisos, atajos globales, bandeja. Extensión de navegador opcional con "Enviar a Shed Stem Studio".

Plan detallado para Windows (instalador, motor portable, GPU, firma, etapas y decisiones abiertas): `docs/windows-instalable.md`.

## Fase 7: Proveedor de separación (nivel C), empaquetado, licencia, documentación

## Reglas de trabajo

- Nada de código, binarios, credenciales ni caché del cliente de TIDAL en este repo.
- Audio de servicios: **solo por decisión del usuario (2026-10-21)** y para uso personal, el motor puede bajar un tema de TIDAL con la sesión del propio usuario, separarlo y **borrar el original**; se guardan solo los stems (caché nueva en `/mnt/plexdata/stemshed`, la vieja es de solo lectura). Fuera de la versión pública hasta verificar los términos de TIDAL.
- Escucha previa (decisión del usuario, 2026-10-21): el motor puede pasar al navegador el audio de un tema de TIDAL o de un archivo local **sin guardarlo** (`/engine/play/<id>`, con rangos) para escucharlo antes de separarlo. Mismas condiciones: uso personal y fuera de la versión pública.
- Probar con la app real o un navegador real antes de afirmar que algo funciona; declarar lo que no se pudo verificar.
- No lanzar ventanas visibles sin avisar al usuario. Temporales en el scratchpad de la sesión; archivos grandes en `/mnt/plexdata` (no en `/home`, casi lleno).
- Licencias: Rubber Band es GPL, pesos de modelos (BS-Roformer-SW y Demucs) a verificar antes de distribuir.
- Verificación de marca de "Shed Stem Studio" y dominio antes de publicar (los candidatos `stemshed.io` / `.dev` eran del nombre anterior y ya no aplican; falta buscar uno nuevo).

## Decisión (2026-10-21): TIDAL por el motor local

El usuario eligió leer TIDAL con `tidalapi` a través del motor local (`engine/`) como método principal, por encima de la API oficial. **Queda abierto** si esto puede ir en una versión pública: no pude leer los Developer Terms de TIDAL (la página no se deja leer sin navegador), así que el riesgo de términos de uso está sin verificar. Mientras tanto la sesión sale del cliente de TIDAL para Linux del usuario y nunca entra al repo.

## Ajustes editables (2026-10-21)

Dónde viven los datos, los modelos y la música se elige en la pantalla de Ajustes y se guarda en `~/.config/stemshed/settings.json` (carpeta de datos, modelos de recomendación, entorno de separación, carpetas de música, servidor de modelos, modelo en uso). El motor valida cada ruta (absoluta, no del sistema, escribible) y administra su propio Ollama. Ver `docs/settings.md`.

## Spotify y YouTube Music (comienzo)

Base en el motor (interfaz común de proveedores, OAuth PKCE, tokens cifrados, lectura de biblioteca) y conectar/desconectar en Ajustes. Audio no obtenible: se usan archivos locales. Detalle y pendientes en `docs/fuentes-spotify-youtube.md`.

## Decisiones abiertas

1. Marco de UI (Svelte vs. vanilla).
2. Interfaz servida solo por el motor local o también como sitio público.
3. Proveedor y costos del nivel C.
4. Licencia del proyecto.
5. Wrapper: Electron vs. Tauri.
