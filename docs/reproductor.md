# Reproductor (barra de abajo)

La barra fija de abajo es un solo componente (`components/Transport.svelte`) con dos skins. Lo que muestra y controla lo decide la fachada `lib/playback.svelte.ts`.

## Modelo

- **Modo** (`playback.mode`): `estudio` si hay un tema cargado en el DAW y no hay cola; `player` si hay una cola activa (escucha normal); `idle` si no hay nada (la barra no se muestra).
- **Cola**: lista de items `{title, artist, album, ids | sourceId | resolve, art, seconds}` más un índice. Se arma con `playback.playFrom(items, start)`: el DAW se pausa (queda cargado) y suena desde `start` hasta el final.
- **Resolución perezosa**: el id reproducible de cada tema se elige cuando le toca (`lib/resolve.ts`, el mismo mecanismo que usaba `TrackRow`: `/engine/pick` con el orden global de fuentes, o `/engine/resolve`). Si no se puede resolver o el audio falla, aviso corto (`toast`) y pasa al siguiente. Si fallan todos, corta.
- **Una sola cosa suena**: empezar la cola pausa el DAW; `player.play()` y `player.load()` cortan la escucha y vacían la cola (la fachada se entera por el gancho `preview.onstopped`).
- **Audio**: `lib/preview.svelte.ts` es ahora un único `<audio>` reutilizado para toda la cola (así el avance automático no choca con la política de autoplay). No tiene lógica de cola.
- Operaciones: reproducir, play/pausa, siguiente, anterior (pasados 3 s reinicia el tema), saltar a un índice, seek, volumen y silencio, avance automático y detener (`stop`: cierra la cola y, si hay un tema en el Estudio, vuelve su skin).

## Volumen general

- Fader de 0 a 1 con curva cuadrática (`ganancia = v²`) y botón de silencio, en las dos skins (`components/Volume.svelte`).
- Reproductor: `HTMLAudioElement.volume`. Estudio: un `GainNode` entre el worklet y la salida (`player.setMaster`); no toca el worklet, el cabezal ni el click.
- Se recuerda en `localStorage` (`stemshed.volume`, volumen y silencio), con `try/catch`: sin almacenamiento arranca en 100 %. Doble clic en el fader vuelve a 100 %.

## Skins

- **Estudio**: lo que ya existía (play, inicio, reloj, velocidad, loop, estirador) + volumen.
- **Reproductor** (`components/PlayerSkin.svelte`): portada, título, artista, "n de total", progreso con seek, anterior / play / siguiente, "Enviar al Estudio", volumen, cola y cerrar. "Enviar al Estudio" usa `lib/separation.svelte.ts`: muestra "Separando n %" y, al terminar, el botón pasa a "Abrir en el Estudio" (carga el tema y lo reproduce en el DAW). Con otra separación en curso queda deshabilitado.
- Cola: panel sobre la barra, tema actual resaltado, clic salta a ese tema, Escape cierra.
- Transición: fundido cruzado de ~0,2 s; sin movimiento con `prefers-reduced-motion`. En celular las filas se apilan y "Enviar al Estudio" queda solo con el ícono.
- `TrackRow` marca la fila que suena (fondo + ecualizador) con `playback.isCurrent(key)`; no guarda estado propio. Se quitó la mini barra de progreso de la fila (ahora está en la barra de abajo).

## Orígenes de cola

- Detalle del álbum en Música y `AlbumCard`: ▶ en una fila = desde ese tema hasta el final del álbum. "Escuchar el álbum" (encabezado del detalle) empieza por el primero.
- Lista "Temas": el tema suena solo.
- Las filas de temas ya separados siguen abriéndose en el Estudio (su botón ▶ es "Reproducir en el Estudio"); dentro de una cola suenan normal.

## Atajos

- Espacio y las teclas de medios (Media Session: título, artista, portada, play, pausa, siguiente, anterior, seek) manejan lo activo en cualquier pantalla. En escucha normal, ← y → saltan 5 s.
- Con stems activos, siguiente y anterior de las teclas de medios saltan de sección. Los atajos del DAW (`M`, `S`, `K`, `[`, `]`, `N`, `P`, números, `,` y `.`) funcionan solo en modo Estudio. Los campos de texto no se tocan.

## Verificación

Con `proto/tools/uicheck.py` (Chromium sin ventana, ahora con `--size` y espera tras cada `--eval`) y una biblioteca sintética de 3 álbumes (10 temas de 20 a 30 s), sobre estado (`audio.paused`, `currentTime`, `volume`, `GainNode.gain`, textos de la barra, índice de la cola):
- Álbum desde Música: aparece la skin Reproductor; en otra pantalla sigue y se maneja (pausa, play, siguiente, anterior, seek, volumen, silencio, doble clic).
- Avance automático al terminar un tema (seek al final) y cierre al terminar el último; "anterior" reinicia pasados 3 s y salta antes.
- Cola: abrir, resaltado del actual, salto a un índice.
- Estudio: cargar un tema pasa a la skin Estudio con volumen general (ganancia maestra 0,25 con el fader en 50 %, 0 en silencio); reproducir un tema normal pausa el DAW, y "Abrir en el Estudio" corta la escucha y suena el DAW; Espacio maneja el DAW.
- Volumen y silencio se recuerdan tras recargar. "Enviar al Estudio" muestra "Bajando / Separando n %" y termina en "Abrir en el Estudio". Un tema sin fuente avisa y salta al siguiente. Sin desborde horizontal a 390 px. 0 errores de consola.

## Qué no se verificó

- Nada de oído: el reloj de audio de Chromium sin ventana no dice cómo suena. Falta comprobar a oído que el fader del Estudio baja el nivel, que el cabezal y el click siguen alineados mientras se mueve el volumen, y la curva en volúmenes bajos.
- Teclas de medios reales y la notificación del sistema (solo se comprobó que `navigator.mediaSession` tenga los metadatos y el estado).
- Temas de TIDAL (los ids y la portada `/engine/albumart` siguen el código existente, pero no se probó con sesión).
- Sin `localStorage` (solo por lectura de código: todo va en `try/catch`).
- Firefox.

## Límites

- La cola vive en memoria: recargar la página la pierde (el volumen no).
- Cargar un tema desde la lista del Estudio corta la escucha en curso.
- Sin reproducción sin cortes entre temas (un `<audio>` que cambia de `src`), sin aleatorio ni repetir.
- Las filas de temas ya separados no tienen botón de escucha normal.
