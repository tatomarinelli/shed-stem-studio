# Contexto del proyecto (para una sesión sin historial)

## Qué es
**Shed Stem Studio**: webapp local-first para estudiar música.
- Separa un tema en instrumentos (guitarra, bajo, batería, piano, voz, otros) con IA.
- Estudio tipo DAW: pistas con onda, mute/solo, zoom, loops, secciones (A-B-C), velocidad sin cambiar el tono, **tonalidad, tempo, acordes, grilla de compases y click**.
- **Música** unificada (archivos locales y TIDAL) y **Recomendaciones**: un disco por período según un perfil, la hora y la memoria de gustos; el modelo de lenguaje propone y MusicBrainz verifica.
- **Ajustes** con modelos por módulo, descargas con progreso, servicios en ejecución.
- **Primeros pasos**: asistente de primer inicio.

Licencia: **GPL-3.0-or-later**. Repo: `tatomarinelli/shed-stem-studio`.

## Piezas
```
Interfaz (Svelte 5 + TypeScript + Vite)   proto/player/
        │ HTTP en 127.0.0.1
        ▼
Motor local (Python, solo librería estándar)   engine/server.py
   ├─ separación y análisis  → proceso hijo con el "entorno" (torch, audio-separator, librosa)
   ├─ recomendaciones        → servidor de modelos (Ollama) + MusicBrainz + Wikipedia
   └─ TIDAL (tidalapi) con la sesión del propio usuario
```
- **Entorno de separación**: carpeta con un `venv` de Python con torch + audio-separator + librosa (≈ 8 GB en Linux con CUDA). Se instala desde el asistente (`engine/envsetup.py`) con `pip` a partir de `engine/requirements-env.txt`. **Nunca se instala solo.**
- **Modelo de separación**: BS-Roformer-SW (≈ 700 MB), se descarga con `audio-separator --download_model_only`.
- **Modelo de recomendación**: Ollama; por defecto `mistral-nemo` (12B, ≈ 7 GB).
- Docker (`docker/`) ya levanta todo en Linux con `docker compose up`.
- Documentación: `docs/` (arquitectura, pantallas, análisis, memoria de gustos, ajustes, publicación, asistente).

## Reglas del proyecto (de `CLAUDE.md`)
- Sin código, binarios, credenciales ni caché de TIDAL en el repo.
- Nada se descarga solo; los modelos y el entorno se eligen y bajan desde Ajustes, a la carpeta del usuario.
- Archivos grandes fuera del disco del sistema.
- Escrituras en cuentas externas (guardar en TIDAL) solo con confirmación explícita; nunca borra.
- El modelo de recomendación solo propone; todo se verifica en MusicBrainz; el motivo mostrado nunca es texto inventado.
- Reacciones por ítem, nunca por género. La banda del usuario (`ownArtists` del perfil) nunca se recomienda.
- Textos en español rioplatense (voseo), cortos.

## Cómo se prueba hoy (Linux)
- Motor: `cd engine && python3 -m unittest discover -s tests` (80 pruebas; usan datos sintéticos).
- Interfaz: `cd proto/player && npx svelte-check --tsconfig ./tsconfig.json` y `npm run build`.
- Interfaz con clics reales: `proto/tools/uicheck.py` (Chromium sin ventana por CDP; en Windows habrá que adaptar la ruta del navegador).

## Qué está verificado para Windows (desde Linux, 2026-10-21)
- Las 83 dependencias fijadas tienen versión para Windows x64 con Python 3.12 a 3.14, **excepto `diffq`**, que solo existe como código fuente (pediría compilador). `diffq` **no hace falta**: BS-Roformer-SW separa sin él (probado en Linux).
- Cuatro paquetes son solo de Linux (`triton`, `nvidia-cufile-cu12`, `nvidia-nccl-cu12`, `nvidia-nvshmem-cu12`).
- `torch` y `torchaudio` 2.11.0 existen para Windows con CUDA 12.8 (`cu128`) y para CPU, en Python 3.12, 3.13 y 3.14. En Windows las bibliotecas de CUDA vienen dentro de la rueda de torch.
- `onnxruntime`, `onnxruntime-gpu` y `onnxruntime-directml` tienen ruedas para Windows en Python 3.11 a 3.14.

## Qué NO está verificado (todo lo demás)
- Que el entorno se instale y funcione en Windows.
- La velocidad de la separación en CPU.
- El motor en Windows (tiene supuestos de Linux: ver `03-motor-portable.md`).
- El reproductor (AudioWorklet, SharedArrayBuffer) dentro de WebView2.
- Ollama en Windows con GPU AMD.
- El instalador, la firma y las actualizaciones.

## Decisiones ya tomadas
- Licencia GPL-3.0-or-later.
- Los modelos **no** van embebidos en la web ni en el instalador: se descargan desde el asistente.
- Instalación por usuario, sin administrador.
- Windows v1: **NVIDIA con CUDA y CPU como respaldo**. AMD/Intel con DirectML queda para después, si la exportación a ONNX del modelo sirve.

## Dudas legales abiertas
- `rubberband-wasm` (estirador por defecto) se declara GPL-2.0 y no se pudo confirmar si es "solo v2" o "v2 o posterior"; si fuera solo v2, no se puede combinar con GPL-3.0. Alternativa: SoundTouch (LGPL-2.1), que ya está integrado.
- Términos de TIDAL para una versión pública: sin verificar.
