# Fase 0: resultados (en curso)

## 0.B-entorno: WebGPU en Chromium real (2026-10-20)

Máquina: RTX 5080 (driver NVIDIA, Vulkan 1.4) + iGPU AMD (RADV). Chromium 154.

| Configuración | `navigator.gpu` | `requestAdapter()` |
|---|---|---|
| Headless, sin flags | sí | **null** |
| Headless, `--enable-unsafe-webgpu` + flags de Vulkan/ANGLE | sí | **null** |
| Con ventana, sin flags | sí | **null** |
| Con ventana, `--ozone-platform=x11 --enable-unsafe-webgpu --enable-features=Vulkan,VulkanFromANGLE,DefaultANGLEVulkan --use-angle=vulkan` | sí | **NVIDIA Blackwell** (maxBufferSize ~4 GB, maxStorageBufferBindingSize ~2 GB, 24 features) |
| Con ventana, `--ozone-platform=wayland --enable-unsafe-webgpu --enable-features=Vulkan --use-vulkan` | sí | NVIDIA Blackwell (Chromium avisa que wayland no es compatible con Vulkan) |

Conclusión parcial:
- WebGPU **funciona en esta máquina, pero solo con flags de Vulkan** y con ventana; en headless no hay adaptador. Un usuario con Chromium "de fábrica" en Linux hoy no tiene WebGPU: el nivel A depende del hardware/SO (en Windows/macOS suele estar activo por defecto; sin verificar acá).
- Límite de buffer de almacenamiento ~2 GB por binding: relevante para modelos grandes (RoFormer 667 MB en fp32 entra, pero hay que fragmentar activaciones).
- `crossOriginIsolated` queda por medir con el servidor COOP/COEP.
- Firefox: sin probar todavía.

## 0.A: reproducción con velocidad variable (parcial)

Diseño medido: un AudioWorklet propio lee los stems no silenciosos desde SharedArrayBuffer (float32), los **mezcla primero** (volumen, mute, solo) y estira **una sola mezcla** con Rubber Band WASM (`rubberband-wasm` 3.3.0, GPL) o SoundTouch (`soundtouchjs` 0.3.0, LGPL). El loop A-B se resuelve en el dominio de la fuente (vuelta de lectura), no con nodos de Web Audio. Requiere COOP/COEP (`crossOriginIsolated` = true, verificado en el servidor del prototipo).

Velocidad de proceso, en veces tiempo real (offline, 60 s de un tema de 226 s, 5 stems, Chromium 154 headless; **no registré la carga de CPU ajena durante la corrida; repetir con la máquina libre antes de dar los números por firmes**):

| Estirador | 100 % | 75 % | 50 % | 25 % |
|---|---|---|---|---|
| Rubber Band rápido | 113.9× | 44.9× | 44.8× | 47.7× |
| Rubber Band fino (R3) | 14.7× | 13.4× | 16.8× | 26.4× |
| SoundTouch | 542.4× | 639.6× | 602.5× | 655.1× |

Hallazgos:
- Los tres sobran para tiempo real en una sola mezcla. El fino cuesta ~7 % de un núcleo; esto es offline, **falta medir en vivo** con el audio sonando.
- Con Rubber Band la salida pasa de 1.0 de pico (hasta 1.35 con el fino): conviene un limitador o bajar la ganancia maestra.
- Bugs propios encontrados por la medición y corregidos: SoundTouch ignoraba la velocidad (orden de inicialización), y el motor fino se quedaba sin salida si se lo alimentaba con pocas muestras.
- `--enable-precise-memory-info` tumba Chromium headless en esta máquina; no usarlo.
- Memoria: 5 stems de un tema de 5:26 son ~560 MB en float32; el de 15 min serían ~1,6 GB. **Sin medir** (ver pendiente).

El prototipo de escucha con interfaz Svelte está en `proto/player/` (ver `docs/screens.md`).

## Click alineado con los pulsos (2026-10-21)

El click se genera **dentro del worklet, después del estirador**, en los pulsos del análisis (segundos de la fuente). Así no se estira ni se corre con la velocidad. El tiempo "que se oye" se calcula de forma determinista: una ancla (posición de la fuente en una muestra de salida) más la velocidad, y se vuelve a anclar al buscar, cambiar de velocidad o de loop. Un primer diseño que usaba "posición leída menos lo pendiente en el estirador" dio tirones y perdía pulsos, y se descartó.

**Medición** (`proto/player/public/_clicktest.html`, abrir en el servidor de desarrollo con `?speeds=0.25,0.5,1`): una pista sintética con un impulso cada 0,5 s, renderizada sin y con click; el click se aísla restando y se compara el inicio de cada click con el de cada impulso. Con las demoras de cada estirador sin compensar:

- **Rubber Band:** el audio se adelanta `X ms × (1/velocidad − 1)` respecto de un mapeo lineal, con X constante (33,5 ms el modo rápido, 52,7 ms el fino), de 40 % a 125 %. Dispersión de 0,2 a 1,5 ms.
- **SoundTouch:** no sigue una ley simple y tiene dispersión de hasta 24 ms.

**Con la compensación aplicada** (renderizado sin conexión):

| Estirador | Desfase medio (40 a 125 %) | Dispersión | En 25 % |
|---|---|---|---|
| Rubber Band rápido | de −0,2 a +0,4 ms | ≤ 1,2 ms | +1,9 ms |
| Rubber Band fino | de −0,5 a +1,0 ms | ≤ 2,4 ms | +3,2 ms |
| SoundTouch | ~0 ms (tabla por velocidad) | hasta 24 ms | no medible: la prueba pierde pulsos |

**Límites:** con SoundTouch el click es solo aproximado, y por encima de 100 % o a 25 % mi prueba no logró aislar los pulsos. La prueba es sintética y sin conexión: **no se verificó de oído ni con la latencia real de una placa de sonido.** El cabezal de la interfaz y el click comparten referencia pero la latencia de salida del dispositivo no se compensa en el click.

## Pendiente
- Bench completo (`proto/runbench.sh full "run=load,speed,loop,seek"`): memoria con los 3 temas, exactitud del loop a 50 vueltas y latencia de seek. Esperando a que la máquina esté libre.
- Escucha del usuario a 25/50/75 % con voz y guitarra, comparando los tres estiradores.
- 0.B Demucs ONNX en WebGPU/WASM y exportación de BS-Roformer-SW.
- Decisión de cierre.
