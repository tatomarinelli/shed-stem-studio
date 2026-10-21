# Shed Stem Studio

Aplicación **local-first** para estudiar música: separa un tema en instrumentos (stems) con IA, te deja tocar encima con velocidad, loops y click, analiza la tonalidad, el tempo y los acordes, y cada día te propone un disco nuevo según lo que escuchás.

Todo corre en tu máquina. El audio, tus gustos y tu sesión de TIDAL no salen de ahí.

> **Estado: prototipo avanzado.** Probado solo en Linux (Arch/CachyOS) con una RTX 5080. Ver [Sistemas compatibles](#sistemas-compatibles) y [Límites conocidos](#límites-conocidos).

## Nombre
El proyecto se llama **Shed Stem Studio** (antes StemShed). Por compatibilidad con datos ya guardados, los identificadores técnicos conservan el nombre anterior: la carpeta `~/.config/stemshed/`, las variables `STEMSHED_*` y los servicios de Docker.

## Qué hace

| Pantalla | Para qué sirve |
|---|---|
| **Fuentes** | Conectar tu música: carpetas de archivos y TIDAL. |
| **Música** | Ver todo junto (búsqueda, filtros por fuente, artista y género, álbumes y temas). Escuchar, separar o pedir parecidos. |
| **Recomendaciones** | Un disco por período según tu perfil, hora y clima. Perfiles por horario, memoria de gustos con decaimiento, historial con deshacer, y guardar en TIDAL. |
| **Estudio** | Un DAW: pistas por instrumento, mute/solo/volumen, zoom, loops A-B, secciones (A, B, C), velocidad sin cambiar el tono, **tonalidad, tempo, acordes, grilla de compases y click**. |
| **Ajustes** | Qué modelo usa cada módulo, cuánto pesa y dónde está; descargas con progreso; qué está corriendo y en qué puerto; apagar el motor. |

## Cómo está armado

```
 Navegador (Svelte)  ──HTTP──▶  Motor local (Python, solo librería estándar)
  proto/player                    engine/  ── 127.0.0.1:8770
                                    ├─ separación y análisis  (entorno con torch/CUDA, aparte)
                                    ├─ servidor de modelos    (Ollama, para recomendar)
                                    └─ MusicBrainz / Wikipedia / TIDAL (con tu sesión)
```

- **Interfaz:** `proto/player/` (Svelte 5 + TypeScript + Vite). El audio se mezcla en un AudioWorklet y se estira con Rubber Band (WASM) o SoundTouch.
- **Motor:** `engine/`. Escucha solo en `127.0.0.1` y solo acepta pedidos de los orígenes permitidos.
- **Docker:** `docker/`. Motor y web en contenedores, con GPU.
- **Documentación:** `docs/` (arquitectura, pantallas, análisis, memoria, ajustes, publicación).

## Principios

1. **Local primero.** Nada de tu audio ni de tus gustos se sube a ningún servicio.
2. **Nada se descarga solo.** Modelos y entornos pesados se eligen y se bajan desde Ajustes, a la carpeta que vos indiques.
3. **El modelo propone, MusicBrainz verifica.** Los modelos locales inventan datos de música; todo lo que se muestra sale de una fuente verificable.
4. **Escrituras solo con un clic.** Guardar en TIDAL pide confirmación y nunca borra nada.
5. **Sin código ni credenciales de TIDAL en este repo.** La sesión se guarda en tu equipo (`~/.config/stemshed/`).

## Sistemas compatibles

| Sistema | Con Docker | Sin Docker (desarrollo) |
|---|---|---|
| **Linux + GPU NVIDIA** | Probado | Probado |
| **Windows** | Sin probar. Docker Desktop con WSL2 podría funcionar, pero la GPU se conecta distinto: el `compose.yml` usa CDI (`nvidia.com/gpu=all`), que es de Linux. | No funciona hoy: el motor lee `/proc` y `nvidia-smi`, y `npm run worklet` usa `cp`. |
| **macOS** | Sin probar y sin GPU NVIDIA: la separación iría a CPU, muy lenta. | No funciona hoy (mismos motivos). |

Los comandos de abajo están escritos para Linux (shell tipo bash).

## Requisitos

- Linux con GPU NVIDIA (la separación en CPU funciona pero es muy lenta).
- **Con Docker:** Docker, Docker Compose y `nvidia-container-toolkit`.
- **Sin Docker:** Python 3.14, Node 26, `ffmpeg`, y `pip install tidalapi`.
- Para recomendar: [Ollama](https://ollama.com) (el motor puede levantar su propia instancia).
- Espacio: el entorno de separación ocupa ≈ 8 GB, el modelo de separación 700 MB y cada modelo de recomendación entre 2 y 8 GB.

## Empezar con Docker

```bash
cd docker
docker compose up -d --build
```

No hay nada que configurar: todo queda en `docker/data/` (configuración, datos, modelos y tu música en `docker/data/music`). Para usar otra carpeta o disco, copiá `.env.example` a `.env` y cambiá las rutas.

Abrí <http://127.0.0.1:5173> (o el puerto de `STEMSHED_WEB_PORT`). Se abre el asistente de primeros pasos; también podés hacerlo desde **Ajustes**:

1. **Instalar** el entorno de separación (≈ 8 GB en disco; los programas que corren la IA en tu placa de video).
2. **Descargar** el modelo de separación.
3. **Descargar** un modelo de recomendación (el servidor de modelos ya viene en el `docker compose up`).

Detalles, variables y GPU: [`docker/README.md`](docker/README.md).

## Empezar sin Docker (desarrollo)

```bash
# Interfaz
cd proto/player
npm install
npm run dev              # http://127.0.0.1:5173 (también construye el worklet)

# Motor (otra terminal)
cd proto/player
npm run engine           # = python3 ../../engine/server.py 8770
```

Por defecto el motor guarda datos en `/mnt/plexdata/stemshed` y espera el entorno de separación en `/mnt/plexdata/tidal-stems`. Cambialo con las variables `STEMSHED_DATA` y `STEMS_ENV`, o desde **Ajustes → Carpetas y ubicaciones**. El entorno de separación se instala con el botón de Ajustes.

## Primer uso

La primera vez, un asistente (**Primeros pasos**) te lleva paso a paso: tu equipo, dónde guardar, instalar la separación, conectar tu música y TIDAL, elegir el modelo de recomendaciones y crear tu perfil. Cada paso se puede dejar para más tarde y se repite desde Ajustes. Lo que sigue es el uso manual.

1. **Fuentes:** agregá una carpeta de música y/o conectá TIDAL (inicio de sesión propio, sin pasar por otra app).
2. **Música:** elegí un tema y tocá **Separar** (tarda unos minutos).
3. **Estudio:** abrilo desde la lista de descargados. `Espacio` reproduce, `M` marca una sección, `S` la repite, `K` activa el click, `\` achica el menú.
4. **Recomendaciones:** completá *Mi perfil* y pedí un disco; reaccioná para que aprenda.

## Pruebas

```bash
# Motor (68 pruebas, datos sintéticos, no tocan tu memoria real)
cd engine && python3 -m unittest discover -s tests
# (algunas necesitan el Python del entorno de separación: soundfile, librosa)

# Interfaz
cd proto/player && npx svelte-check --tsconfig ./tsconfig.json

# Chequeo de la interfaz con Chromium sin ventana (clics reales)
python3 proto/tools/uicheck.py "http://127.0.0.1:5173/#/ajustes" --wait 4 --text main
```

Evaluación de la variedad de las recomendaciones (en un entorno aislado): `python3 engine/eval/recs_variety.py --runs 3`.

## Documentación

- [`PLAN.md`](PLAN.md) — plan de trabajo y decisiones.
- [`docs/architecture.md`](docs/architecture.md) — arquitectura.
- [`docs/screens.md`](docs/screens.md) y [`docs/settings.md`](docs/settings.md) — pantallas y ajustes.
- [`docs/analysis.md`](docs/analysis.md) — tonalidad, tempo y acordes: cómo funciona y con qué exactitud.
- [`docs/memory-format.md`](docs/memory-format.md) — memoria de gustos.
- [`docs/recs-plan-v3.md`](docs/recs-plan-v3.md) y [`docs/recs-baseline.md`](docs/recs-baseline.md) — plan de mejora de recomendaciones y su línea de base.
- [`docs/publicacion.md`](docs/publicacion.md) — web pública + motor local, Docker, dominio.
- [`docs/ideas.md`](docs/ideas.md) — ideas y análisis de lo que ya existe.
- [`docs/phase0-results.md`](docs/phase0-results.md) y [`docs/overnight-log.md`](docs/overnight-log.md) — mediciones y registro de trabajo.

## Límites conocidos

- **Click:** medido con audio renderizado sin conexión; no verificado de oído con placa real. Con SoundTouch es aproximado (±24 ms).
- **Análisis:** el tempo puede salir al doble o a la mitad; solo 4/4; los acordes no informan tensiones. Medición completa en `docs/analysis.md`.
- **Recomendaciones:** hoy sesgan hacia el jazz (47 % de los discos en la línea de base). El plan para corregirlo está en `docs/recs-plan-v3.md`.
- **TIDAL:** guardar en TIDAL no se probó contra una cuenta real. Spotify y YouTube Music no están conectados.
- **Docker:** Ollama en contenedor y TIDAL desde el contenedor sin verificar.
- **Plataformas:** solo Linux probado.

## Seguridad y datos

- El motor escucha solo en loopback (`127.0.0.1`) y valida el `Origin` de cada pedido contra una lista explícita (`STEMSHED_ORIGINS`).
- Credenciales y memoria viven en `~/.config/stemshed/` (permisos `600`). No se versionan.
- Antes de publicar la web: emparejamiento por código y token por instalación (planificado en `docs/publicacion.md`).

## Licencia

Shed Stem Studio es software libre bajo la **GNU General Public License v3.0 o posterior** (GPL-3.0-or-later). Ver [`LICENSE`](LICENSE). Cualquiera puede usarlo, estudiarlo y modificarlo; quien distribuya una versión modificada tiene que publicar su código bajo la misma licencia.

Para tener en cuenta:
- **Rubber Band** (estirador por defecto, `rubberband-wasm`) se declara GPL-2.0. **Sin verificar** si es "solo v2" o "v2 o posterior": si fuera solo v2, no se podría combinar con una obra GPL-3.0. Hay que confirmarlo con la licencia de la biblioteca original antes de una versión publicada.
- **Términos de TIDAL** para una versión pública: sin verificar.
- Los modelos de terceros (BS-Roformer, Mistral Nemo, Gemma) tienen sus propias licencias y no se distribuyen con este repo.
- Esto no significa que cualquiera pueda escribir en el repo: los cambios de terceros entran por pull request y los acepta quien mantiene el proyecto.
