# Plan: separación acelerada en AMD/Intel con ONNX + DirectML

Estado: **plan** (2026-10-21), sin implementar. Contexto: en Windows con AMD/Intel la separación hoy va por CPU (`docs/backends-separacion.md`). PyTorch+ROCm no cubre RDNA2 (RX 6000) y Ollama no puede separar. DirectML corre en cualquier placa DirectX 12 sin controladores especiales.

## 1. Lo que ya se sabe (con fuentes; nada verificado en esta máquina todavía)

- **audio-separator** (el que ya usamos) trae DirectML como **experimental** (`--use_directml`, desde la 0.44.x). En el informe de un usuario con una AMD integrada en Windows 11, los modelos **MDX y VR separaron bien con DirectML; RoFormer y Demucs fallaron**. Fuente: [issue #292](https://ithub.global.ssl.fastly.net/nomadkaraoke/python-audio-separator/issues/292), [releases](https://github.com/nomadkaraoke/python-audio-separator/releases).
- **El obstáculo de ONNX es la STFT.** ONNX no soporta tensores complejos, así que `torch.stft`/`istft` no se exportan. El patrón que usan todas las exportaciones: **sacar la STFT/iSTFT del grafo**, que el programa que llama la haga y le pase al modelo la parte real e imaginaria. Fuentes: [Mixxx GSoC 2025](https://mixxx.org/news/2025-10-27-gsoc2025-demucs-to-onnx-dhunstack/), [issue de Demucs #530](https://github.com/facebookresearch/demucs/issues/530), [PyTorch #86746](https://github.com/pytorch/pytorch/issues/86746).
- **Exportaciones públicas que siguen ese patrón:** [htdemucs core](https://huggingface.co/sathvik77/htdemucs-core-onnx), [demucs-onnx](https://huggingface.co/HRSadeghi/demucs-onnx), [BS-RoFormer de 4 stems](https://huggingface.co/silverdaw/bs-roformer-rhythm-onnx) (dice correr en DirectML con opset 17; usa trozos fijos de 8 s porque el embedding rotatorio se cachea por largo), [Mel-Band RoFormer de voz](https://huggingface.co/audiojs/mel-roformer). **No encontré** una de BS-Roformer-SW (6 stems) ni de htdemucs_6s.
- **Licencia:** una de esas páginas dice que los pesos de Demucs v3/v4 son CC BY-NC 4.0 (no comercial). Contradice lo que se supone hasta ahora: **hay que verificarlo** antes de distribuir cualquier exportación.

## 2. Alternativas de modelo

| Modelo | Stems | Formato / DirectML | Calidad | Nota |
|---|---|---|---|---|
| **BS-Roformer-SW** (actual) | 6: voz, batería, bajo, guitarra, piano, otros | PyTorch. ONNX: exportarlo nosotros con STFT afuera | La mejor de las que usamos | 667 MB. Riesgo: operaciones que DirectML no soporte; trozos fijos |
| **htdemucs_6s** | 6 | PyTorch. ONNX con STFT afuera (hay patrón, no hay export 6s público) | Menor (el piano sale flojo) | 52 MB, rápido. Plan B natural |
| **htdemucs / htdemucs_ft** | 4: sin guitarra ni piano | ONNX público | Buena en 4 stems | Licencia a verificar |
| **MDX-Net / VR** | 2: voz e instrumental | ONNX nativo; **DirectML funciona** (informe de usuario) | Buena en voz | Solo sirve para voz/instrumental o encadenado |
| **BS-RoFormer 4 stems (Silverdaw)** | 4 | ONNX con DirectML | A medir | Licencia y calidad a verificar |

## 3. Etapas, cada una con su criterio de salida

| # | Qué | Criterio |
|---|---|---|
| 0 | **Línea base en CPU**: instalar el entorno CPU (~4 GB, en C:) y separar un tema con BS-Roformer-SW y con htdemucs_6s | Tiempo por tema y RAM. Sin esto no sabemos si acelerar vale la pena |
| 1 | **Prueba de humo de DirectML**: `onnxruntime-directml` en un venv aparte y un modelo MDX con `audio-separator --use_directml` | `DmlExecutionProvider` disponible, la RX 6700S sube de uso (monitor) y el resultado suena bien. Medir contra CPU |
| 2 | **htdemucs_6s a ONNX** con STFT afuera y un corredor propio (`engine/onnxsep.py`): trozos con solapado, STFT/iSTFT en numpy, onnxruntime-directml | Paridad con PyTorch (correlación y SDR por stem sobre el mismo tema) y velocidad contra CPU |
| 3 | **BS-Roformer-SW a ONNX**, mismo patrón (real/imaginario de entrada y salida, trozo fijo) | Misma paridad; que DirectML soporte todas las operaciones; VRAM (8 GB) |
| 4 | **Integración**: `directml` pasa a instalable en `backends.py` (`requirements-env.win-directml.txt`, descarga explícita del ONNX), `stems.py` elige el camino según el motor, pruebas, asistente | Un tema separado de punta a punta desde la interfaz en la RX 6700S |

Puertas de decisión: si la etapa 1 falla, DirectML no sirve en esta placa y el plan se corta. Si la 2 anda y la 3 no, se ofrece htdemucs_6s acelerado (menor calidad) y RoFormer queda en CPU. Los criterios numéricos (cuánto más rápido, qué pérdida de calidad se acepta) se fijan al terminar la etapa 0, con la línea base a la vista.

## 4. Riesgos

- Operaciones que DirectML no soporte o resuelva lento (atención, rotary): se ve recién en las etapas 2 y 3.
- Los trozos fijos y el solapado cambian el resultado respecto de PyTorch: hay que medirlo, no suponerlo.
- Exportaciones de terceros: procedencia y licencia sin verificar.
- Una sola máquina AMD para probar; Intel y otras placas quedan sin verificar.
- Mantener dos caminos de separación (PyTorch y ONNX) y que den resultados comparables.

## 5. Costo estimado (sin garantía)

Etapa 0: horas. Etapa 1: medio día. Etapa 2: 1–2 días. Etapa 3: varios días, es la más incierta. Etapa 4: 2–3 días.
