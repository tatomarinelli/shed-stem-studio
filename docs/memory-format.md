# Memoria de gustos: formato y motivos

Estado: implementado en `engine/memory.py`, `engine/profile.py`, `engine/presets.py`, `engine/genresim.py` (2026-10-21). Pruebas: `cd engine && python3 -m unittest tests.test_memory tests.test_profile_context tests.test_presets tests.test_seed_import tests.test_genresim tests.test_albumctx tests.test_destinations` (46 pruebas, solo datos sintéticos, carpetas temporales).

## Objetivo

Recordar la historia y los gustos del usuario **sin que el contexto del modelo crezca indefinidamente**, y que un gusto que dejó de alimentarse (por ejemplo, reggae a full hace un año y nada desde entonces) **pierda peso hasta recortarse**. El modelo local tiene un contexto de 4096 tokens (medido con `/api/ps`). Si el pedido se pasa, Ollama corta el principio sin avisar y se pierde la consigna del sistema. Por eso el prompt lleva solo un resumen acotado. Medido: 570 a 680 tokens con el perfil vacío o de prueba y unos 1240 con un perfil importado completo. Más 700 de respuesta, sigue lejos del límite. El motor corta con error si `prompt_eval_count + 700 > 4096`.

## Archivos (carpeta de memoria: `~/.config/stemshed/`, o `STEMSHED_MEMORY_DIR` para pruebas; todos con permisos 600)

| Archivo | Qué guarda | Quién lo escribe | Tope |
|---|---|---|---|
| `events.jsonl` | Eventos crudos **del usuario**: reacciones (`loved`/`liked`/`disliked`/`no`/`clear` = deshacer; `heard` es el viejo "Ya lo escuché", solo lectura; el `no` puede llevar `reason`) y discos mostrados (`shown`). Cada uno lleva fecha, disco (mbid, artista, título), géneros de MusicBrainz y el **perfil de sugerencia** con que se generó (contexto, por si después conviene separar memorias por perfil). Solo se agrega al final. | motor | 60 días o 300 líneas; lo más viejo se compacta |
| `taste.json` | Lo técnico. Pesos agregados por **artista** y **género**, cada uno `{w, at}` (peso medido en la fecha `at`), más `known`: los discos ya clasificados, para no repetirlos. | motor (compactación) | pesos < 0,05 se podan; `known` ≤ 400 |
| `profile.json` | Cuestionario (perfil declarado), contexto opt-in (hora/día, ciudad → Open-Meteo) y lo importado del cliente anterior (`imported`, marcado como no verificado). | usuario (Mi perfil) y el importador de una sola vez | campos con tope de largo |
| `presets.json` | Perfiles de sugerencia por horario (intención, días y horas, prioridad, novedad, estilos a favorecer o evitar, referencias, consigna, "manda sobre"). | usuario | 8 perfiles, 6 rangos cada uno |
| `memory.md` | Resumen corto en lenguaje natural, generado con una **plantilla a partir de datos** (nunca texto del modelo). | motor | unas 1500 caracteres |
| `sources.json` | Último snapshot de favoritos de las fuentes **con su fecha de alta** (TIDAL `user_date_added`), para recalcular sin red. | motor | lo que da la fuente (100 discos, 100 artistas, 200 temas) |
| `saved.jsonl` | Historial local de lo guardado en cuentas externas (Guardar álbum o playlist). | motor | solo se agrega al final |
| `recs-last.json` | Último "Disco de hoy" y último pedido a demanda. | motor | 2 resultados |

Cachés que **no** son del usuario (en `<dataDir>/recs/`): géneros de MusicBrainz por disco (`mb-genres.json`, 90 días), contexto del disco (`albumctx.json`), vectores de géneros (`genre-emb.json`).

## Por qué los favoritos no son eventos

Los favoritos de una fuente son un **estado**: se releen y se recalculan en cada corrida con su fecha de alta, y eso es idempotente. Si se guardaran como eventos, cada corrida los duplicaría y el log crecería sin fin. `events.jsonl` guarda solo lo que el usuario **hizo** en Shed Stem Studio.

## Pesos con decaimiento

- `decay(w, desde, hasta) = w · 0,5^(días / vida media)`. La vida media se configura en `recsHalfLifeDays` (180 por defecto).
- Al sumar un evento a un balde se llevan los dos a la fecha más nueva. Por eso compactar en t1 y leer en t2 da lo mismo que no compactar (probado; la diferencia queda acotada por la poda).
- Favoritos: un disco suma 1 al artista y 0,5 a cada género (de la caché del catálogo) y a su **década**. Un artista favorito suma 1 y un tema 0,3. Todo se cuenta desde la fecha de alta.
- Reacciones (por ítem, nunca por género): "me encantó" suma 3 al artista y 1 a cada género. "Ya lo escuché" suma 0,5 y 0,25. **"No me va" excluye ese disco y no resta al artista ni al género.** La reacción nueva reemplaza a la anterior y deshacer la borra; si la anterior ya estaba compactada, se descuenta su aporte.
- Declarado en el perfil (artistas imprescindibles, estilos que ama): peso 2, **sin decaimiento** (lo edita el usuario).
- Recorte: el ejemplo del reggae está probado. Un disco favorito se recorta en unos 2 años; diez discos, en unos 3,5. En el prompt dejan de aparecer mucho antes, porque solo entra el top 12 de artistas y el top 10 de géneros.
- "Bajando" en `memory.md`: géneros cuya **parte del total** cayó a menos del 60 % de la que tenían hace una vida media.

## Qué ve el modelo (acotado)

Perfil declarado (texto corto), top 12 artistas y top 10 géneros con peso, top 5 décadas, hasta 700 caracteres de historial importado, hasta 8 playlists propias, las 8 reacciones más recientes, el momento si el usuario lo activó, el pedido (perfil de sugerencia, modo, consigna, semilla con sus géneros reales) y una lista "No proponer" de hasta 25 ítems. El resto de las exclusiones (todos los favoritos y todo lo clasificado) se aplica **en código**, sin gastar contexto.

## Qué se evaluó para clasificar gustos (medido el 2026-10-21)

| Opción | Qué se probó | Resultado | Decisión |
|---|---|---|---|
| **1. Rasgos verificables sin modelo** | Géneros de MusicBrainz (`inc=genres`), artista, década del disco (TIDAL), con pesos y decaimiento | Es la base de todo; determinística y testeable | **Adoptada** |
| **2. Embeddings locales** (`nomic-embed-text`, 274 MB, Apache-2.0, en el Ollama propio) | 40 pares de géneros que etiqueté a criterio musical (20 relacionados: soul jazz~hard bop, roots reggae~dub, deep house~organic house…; 20 no relacionados) | Cruce por palabras: AUC 0,55, detecta 2 de 20 relacionados. Embeddings: **AUC 0,96**, 90 % de acierto con umbral 0,835. Pero hay no relacionados de hasta 0,853 | **Adoptada como similitud suave** (coseno 0,83→0 … 0,93→1) para cruzar los géneros del candidato con los del usuario. Sin el modelo vuelve al cruce por palabras |
| 2b. Grupos de gustos por embeddings | Agrupamiento simple de los 40 géneros más frecuentes de la biblioteca | Umbral 0,8: un solo grupo. 0,88: 17 grupos con errores (dub aparte de reggae, hard bop aparte de jazz, funk junto a reggae) | **Descartada**: no se crea el archivo de grupos. Se puede revisar con un método mejor (por ejemplo, la jerarquía de géneros de MusicBrainz) |
| **3. Clasificador LLM anclado** (mistral-nemo, JSON con probabilidades de uso: estudiar, concentrarme, sorprenderme, libre; e instrumental) | Entrada: solo géneros de MusicBrainz y el texto ya validado de Wikipedia; 10 discos × 3 corridas | Misma respuesta en las 3 corridas: **2 de 10**. Diferencia media de probabilidades: 0,21. "Instrumental" salta de 0 a 0,7 en el mismo disco | **Descartada**. No hay suficientes reacciones reales (2) para medir acuerdo con el usuario |
| **4. Open-Jev-2B** (gionebeats/Open-Jev-2B) | Lectura de la ficha | Apache-2.0, pero es un adaptador LoRA sobre Qwen3.5-2B (la base, de varios GB, aparte). Necesita el loader propio e instalar Transformers 5.10.2 + PEFT + torch (`pip install -e '.[train]'`). No está entrenado en música | **Descartada**: pide paquetes nuevos en un entorno compartido y una descarga que pasa el presupuesto de < 1 GB |
| openjev/openjev (JEV 27B) | Investigado antes | 27B (~54 GB), licencia CC BY-NC 4.0, decisiones sobre texto, páginas y capturas; no es de música y no entra cómodo en 16 GB | **Descartada**. Idea que sí se tomó: pedir respuestas **estructuradas con un esquema JSON** (Ollama `format`) y un campo `confianza` 0-100 |

## Memoria por temas (facetas)

Además de los tres archivos de arriba, el motor deriva cada vez que cambia algo una carpeta `memory/` con **una faceta por tema**, en JSON
(para el motor y para el mapa visual) y en Markdown (para leerla). Nunca es la fuente de verdad: se regenera desde `events.jsonl`,
`taste.json` y `profile.json` (`engine/facets.py`), así que se puede borrar sin perder nada.

| Faceta | Qué tiene |
|---|---|
| `identity` | Instrumento, nivel, banda propia (`ownArtists`), cómo escucha. Lo declarado por el usuario. |
| `taste` | Artistas, géneros y décadas con su peso actual (ya con decaimiento) y de dónde sale cada uno. Sin la banda propia. |
| `avoid` | Estilos que evita (perfil), discos que descartó y los estilos que **confirmó** evitar desde una observación. |
| `habits` | Mostrados por perfil, reacciones por tipo, cuánto de lo clasificado ya conocía. |
| `learning` | Qué quiere mejorar (con el texto de lo que se le busca) e instrumento. |
| `observations` | Hipótesis con **evidencia** (ids de discos) y confianza, para confirmar o rechazar. |
| `graph` | Nodos (artistas, géneros, discos, observaciones) y aristas (`by`, `has-genre`, `subgenre-of`, `evidence`) para el mapa visual. |

`observation-states.json` guarda lo que el usuario decidió de cada observación (`confirmed` / `rejected`).

**Observaciones.** Las arma el código con reglas, nunca el modelo: un género con 3 o más reacciones y al menos 75 % del mismo signo, un
artista con 2 "Me encantó", o "ya conocías la mitad de lo reciente". Cada una cita los discos que la sostienen y dice qué efecto tiene.
Respetan la regla de **reacciones por ítem, nunca por género**: una observación negativa ("seguís descartando X") se muestra pero **no cambia
pesos ni llega sola al modelo**; solo si el usuario la confirma pasa a la lista de estilos a evitar.

**Qué entra al prompt.** Lo mismo de antes (perfil, gustos, reacciones recientes) más los estilos confirmados. El resto de las facetas es para
mostrarle al usuario qué se sabe de él y para el mapa.

**Reacciones.** `loved` (Me encantó, +3,0 al artista y +1,0 a cada género), `liked` (Me gusta, +1,5 / +0,5), `disliked` (No me gustó: excluye el
disco y resta 0,5 solo a ese artista, nada a los géneros), `no` (No me interesa: solo excluye) y el viejo `heard` (solo lectura, "Lo conocía").
El evento puede llevar `known: true` ("Ya lo conocía") y, en un `no`, un `reason` (`off_genre`, `seen`, `off_request`) que no cuenta como gusto.

## Resumen en lenguaje natural

`memory.md` sale de una plantilla con datos: nombres de favoritos, géneros, décadas, reacciones y la parte importada (con la etiqueta "no verificado acá"). No se le pide al modelo que lo reescriba: el modelo medido (Mistral Nemo) desobedeció "hablá solo de los gustos del usuario" e inventó datos. Validar texto libre es frágil. Si algún día se usa un modelo para redactarlo, tiene que pasar el mismo validador que el contexto de los discos (cada nombre propio y cada número presentes en los datos de origen) y, si falla, volver a la plantilla.
