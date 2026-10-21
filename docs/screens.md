# Shed Stem Studio: pantallas

Estado: **diseño vigente (2026-10-21)**. Reemplaza la primera propuesta. Lenguaje visual: vidrio oscuro azul-petróleo, color por instrumento, loop magenta, Bricolage Grotesque. Texto en español rioplatense, corto, sin etiquetas de más.

## Flujo

```
Fuentes  ->  Música  ->  (buscar o elegir de lo guardado)  ->  Reproducir  /  Recomendaciones a partir de lo elegido  ->  Estudio
conectar      ver todo                                          escuchar        pedir parecidos                          DAW
```

Menú lateral vertical, en este orden: **Fuentes, Música, Recomendaciones, Estudio, Ajustes**. La **barra de abajo** (el reproductor) queda fija en todas y toma el control de lo que esté sonando: ver más abajo y `docs/reproductor.md`.

## Fuentes (solo conexiones)

Por ahora dos fuentes: **Archivos locales** y **TIDAL**. Esta pantalla solo gestiona la conexión y la configuración; no lista música (eso es Música).
- **Archivos locales:** carpetas de música (agregar, quitar), estado del escaneo, volver a leer.
- **TIDAL:** conectar / desconectar, estado, cuántos favoritos y playlists trajo, actualizar.
- El **orden de las fuentes de audio** (de dónde sale el sonido para escuchar y separar) vive en Ajustes.

## Música (nueva)

GUI unificada que se alimenta de **todas** las fuentes configuradas. La responsabilidad de mostrar la música es de esta pantalla.
- **Buscador** y **filtros**: fuente (todas / archivos / TIDAL), artista, género, con conteos.
- Vista **Álbumes** (grilla con arte) o **Temas** (lista).
- Con todas las fuentes a la vista, cada ítem indica su **origen** con una etiqueta; un mismo disco o tema presente en dos fuentes se muestra una sola vez con las dos etiquetas.
- **Detalle de álbum**: sus temas con Reproducir (si ya está separado), Escuchar (previa), Separar para estudiar y Enviar al estudio. El audio sale del orden global de fuentes, no de la fuente por la que se llegó al ítem.
- **Recomendar parecidos**: pasa lo elegido como semilla a Recomendaciones.
- **Géneros**: de las etiquetas de los archivos; para el resto, de MusicBrainz en segundo plano y con caché (son géneros que aportan usuarios de MusicBrainz: estimaciones).
- Motor: `catalog.py` (snapshot local de TIDAL + biblioteca de archivos + géneros), `GET /engine/music`.

## Recomendaciones

Foco en **un disco por período** (diario o cada N horas, configurable), no en una lista.
- **Cuestionario** (primer uso, editable): instrumento y nivel, qué mejorar, estilos que ama y que evita, artistas imprescindibles, si quiere conocer música nueva (nada / algo / mucho), cómo escucha, ritmo de estudio, y si le interesa el contexto de horario, día, ubicación y clima. El modelo lee primero las fuentes; el cuestionario complementa.
- **Consigna a demanda** con modos (estudiar, concentrarme, sorprenderme) y **semilla** opcional desde Música.
- **Clasificar** un disco (ya lo escuché, me encantó, no me va) lo saca de la pantalla y lo manda al **Historial** (colapsado, con deshacer).
- **Memoria**: ver `docs/memory-format.md`.
- Regla: el modelo solo propone candidatos; todo se verifica en MusicBrainz y el motivo mostrado nunca es texto inventado. La banda o proyecto propio del usuario nunca se recomienda.

## Estudio

Queda **exclusivamente para el DAW y la gestión de lo descargado**.
- A la izquierda, **Descargados**: versión recortada de Música (búsqueda, arte, tamaño). Un clic carga el tema en el DAW. Borrar los stems pide confirmación y dice cuánto espacio libera. La caché anterior es de solo lectura y no se puede borrar.
- A la derecha, el DAW: pistas con onda, regla con loop arrastrable, mute / solo / volumen (faders con el color de cada instrumento; doble clic vuelve a 100 %).
- **Zoom** con Ctrl + rueda (anclado al cursor, tope 400 px/s), Shift + rueda para desplazar, botones − + Ajustar y Seguir, y barra de desplazamiento con el loop y el cabezal.
- **Secciones** (A, B, C…) con inicio y fin propios: `M` marca, clic selecciona, `Supr` borra, se arrastran los bordes, doble clic o `S` repite la sección (el loop queda enlazado a ella y sigue sus cambios), `N` y `P` saltan, `1` a `9` van a una. Se guardan en el navegador.
- **Análisis** (ver `docs/analysis.md`): tonalidad, tempo y acorde actual arriba; pista de **acordes** sobre la línea de tiempo; **grilla de compases** con su número; **click** en los pulsos detectados (`K`).
- El menú lateral se achica a íconos (`\`).
- La barra de abajo con la **skin Estudio** (play, loop, velocidad, estirador y **volumen general**) aparece cuando hay un tema cargado en el DAW.
- Falta (ver `PLAN.md`): loops guardados en el motor, entrenador de velocidad, transposición, modo "oído primero".

## Barra de abajo (reproductor)

Visible en todas las pantallas mientras haya algo cargado o sonando. Tiene **dos skins** que se funden entre sí:
- **Estudio** (stems del DAW): lo de siempre + volumen general.
- **Reproductor** (escucha normal): portada, título y artista, progreso con tiempos y seek, anterior / play-pausa / siguiente, volumen con silencio, cola, "Enviar al Estudio" (separa el tema y muestra el avance; si ya está separado, "Abrir en el Estudio") y "n de total" en álbumes.
- ▶ en una fila de un álbum reproduce desde ese tema hasta el final; "Escuchar el álbum" empieza por el primero. Un tema suelto de la lista Temas suena solo.
- El **volumen** se recuerda; doble clic en el fader vuelve a 100 %. Espacio y las teclas de medios manejan lo activo en cualquier pantalla. Detalle en `docs/reproductor.md`.

## Ajustes

Modelos por módulo y cuál está en uso, specs del equipo, carpetas y ubicaciones editables, orden de las fuentes de audio. Ver `docs/settings.md`.

## Primeros pasos (asistente de primer inicio)

Pantalla completa que se abre sola la primera vez que falta algo esencial (separación, música, modelo, perfil). Ocho páginas: bienvenida, tu equipo, dónde guardar, separar en instrumentos, tu música (archivos y TIDAL), recomendaciones (modelo), tu perfil (pre-cargado con tus favoritos) y listo (con "Armar mi primer disco"). Cada paso esencial se puede dejar para más tarde; después queda un aviso con "Completar". Se repite desde Ajustes. Detalle en `docs/wizard-inicio.md`.
