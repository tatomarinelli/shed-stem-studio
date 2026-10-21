# Análisis musical: tonalidad, tempo y acordes

Para un tema ya separado, el motor estima la **tonalidad** (con el modo), el **tempo** con los pulsos reales y el 1 de cada compás, y la **progresión de acordes**. Todo es una estimación: cada campo trae su confianza y `notes` explica las dudas.

## Piezas

- `engine/analyze.py` corre en el venv de separación, solo con CPU (8 hilos, sin CUDA ni torch).
  - Uso: `analyze.py <carpeta_stems> [--out archivo] [--track-id ID]`.
  - Variantes para comparar: `--beat-source drums|bass|all`, `--no-chord-bass` y `--with-vocals`.
  - El progreso sale por stderr como `PROGRESS <etapa> <pct>`.
- `engine/analysis.py` es el envoltorio con la librería estándar.
  - Un trabajo a la vez, con prioridad baja y un tope de 15 min.
  - Guarda en `<dataDir>/analysis/<id>.json`; nunca escribe en las cachés de stems.
  - Funciones: `configure`, `start(id, force)`, `job_status`, `get` (None si es de otra versión del formato) y `delete`.
- Rutas del motor: `GET /engine/analysis/<id>`, `POST /engine/analysis/<id>/start` (cuerpo opcional `{"force": true}`), `GET /engine/analysis/<id>/status`.

## Cómo funciona

- **Tempo** (batería + bajo): envolvente de ataques y producto autocorrelación × DFT del tempograma. Los pulsos los sigue `librosa.beat`. Si varía más del 3 % entre ventanas, se sigue el tempo local y se marca `stable: false`.
- **Octava del tempo:** se prueba el par (lento, rápido) con tres reglas en orden: timbre alternado bombo/redoblante, contratiempo en 2 y 4, y paridad de acentos. Como control, si el seguidor no sostiene el tempo, se usa la otra octava. La alternativa se devuelve siempre.
- **Compases:** se elige la fase del 1 entre 4, combinando bombo, ataques del bajo y cambio armónico. Siempre asume 4/4.
- **Acordes** (guitarra + piano + otros, sin voz; el bajo da la fundamental): croma CQT afinada por mediana circular (±50 cents) y promediada por pulso; plantillas de 8 calidades que cuentan los armónicos; el bajo suma un bonus a la fundamental, con más peso en el 1; Viterbi suaviza, con el cambio más barato en el 1 y el 3; una segunda pasada prefiere levemente los acordes diatónicos; slash cuando el bajo es otra nota del acorde.
- **Tonalidad:** se puntúan 7 modos × 12 tónicas. El perfil reconoce el conjunto de notas y la evidencia de tónica (fundamentales, bajo, primer y último compás) elige el centro. Frigio, lidio y menor armónico llevan una pequeña penalización; el menor armónico se informa como `minor` con `variant`. Si el I y el IV dominan con acordes 7, se marca blues.

## Formato (versión 1)

```
{version:1, trackId, createdAt, durationSec, title, artist,
 key:{tonic, mode, family, label, variant, blues, majorMinor:{...}, confidence, tonicConfidence,
      alternatives:[{tonic,mode,score}x3], tuningCents},
 tempo:{bpm, confidence, beats:[s...], downbeats:[s...], timeSignature:"4/4", stable, variation,
        local:[{t,bpm}], alternatives:[{bpm,score,relation:"mitad"|"doble"}], downbeatConfidence, source},
 chords:[{start,end,root,quality,label,bass,confidence}],   // label "N" = silencio
 notes:[...], stats:{...}}
```

`beats` son los pulsos reales detectados (no una grilla uniforme) y sirven tal cual para el click. `downbeats` es uno de cada 4 pulsos.

## Rendimiento

Entre 2,5 y 3 s por tema de 4 a 6 min y 7,7 s para uno de 15 min. Memoria de 0,5 a 0,6 GB (0,8 GB para el de 15 min).

## Límites

- La octava del tempo es la parte más frágil.
- Solo 4/4.
- Con brushes o funk sincopado, el 1 del compás es poco fiable (`downbeatConfidence` bajo).
- Los acordes van por pulso y sin tensiones (9, 13, #9); un solo ensucia la croma.
- Cuando la evidencia de tónica es pareja, el modo es una apuesta.
- Con la afinación cerca de ±50 cents, la tónica puede quedar corrida medio tono (se avisa en `notes`).
- Lo sintético es más fácil que lo real.

Medición completa y comparación con fuentes reales: `docs/agent-notes/analisis.md`.
