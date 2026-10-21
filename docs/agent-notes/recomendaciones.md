# Informe del agente: Recomendaciones (2026-10-21)

Formato de la memoria y evaluación de clasificadores: `docs/memory-format.md`.

## Qué hice

**Motor** (`engine/`):
- `recs.py`, reescrito. Pipeline: fuentes con fecha de alta, cuestionario, memoria y perfil de sugerencia → el modelo **solo propone** (JSON con esquema: artista, disco, año, confianza) → verificación en MusicBrainz (búsqueda por frase y, si falla, por palabras; título sin artículo; sin compilados; el año del modelo no se muestra ni descarta) → géneros de MusicBrainz → puntaje → contexto del disco. Si hay pocos válidos, pide de nuevo (hasta 3 rondas, buscando 1 recomendado + 3 alternativas). Limitador global de MusicBrainz (1,1 s entre consultas, reintentos ante 503, espera a que termine el enriquecimiento del catálogo).
- `memory.py`: memoria con decaimiento y compactación. `profile.py`: cuestionario. `presets.py`: perfiles por horario. `context.py` + `weather.py`: hora, día y clima, opt-in (Open-Meteo, verificado con curl; solo sale la ciudad o las coordenadas). `seed_import.py`: importador de una sola vez de `profile-seed.json`. `albumctx.py`: contexto del disco desde Wikipedia. `genresim.py`: similitud de géneros con embeddings. `destinations.py`: guardar en cuentas externas.
- `settings.py`: `recsAuto`, `recsCadenceHours` (6, 12, 24 = una vez por día calendario, 48, 72, 168) y `recsHalfLifeDays`.
- `server.py`: `GET /engine/recs/status`; `POST /engine/recs/generate|reaction|profile|presets|schedule`; `GET /engine/destinations`; `POST /engine/save` (exige `confirm: true`). La tarea en segundo plano solo corre en el motor principal (puerto 8770). Genera cuando toca, sin prender el servidor de modelos, sin competir con una separación en curso, y espera 30 min después de un error.
- Tests: `engine/tests/test_{memory,profile_context,presets,seed_import,genresim,albumctx,destinations}.py`. Son 46 y pasan. `test_analysis.py` es de otro agente y necesita `soundfile`.

**Interfaz** (`proto/player/src/`): `screens/Recomendaciones.svelte`, `lib/recs.svelte.ts`, `lib/presetText.ts`, `lib/suggest.svelte.ts` y `components/recs/{AlbumCard,ProfileForm,TagInput,PresetsEditor,PresetWizard,SaveBox}.svelte`.
- Arriba, "Perfil: Trabajo · por horario" (o "por defecto" o "elegido por vos"), con un selector para generar ahora con otro perfil sin tocar el horario, "Editar perfiles" y "+ Nuevo" (asistente).
- "Disco de hoy": tarjeta grande con portada, ✓ MusicBrainz, géneros, **contexto del disco con su fuente** (Wikipedia o MusicBrainz), Ver temas (TrackRow), Guardar y las reacciones. Debajo, "Otras opciones". Cadencia y "automático" se cambian desde la misma pantalla.
- "Pedí algo": texto + Estudiar / Concentrarme / Sorprenderme + la semilla que llega desde Música (chip removible; se limpia al generar).
- Al reaccionar, el disco sale de la pantalla y pasa al **Historial** (colapsado, con el perfil y "Deshacer"). Aparece además un aviso de 8 s con Deshacer.
- "Mi perfil": cuestionario con chips y autocompletado (estilos y artistas de su biblioteca primero, después una lista fija; texto libre permitido). En el primer uso, una tarjeta de bienvenida que se puede omitir. Con perfil importado, el aviso "Tu perfil salió de tu historial. Corregí lo que no cuadre."
- "Qué vio el modelo" (colapsado): por qué encaja cada disco con sus gustos (el cruce con favoritos vive solo acá), descartados con su motivo, cuántos tienen contexto y el prompt.

## Pedidos que llegaron durante el trabajo (todos hechos)
1. **Sugerencias en el cuestionario**: `TagInput` (chips para tocar, autocompletado con flechas y Enter, quitar con un clic) y objetivos ampliados (teoría, modos, oído, repertorio, improvisación, ritmo, lectura, técnica). Fuentes: `GET /engine/music` (facets) más una lista fija.
2. **Perfiles por horario**: selección pura por día y hora. Gana lo que el usuario eligió explícitamente ("manda sobre"), después el rango más corto, después la prioridad y después el orden. Los rangos pueden cruzar la medianoche y, si no coincide ninguno, se usa el de por defecto. Cada evento guarda el perfil; la memoria es compartida.
3. **Asistente para crear perfiles**: 8 pasos con barra de avance, Atrás/Saltar/Siguiente y resumen con el horario en palabras. Si se pisa con otro perfil, avisa ("Se pisa con Trabajo los lunes de 9:00 a 18:00. ¿Cuál manda?"). Los existentes se editan con un formulario, que también permite duplicar y borrar con confirmación.
4. **Semilla** (`~/.config/stemshed/profile-seed.json`): se importó **una vez** al arrancar el motor real. Entraron el cuestionario (marcado como deducido y editable), los 6 perfiles, el evento inicial (un disco guardado y "me encantó": entró como `loved`, encontrado en MusicBrainz, y no se vuelve a recomendar) y la memoria natural como "importado, no verificado acá". No pisa lo que el usuario haya editado. La semilla quedó intacta (mismo SHA-256). Sus datos personales viven solo en `~/.config/stemshed/`; los tests usan datos sintéticos.
5. **Guardar en destinos**: TIDAL (agregar a favoritos o crear una playlist propia nueva) y Spotify solo diseñado (aparece como "Todavía no se puede conectar"). Siempre con confirmación que dice qué y dónde, nunca automático, nunca borra y queda en `saved.jsonl`. Los destinos son independientes entre sí.
6. **Contexto del disco en vez de "de tus favoritos"**: artículo de Wikipedia (es, después en; se confirma que la página es la del disco), resumido por el modelo **solo con ese texto** y validado: cada número (en cifras o en palabras) y cada nombre propio tiene que estar en el extracto. Si falla, se muestran las primeras oraciones del extracto tal cual. Sin artículo: una línea de MusicBrainz (año · sello · país · géneros). Wikipedia: una consulta cada 2 s y caché por disco.
7. **Historia y gustos**: se evaluaron 4 opciones (tabla en `docs/memory-format.md`). Quedaron los rasgos verificables (géneros, artista y ahora década) más la similitud por embeddings (`nomic-embed-text`, 274 MB, Apache-2.0, descargado en el Ollama propio en `/mnt/plexdata`). Se descartaron el agrupamiento, el clasificador LLM, Open-Jev-2B y JEV 27B.

## Métricas de calidad (antes / después)

| | Línea de base (pipeline viejo, 3 corridas, mistral-nemo) | Nuevo v1 (6 corridas, mistral-nemo) | Nuevo v2 (6 corridas, mistral-nemo) | Corridas posteriores (UI, perfiles, real; modelo elegido por el motor, ver abajo) |
|---|---|---|---|---|
| Existen en MusicBrainz / propuestos | 11/18 (61 %; 5 fallas de consulta HTTPError) | 24/64 (38 %, año estricto) | **38/48 (79 %)** | 6/8, 6/8, 7/8, 7/8, 6/8, 5/8 |
| Tokens del prompt | (sin medir) | ~890 | **~570** | 600 a 680; ~1240 con el perfil real |
| Familia jazz entre los mostrados | 5/11 (45 %) | 17/17 | 24/24 | — (depende del perfil: Trabajo dio jazz contemporáneo de Londres) |
| Motivo | 18/18 texto del modelo; 0 citan sus gustos; afirman datos sin verificar | determinístico | determinístico | contexto anclado en una fuente |

- Modelos: las tres primeras columnas tienen mistral-nemo fijo en el script. En las posteriores, el motor elegía "el primero instalado" de `/api/tags`, pero Ollama devuelve ese listado en un **orden que cambia entre llamadas**. Las corridas que pude comprobar (el último Disco de hoy y el último pedido aislados, y el Disco de hoy real) usaron mistral-nemo; de las anteriores no quedó registro y pudo haber sido gemma3:12b. **Lo corregí**: el motor solo elige modelos con capacidad `completion` (nunca uno de embeddings) y, con `llmModel` vacío, el instalado primero por fecha (hoy, mistral-nemo). Tiene un test.
- En v2, el año que dijo el modelo estaba mal en 16 de 38 discos que existen. Por eso ya no se usa para descartar ni se muestra.
- Contexto del disco: en 21 discos reales, 17 tienen artículo de Wikipedia (15 resumidos y validados, 2 con el extracto tal cual porque el resumen no pasó la validación) y 4 tienen solo la línea de MusicBrainz. Casos pedidos: Kind of Blue (es), Empyrean Isles (en) e Idle Moments (en), resumidos y validados. Un disco oscuro (Charlie Hunter Trio, *Bing, Bing, Bing!*) cayó en "1995 · Blue Note · XE · jazz".
- Un pedido escrito ("algo de dub y reggae instrumental") pasó de devolver jazz a devolver *Catch a Fire* (The Wailers) y *Legalize It* (Peter Tosh) arriba de todo, después de que el pedido entrara al puntaje.

## Cómo verifiqué
- Unit tests (46). `svelte-check`: 0 errores y 0 advertencias.
- `proto/tools/uicheck.py` con clics reales, contra un motor **aislado** (`STEMSHED_MEMORY_DIR` en el scratchpad, sin la tarea automática, con `STEMSHED_SAVE_DRYRUN=1`):
  - Cuestionario: chips, autocompletado y quitar.
  - Asistente de punta a punta, con detección de solape y elección de quién manda.
  - Editar, duplicar y borrar con confirmación (revisé `presets.json` y los permisos 600).
  - Generar con otro perfil elegido a mano.
  - Reaccionar, pasar al Historial y deshacer (revisé `events.jsonl`).
  - Semilla desde Música → chip → pedido → se limpia.
  - Guardar en TIDAL en modo prueba: confirmación, "Prueba, no se guardó: TIDAL" y registro en `saved.jsonl`.
  - Capturas revisadas.
- Motor real: la importación de la semilla y un "Disco de hoy" real con el perfil Trabajo. La pantalla real la revisé sin clics que escriban.
- Hashes antes y después: `settings.json`, `tidal-session.json`, `reactions.json` y `profile-seed.json` no cambiaron.

## Qué NO pude verificar
- **Escritura real en TIDAL** (agregar a favoritos o crear una playlist): no la probé, a propósito. Para probarla a mano de forma segura: en la tarjeta de un disco, tocá Guardar, marcá TIDAL, confirmá y miralo en Favoritos de TIDAL. Shed Stem Studio nunca borra; si no lo querías, sacalo a mano en TIDAL. La playlist tiene API y componente (`SaveBox kind="playlist"`), pero todavía no hay botón en ninguna pantalla. Música podría usarlo.
- **Spotify**: solo diseñado. Necesita OAuth PKCE y un Client ID registrado por el usuario; antes de implementarlo hay que verificar en developer.spotify.com los endpoints de biblioteca (en 2026 se unificaron por URI) y los permisos mínimos.
- **YouTube Music**: no se lee en vivo (no hay `ytmusicapi` y no instalé nada). Solo existe lo que trae la semilla. Para conectarlo después: un complemento aparte con `ytmusicapi` (no oficial, autenticación con cabeceras del navegador) que agregue sus "me gusta" e historial a `sources.json` con fecha, igual que TIDAL.
- La tarea automática disparándose sola en el tiempo real (probé `is_due` y la lógica de `_tick`, no la esperé un día). El decaimiento a meses vista solo está probado con fechas inyectadas.
- El validador del contexto revisa números y nombres propios, **no afirmaciones** ("considerado pionero de…"): un juicio sin nombres ni números puede pasar si el modelo lo agrega.
- Acuerdo de los clasificadores con las reacciones reales: hay solo 2 reacciones reales.
- El validador no exige la primera palabra de cada oración (va con mayúscula igual). Un nombre de una sola palabra al principio de una oración ("Coltrane grabó…") puede pasar sin verificar.

## Decisiones y problemas
- El modelo solo propone; lo que se muestra sale de MusicBrainz (existencia, año, géneros, sello) o de Wikipedia (contexto validado). El cruce con los gustos (determinístico) va solo en "Qué vio el modelo".
- La semilla sin géneros conocidos (un disco de la biblioteca sin géneros en MusicBrainz ni en la caché) solo llega al prompt como pista, y el modelo la sigue poco. Con géneros, entran al puntaje.
- Las frases largas en "evitar" ("rock con letras que distraen") van solo al prompt; cortadas en palabras sueltas filtrarían de más. En una corrida real del perfil Trabajo, el modelo igual propuso *Kind of Blue*, que choca con "evitar discos didácticos de jazz clásico".
- Sin perfil cargado se usa el texto que ya se usaba antes (un texto genérico de músico que estudia). Hoy ya está el perfil importado.
- La línea de MusicBrainz toma el país del primer lanzamiento fechado; puede sorprender (un disco figuró con país "DZ").
- **Incidentes**:
  - A las 01:54 un proceso que no era mío arrancó el motor nuevo contra la carpeta real y migró la única reacción real que existía (correcto, sin cambiar su valor).
  - Desde entonces la tarea automática solo corre en el puerto 8770.
  - Otro actor usó mi motor aislado durante las pruebas (un pedido "electronic music ambient like reggae dub" que no era mío). Gracias a eso apareció un problema real: el pedido escrito no pesaba en el puntaje.
  - A las 06:16 el coordinador reinició el motor en modo real y un pedido mío fue a ese motor. Se generó un Disco de hoy **real** con el perfil Trabajo y se anotaron 4 eventos "mostrado" en la memoria real. No hay reacciones inventadas.
  - Wikipedia me limitó una vez por exceso de consultas: bajé a 1 cada 2 s, y una falla no se cachea.
- Para el coordinador: `nomic-embed-text` ahora aparece en Ajustes, en "Modelos de recomendación" (vía `models.report()`, que no es de mi zona). Alguien podría elegirlo ahí como modelo de chat. `recs` ya lo ignora, pero conviene filtrarlo también en esa pantalla.
- Estado final: motor real corriendo en 8770 con la tarea automática activa (`recsAuto: true`, una vez por día). `settings.llmModel` sin tocar.
