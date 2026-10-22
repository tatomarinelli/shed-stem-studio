# Shed Stem Studio: arquitectura (v2, web local)

Estado: **propuesta para revisar**. No hay código nuevo; todo lo que se reutiliza ya existe y está probado dentro del cliente de TIDAL para Linux (ver sección 11).

**Nombre.** *Stem* (los instrumentos que separás) + *shed* (de *woodshedding*, la jerga del jazz para encerrarse a estudiar un pasaje; también *shedding*, soltar capas, que es lo que hace la separación; y el cobertizo de tu casa, tu taller propio). Suena a *watershed*, el divisor de aguas.

## 1. Qué es

Una app web que corre en tu máquina, sin cuentas y sin mandar tu audio a ningún lado:

1. **Fuentes**: conectás tus servicios (Spotify, TIDAL, YouTube) y tus archivos locales en una sola interfaz.
2. **Recomendación**: un descubrimiento diario que te conoce (álbum del día educativo, playlist del día), a partir de un **cuestionario inicial**, tus fuentes conectadas, el contexto y tus reacciones; con el modelo de lenguaje que elijas, **local** o de un proveedor.
3. **Estudio**: separa un tema en instrumentos y permite estudiarlo con ondas, loops A-B, velocidad sin cambiar el tono y entrenador de velocidad.
4. Un botón **"Enviar al estudio"** en cada tema de cualquier fuente.

## 2. Principios

- **Local primero**: separación, memoria de gustos y archivos viven en tu máquina; el modelo de lenguaje puede ser local.
- **Sin instalar lo pesado por defecto**: abrís la web y funciona; lo que mejora la calidad es opcional.
- **Fuentes por vías oficiales** en la versión pública; lo no oficial es un complemento aparte.
- **Nada llega a pantalla sin verificar** contra un catálogo.

## 3. Tres formas de correr la separación

| Nivel | Qué es | Calidad y velocidad | Qué necesita | Privacidad |
|---|---|---|---|---|
| **A. Solo web** | La página corre un modelo liviano en tu navegador (ONNX Runtime Web con WebGPU/WASM) | Buena, más lenta; sin los mejores modelos | Un navegador moderno con WebGPU; cero instalación | El audio no sale de tu equipo |
| **B. Motor local** | Un servidor en tu máquina (un comando) con tu GPU y los mejores modelos (RoFormer, Demucs) | La mejor; ~30 s por tema con una RTX 5080 | Python y una GPU (CUDA hoy; DirectML/MPS a evaluar) | Todo local |
| **C. Proveedor** *(pendiente)* | Un servicio remoto de separación, elegido por el usuario | Depende del servicio | Una clave de API | El audio sale a ese servicio |

La web **detecta** si hay un motor local (`localhost`) y lo ofrece; si no, usa el nivel A; el C es una opción explícita. Todos cumplen la misma interfaz `SeparationProvider`.

Salvedades a verificar con un prototipo: la velocidad y la memoria del nivel A con temas largos; y que los navegadores empiezan a pedir permiso para que una página pública hable con `localhost` (la web debe explicarlo y funcionar con el motor sirviendo también la interfaz).

## 4. Fuentes y conectores

Interfaz común: `gustos()`, `colecciones()`, `buscar(q)`, `abrir(item)`, `guardar(playlist)`. Lo que se **puede** hacer con cada una:

| Fuente | Gustos y colecciones | Vía | Dónde corre | Audio para estudiar |
|---|---|---|---|---|
| **Archivos locales** | Etiquetas y carpetas | — | Navegador (File System Access) o motor | **Sí** |
| **Spotify** | Tus top artistas y temas, historial reciente, playlists; guardar playlists | API oficial, OAuth con PKCE | Navegador | No (DRM y términos) |
| **TIDAL** | Favoritos, playlists | API oficial para desarrolladores (verificar alcance); `tidalapi` no oficial como complemento | Navegador / motor | Solo en un complemento personal opcional |
| **YouTube / YouTube Music** | Videos con "me gusta" y playlists (API oficial); historial de Music solo vía `ytmusicapi` (no oficial) | OAuth de Google / complemento | Navegador / motor | No |
| **MusicBrainz, ListenBrainz, Last.fm** | Catálogo abierto e historial abierto | Abierta | Navegador | No |

**Actualización:** Spotify y YouTube Music se conectan desde el motor (no el navegador), con almacén cifrado de tokens; ver `docs/fuentes-spotify-youtube.md`.

A verificar antes de construir: las cuotas y requisitos actuales de las apps de desarrollador de Spotify y Google (los modos de desarrollo suelen limitar los usuarios) y qué cubre hoy la API oficial de TIDAL.

## 5. "Enviar al estudio" desde una fuente

El estudio se **alimenta** de las fuentes conectadas, pero el audio sale de **tus archivos**:

1. En la interfaz unificada elegís un tema de cualquier fuente y tocás **Enviar al estudio**.
2. Shed Stem Studio lo **busca en tu biblioteca local** (etiquetas, artista, título y duración).
3. Si lo encuentra: lo separa. Si no: te pide que lo arrastres (o te dice cómo conseguirlo legalmente, por ejemplo una compra en Bandcamp).
4. Un complemento opcional (TIDAL no oficial, de uso personal) podría traer el audio por su cuenta; **no viene en la versión pública**.

Spotify y YouTube no entregan su audio para procesar, y bajarlo va contra sus términos; por eso el audio siempre pasa por tus archivos.

## 6. Módulo de recomendación

**Cuestionario inicial** (cuando todavía no hay datos o para afinar): instrumento y nivel, qué querés mejorar (teoría, oído, repertorio, improvisación), estilos que amás y que evitás, cuánto querés salir de tu zona (nada / algo / mucho), artistas imprescindibles, cómo escuchás (discos enteros o temas sueltos), ritmo de estudio diario. Se guarda como tu perfil editable.

**Señales** (todas opcionales, se combinan con pesos): cuestionario, fuentes conectadas, reacciones (ya lo escuché / me encantó / no me gusta, **por ítem, nunca por género**), contexto (hora, día, estación, clima) y memoria que el modelo reescribe.

**Modelo de lenguaje**, intercambiable: **local** (Ollama o LM Studio, que el navegador alcanza si se permite el origen), clave de API propia (se queda en tu navegador) o el motor local. Los modelos locales chicos saben menos música y se equivocan más; la verificación contra MusicBrainz evita discos inventados. Con 16 GB de VRAM conviene probar un modelo de tamaño medio.

**Salida**: álbum del día con ficha educativa, playlist del día con mosaico de portadas, y "Guardar en…" solo si el usuario lo pide.

## 7. Interfaz unificada

Barra lateral: **Hoy** (recomendación), **Fuentes** (Spotify, TIDAL, YouTube, Archivos, con su biblioteca navegable), **Estudio**, **Mi perfil** (cuestionario, memoria editable), **Ajustes y almacenamiento**. Cada tema, en cualquier lista, tiene: **Enviar al estudio**, **Abrir en el origen**, **Más como este**, y las reacciones. Se mantiene el historial del navegador para Atrás y Adelante dentro de la app.

## 8. Motor de audio: Web Audio

El navegador resuelve lo que antes era el problema de portar el motor: **Web Audio** con un **AudioWorklet** de estiramiento de tiempo (SoundTouch o Rubber Band en WASM) para velocidad sin cambiar el tono, mezcla por stem, y loop A-B. Funciona igual en Windows, macOS y Linux.
A medir en la fase 0 con stems reales: memoria (6 stems de 5 minutos son ~600 MB en float32; se decodifican solo los no silenciosos y se evalúa decodificar por tramos), calidad a 25–50 % de velocidad y exactitud del loop.

## 9. Arquitectura técnica

```
 navegador (PWA)                          motor local (opcional, 1 comando)
 ┌────────────────────────────┐   HTTP    ┌──────────────────────────────┐
 │ UI (TypeScript + Vite)     │◄─────────►│ Python (FastAPI)             │
 │ Estudio · Hoy · Fuentes    │ WebSocket │ separación (GPU) · ondas     │
 │ Web Audio + worklet        │           │ memoria · LLM · conectores   │
 │ conectores de navegador    │           │ no oficiales (complemento)   │
 │ separación nivel A (ONNX)  │           │ sirve también la UI          │
 │ IndexedDB / OPFS           │           └──────────────────────────────┘
 └────────────────────────────┘
```

- La **UI funciona sola** (nivel A); el motor es una mejora y también puede servir la UI desde `http://localhost:<puerto>`.
- Seguridad del motor: solo loopback, token de emparejamiento, lista de orígenes, y todo lo que viene de afuera (títulos, URLs) se trata como dato.
- Datos: IndexedDB y OPFS en el navegador; con motor, también archivos en una carpeta del usuario. Todo exportable.
- Extensión de navegador opcional (por sitio) con el botón "Enviar a Shed Stem Studio" sobre los reproductores web oficiales.

## 10. Qué es compartible y qué no

Compartible: la UI, el núcleo, los conectores con API oficial, el estudio sobre archivos locales. **No** compartible: el cliente de TIDAL modificado de este repo (software propietario), y bajar audio de un servicio para separarlo. Los conectores no oficiales (`tidalapi`, `ytmusicapi`) solo como complemento aparte, no en la versión pública. Antes de distribuir: licencia de los pesos de cada modelo y verificación de marca del nombre.

## 11. Reutilización de lo que ya existe

| Hoy | En Shed Stem Studio |
|---|---|
| `studyPanel/` (ondas, loops, entrenador, progreso, biblioteca) | UI de Estudio: se reescribe en TypeScript sobre Web Audio |
| `tidalrecs/stems.py`, `stems_peaks.py`, `stems_probe.py` | Motor local: separación y ondas, casi iguales |
| `tidalrecs/memory.py`, `daily.py`, `context.py`, `llm.py` | Módulo de recomendación (parte en el navegador, parte en el motor) |
| `sources.py`, `ground.py` | Pasan a conectores y a verificación contra MusicBrainz |
| `recsPanel/` | UI de Hoy y de Almacenamiento |
| 90 pruebas | Se mudan con el código |
| `study-engine`, `tidal-player`, `trackIdTap`, `apiLogin`, wrapper de wine | **No se mudan** |

## 12. Fases

| # | Entrega | Cómo se verifica |
|---|---|---|
| 0 | **Prototipo del motor Web Audio** con stems reales de nuestra caché: mezcla, velocidad, loop | Medición de memoria, calidad a baja velocidad y exactitud del loop |
| 1 | **Estudio local**: motor Python + UI web, arrastrar archivos, separación nivel B, ondas, loops | Pruebas del núcleo + captura + un tema real de punta a punta |
| 2 | **Separación en el navegador (nivel A)** con un modelo liviano | Tiempo y calidad frente al nivel B |
| 3 | **Fuentes y "Enviar al estudio"**: archivos locales, MusicBrainz, Spotify (PKCE) | Pruebas con conectores simulados; Spotify real con una cuenta |
| 4 | **Cuestionario y recomendación** con modelo local y proveedor | Pruebas + una corrida real con un modelo local |
| 5 | TIDAL y YouTube (oficial y complementos) | — |
| 6 | Proveedor de separación (nivel C), extensión de navegador, empaquetado, licencia, documentación | — |

## 13. Decisiones abiertas

1. **Cómo se distribuye la interfaz**: servida por el motor local (un comando, sin permisos de red local) o también como sitio público estático que detecta el motor. Recomiendo ambos, empezando por el primero.
2. **Marco de la UI**: TypeScript + Vite con un marco liviano (Svelte o Preact) o vanilla. Recomiendo Svelte.
3. **Proveedor del nivel C** y modelo de costos.
4. **Licencia** del proyecto y de los modelos.
5. **Dónde vive**: en su propio repositorio, separado del cliente de TIDAL.
