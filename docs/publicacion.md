# Publicación: web pública + motor local

Estado: **plan** (2026-10-21). Decisión del usuario: **los modelos no van embebidos en la web**. La web instala el motor en la máquina del usuario y lo usa cuando lo necesita. Es el "nivel B" (motor local); el "nivel A" (todo en el navegador) queda descartado por ahora.

## Piezas

1. **Web pública** (estática, interfaz Svelte): no guarda audio ni modelos. Hosting gratis con encabezados propios.
2. **Instalador/arrancador** (programa chico, firmado): lo descarga el usuario desde la web, una vez. Instala y actualiza el motor, los modelos y el entorno de separación, en las carpetas que el usuario elija.
3. **Motor local** (el actual): escucha solo en `127.0.0.1`. Hace separación, análisis, LLM, MusicBrainz y TIDAL.

## Qué puede y qué no puede hacer la web

- **No puede** instalar ni ejecutar un programa por sí sola (el navegador no lo permite). El mínimo inevitable es: **descargar el instalador y abrirlo una vez**.
- **Sí puede**: detectar si el motor está andando, ofrecer la descarga correcta para el sistema, abrir el motor con un enlace `stemshed://` si ya está instalado, y a partir de ahí dar todas las órdenes (descargar modelos, separar, analizar, recomendar).

## Flujo del usuario

1. Entra al sitio. La web busca el motor en `127.0.0.1:8770`.
2. Si no responde → pantalla "Instalar Shed Stem Studio": botón de descarga para su sistema (AppImage/instalador/Docker) y un comando para copiar.
3. El instalador pregunta carpetas (motor, modelos, música), revisa GPU/VRAM/disco (ya existe `hardware.py`) y arma el entorno. No instala modelos grandes sin que el usuario los elija.
4. Registra el arranque: el motor queda disponible; si preferís que no esté siempre prendido, arranca bajo demanda con `stemshed://` y se apaga solo tras un rato sin uso.
5. Emparejamiento: el motor muestra un código la primera vez; el usuario lo escribe en la web; desde ahí cada llamada lleva un token.
6. Los modelos se descargan **desde el motor** (Ollama / Hugging Face) a la carpeta elegida, con progreso y verificación de hash. La web solo da la orden.

## Seguridad (obligatoria antes de publicar)

Una web pública que le habla al motor local expone el motor a cualquier página abierta en el navegador si no se protege.
- Allowlist **estricto** de orígenes (solo el sitio oficial y `127.0.0.1:5173` en desarrollo); nunca `*`.
- Emparejamiento con código y token por instalación; el token se puede revocar desde Ajustes.
- Respuestas con CORS y `Cross-Origin-Resource-Policy` correctos; el preflight de red privada de Chrome.
- Instaladores **firmados** y con hash publicado; el motor se actualiza desde el instalador, nunca desde código que mande la web.
- El motor nunca expone la sesión de TIDAL ni rutas fuera de las carpetas configuradas; ya cumple con las reglas del proyecto (`CLAUDE.md`).

## Dominio y hosting gratis

- **Cloudflare Pages** (`*.pages.dev`): permite el archivo `_headers` (COOP/COEP necesarios para el reproductor). Primera opción.
- Netlify (`*.netlify.app`): también permite encabezados propios.
- GitHub Pages: no permite encabezados; habría que usar un service worker de aislamiento, más frágil.
- Dominio propio gratis: prácticamente no existe (Freenom cerró). Un `.dev`/`.app` cuesta unos USD 10–15 al año; la marca y el dominio de Shed Stem Studio siguen sin verificar (`PLAN.md`).

## Formas de entregar el motor (a elegir)

| Opción | Pro | Contra |
|---|---|---|
| App de escritorio con Tauri | Experiencia de un clic en Windows/Mac/Linux; bandeja con estado | Más trabajo: empaquetar Python + el entorno de separación |
| AppImage / script de instalación | Simple para Linux; sirve ya | Menos amigable en Windows/Mac |
| Docker (comando copiable) | Aislado, repetible | Requiere `nvidia-container-toolkit` para la GPU; poco amigable |

Orden sugerido: AppImage en Linux (la máquina de desarrollo) → Docker para quien lo pida → Tauri cuando el motor esté estable.

## Pendientes y riesgos

- **Navegador → red local**: Chrome reciente pide un permiso de "acceso a la red local"; Firefox y Safari tienen reglas propias. **Sin verificar**; probar en Chromium y Firefox antes de comprometerse.
- **Términos de TIDAL** para una versión pública: sin verificar. Aunque la web no aloje audio, hay que leerlos antes de lanzar.
- **Licencia**: Rubber Band es GPL; si se publica el reproductor con ella, el proyecto pasa a GPL. SoundTouch (LGPL) deja más margen.
- **Tamaño del instalador**: el entorno de separación pesa varios GB (hoy 7,4 GB en `/mnt/plexdata`); el instalador debería bajarlo aparte, con progreso, no incluirlo.
- Windows/Mac: el motor se desarrolló y se midió solo en Linux.

## Etapas

1. Motor: orígenes configurables + emparejamiento por código + token (con tests).
2. Web: detección del motor, pantalla "Instalar" y estado de conexión.
3. Descargas de modelos con progreso y verificación de hash.
4. AppImage de prueba que instale el motor y el entorno en carpetas elegidas.
5. Publicación de prueba en `*.pages.dev` con `_headers`; probar en Chromium y Firefox.
6. Decidir dominio, firma de instaladores y Tauri.

## Avance (2026-10-21): Docker
- `docker/` tiene `compose.yml`, `Dockerfile.engine`, `Dockerfile.web`, `nginx.conf`, `.env.example` y `README.md`. Probado en esta máquina: motor y web en contenedores, GPU visible (RTX 5080), proxy de la web al motor, instalación del entorno de separación desde el botón de Ajustes (7,6 GB en el volumen), separación de un clip de prueba de 15 s en GPU dentro del contenedor (6 stems, 17 s), apagado desde Ajustes sin reinicio automático.
- La imagen del motor es chica (≈ 1 GB); el entorno de separación y los modelos viven en volúmenes elegidos por el usuario.
- Sin verificar: servidor de modelos en Docker (perfil `llm`, no se bajó la imagen de Ollama de 3,4 GB), recomendaciones dentro del contenedor, conexión a TIDAL desde el contenedor, la web publicada en otro dominio.
- Incidente: el disco raíz (btrfs) se quedó sin espacio asignado (1 MiB sin asignar) y Docker no podía crear contenedores; se resolvió con `btrfs balance` por pasos. Sigue casi lleno (14 GB libres): conviene liberar espacio.
- Cambios del motor: sirve los stems él mismo (`/engine/tracks`, `/engine/files/...`) en vez del plugin de Vite; `STEMSHED_HOST` y `STEMSHED_ORIGINS`; instalación del entorno y descarga de modelos solo por clic; `/engine/services` y `/engine/shutdown`.

## Recorrido completo desde cero en Docker (2026-10-21)

Instancia nueva (carpetas vacías, otros puertos), con `docker compose up`: motor, Ollama e interfaz.
- **Hecho de verdad:** instalación del entorno de separación (7,6 GB, ≈ 4,4 GB descargados), descarga del modelo de separación (699 MB, ≈ 50 s) y de Mistral Nemo (≈ 7 GB), separación de un tema de prueba en la GPU del contenedor (6 stems), análisis (tonalidad, tempo y acorde correctos para la señal sintética), carga en el Estudio y un "Disco de hoy" generado por el modelo dentro del contenedor (8 propuestos, 4 verificados en MusicBrainz, 104 s).
- **Errores encontrados y corregidos:** el chip de descargas del menú se estiraba a toda la altura; sin TIDAL el motor se negaba a recomendar aunque el perfil estuviera completo (ahora usa el perfil y la memoria); la velocidad y los bytes de la descarga del modelo de separación no se leían (formato de tqdm); `Dockerfile.web` dependía de haber corrido `npm run build` en el equipo (ahora se construye dentro de la imagen).
- **Sin verificar:** conectar TIDAL en Docker; los bytes y la velocidad de la descarga del modelo de separación tras la corrección (el archivo ya estaba bajado); el contexto de Wikipedia (el contenedor recibió 429 de Wikipedia por exceso de consultas desde la misma IP; el disco se mostró con la línea de MusicBrainz).
- **Comportamiento a tener en cuenta:** reiniciar el motor corta una descarga en curso (la de Ollama se retoma sola desde lo ya bajado al volver a tocar Descargar).
