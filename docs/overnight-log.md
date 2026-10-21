# Registro de la noche (2026-10-21)

Trabajo autónomo mientras el usuario dormía, con cuatro agentes en paralelo y verificación propia de cada etapa. Lo no verificado se declara.

## Estado al cierre

- **60 tests del motor pasan** (`cd engine && /mnt/plexdata/tidal-stems/venv/bin/python -m unittest discover -s tests`).
- `svelte-check`: 0 errores y 0 advertencias. **0 errores de consola** en las cinco pantallas (verificado con `proto/tools/uicheck.py`).
- El motor corre en 8770 con el código final (incluye análisis, perfiles y la tarea de "Disco de hoy").

## Hecho

- **Fuentes** reducida a conexiones (archivos y TIDAL) y **Música** nueva con catálogo unificado, búsqueda, filtros y origen por ítem. Panel de álbum compacto (▶, Separar, ✦) y ajustado a su contenido.
- **Estudio**: lista de descargados con arte, tamaño y borrado seguro (la caché anterior es de solo lectura); DAW con:
  - cabezal rediseñado sobre el reloj de audio (72 retrocesos medidos en loop → 0);
  - zoom con Ctrl + rueda, desplazamiento, faders visibles, menú colapsable;
  - secciones con bordes arrastrables, `Supr`, loop enlazado, N/P;
  - **análisis**: tonalidad, tempo, acorde actual, pista de acordes, grilla de compases y **click** alineado (desfase medio de ±1 ms con Rubber Band; detalle en `docs/phase0-results.md`).
- **Análisis musical** (agente): tonalidad con modo, tempo con pulsos reales, y progresión de acordes sobre stems separados; 13 tests, 6 temas reales analizados (2,6 a 7,7 s cada uno). Concuerda con fuentes públicas en la tónica de 5 de 5 temas con referencia; **el tempo discrepó por un factor de 2 en 2 de 6** y los acordes no tienen verdad compás a compás (`docs/analysis.md`, `docs/agent-notes/analisis.md`).
- **Recomendaciones** (agente): cuestionario con sugerencias, 6 perfiles por horario creados desde tu historial (con asistente de creación y selección automática), un disco por período, consigna a demanda, historial con deshacer, contexto de cada disco desde Wikipedia validado, guardar en destinos (solo TIDAL), y memoria en varios archivos con decaimiento. Detalle y mediciones en `docs/agent-notes/recomendaciones.md` y `docs/memory-format.md`.
- **Modelos** (agente): ningún modelo local sirve como fuente de datos de música (10 de 10 trampas alucinadas); Mistral Nemo por defecto, Gemma 3 12B instalada como alternativa (`docs/model-comparison.md`). Se agregó `nomic-embed-text` (274 MB) para similitud entre géneros.
- **Ideas** y análisis de lo que existe (Moises, Anytune, iReal Pro, redes de músicos, "referencias con tiempo", dónde viviría una parte paga): `docs/ideas.md`.

## Sin verificar o con límites (importante)

- **Escritura real en TIDAL** (guardar álbum o playlist): solo probada en modo prueba. Spotify no existe todavía.
- **Click**: medido con audio renderizado sin conexión; no se escuchó con placa real. Con SoundTouch es aproximado (±24 ms).
- **Cabezal en loop**: medido con el reloj de audio lento de Chromium sin ventana.
- **Secciones y arrastre de bordes**: probados con eventos sintéticos, no con mouse real.
- **YouTube Music** no se leyó en vivo (falta `ytmusicapi`): los perfiles usan lo que ya había extraído tu cliente anterior.
- **Análisis**: solo 4/4; el 1 del compás es poco fiable con brushes o funk sincopado; sin tensiones en los acordes.
- Un reinicio del motor durante la noche disparó un "Disco de hoy" real con el perfil Trabajo (4 discos quedaron marcados como mostrados); no hay reacciones inventadas.

## Pendiente / decisiones para el usuario

- Si `gemma3:12b` entra al catálogo recomendado (tiene más discos afines a jazz/soul/funk pero licencia con restricciones y repite candidatos).
- Conector de Spotify (necesita que registres una app de desarrollador).
- Términos de TIDAL para una versión pública: sin verificar.
- Bench de loop, seek y memoria de la Fase 0 y ONNX/WebGPU (0.B) siguen sin hacerse.
