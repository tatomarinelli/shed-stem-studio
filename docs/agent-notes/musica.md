
# Informe: Fuentes + Música (agente musica)

## Qué se hizo
- `screens/Fuentes.svelte` reescrita: solo gestión. Tarjeta Archivos locales (carpetas: listar/agregar con FolderPicker/quitar vía settings.save, estado de escaneo, "Volver a leer") y tarjeta TIDAL (conectar/desconectar con el flujo de `lib/tidal.svelte.ts`, cantidades de álbumes/temas favoritos y playlists, "Actualizar" = POST /engine/music/refresh). Sin Spotify/YouTube ni listados.
- Nueva `screens/Musica.svelte` (#/musica; menú: Fuentes, Música, Recomendaciones, Estudio, Ajustes): buscador (debounce 250 ms), filtro de fuente (Todas / Mis archivos / TIDAL con conteos), artista y género (`components/Combo.svelte`, desplegable con búsqueda y conteos), vista Álbumes (grilla con arte) / Temas (TrackRow con `ids`), etiquetas de origen cuando la fuente es "Todas", scroll infinito (limit 60, IntersectionObserver), estados cargando (esqueletos) / vacío / sin fuentes (invita a Fuentes) / error del motor / actualizando / "Completando géneros x de y", limpiar filtros.
- Detalle de álbum en panel lateral con sus temas (TrackRow con `ids`) y "Recomendar parecidos" (seed.set + #/recomendaciones). Cada tema también lo tiene.
- `TrackRow`: props nuevas `ids` y `art`. Con `ids`, ensure() usa /engine/pick; "separado" = cualquier id en player.tracks. Usos viejos intactos. El layout compacto ahora depende del ancho del contenedor (container query 640px) en vez del viewport, para que entre en el panel.
- `lib/music.svelte.ts`: estado/polling de status compartido. `lib/nav`, `SideMenu`, `App` actualizados. `lib/sample.ts` queda sin uso en Fuentes (no lo borré).

## Verificación (real)
- `svelte-check`: 0 errores, 0 avisos.
- uicheck con clics reales, 0 errores de consola en todas las corridas: grilla de álbumes (captura leída), búsqueda "arctic" -> 4 temas en vista Temas, alternar vista, filtro TIDAL, artista (4 opciones con búsqueda; "Arctic Monkeys" -> 2 álbumes), género "rock" -> 16 álbumes, abrir álbum (lista de temas), "Escuchar" (preview sonó 0:03 / 2:52 vía /engine/pick + /engine/play), "Recomendar parecidos" en el álbum -> hash #/recomendaciones, scroll infinito 60 -> 300 temas, Fuentes (captura leída: TIDAL 100 álbumes, 571 temas, 11 playlists).
- curl: /engine/pick, /engine/music, /engine/music/album respondieron como se esperaba.

## NO verificado
- Agregar/quitar carpetas y escaneo (no toqué settings.json del usuario; el flujo reutiliza lo de Ajustes pero no lo ejecuté). No hay archivos locales para probar "Mis archivos" con datos.
- Estado "sin fuentes" (TIDAL está conectado; la lógica existe pero no la vi renderizada).
- Separar y Reproducir/Enviar al estudio desde Música (no lancé separaciones). Que Recomendaciones consuma el seed depende del otro agente (solo comprobé el cambio de ruta).
- Conectar/desconectar TIDAL (no toqué la sesión). Vista móvil no revisada.

## Decisiones y notas
- "Actualizar" se desactiva mientras corre cualquier trabajo (incluido completar géneros); los géneros se van completando y el catálogo se recarga al terminar.
- Los conteos de fuente cambian según la vista (álbumes vs temas), tal como los devuelve el motor.
- /engine/pick con un id local inexistente devolvió error de TIDAL (ValueError) en vez de caer al id de TIDAL: ver pedido.

## Pedidos al motor
- /engine/pick?local=<inexistente>&tidal=<id> debería ignorar el id local inválido y devolver el de TIDAL (hoy: 500 "tidal_error ValueError").
