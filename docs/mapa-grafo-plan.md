# Mapa de conocimiento (la "red neuronal visual"): plan

Estado: **prototipo funcionando** (2026-10-22): núcleo del grafo (`engine/graph.py`, `GET /engine/graph`) y pantalla Mapa con sigma, lista, búsqueda, filtros y panel de evidencia. Fase 3 hecha (comunidades por Louvain, puentes, huecos); layout en flor: cada artista al centro de sus discos. Es el "end game" del producto: una pantalla donde ves, explorando, **qué sabe la app de vos y por qué**. Es propio de la app: no se arma a mano y no busca compatibilidad con Obsidian.

Todo lo de abajo sale de leer el código y los datos reales (solo conteos). Lo que no pude verificar está marcado **(sin verificar)**.

## Alcance del prototipo (decidido 2026-10-22, manda sobre el resto del documento)

**Qué es:** un mapa lógico de toda la música que escuchás. Relaciona artistas, géneros y discos favoritos; al hacer clic en un disco se resaltan sus conexiones con lo parecido.

**Layout radial:**
- Distancia al centro = peso de gusto. Centro = lo que más pesa; bordes = lo que menos pesa.
- Ángulo = parecido (comunidades por géneros y artistas).
- Anillo exterior, fuera de la red = recomendados, unidos al nodo tuyo con el que más se parecen, con motivo por plantilla.

**Cercanía en el prototipo = opción A:** peso de gusto que ya existe (favorito, reacciones, recencia, playlists propias). **No hay datos de escucha**: TIDAL no los expone en lo que revisé y YouTube Music los daría vía `get_history()` (sin verificar cuánto trae). Por eso el centro es "lo que más te importa", no "lo más escuchado", y la pantalla debe decirlo.

**Dentro:** fase 1 (núcleo del grafo), fase 2 (pantalla Mapa con sigma y vista de lista accesible), fase 3 (comunidades, puentes, huecos), y de la fase 0 solo guardar los recomendados vigentes para el anillo exterior.

**Fuera por ahora:** sesiones de estudio (fase 5), agentes en vivo y SSE (fase 4), línea de tiempo (fase 6), realimentación a las recomendaciones (fase 7).

**Etapa futura, multifuente:** una capa de traducción que normalice las escuchas de cada fuente (historial de YouTube Music, Last.fm como puente para TIDAL, etc.) a una sola medida comparable, para que la cercanía pase a ser "lo más escuchado". Hay que diseñarla aparte: las escuchas de fuentes distintas no son comparables sin normalizar.

---

## 0. Resumen en diez líneas

1. El mapa es **una vista derivada**, igual que las facetas: se regenera desde los datos que ya existen y se puede borrar sin perder nada. No es una fuente de verdad nueva.
2. Lo arma un módulo nuevo del motor, `engine/graph.py`, como **función pura** (recibe datos y `now`, devuelve nodos y aristas). Se prueba con `unittest` como el resto.
3. Cada arista lleva **peso, fecha, evidencia verificable y un "por qué" armado con plantilla** (nunca texto del modelo).
4. Hoy ya hay un `memory/graph.json` (77 nodos, 64 aristas en tu máquina), pero solo cubre lo reaccionado: **no incluye tus 250 discos favoritos, 354 artistas ni 1504 temas**. El grueso del trabajo es sumarlos.
5. Faltan datos que hoy **no se guardan**: historial de pedidos y corridas (solo queda el último), sesiones de estudio (los loops viven en `localStorage` del navegador) y fechas de YouTube Music. Sin eso, "qué sabía hace 3 meses" y "mostrar el trabajo de los agentes" quedan a medias. Se agregan **ledgers** chicos (archivos de solo agregar).
6. Visualización recomendada: **graphology + sigma 4 (WebGL)**, con comunidades y puentes calculados **en el motor** (testeable).
7. Por defecto el mapa muestra **artistas, géneros y discos** (~800 nodos); los temas (1504) se expanden a pedido. Escala a decenas de miles sin cambiar de librería.
8. Interacción: un solo panel lateral de evidencia, filtros en una barra, línea de tiempo abajo. Nada de botones sueltos sobre el lienzo.
9. "Inteligente" = comunidades, puentes, huecos y caminos explicables, **todo calculado por reglas sobre datos**. El modelo puede proponer; el grafo verifica.
10. Esfuerzo honesto: **unas 5 a 7 semanas de trabajo de un agente con revisión tuya**, en 7 fases que se pueden cortar después de cualquiera (§7).

---

## 1. Qué datos existen hoy y dónde

Conteos reales de tu máquina (solo metadatos agregados): TIDAL 183 discos / 748 temas / 11 playlists; YouTube Music 73 discos / 789 temas; Spotify sin conectar; biblioteca local vacía. Unidos y deduplicados por `catalog.album_key`: **250 discos, 354 artistas, 1504 temas**. `events.jsonl`: 64 líneas (52 mostrados, 12 reacciones). Separados: 4 temas. `memory/graph.json`: 77 nodos / 64 aristas.

| Fuente | Archivo / función | Qué aporta | Huecos |
|---|---|---|---|
| Favoritos TIDAL | `catalog.py: _albums_raw, _tracks_raw`, `tidal_source`; `<dataDir>/catalog/tidal.json` | Nodos disco, tema, artista. `savedAt` por ítem (tiempo). Playlists con sus temas (`playlists[].tracks`, flag `own`) y `collections` por tema | Los discos no traen mbid ni géneros; la identidad es `album_key` = `norm(artista)\|norm(disco)` |
| Favoritos YouTube Music | `catalog._ext_state("ytmusic")`; `ytmusic.json` | Discos y temas, link al original | **Ningún ítem tiene fecha** (`addedAt` en 0 de 73 y de 789). `recs.external_sources` les inventa fecha con `UNDATED_DAYS`: sirve para pesar, **no** para una línea de tiempo honesta |
| Favoritos Spotify | `catalog.EXT_IDS`, `spotify_source.py` | Igual que YouTube Music | Sin cuenta conectada acá: **sin verificar** con datos reales |
| Archivos locales | `library.report()`, `library.find_track/find_album`; `library-index.json` | Temas con etiquetas (artista, álbum, género, año) | Índice vacío hoy: **sin verificar** con datos reales |
| Géneros por disco | `catalog._genres` → `<dataDir>/catalog/genres.json` (`enrich_genres`, `_mb_genres`: top 3) | Arista disco→género (MusicBrainz) con fecha de consulta | **Solo 130 de 250 discos tienen géneros**. El resto queda sin conectar a ningún género |
| Géneros por mbid | `recs.mb_genres(mbid)` → `recs/mb-genres.json` (111 entradas, incluye `artist:<nombre>`) | Géneros de discos recomendados y de artistas (hasta 6, con voto) | Cobertura parcial; caché de 90 días |
| Artistas | `recs/mb-artists.json` (137 entradas: mbid, nombre, géneros) | mbid de artista y géneros | Cubre 137 de 354 artistas |
| Jerarquía de géneros | `genregate.PARENTS` (34 hijos), `ALIASES` (35), `GENRES` (97) | Arista género→género `subgenre-of` | **Escrita a mano**, no sale de MusicBrainz. No verifiqué si MusicBrainz expone jerarquía de géneros por su API de servicio web: **sin verificar** |
| Similitud entre géneros | `genresim.py` (`nomic-embed-text`, `recs/genre-emb.json`) | Coseno 0,83→0 … 0,93→1 como pista suave | Medido en `docs/memory-format.md`: AUC 0,96 pero hay no relacionados hasta 0,853. Agrupar por embeddings fue **descartado** (17 grupos con errores) |
| Gustos con peso | `memory.weights()` (artistas, géneros, décadas, con decaimiento por `half_life`, 180 d) y `taste.json` | `w` por nodo y su fecha | `taste.json` guarda solo pesos agregados; no sabe de dónde vino cada uno (eso lo recalcula `facets`) |
| Reacciones | `events.jsonl` (`type: reaction`, `action`, `reason`, `known`, `preset`) y `taste.known[mbid]` (`at`, `genres`) | Atributo del disco (por ítem), con fecha | Las reacciones viejas pasan a `taste.known` (tope 400): se conserva fecha y acción, no el evento original |
| Mostrados | `events.jsonl` (`type: shown`, `kind`, `preset`) | Qué se te mostró y con qué perfil | **Se borran a los 60 días / 300 líneas** (`memory.compact`) |
| Observaciones | `facets.observations()` + `observation-states.json` | Nodo observación con `evidence` (mbids), confianza y estado `proposed/confirmed/rejected` | Solo 4 reglas; evidencia tope 8 discos |
| Grafo actual | `facets.graph()` → `memory/graph.json`; ids `a:` `g:` `d:` `o:`; aristas `by`, `has-genre`, `subgenre-of`, `evidence`; topes 25/25/40 | Base del esquema y de los ids | Solo discos con reacción; sin temas, sin fuentes, sin pedidos, sin estudio; sin fecha ni evidencia por arista |
| Perfil | `profile.py` (`ownArtists`, `loves`, `essentials`, `avoids`, `improve`, `instrument`, `level`), `presets.json` | Nodo perfil; aristas "declarado" a artistas y géneros | `ownArtists` solo se filtra en `recs` y `facets`; **el catálogo (`catalog.py`) no lo filtra**: tu propia banda aparece en `genres.json` como disco favorito. El grafo tiene que filtrarla por su cuenta |
| Resultado de una corrida | `recs-last.json`: `pick`, `alternatives`, `discarded` (`category`, `why`), `request`, `stats`, `agents`, `log` (tope `LOG_MAX`), `inputs` (`runinfo.describe`) | Pedido→disco con `trail` (`proposedBy`, `via`, `round`, `confidence`, `mbScore`, `classifier`, `review`, `score`, `diversity`) | **Solo guarda el último diario y el último a demanda.** Sin historial de pedidos ni de descartes |
| Clasificador | `classifier-log.jsonl` (`classify.log_append`, tope 500) y calibración | Veredicto por disco y género, con fecha | Rotación a 500 líneas; no guarda el pedido que lo originó |
| Agentes en vivo | `recs._state` (`agents`, `log`, `found`, `inputs`), `GET /engine/recs/status`; pantalla `Agentes.svelte` (sondeo cada 1,5 s) | Qué hace cada agente ahora | Es estado en memoria: se pierde al reiniciar |
| Estudio: separación | `stems.list_separated/tracks_index` + `manifest.json` (título, artista, `created`) | Nodo "tema trabajado" con fecha de creación | Solo 4 temas hoy. IDs de TIDAL o `L<hash>` (local) |
| Estudio: análisis | `analysis.get(id)`: `key` (tónica, modo, confianza), `tempo`, `chords` | Atributos del tema estudiado (tonalidad, modo, tempo) | Solo existe si se analizó |
| Estudio: sesiones | `player.svelte.ts` guarda secciones por tema en `localStorage` (`stemshed.sections.<id>`) | Casi nada | **No hay sesiones**: ni cuándo abriste un tema, ni cuánto, ni qué stems, ni loops, ni velocidades. El motor no se entera |
| Pedidos | `result.request` (`prompt`, `mode`, `seed`, `genres`) y `inputs` | Nodo pedido | Solo el último; los mostrados viejos se borran |
| Lo descartado | `memory.history` (`disliked`, `no`, `reason`) y `result.discarded` | Arista "descartó" con motivo | Motivo `reason` solo en `no`; `discarded` solo del último resultado |

**Conclusión.** Para armar el mapa de **gustos y biblioteca** alcanza con lo que hay (más completar géneros). Para **historia, agentes y estudio** hay que empezar a guardar cosas hoy, porque lo que no se guarda no se puede reconstruir después. Eso va primero en el plan (fase 0).

---

## 2. Esquema unificado del grafo

### 2.1 Nodos

| Tipo | Prefijo de id | Clave de identidad | Peso `w` | Atributos clave |
|---|---|---|---|---|
| Artista | `a:` | `norm(nombre)` (como hoy); `mbid` si se conoce | gusto con decaimiento (`memory.weights`) | fuentes, primera/última vez, géneros |
| Género | `g:` | `genregate.canon(nombre)` | gusto con decaimiento | padres, familia, nº de discos |
| Disco | `d:` | mbid si lo hay, si no `d:` + hash de `album_key` | 1 si es favorito; reacción como atributo | año, década, fuentes, links, `savedAt`, reacción `{action, at, reason}` |
| Tema | `t:` | hash de `artista\|título` | 0,3 si es favorito | disco, playlists, ids por fuente, `studied` |
| Sesión de estudio | `s:` | id del tema separado | veces y tiempo estudiado | tonalidad/modo, tempo, stems usados, fechas |
| Observación | `o:` | el id actual (`kind:hash`) | confianza | texto, estado, efecto |
| Perfil | `p:` | `instrument`, `level`, `improve:<x>`, `loves:<x>`, `avoids:<x>` | 2 (sin decaimiento) | lo declarado |
| Pedido | `q:` | hash de `(createdAt, kind, request)` | 1 | texto recortado, modo, perfil de sugerencia, tipo, géneros, país |

Reglas de nodos:
- **Un nodo por entidad, no por fuente.** Cada nodo lista `sources: ["tidal","ytmusic","local"]` con la fecha de cada una. La fuente es **filtro y color de borde**, no un nodo (un nodo "TIDAL" conectado a 250 discos arruinaría el dibujo).
- **No hay nodo "yo" central** por la misma razón. Lo declarado cuelga de nodos `p:` chicos.
- Los **temas no entran en la vista por defecto**: son 1504 y el 70 % no aporta información que no dé su disco. Se cuentan en el disco y se expanden al hacer doble clic o con el filtro "Temas".
- La **década** queda como atributo del disco y filtro; no es nodo (ya vive en `taste.decades`).

### 2.2 Aristas

Todas llevan: `from`, `to`, `type`, `w` (0-1, normalizado por tipo), `at` (fecha del hecho), `firstSeen` (cuándo el mapa lo supo), `evidence` (lista) y `why` (frase armada con plantilla).

| Tipo | Entre | Peso | Evidencia verificable (`kind`) |
|---|---|---|---|
| `by` | disco→artista, tema→disco | 1 | `catalog` (fuente y id) |
| `has-genre` | disco→género, artista→género | votos de MusicBrainz normalizados por posición | `musicbrainz` (mbid, fecha de la consulta) |
| `subgenre-of` | género→género | 1 | `rule` (`genregate.PARENTS`; **curada, no de MusicBrainz**) |
| `saved` (atributo, no arista) | fuente→ítem | decae con `half_life` | `catalog` + `savedAt` |
| `declared` | perfil→artista/género | 2, sin decaimiento | `profile` (campo) |
| `reacted` (atributo del disco) | usuario→disco | tabla `DELTAS` | `event` (ts, acción, motivo) |
| `evidence` | observación→disco | 1 | `event` (los ids que cita la regla) |
| `proposed` | pedido→disco | puntaje final | `run` (`trail`: quién, vía, ronda, confianza) |
| `discarded` | pedido→disco | 1 | `run` (`category`, `why`) |
| `seed` | pedido→disco | 1 | `run` (la semilla del pedido) |
| `studied` | sesión→disco/tema | tiempo estudiado | `study` (eventos de sesión) |
| `in-playlist` | tema→playlist-grupo | 1 | `catalog` (playlist propia) |
| `related` (derivada) | artista↔artista | Jaccard de géneros + co-aparición en playlists | `derived` (la fórmula y sus insumos) |

`why` es una **plantilla con datos**, por ejemplo: `Guardaste "{disco}" en {fuente} el {fecha}` o `MusicBrainz lista "{género}" entre los géneros de "{disco}" (consultado el {fecha})`. Se prueba igual que el contexto de los discos (`albumctx`): cada nombre propio y cada número del `why` tiene que estar en la evidencia de la arista.

### 2.3 Reglas del proyecto, como invariantes que se prueban

1. **Reacciones por ítem, nunca por género.** La reacción vive en el disco; un género nunca recibe peso negativo ni de un "No me interesa". `disliked` resta solo al artista de ese disco (como `memory.DELTAS`). Prueba: construir con 10 `no` de un mismo género y verificar que el peso del género no baja.
2. **Una observación negativa se muestra pero no pesa** (como en `facets`). Solo si el usuario la confirma entra a `avoid`. En el mapa se dibuja punteada y con la etiqueta "sin confirmar".
3. **`ownArtists` nunca aparece**: ni como nodo, ni como vecino, ni como semilla, ni en un `why`. Se filtra **al principio** del armado (el catálogo no lo hace hoy; verificado: solo `recs.py` y `facets.py` lo usan). Se compara con `memory.norm`. Prueba con la banda propia en TIDAL y en una playlist.
4. **El modelo propone; los datos verifican.** Ninguna arista nace de texto del modelo. Del modelo solo queda un hecho verificable: "el buscador X propuso Y en la ronda N" (`proposed`, evidencia `run`). Lo que se muestra como verdad (`has-genre`, `by`) viene de MusicBrainz o del catálogo.
5. **Motivos nunca inventados.** Todo `why` sale de plantilla + evidencia. Las aristas derivadas (`related`, puentes, huecos) se rotulan **"calculado"** y muestran la fórmula.
6. **Nada de texto personal fuera de la máquina.** El mapa es local; no se manda a ningún modelo ni servicio. El resumen para el prompt (§6) está acotado y sin datos sensibles.
7. **Escrituras:** el mapa es de **solo lectura sobre cuentas externas**. No guarda nada en TIDAL/Spotify/YouTube.

---

## 3. Cómo se construye, automático e incremental

### 3.1 Dónde vive y qué se guarda

```
<memoria>/graph/               (permisos 600, derivado: se puede borrar)
  graph.json         el grafo completo actual (nodos, aristas, comunidades, puentes, huecos)
  ledger.jsonl       primera vez que se vio cada nodo/arista (solo se agrega) -> línea de tiempo
  layout.json        posiciones fijas por id (para que el mapa no "salte")
<memoria>/runs.jsonl            historial compacto de corridas (NUEVO, ver fase 0)
<memoria>/study.jsonl           eventos de sesión de estudio (NUEVO, ver fase 0)
```

- La **fuente de verdad** sigue siendo lo que ya existe más los dos ledgers nuevos. `graph/` se regenera.
- Los ledgers nuevos son **de solo agregar y con tope por tamaño** (como `events.jsonl`), en la carpeta de memoria (`~/.config/stemshed/`), no en `/home` pesado: son KB.

### 3.2 Cuándo se recalcula

| Disparador | Qué hace | Costo |
|---|---|---|
| Arranque del motor | Carga `graph.json` si es de la misma versión del esquema y de los insumos; si no, reconstruye | segundos |
| Cambia el catálogo (`catalog._bump`: refresco de fuentes, géneros enriquecidos) | Reconstruye en segundo plano | ~ cientos de ms (ver abajo) |
| Reacción, observación confirmada, perfil o presets editados | Reconstruye (ya hoy `recs.snapshot` regenera facetas en cada cambio) | idem |
| Termina una corrida de recomendación | Agrega el pedido y sus aristas; reconstruye | idem |
| Termina una separación o un análisis | Agrega el nodo de estudio | idem |
| Evento de estudio (abrir/cerrar tema) | Agrega al ledger; el nodo se actualiza en la próxima reconstrucción | casi nada |

**Se reconstruye entero cada vez; el "incremental" está en el ledger y en no mandar todo al navegador.** Con ~1100 favoritos y ~2500 nodos es una pasada en memoria: estimo cientos de milisegundos en Python **(sin verificar: se mide en la fase 1)**. Es más simple y más seguro de probar que mantener un grafo con parches. Si en la fase 1 se mide más de 1 s, se cachea por insumo (hash del catálogo, de los eventos, del perfil).

### 3.3 Tamaño estimado

| Vista | Nodos | Aristas | JSON |
|---|---|---|---|
| Por defecto (artistas, géneros, discos, observaciones, perfil, pedidos recientes) | ~800 | ~2 500 | unos 300 a 500 KB **(estimado, sin verificar)** |
| Con temas | ~2 500 | ~6 000 | ~1 MB |
| Con el doble de biblioteca | ~5 000 | ~12 000 | ~2 MB |

### 3.4 Endpoints propuestos

| Método y ruta | Devuelve |
|---|---|
| `GET /engine/graph?types=artist,genre,album&since=ISO&until=ISO&min_w=0.05` | Grafo filtrado + `version` (hash). Responde `304` si coincide `If-None-Match` |
| `GET /engine/graph/node/<id>` | Nodo con **todas** sus aristas, evidencia y `why` (para el panel) |
| `GET /engine/graph/expand/<id>?type=track` | Vecinos pesados (temas de un disco) |
| `GET /engine/graph/timeline?bucket=month` | Conteo de nodos/aristas nuevos por mes (para la barra de tiempo) |
| `GET /engine/graph/insights` | Comunidades, puentes y huecos (§6) |
| `GET /engine/graph/events` | **SSE** con `{version, changed:[ids], agents:[…]}` |
| `POST /engine/study/event` | Evento de sesión de estudio (fase 5) |

**Formato de intercambio.** JSON columnar para lo grande: `nodes: {id[], type[], label[], w[], x[], y[], community[]…}` en vez de una lista de objetos (la mitad de bytes, parseo más rápido); aristas como pares de índices `[from, to, type, w]`. El detalle (evidencia, `why`) **no viaja** en la carga inicial: se pide por nodo. El navegador lo carga directo a `graphology`. **(Sin verificar:** el ahorro exacto; es una estimación.)

**Sondeo vs SSE.** Hoy todo el front **sondea** (`recs.svelte.ts` pide `/engine/recs/status` cada 1,5 s mientras corre). Propuesta: **SSE** para el mapa (el servidor es `ThreadingHTTPServer`, cada conexión tiene su hilo; un `text/event-stream` es una respuesta larga). Motivos: el mapa tiene que reflejar a los agentes "en vivo" sin pegarle 1,5 s al motor ni recargar 500 KB; el evento solo trae ids cambiados y el cliente pide el detalle. Con `ETag` + sondeo cada 5 s como **respaldo automático** si SSE falla. **(Sin verificar:** cómo se comporta SSE con el proxy de Vite en dev (`:5173`) y con el servidor del motor en Windows; se prueba en la fase 4.)

---

## 4. Librería de visualización

Medido por mí, en un directorio temporal (**no** toqué `proto/player/package.json`), con `esbuild --bundle --minify` y `gzip -9`:

| Opción | Versión (npm) | Licencia | Bundle min / gzip | Render | Escala | Offline | Nota |
|---|---|---|---|---|---|---|---|
| d3-force + d3-zoom + d3-selection (canvas propio) | 3.0.0 / 3.0.0 | ISC | 39 KB / **13 KB** | Canvas 2D (lo dibujás vos) | cómodo hasta ~2-3 mil nodos; después hay que construir culling, etiquetas, hit-test | Sí | Mínimo y estable (d3-force sin cambios desde 2022). Todo lo demás (resaltado, etiquetas, accesibilidad) es código propio |
| **graphology + sigma + louvain + ForceAtlas2** | 0.26.0 / **4.0.3** / 2.0.2 / 0.10.1 | MIT | 481 KB / **122 KB** | **WebGL** | decenas de miles de nodos | Sí (sin CDN) | npm la marca modificada el 2026-10-15 (dist-tag `latest` = 4.0.3, con betas 4.0.0 previas); hay `reducers` para resaltar vecinos sin recrear el grafo; layout en worker |
| Cytoscape.js | 3.34.4 | MIT | 445 KB / 143 KB | Canvas 2D | unos miles de nodos | Sí | Muy completa (compuestos, algoritmos), pero Canvas 2D y API orientada a "app de análisis" |
| force-graph (vasturiano) | 1.52.0 | MIT | 181 KB / 61 KB | Canvas 2D (d3-force por dentro) | unos miles | Sí | Rápido de armar; poca personalización de etiquetas y accesibilidad |
| Cosmograph | 2.5.1 | **CC-BY-NC-4.0** | n/m | WebGL | cientos de miles | Sí | **Descartada:** licencia no comercial; el proyecto es GPL-3.0-or-later y quiere poder publicarse |
| vis-network | 10.1.2 | Apache-2.0 / MIT | n/m (84 MB de paquete) | Canvas 2D | unos miles | Sí | Pesada y de mantenimiento lento **(sin verificar)** |

Licencia del proyecto: `proto/player/package.json` declara `GPL-3.0-or-later`. ISC y MIT son compatibles. Ninguna librería elegida necesita red en tiempo de ejecución: se instalan con `npm` y salen en el bundle de Vite, igual que `rubberband-wasm` hoy.

### Recomendación: **graphology + sigma 4**

Por qué:
- **Escala sin reescribir.** Hoy son ~800 nodos por defecto, pero con temas son ~2 500 y tu biblioteca va a crecer (Spotify sin conectar, más fuentes). Con WebGL no hay un "techo" cercano; con canvas propio sí.
- **Resaltar vecinos y filtrar por tiempo/tipo es barato** (se cambia el estado del `reducer`, no se reconstruye el grafo). Es justo la interacción que pedís.
- **Menos código propio** de lo más difícil: etiquetas sin solaparse, hit-test, zoom por cámara.
- El costo es peso (122 KB gzip contra 13 KB), irrelevante porque se sirve desde localhost y sin CDN.

Riesgos de esta elección, dichos claros:
- **Accesibilidad.** Un lienzo WebGL no es accesible por sí solo. Mitigación obligatoria: una **vista de lista** equivalente (tabla de nodos con búsqueda, navegable por teclado, con `aria-live` para cambios) y atajos de teclado en el mapa (Tab entre vecinos, Enter abre el panel). El plan lo trata como requisito de aceptación, no como extra.
- **Pruebas sin ventana.** `uicheck.py` usa Chromium `--headless=new`; WebGL ahí depende de SwiftShader/ANGLE **(sin verificar: se prueba en la fase 2 antes de seguir)**. Plan B si no anda: pruebas de la lógica con `jsdom`/datos y captura con `--use-angle=swiftshader`; plan C: probar con el grafo ya en JSON y comprobar el DOM de la vista de lista.
- **Sigma 4 es reciente** (`latest` 4.0.3, con betas 4.0.0 hasta hace poco; no verifiqué su historial de cambios ni qué rompe respecto de 3.x). Mitigación: fijar la versión exacta en `package.json`, aislar sigma detrás de un componente `GraphView` con interfaz mínima (cargar, resaltar, enfocar, evento de clic). Cambiar a canvas propio sería reescribir un solo componente.
- **Layout.** ForceAtlas2 en worker (`graphology-layout-forceatlas2`) da posiciones nuevas en cada corrida. Se guardan por id en `layout.json` y los nodos nuevos arrancan al lado de sus vecinos. **(Sin verificar:** que la estabilidad resultante sea buena con tus datos; se mira en la fase 2.)

Descartadas con motivo: **d3 + canvas** es la segunda opción si sigma resulta problemática (la mejor para "mínimo y estable"); **Cytoscape** y **force-graph** no aportan lo que sigma sí a escala; **Cosmograph** por licencia.

---

## 5. Diseño de interacción y UX

Principios (de lo que pediste y de la memoria del proyecto): **no amontonar botones**, acciones agrupadas, reacciones aparte; textos cortos en voseo.

### 5.1 Pantalla "Mapa" (entrada nueva en el menú, junto a Agentes)

```
+----------------------------------------------------------------------------------+
| Mapa                          [ Buscar un artista, género o disco...        ] [?]|
| Ver: [Todo v]  Tipos: (x)Artistas (x)Géneros (x)Discos ( )Temas ( )Pedidos       |
|      Fuente: [Todas v]   Agrupar por: [Comunidades v]       Peso mínimo: ---o--- |
+-------------------------------------------------------------+--------------------+
|                                                             | Dub (género)       |
|              .  o----o                                      | Peso 2,4 · 31 discos|
|        o--o    / \    \         [ reggae ]                  |                    |
|       /    \  o   o    o---o       /  |  \                  | Por qué está acá   |
|     o   [ jazz ]--o      \       o   o   o                 | - 31 discos de tus |
|      \     |   \          o--[ dub ]--o                     |   favoritos lo     |
|       o----o    o              \     \                      |   tienen (MB)      |
|                                  o     o                    | - Hijo de reggae   |
|   (puente: soul jazz)                                       |   (regla propia)   |
|                                                             |                    |
|  * comunidad 1: jazz y fusión (84)   * comunidad 2: reggae  | Vecinos (12)       |
|  * comunidad 3: organic house...                            | King Tubby  0,9    |
+-------------------------------------------------------------+--------------------+
| Tiempo:  ene    feb    mar    abr    may    jun    jul    ago    sep    oct       |
|          ||||   |||    ||||||  ||    |||||  |||    ||||   ||||   |||||  ||||||     |
|          [<=== 22 oct 2026 ==o]  "Esto sabía la app el 22 jul"        [Hoy]      |
+----------------------------------------------------------------------------------+
```

### 5.2 Qué hay en cada zona

- **Barra superior (una sola fila):** búsqueda con autocompletado (`Ctrl+K`), "Ver" (vistas guardadas: *Todo*, *Mis gustos*, *Lo que descarté*, *Lo que estudié*, *Trabajo de los agentes*), chips de tipo, y un menú "Más" con fuente, agrupar y peso mínimo. Nada de botones sobre el lienzo salvo zoom (+, −, encajar) en una esquina.
- **Lienzo:** zoom y paneo con rueda/arrastre y táctil. Etiquetas solo de los nodos más pesados; al acercarse aparecen más (el LOD lo resuelve sigma). Color por **tipo**; borde por **fuente**; tamaño por **peso**. Las comunidades se distinguen con halo/etiqueta de grupo, no con más colores (máximo 8 tonos; el resto gris).
- **Panel lateral derecho (siempre el mismo, un solo lugar para todo):** al hacer clic en un nodo muestra **Por qué está acá** (lista de evidencias con fecha y fuente, cada una enlazable al disco/tema/pedido real), pesos con su decaimiento ("pesa 2,4 hoy; hace 6 meses pesaba 3,1"), vecinos ordenados por peso, y debajo las acciones agrupadas ("Abrir disco", "Pedir algo parecido"). Las reacciones se muestran como dato del disco, **no se editan desde acá** (se hace donde ya se hace, en Recomendaciones).
- **Resaltar vecinos:** al pasar el mouse o enfocar un nodo, el resto baja de opacidad; clic fija la selección; `Esc` limpia.
- **Línea de tiempo (abajo, plegable):** histograma por mes de lo que el mapa fue sabiendo (`firstSeen`). Arrastrar el cabezal filtra el mapa: *"qué sabía la app el 22 de julio"*. Los pesos se muestran **como eran en esa fecha** (se recalculan con el decaimiento a esa fecha). Texto honesto: para YouTube Music dice "sin fecha de alta" (no tiene) y esos nodos no se pueden ubicar en el tiempo.
- **Trabajo de los agentes en vivo:** la vista *Trabajo de los agentes* dibuja el pedido actual como nodo que se prende; cada disco verificado aparece conectado con un pulso corto y su `trail` en el panel (quién lo propuso, qué decidió el revisor y el clasificador). Los descartados se muestran grises con el motivo. Reutiliza `_state["agents"]` y `_state["log"]`; no duplica la pantalla Agentes, la **enlaza**.
- **Vista de lista (alternativa, accesible):** el mismo contenido como tabla ordenable. Se cambia con un conmutador "Mapa | Lista". Sirve también en pantallas chicas.
- **Estados vacíos y de carga:** "Todavía no hay suficientes datos: conectá una fuente o reaccioná a discos" con enlace; barra de progreso mientras el motor reconstruye. Respeta `prefers-reduced-motion` (sin animaciones de layout).

### 5.3 Qué lo mantiene ordenado a escala

- Por defecto **no se dibuja todo**: top por peso por tipo y "más…" que lo expande. Nunca más de unos 1 500 nodos visibles sin que lo pidas.
- **Agrupar por comunidad** colapsa cada una en un súper-nodo (con el número de miembros) que se abre con doble clic.
- Los filtros se reflejan en la URL (`#/mapa?tipos=...&hasta=...`) para volver atrás con el botón del navegador, como el resto de la app (`nav.svelte.ts`).

---

## 6. "Automático e inteligente"

Todo por reglas y fórmulas sobre los datos del grafo. **Ningún modelo decide qué es verdad.**

| Qué | Cómo | Dónde | Se prueba con |
|---|---|---|---|
| **Comunidades** | Louvain (o propagación de etiquetas con orden fijo) sobre el grafo artista–género–disco, con semilla fija. Cada comunidad se nombra con sus 2-3 géneros de más peso (dato, no invento) | `graph.py` (Python, determinístico) | Grafo sintético con dos mundos claros (jazz y reggae) + comprobación de que `soul jazz` y `hard bop` caen juntos |
| **Nodos puente** | Nodos con vecinos en ≥2 comunidades y alta intermediación (aproximada, muestreo) cuyo peso no es despreciable: "`dub` conecta tu reggae con tu música electrónica" | idem | Grafo sintético donde el puente es conocido |
| **Huecos** ("te falta explorar X") | Géneros que son **padre/hijo o hermano (`PARENTS`)** de lo que ya pesa, con **0 discos favoritos** y que no descartaste por ítem. Se ordena por cercanía + peso del vecino. Si hay embeddings (`genresim`) se usa como desempate suave | idem | Casos: un hijo sin discos aparece; uno descartado explícitamente no |
| **Caminos explicables** | Para cualquier disco recomendado, el camino más corto por géneros/artistas hasta algo tuyo: "Ryo Fukui → hard bop → Grant Green (lo guardaste en marzo)". Es lo que alimenta el motivo mostrado | idem | Plantilla + verificación de que cada nombre del camino está en el grafo |
| **Observaciones nuevas** | Las 4 reglas actuales de `facets.observations` más reglas del grafo: "tus 3 comunidades son X, Y, Z" y "estudiaste en 4 tonalidades menores y ninguna mayor" (cuando existan sesiones) | `facets.py` / `graph.py` | Tests como `test_facets.py` |
| **Frescura** | Nodos cuyo peso cayó por debajo de un umbral se dibujan atenuados ("bajando"), como el resumen de `memory.summary` | idem | Fechas sintéticas |

**Límite honesto sobre géneros.** La jerarquía hoy son 34 hijos escritos a mano. Con ella, las comunidades y los huecos van a ser pobres para géneros fuera de esa tabla (por eso la fase 3 empieza midiendo qué porcentaje de tus géneros tiene padre). Opciones, sin decidir todavía: ampliar la tabla a mano; ver si MusicBrainz trae relaciones de géneros por su API **(sin verificar)**; usar embeddings solo como pista suave (ya medido: no alcanza para agrupar solo).

### Cómo realimenta a las recomendaciones

Regla: **el grafo da contexto y verificación; el modelo propone**.

1. **Para el buscador** (`recs.build_artist_prompt`): una línea extra y acotada (≤ 150 tokens, hoy el prompt anda en 570 a 1240 de 4096) con datos del grafo: tus comunidades principales, un puente y un hueco elegidos por reglas ("Explorá cerca de: hard bop. Evitá repetir: …"). El contexto de 4096 tokens es el límite duro (`CTX_LIMIT`); se mide con `prompt_eval_count` como hoy.
2. **Para el revisor** (`reviewer`): recibe el **camino explicable** del candidato como evidencia verificable (no la opinión del grafo).
3. **Para el motivo que se muestra**: el `reason` del disco puede citar el camino del grafo, armado por plantilla. Ya existe `overlap` (géneros compartidos); el camino lo generaliza.
4. **Para el puntaje**: la cercanía al grafo reemplaza o complementa a `fit` de `recs.assess` (hoy cruce por palabras + embeddings contra top 12 artistas/top 10 géneros). Se habilita **solo después de medir** que mejora `verifiedRate` y la aceptación sobre las corridas de `engine/eval/` (las mismas métricas de `docs/recs-plan-v4.md`). Si no mejora, queda solo como contexto.
5. **Respeta las reglas:** los huecos son sugerencias de exploración para un pedido, no cambian pesos; una reacción negativa nunca se convierte en un género a evitar sin que lo confirmes.

---

## 7. Fases, criterios de aceptación y pruebas

Estimaciones en **días de trabajo de un agente con revisión**; son órdenes de magnitud, no compromisos. Cada fase se puede dejar como producto usable.

| # | Fase | Entrega | Criterio de aceptación (verificable) | Días |
|---|---|---|---|---|
| 0 | **Guardar lo que hoy se pierde** | `runs.jsonl` (pedido, resumen, picks, descartes con motivo, agentes, tiempos; tope por tamaño); `study.jsonl` + `POST /engine/study/event` (abrir/cerrar tema, tiempo, stems en uso, loops, velocidad); marcar fecha de captura (`firstSeen`) para ítems sin fecha (YouTube Music) | Test: dos corridas dejan dos líneas en `runs.jsonl` (hoy `recs-last.json` guarda solo la última); el ledger respeta el tope; el endpoint rechaza ids inválidos. En la app real: abrir un tema separado deja una línea | 3 |
| 1 | **Núcleo del grafo en el motor** | `engine/graph.py` puro + `GET /engine/graph` + `ledger.jsonl`. Incluye: favoritos de todas las fuentes, géneros (completando los 120 discos sin género con el enriquecimiento existente), reacciones, observaciones, perfil | `python3 -m unittest tests.test_graph`: (a) invariantes de §2.3 (reacción por ítem, `ownArtists` filtrada, observación negativa sin peso), (b) todo `why` verificable contra su evidencia, (c) idempotencia (dos corridas = mismo grafo), (d) tiempo de armado sobre los datos reales < 1 s o se cachea. Cobertura de géneros medida y reportada | 5 |
| 2 | **Pantalla Mapa mínima** | `screens/Mapa.svelte`, `components/GraphView.svelte` (sigma), panel de evidencia, búsqueda, filtros por tipo, vista de lista | `svelte-check` sin errores; `uicheck.py` sin ventana: la pantalla abre, el recuento de nodos del DOM de la lista coincide con `/engine/graph`, clic en un nodo muestra "Por qué está acá" con ≥1 evidencia, búsqueda de un artista conocido lo enfoca. **Primero se prueba que WebGL anda en headless**; si no, se usa el plan B (§4) | 5 |
| 3 | **Inteligencia sobre el grafo** | Comunidades, puentes, huecos, caminos; jerarquía de géneros ampliada según la medición | Tests con grafos sintéticos (§6); informe real: % de géneros con padre antes y después; ningún hueco propone algo que descartaste por ítem | 5 |
| 4 | **Agentes en vivo y pedidos** | Nodos `q:`, aristas `proposed/discarded/seed`, SSE con respaldo por sondeo, vista *Trabajo de los agentes* | Test del stream: un cliente recibe `changed` al terminar una corrida simulada; `uicheck.py` con una corrida falsa (motor de prueba) muestra el pedido y los discos; apagar SSE cae a sondeo sin perder datos | 4 |
| 5 | **Estudio** | Nodos `s:` con tonalidad/modo/tempo (de `analysis.get`), aristas `studied`, vista *Lo que estudié*, regla "modos que no tocaste" | Test: dado un `study.jsonl` y un análisis sintéticos, aparece el nodo con sus atributos; con la app real, estudiar un tema lo hace aparecer | 3 |
| 6 | **Línea de tiempo** | Barra de tiempo, pesos "a la fecha" | Test: pesos a una fecha pasada coinciden con `memory.weights(…, now=T)` sobre los mismos datos; `uicheck.py` mueve el cabezal y el recuento baja | 4 |
| 7 | **Realimentación a las recomendaciones** | Línea de contexto del grafo, camino explicable como motivo, y (si mejora) puntaje | Medición antes/después con `engine/eval/` (mismas métricas de `docs/recs-plan-v4.md`): `verifiedRate` y rechazo "no es el género" no empeoran; tokens del prompt ≤ presupuesto | 5 |

Total: **~34 días de agente**, es decir unas **5 a 7 semanas** calendario con revisiones y arreglos. Cortes naturales: después de la fase 2 ya tenés un mapa útil de tu biblioteca; la 4 y la 5 son las que más se parecen a la visión "red neuronal en vivo".

### Cómo se prueba, siguiendo el estilo del proyecto
- **Motor:** `cd engine && python3 -m unittest discover -s tests`, con datos sintéticos y carpetas temporales (`STEMSHED_MEMORY_DIR`), como `test_facets.py`. Tests nuevos: `test_graph.py`, `test_graph_insights.py`, `test_runs.py`, `test_study.py`.
- **Interfaz:** `cd proto/player && npx svelte-check --tsconfig ./tsconfig.json`.
- **Clics reales sin ventana:** `proto/tools/uicheck.py` contra la pantalla `#/mapa`, con `--click`, `--text` y `--eval` (por ejemplo, contar nodos de la lista y verificar que el panel muestre la evidencia).
- **Datos reales:** tamaño y cobertura (conteos solamente) reportados por una función de diagnóstico del motor; nunca se imprime contenido personal.

### Riesgos

| Riesgo | Efecto | Mitigación |
|---|---|---|
| Cobertura de géneros baja (130 de 250 discos hoy) | Comunidades pobres, discos aislados | Fase 1 mide y completa con `enrich_genres` (1 consulta/s a MusicBrainz: unos 2 minutos para 120 discos); mostrar los "sin género" como un grupo explícito, no esconderlos |
| Jerarquía de géneros escrita a mano | Huecos y puentes poco fiables | Fase 3 mide cobertura; ampliar tabla; no prometer más de lo medido |
| Hairball (todo conectado con todo) | Mapa ilegible | Filtros por defecto, súper-nodos por comunidad, aristas derivadas ocultas hasta pedirlas |
| WebGL en Chromium sin ventana | No se puede probar la pantalla con `uicheck.py` | Probar al inicio de la fase 2; plan B de §4 |
| Sigma 4 recién salida | Cambios de API | Versión fija + componente aislado + plan de salida a canvas propio |
| Historia incompleta | La línea de tiempo no puede mostrar lo anterior a la fase 0 | Se dice en pantalla ("desde el 22 oct; antes, solo lo guardado con fecha"); favoritos de TIDAL sí tienen `savedAt` desde antes |
| Privacidad al crecer el mapa | Datos personales en un solo archivo | Permisos 600, nunca sale de la máquina, no va al repo, ni al modelo (solo el resumen acotado) |
| Peso de la reconstrucción en máquinas lentas | Cuelgues | Segundo plano con hilo propio y cancelación, como `catalog.enrich_genres` |

---

## 8. Decisiones que tenés que tomar

| # | Decisión | Mi recomendación por defecto |
|---|---|---|
| 1 | Empezar por la fase 0 (guardar historial de corridas y estudio) aunque no se vea nada nuevo todavía | **Sí.** Lo que no se guarda hoy no se puede reconstruir; cuesta 3 días y habilita fases 4 a 6 |
| 2 | Librería de visualización | **graphology + sigma 4**; plan de salida a d3 + canvas |
| 3 | Qué entra por defecto en el mapa | Artistas, géneros, discos, observaciones y perfil. **Temas y pedidos a pedido** |
| 4 | ¿Registrar tus sesiones de estudio (qué temas abrís, cuánto, con qué stems)? Es un dato nuevo y personal | **Sí**, local y con tope, con un interruptor en Ajustes para apagarlo y borrarlo |
| 5 | ¿El mapa puede cambiar lo que se te recomienda (fase 7) o solo mostrarse? | **Primero contexto y motivo explicable**; puntaje solo si la medición mejora |
| 6 | Dónde va el cálculo de comunidades | **En el motor (Python)**, para que sea testeable y estable entre sesiones |
| 7 | Jerarquía de géneros | Medirla primero (fase 3) y ampliar la tabla; no depender de un servicio externo hasta verificarlo |
| 8 | Línea de tiempo con YouTube Music sin fechas | Fechar desde la **primera vez que la app lo vio** y decirlo en pantalla |
| 9 | Tu banda (`ownArtists`) en el catálogo | Filtrarla en el grafo ya; **aparte**, evaluar filtrarla también en `catalog.py` (hoy aparece en tus favoritos de Música) |
| 10 | ¿Una pantalla propia "Mapa" o dentro de Recomendaciones/Agentes? | **Pantalla propia** en el menú, con enlaces cruzados a Agentes |

## Referencias de código usadas

`engine/facets.py: graph, observations, derive`; `engine/memory.py: weights, fold, compact, DELTAS`; `engine/genregate.py: PARENTS, canon, relation`; `engine/genresim.py`; `engine/catalog.py: _albums_raw, _tracks_raw, enrich_genres, album_key`; `engine/recs.py: snapshot, external_sources, _state, _log, _run (trail), mb_genres, own_artists, memory_facets`; `engine/runinfo.py: describe`; `engine/classify.py: log_append`; `engine/stems.py: list_separated, tracks_index`; `engine/analysis.py: get`; `engine/server.py` (rutas `/engine/recs/*`, `ThreadingHTTPServer`); `proto/player/src/lib/recs.svelte.ts`, `nav.svelte.ts`, `lib/player.svelte.ts`; `proto/tools/uicheck.py`; `docs/memory-format.md`, `docs/recs-plan-v4.md`, `docs/analysis.md`.
