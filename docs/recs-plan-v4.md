# Recomendaciones v4: artistas primero, barrera de género, memoria por temas

Estado: **implementado y medido el 2026-10-22** (lo que dice "pendiente" no está hecho). Reemplaza a `recs-plan-v3.md` en lo que toca a la generación.

## Qué problema había (medido)

- Pedir un género era texto suelto en el prompt: un disco de otro género igual se aceptaba ("un paso fuera de tu zona").
- El modelo local proponía **discos** y MusicBrainz los verificaba: 29 de 49 propuestos (59 %) no existían, cada inexistente costaba dos
  consultas de 1,1 s, y una búsqueda tardaba **120 a 228 s**.
- No se podía cancelar, ni ver el avance real, ni saber cuánto costaba cada opción.
- "Ya lo escuché" no decía si gustó; la memoria era un resumen que no entraba al prompt; solo se leía TIDAL.

## Cómo funciona ahora

1. **Pedido estructurado** (`recs.clean_request`): `genres` (hasta 3), `strict`, `type` (álbum / EP / en vivo). Si el texto dice "algo de dub" se
   detecta el género (`genregate.detect`) y se muestra como "detectado" para poder quitarlo. En la pantalla: sección **Afinar**.
2. **Artistas primero** (`recs._run`, `artistfirst.py`): el modelo propone ~10 **artistas** (los conoce mucho mejor que los títulos exactos).
   Para cada uno, MusicBrainz da sus tags con votos y su lista real de discos (con géneros). Un artista que ya no es del género se descarta
   **sin pedir sus discos**. Entre los discos reales (un álbum de estudio por artista, sin compilados ni en vivo salvo que se pida) el modelo
   elige uno **por número de una lista**: no puede inventar un título. Si esa elección falla, se toma el mejor según género y votos.
3. **Barrera de género** (`genregate.py`, funciones puras): compara lo pedido con los géneros del disco (y del artista si el disco no tiene) y
   devuelve `match` / `weak` (misma familia) / `off` / `unknown`, con el motivo armado con esos géneros. Con `strict`: `off` y `unknown` se
   descartan (`off_genre`, `genre_unknown`); `weak` solo entra si faltan y siempre rankea después de un `match`. Los embeddings **no** alcanzan
   para dar "match" (miden coseno 0,85 entre géneros lejanos).
4. **Puntaje y rastro** (`accept` en `_run`): cercanía a los gustos + género. Cada disco lleva `trail`: quién lo propuso, ronda, seguridad,
   coincidencia en MusicBrainz, tipo, y el desglose del puntaje. En la tarjeta: **Por qué este disco**. El motivo nunca es texto del modelo.
5. **Cancelar** (`recs.cancel`, `POST /engine/recs/cancel`): corta la conexión al modelo (el servidor deja de generar), se revisa entre cada
   consulta a MusicBrainz y se muestra lo ya verificado ("cortada"). Sin nada verificado no pisa el último resultado.
6. **Progreso real** (`done/total/found` en el estado): "3 de 10 · 2 de 4 encontrados", no cinco etapas fijas.
7. **Costo de cada variable** (`timing.py`, `POST /engine/recs/estimate`): mediana de las últimas búsquedas propias (modelo, MusicBrainz,
   contexto); sin historial, valores de referencia y se dice "estimado". Se ve junto a **Buscar** y en Ajustes.
8. **Contexto del disco a demanda** (ajuste `recsContext`, por defecto `demand`): la lista sale sin esperar a Wikipedia; "Contarme más del
   disco" lo pide (`GET /engine/recs/context`). En `now` se arma al generar (más lento).
9. **Más rápido contra MusicBrainz** (`mb_get`): una consulta cada 1,1 s **contada desde que empieza la anterior** (antes se sumaba la latencia),
   consultas de artistas en paralelo (3), corte al tener 6 artistas con discos, caché de 30 días de artistas y discos en
   `<dataDir>/recs/mb-artists.json`. Si MusicBrainz no responde (503) se avisa y no se pisa el último resultado.
10. **Más fuentes** (`recs.external_sources`): los favoritos de Spotify y YouTube Music que el catálogo ya leyó (solo lectura) cuentan para el
    gusto y para no repetir discos, sin contar dos veces lo guardado en dos servicios. Lo que no trae fecha pesa como de hace 90 días.
11. **Memoria por temas** (`facets.py`): ver `memory-format.md`. Identidad, gustos, evitar, hábitos, aprendizaje, observaciones con evidencia y
    `graph.json` (nodos y relaciones para el mapa visual futuro).
12. **Feedback**: Me encantó / Me gusta / No me gustó / No me interesa + casilla "Ya lo conocía". "Ya lo escuché" desapareció (los datos viejos
    se leen como "Lo conocía").

## Medición (modelo mistral-nemo 12B, RTX 5080; MusicBrainz y modelo reales; perfil sintético)

Arnés: `engine/eval/recs_genre.py` (no toca tus datos, no guarda, sin TIDAL).

| | Antes (modelo propone discos) | Artistas primero |
|---|---|---|
| Discos propuestos que no existían | 29 de 49 (59 %) | 0 (los discos salen de la lista real) |
| Segundos por búsqueda (dub / bossa nova), caché fría | 120 / 228 | 45 / 46 → **~28 s** al medir bien (el resto era el chequeo del arnés) |
| Fuera de género entre los mostrados | 0 de 8 | 0 de 8 |
| Pedidos sin género (estudiar / sorprenderme / concentrarme) | — | 4 de 4 discos reales, ~22 s |
| Modelo (llamadas al LLM) | 10 a 14 s | 3 a 6 s |

Casi todo el tiempo que queda es MusicBrainz: ~1,1 s por consulta con un límite de 1 por segundo para toda la IP. La caché de artistas hace que
repetir un pedido casi no consulte.

**Qué NO se midió**: si las recomendaciones son *mejores* que las de YouTube o TIDAL. No hay una vara honesta para eso sin un estudio con el usuario;
lo medido es adherencia al género, existencia, repetición y tiempo. La transparencia sí es verificable: cada decisión tiene su rastro.

### Los 8 géneros (una corrida cada uno, `eval-genre-8.json`)

| Género | Discos | Segundos | Rondas | Descartados |
|---|---|---|---|---|
| dub | 4 | 19,7 | 1 | — |
| bossa nova | 4 | 27,9 | 1 | — |
| post-rock | 4 | 26,2 | 1 | 1 fuera de género |
| modal jazz | 4 | 70,7 | 3 | 1 sin disco que cumpla |
| afrobeat | 4 | 27,4 | 1 | 1 inexistente, 1 sin disco |
| shoegaze | 4 | 21,0 | 1 | — |
| bebop | 4 | 18,8 | 1 | — |
| ambient | 4 | 23,8 | 1 | 2 fuera de género |

**8 de 8 con cuatro discos, 0 fuera de género** (por la barrera y por un chequeo independiente con los géneros del artista), **29,4 s** en
promedio (parte con artistas ya en caché). El caso difícil es *modal jazz*: MusicBrainz suele etiquetar esos discos solo como "jazz", así que hizo
falta más de una ronda.

**Una debilidad encontrada leyendo los discos, no por los números:** *Explosions in the Sky – The Wilderness* pasó como "ambient" aunque sus
géneros principales son post-rock y rock; "ambient" estaba más abajo en la lista. La barrera aceptaba el género pedido en cualquier posición.
Ahora solo cuenta como `match` si está entre los 3 más votados y, más abajo, como mucho `weak` ("cercano"). Está cubierto por un test con ese
orden de géneros; **no se volvió a correr la evaluación** con ese cambio.

También discutible: con "bebop" salieron discos de hard bop (Coltrane, Adderley). La tabla de familias los acepta como subgénero de bebop; si
se quiere más estricto se cambia en `genregate.PARENTS`.

## Clasificador complementario (texto) y OpenJev

**Corrección:** el primer veredicto ("no, no procesa audio") respondía otra pregunta. Lo que se pidió es un **verificador de texto complementario** del
recomendador, con alimentación mutua. Revisado en las fuentes primarias el 2026-10-22:

- **OpenJev** (ficha de Hugging Face `AlexWortega/openjev`): cross-encoder NLI (premisa + hipótesis → entailment / neutral / contradiction, con
  probabilidades) y "decisiones tipadas" (estado + opciones → probabilidad de cada una). Fine-tune de Qwen3.5 en 4B, 2B y 0,8B. Inglés. Licencia
  MIT según la ficha (otra fuente decía CC BY-NC: **confirmar en el repo antes de adoptarlo**). Corre con `transformers` o SGLang; GGUF y ONNX no están
  documentados, así que **no sale por Ollama** y necesita un entorno Python aparte.
- **Avisos de la propia ficha:** no está endurecido contra prompt injection (una línea adversarial bajó JevBench de 0,833 a 0,467), se entrenó con splits
  de test de varios benchmarks (esos números no valen) y "va al lado de chequeos deterministas, no en su lugar".
- `openjev.com` es otra cosa (SemIf, una decisión de texto en el navegador con GGUF chicos); no es el mismo modelo.

### La familia Jev: cuatro piezas distintas (revisadas el 2026-10-22)

| | Qué es | Local | Licencia | Entrada | Encaja como |
|---|---|---|---|---|---|
| **Jev** (TypeSafe) | Modelo de decisión alojado: estado + pregunta + opciones → probabilidad de cada una | No: API con clave | Cerrada | Texto | Referencia del patrón. No se adopta: manda datos a un servicio externo |
| **`jev-music-tag`** (`xhongc`, en metatext.io) | Prototipo (FastAPI + React) que usa **la API de Jev** para elegir un género entre opciones a partir de los **tags** de los archivos y escribirlo en ellos | No: necesita `JEV_API_KEY` | No declarada | Tags de texto, no audio | Demuestra exactamente nuestro patrón, pero hospedado y sin métricas |
| **OpenJev** | Cross-encoder NLI de texto, abierto (Qwen3.5 0,8B / 2B / 4B) | Sí (`transformers`) | MIT según la ficha, a confirmar | Premisa + hipótesis | Verificador de texto (la costura de `classify.py`) |
| **Toddler-Jev** (`TeenageWorks`) | Modelo de decisión **de audio**: audio + pregunta + opciones → opción elegida y probabilidades sin calibrar. Qwen2.5-Omni-3B + LoRA + cabeza de decisión | Sí (descarga base ~12 GB) | **Qwen Research License: solo investigación/evaluación**, uso comercial aparte | Audio mono 16 kHz | Verificador por **audio** donde no hay texto útil |
| **Kev** (`jaredpalmer/kev`, 9,5 k estrellas) | Modelos de decisión **abiertos tipo Jev** para texto: LoRA + cabeza sobre Qwen3.5 (0,8B / 4B / 9B / 27B). Se sirve **local** (`python -m kev.serve`, puerto propio, API compatible con TypeSafe `POST /v1/systemone`) | Sí | **Apache-2.0** (código, adaptador y base de kev-4b) | Estado de texto + preguntas `choice` / `noul` (sí-no) / `score` (escala) | **El mejor candidato** a backend de `classify.py`: HTTP local, probabilidades **calibradas** (ECE 0,029 con una temperatura) y tres tipos de pregunta |

**Kev, con los datos de su ficha (kev-4b):** exactitud 0,69 en su prueba amplia contra 0,757 de Jev; 0,838 en la de transferencia; en inglés; estados de hasta ~8 k tokens; "el orden
de las opciones puede cambiar la respuesta". No se entrenó con música ni con géneros (reclamos de consumo, código, clasificación pública). **kev-4b ocupa 14,3 GB de VRAM
y pide ~16 GB libres en CUDA: no entra junto a `mistral-nemo` en una RTX 5080 de 16 GB**; el 0,8B es el que convive (su ficha no la leí). El servidor queda abierto salvo que se
defina `KEV_API_KEY`. Cómo encaja: `choice` con el género pedido y "otro" como opciones, `noul` ("¿es dub?") o `score` para el *clima* (tranquilo, 0 a 4), siempre con
una descripción real como estado, no solo tags.

**Toddler-Jev** es lo más cercano a "clasificar un disco por cómo suena": se le pasa un clip y las opciones (el género pedido más algunos distractores) y elige.
Cautelas, todas de su ficha: está entrenado con NSynth (sonidos de instrumentos), NonSpeech7k, MELD (emociones en habla) y datos sintéticos de texto, **no con
género musical**; no publica ninguna métrica de género (su mejor dato es MMAU-mini 68,7 %, que mezcla voz, sonido y música); las probabilidades son "relativas al
conjunto de opciones, no confianza calibrada"; es inglés; y la licencia de investigación **no permite distribuir la app de escritorio** con él adentro. Para uso
personal local alcanza; si la app se reparte, es un bloqueo.

Encaja donde hoy falla la barrera: discos **sin géneros en MusicBrainz** (p. ej. *Quiet Nights of Quiet Stars* llegó solo con los géneros del artista). Necesita un clip
de 30 s del disco (de tus archivos o de TIDAL) y ~8 GB de VRAM, así que no corre a la vez que `mistral-nemo` en una GPU de 16 GB: sería en serie.

### Benchmark del clasificador sobre casos etiquetados (2026-10-22)

`engine/eval/clf_bench.py` + `clf_cases.json`: **50 casos** (26 sí, 24 no, 12 "difíciles" = géneros vecinos como bebop/hard bop o dub/dubstep), etiquetados a
mano por el asistente (**revisalos**: son conocimiento de dominio, no verdad absoluta). Evidencia = la descripción del artículo de Wikipedia. Sobre n = 50 una
diferencia de 1 a 2 casos es ruido.

| Verificador | Evidencia | Exactitud | AUROC | Brier | Difíciles | Latencia | VRAM |
|---|---|---|---|---|---|---|---|
| `mistral-nemo` con guarda | 2 oraciones | 68 % | 0,70 | 0,22 | 100 % | 0,27 s | (ya cargado) |
| `mistral-nemo` sin guarda | 5 oraciones | **96 %** | 0,97 | 0,046 | 92 % | 0,27 s | (ya cargado) |
| `mistral-nemo` sin guarda | extracto completo | 94 % | 0,95 | 0,065 | 83 % | 0,28 s | (ya cargado) |
| Kev 0,8B `choice` | extracto completo | 84 % | 0,94 | 0,115 | 67 % | 0,02 s | ~4 GB |
| Kev 0,8B `noul` | extracto completo | 80 % | 0,93 | 0,138 | 42 % | 0,01 s | ~4 GB |
| **Kev 4B `choice`** | extracto completo | **96 %** (98 % con umbral 0,6) | **0,997** | 0,040 | 92 % | 0,06 s | ~15 GB |
| Kev 4B `noul` | extracto completo | 92 % | 0,989 | 0,050 | 83 % | 0,05 s | ~15 GB |

**Lecciones:**
1. **La evidencia manda más que el modelo.** Con 2 oraciones (a menudo ni nombran el género) un juez cae a 68-78 %; con la descripción llega a 94-96 %. Por eso
   la premisa ahora lleva ~1200 caracteres del artículo (`albumctx.extract`) y el clasificador **no opina sin descripción**.
2. **La guarda "el género tiene que aparecer en la premisa" era perjudicial** (rebajaba aciertos legítimos a "neutral"): ahora es opcional y está apagada.
3. **Kev 4B y `mistral-nemo` empatan dentro del ruido** en exactitud; Kev es 5× más rápido y rankea mejor (AUROC 0,997), pero **ocupa toda la GPU de 16 GB** y no
   convive con el modelo de recomendación. El 0,8B convive pero acierta 84 %. Sin VRAM extra, el propio modelo local alcanza.
4. Las probabilidades de Kev, pese a su temperatura ajustada, tienen ECE ~0,13 en esta tarea: se tratan como sin calibrar y el umbral se ajusta con tus reacciones.
5. **Efecto de punta a punta (modal jazz / bebop / afrobeat): casi ninguno en las listas finales.** El clasificador solo opina sobre los `weak` y la barrera por
   tags resuelve el resto. Su aporte es decidir bien esos pocos casos, no cambiar el resultado en promedio. No se puede afirmar una mejora medida de la lista final.

**Costo extra:** cada descripción que no esté en caché cuesta ~2 s (Wikipedia limita a 1 consulta cada 2 s); hay un tope de 6 por búsqueda (`CLASSIFIER_FETCHES`).

### Diversidad de lo que se muestra (MMR)

`engine/rerank.py`. Pedir "bebop" mostraba tres discos casi iguales (`jazz, hard bop`). Ahora, de los discos verificados, el primero es el de mayor puntaje y cada
siguiente maximiza `0,7 · puntaje − 0,3 · parecido con lo ya elegido` (parecido = géneros sin contar el pedido + década). Un "cercano" no entra mientras queden del
género exacto. Cada disco guarda cuánto se parecía a los anteriores (`trail.diversity`) y la búsqueda informa la variedad antes y después (`stats.spread`). Es un
criterio clásico de recomendación; **no se midió con el usuario si lo prefiere**.

### Prueba real del clasificador (mistral-nemo como juez, MusicBrainz real, 2026-10-22)

Se integró primero y se probó después (con simulaciones); recién después se corrió con datos reales. Sobre *modal jazz* hubo 9 casos dudosos (`weak`):

- Subió 2 a "del género" y dejó 7 sin cambio. Uno de los dos era *Cannonball Adderley – Quiet Nights of Quiet Stars* (álbum bossa-jazz), con *modal jazz* en 5.º
  lugar del artista y **1 solo voto**: el modelo le pasó por encima a la regla de los 3 géneros más votados.
- Error mío en la lectura: primero lo di por "sin evidencia" porque recorté la lista a 4 géneros; la lista completa sí lo incluía.
- **Conclusión:** una premisa hecha solo de tags no aporta información nueva (la barrera ya los usó) y el modelo agrega ruido. Regla nueva: el clasificador solo
  opina si hay **información nueva** (la descripción de Wikipedia ya en caché; a futuro, el audio). Con solo tags se abstiene. Sigue **apagado por defecto**.
- Con la regla nueva el modo `llm` casi no se activa (la mayoría de los discos no tiene el contexto en caché). Su valor real depende de OpenJev o de un modelo de audio.

**Dónde sirve acá:** donde la barrera por tags duda. Un disco `weak` (misma familia: "reggae" cuando se pidió "dub"). Y, a futuro, el *clima*
("tranquilo para trabajar"), que hoy no tiene ninguna verificación (el pedido "concentrarme: algo tranquilo" devolvió funk).

**Cómo se integra (hecho, `engine/classify.py`):**
1. *Costura con backends.* `classify.register(nombre, fábrica)`; hoy existe `llm` (el modelo local de recomendación como juez NLI, con
   pseudo-probabilidades **no calibradas**). El adaptador de OpenJev **no está escrito**: no se puede probar sin instalarlo, y los pesos los elige y baja el
   usuario desde Ajustes.
2. *Solo opina donde hay duda.* Un `weak` sube a "del género" si p(implica) ≥ umbral o se descarta si p(contradice) ≥ umbral. Un `match` o un `off` de
   MusicBrainz **nunca** se tocan. Sin evidencia en la premisa (solo nombres) no hay veredicto: no se le deja adivinar con lo que "recuerda".
3. *Premisa segura.* Géneros del disco y del artista de MusicBrainz y, si ya está en caché, el texto de Wikipedia, limpiado (sin caracteres de control ni
   llaves, acotado a 500 caracteres) y tratado como dato.
4. *Alimentación mutua.* Cada veredicto queda en `classifier-log.jsonl`. Las reacciones vuelven: un "No me interesa → no es el género" sobre algo que el
   clasificador subió es un falso positivo medido; con ≥ 5 casos, precisión < 80 % sube el umbral y ≥ 95 % (con ≥ 10) lo baja de a poco
   (piso 0,6). Los "no es el género" sobre discos que **solo** los tags aprobaron se cuentan aparte (falsos positivos de la barrera). No se entrena
   nada: se ajusta cuánta confianza se le da. Estado en `GET /engine/recs/classifier`.
5. *Se ve.* "Por qué este disco" muestra qué dijo el clasificador y si es sin calibrar. Ajuste en Ajustes (apagado por defecto).

**Lo que falta para probar OpenJev (texto) o Toddler-Jev (audio) de verdad:** (a) confirmar la licencia en el repo, (b) elegir y bajar el checkpoint desde Ajustes a una carpeta
(el 0,8B pesa ~1,6 GB y entra junto al modelo de recomendación; el 4B ~8 GB casi llena una GPU de 16 GB con `mistral-nemo`), (c) escribir el adaptador
(`AutoModelForSequenceClassification` + la plantilla `nli_template` de la ficha), (d) comparar contra el modo `llm` con 20 casos `weak` reales: ¿cuántos
cambia, cuántos acierta según tus reacciones y cuántos segundos cuesta?

**Audio** (otra pregunta, no es lo pedido ahora): lo que existe es Essentia (discogs-effnet, ~400 estilos de Discogs), CLAP y MERT, con licencias de
varios modelos no comerciales por verificar. Solo haría falta para los `unknown` (sin géneros ni del disco ni del artista).

## Flujo multiagente: planificador → buscador → revisor → clasificador

Diseño del usuario: etapas **en serie, una a la vez** (en paralelo no entran los recursos). Cada etapa puede usar un modelo distinto y el resultado de una pasa a la siguiente.

| Etapa | Qué hace | Modelo | Dónde |
|---|---|---|---|
| 0. **Planificador** (opcional, apagado por defecto) | Lee el pedido escrito y devuelve un plan de esquema cerrado (época, ánimo, instrumental, idioma, referencias, brief). Ver sección más abajo | el mismo, u otro instalado (`recsPlanner`) | `planner.py`, `recs._plan_stage` |
| 1. **Buscador** | Propone artistas; MusicBrainz da sus discos reales y géneros; elige entre títulos reales; barrera de género y puntaje | el modelo de recomendación | `recs.artist_round`, `artistfirst.py`, `genregate.py` |
| 2. **Revisor** | Lee lo elegido contra el pedido (modo, género, gustos): por disco `si` / `dudoso` / `no` con un motivo de una lista cerrada | el mismo, u otro instalado (`recsReviewer`) | `reviewer.py` |
| 3. **Clasificador** | Verifica con la descripción de Wikipedia solo lo que la barrera dejó en duda | `llm` o Kev (`classifier`) | `classify.py` |

**Circuito de vuelta:** lo que el revisor baja (`no`) no cuenta como encontrado; la búsqueda hace otra ronda y el buscador recibe "un revisor descartó estos por no encajar:
…" para ir por otro lado. Tope: las rondas de siempre.

**Reglas del revisor (`reviewer.py`):** es una opinión del modelo basada en lo que recuerda del disco, **no un dato verificado**. Por eso solo puede **bajar** el puntaje (`dudoso` ×0,85,
`no` ×0,6), nunca descartar ni subir; el texto que se muestra sale de una tabla fija (no del modelo) y siempre dice "opinión del modelo, no verificada". Un fallo del revisor no tira la búsqueda.

### Pantalla "Agentes" (front)

Menú → **Agentes** (`screens/Agentes.svelte`). Muestra los cuatro agentes como tarjetas en orden (planificador → buscador → revisor → clasificador; el planificador casi siempre apagado) con su estado (Esperando / Trabajando / Listo / Apagado / Cortado), el modelo
que usa, lo que está haciendo ahora o un resumen, y el tiempo y las consultas. Debajo, **"Qué fueron decidiendo"**: el registro cronológico (qué artista descartó el buscador y por
qué, qué verificó, qué opinó el revisor de cada disco, qué dijo el clasificador). En vivo mientras se busca (el front ya sondea cada 1,5 s); después, la última búsqueda guardada
(`lastRun`, que sobrevive a reiniciar el motor). Cada tarjeta de planificador, revisor y clasificador tiene **Prender / Apagar** (no se cambia mientras se busca). Desde la barra de progreso de
Recomendaciones hay un enlace "Ver agentes". Las líneas salen de datos del motor; la opinión del modelo se rotula como tal.

Backend: `_state["agents"]` y `_state["log"]` (`recs._agents_reset`, `_ag`, `_log`; registro acotado a 120 líneas), y se guardan con el resultado (`result.agents`, `result.log`).

**Tarjeta "Con qué variables corre"** (arriba de los agentes; `engine/runinfo.py`, `result.inputs`): lo que se entendió del pedido y del perfil, en frases y no el texto del prompt. Qué pediste
(género y si es estricto o detectado de tu texto, tipo, modo y si lo pediste vos o vino del perfil), qué se entendió de vos (instrumento y nivel, qué querés mejorar —y si ese dato **no se usa**
en este modo—, descubrimiento, gustos), el perfil de sugerencia activo y cómo se eligió, cuánto pesan tus gustos frente a la novedad (la barra) y el género o tu texto en el puntaje, tus gustos
de hoy (con cuántos favoritos y reacciones se armaron), qué se deja afuera (discos ya tuyos, estilos que evitás, tu banda), el contexto (hora y clima si se usan) y los parámetros de cada agente.

### Pedidos con país, "lo fundamental" y pesos por tipo de pedido (2026-10-22)

**Caso real que falló:** *"Busca discos de Argentina que tengo que haber escuchado"* devolvió *Toto* (EE. UU.). Causas: (1) "Argentina" solo viajaba como texto en el prompt, **nadie verificaba el país**; (2) el perfil activo
("Trabajo: concentrarme, instrumental") y los gustos al 90 % le ganaron al pedido; (3) "tengo que haber escuchado" no se interpretaba como "lo fundamental"; (4) el revisor lo marcó "duda" pero solo baja puntaje.

- **`engine/intent.py`** (puro): `countries(texto)` extrae países y gentilicios ("rock uruguayo", "de Estados Unidos y Francia"), sin falsos positivos con géneros ("americana"), verbos ("usa") ni idiomas ("en francés"); `canon(texto)` detecta
  "imprescindibles / clásicos / tengo que haber escuchado". `judge_origin` decide con el `country` y el `area` de **MusicBrainz** (match / off / unknown); sin dato no se adivina, y con `strict` se descarta con el motivo real
  ("No es de Argentina: MusicBrainz lo ubica en Venezuela"). La caché de artistas guarda `country`/`area`; lo guardado antes se vuelve a pedir solo si hace falta.
- **Pedido explícito > perfil activo:** con texto, género, país o disco de partida, el modo, "instrumental" y "favorece" del perfil no se aplican (sí valen lo que evita y su descubrimiento).
- **`engine/planner.py`** (puro): el **tipo de pedido** fija los pesos, en una tabla visible: *parecido a otro disco* (gustos 25 %, parecido 75 %, sin instrumento ni objetivos ni gustos en el prompt), *lo fundamental* (gustos 30 %),
  *de un país* y *de un género* (50 %), *para un modo*, *pedido escrito* y *para vos* (como siempre). El instrumento y los objetivos de estudio solo se usan en "para vos", en "pedido escrito" y en modo estudiar.
  La similitud con el disco de partida mide géneros emparentados (hard bop ~ bebop cuenta parcial) y cercanía de década. La pantalla Agentes muestra el tipo y qué no se usa.
- **Medido con modelo y MusicBrainz reales (gemma3:12b):** el pedido de Argentina devolvió 4 de 4 argentinos y clásicos (Mercedes Sosa, Charly García, Fito Páez, Atahualpa Yupanqui) y descartó con motivo a Daniel Viglietti (Uruguay) y Ricardo
  Montaner (Venezuela). "Parecido a Kind of Blue" devolvió *Saxophone Colossus*, *Somethin' Else* y *Chet*, con un prompt sin instrumento, objetivos ni gustos.
- **Agente planificador con modelo:** hecho y medido, apagado por defecto (sección "Agente planificador" más abajo).

**Portadas (2026-10-22):** al volver a Recomendaciones muchas no cargaban. En Chromium limpio no se reproduce (8 de 8, también al salir y volver) y el motor responde en < 0,05 s; sospecha: conexiones del navegador ocupadas (el reproductor usa varias).
Se agregó (1) precarga en memoria de las portadas apenas llegan los resultados (`lib/coverCache.ts`), (2) sin `loading="lazy"` y con prioridad en las de esta pantalla, y (3) diagnóstico local: cuando una portada falla o tarda más de 6 s,
el navegador avisa y queda una línea en `<datos>/diag/covers.log` (cuántos pedidos había en curso, si había red, etc.).

**Incidente (2026-10-22): los tests contaminaron la caché real.** Tests de `recs` escribían en la carpeta de datos REAL: `mb-artists.json` quedó con artistas falsos (`King Tubby`, id `a1`) y las
búsquedas de esos artistas devolvían discos con identificadores falsos (portadas y enlaces rotos). Además el motor en ejecución tenía esas entradas en memoria y las reescribió. Arreglo: (1) tests aislados
a nivel de **módulo** (`setUpModule` parchea `settings.load` y `settings.effective` con una carpeta temporal) en `test_recs`, `test_facets` y `test_profile_context`; (2) la caché de artistas **ignora
entradas con ids que no son UUID de MusicBrainz** (se cura sola); (3) los ids simulados de los tests tienen forma de UUID. Se limpió el archivo real (respaldos `*.antes-de-limpiar`) y se reinició el motor.

**Regresión de portadas (2026-10-22):** al pasar el contexto a "a demanda" la precarga de portadas (`covers.prefetch`) quedó dentro del bloque del contexto y nunca corría con el valor por defecto: las
portadas se pedían recién al abrir la pantalla (TIDAL + Cover Art Archive, hasta ~15 s). Ahora corre siempre que no se cancele (hay test).

**Regla aprendida viéndolo funcionar:** el revisor **solo actúa si hay algo explícito que revisar** (un modo o un texto que pidió el usuario, o el disco de hoy sin género). En un pedido
solo de género se **omite** y lo dice. Sin esto, `gemma3:4b` dudó de 10 de 13 y luego 12 de 16 discos: juzgaba de nuevo, con lo que recuerda, un género que MusicBrainz ya había
verificado con datos, y con el modo del perfil (que el usuario no eligió en ese pedido) forzaba rondas extra (102 s). Y cuando hay género pedido, el revisor no lo juzga
(se le dice, y se ignora el motivo `no_pedido`).

**Bug de arranque que apareció solo con la corrida real:** un alias a nivel de módulo entre `recs` y `catalog` creaba un import circular y **el servidor no levantaba**; los tests no lo
veían porque importan en otro orden. Ahora hay `tests/test_startup.py` (importa en intérprete limpio, en ambos órdenes; comprobado que falla con el bug).

### Medición del revisor (`engine/eval/review_bench.py`, 32 discos etiquetados para *concentrarme*, extremos claros)

| Modelo | VRAM | sin géneros: exactitud / baja a los malos / deja pasar a los buenos | con géneros | s por tanda de 8 |
|---|---|---|---|---|
| gemma3:4b | ~4,7 GB | 97 % / **100 %** / 94 % | 94 % / 100 % / 88 % | 2-3 |
| qwen3:8b (sin razonamiento) | ~10 GB | 97 % / **100 %** / 94 % | 97 % / 100 % / 94 % | 2-4 |
| gemma3:12b | ~13 GB | 97 % / **100 %** / 94 % | 88 % / 100 % / 75 % | 6 |

Los 16 discos claramente no aptos (thrash metal, punk, rap metal, etc.) los bajaron los tres modelos; los errores son siempre de más cautela (dudar de uno bueno), que solo cuesta
un 15 % de puntaje. **Son extremos claros a propósito**: dice que el revisor tiene sentido común, no cómo se porta en casos ambiguos. n = 32: 1 caso = 3 puntos. Un modelo de 4 GB rinde igual que uno de 13 GB.

**De punta a punta (gemma3:12b, perfil sintético, pedidos de ánimo):** con el revisor, *"concentrarme: algo tranquilo para trabajar"* dejó de devolver funk (*The Meters*) y reggae-dub (*Lee Perry*) y trajo
*Idle Moments* (calmo) y 2 más en duda; *estudiar* quedó con 4 de 4 aprobados. **Costo:** 56 s contra 21 s (una ronda más). **No hay una medición independiente de "mejor"**: el mismo tipo de modelo
es quien revisa y la vara de comparación son mis etiquetas de 32 discos.

## Agente planificador (etapa 0, 2026-10-22)

Idea del usuario: un modelo local lee el pedido libre antes que nadie y devuelve un **plan estructurado**; las reglas de `intent.py` siguen decidiendo lo verificable. Se prende en Agentes (Prender/Apagar) o con el ajuste `recsPlanner` (`off` | `same` | nombre de un modelo; **por defecto `off`**). Etapas **en serie**, nunca en paralelo.

**Qué devuelve (esquema JSON cerrado, `planner.SCHEMA`):** `desde`/`hasta` (años 1900-2030), `animo` (tranquilo, melancólico, alegre, enérgico, oscuro, romántico o ninguno), `instrumental` (sí / no / indiferente), `idioma`, `referencias` (artistas o discos nombrados), `paises` (ISO de `intent.COUNTRIES`), `generos`, `fundamental` y `brief` (≤ 280 caracteres).
Entra al plan solo lo que pasa la validación (`planner.parse`): años numéricos y no al revés, ánimo/idioma de la lista, países ISO de la lista, géneros del vocabulario de `genregate`, **referencias que realmente aparecen en el texto del pedido**, épocas de más de 35 años descartadas (no es un filtro, es "cualquier época") y el brief limpio y acotado. Lo descartado queda en el registro ("Descartó: …").

**Reglas de diseño (con test):**
- **Las reglas ganan en lo verificable.** País, género, "lo fundamental" y semilla siguen saliendo de las reglas. El modelo solo suma lo que ellas no ven: hoy **solo la época** (`planner.MODEL_ADDS = ("era",)`). Una época escrita en el pedido ("de los 70", "entre 1965 y 1975", "los ochentas"; `planner.rule_era`, regex) le gana a la del modelo.
- **La época se comprueba con datos.** Es filtro duro (con `strict`, o sea salvo que el pedido sea flexible) contra el año real del disco en MusicBrainz: en `artist_round.keep` se filtran los discos y, si ninguno cumple, el artista se descarta con el dato ("Ningún disco suyo es de 1975-1979: MusicBrainz los ubica en 1974-1997", categoría **`off_era`**; sin año: **`era_unknown`**). El disco que pasa lleva "Es de 1976 según MusicBrainz, dentro de 1975-1979." en el motivo y `trail.era`. Pedido flexible: la época solo orienta al prompt.
- **El brief es opinión del modelo.** Entra al prompt del buscador y de la elección rotulado ("ORIENTACIÓN DEL PLANIFICADOR (opinión de un modelo, no un dato)"), nunca va a un motivo, al rastro ni al registro; la pantalla lo muestra con la etiqueta "opinión del modelo". Ánimo, instrumental, idioma y referencias también solo orientan (no se pueden verificar).
- **Una falla no rompe la búsqueda:** un solo intento (`tries=1`), cualquier error → "No pude armar el plan: sigo con las reglas". **Cancelable** (usa `_chat_json`/`_open` como el resto). Sin texto escrito (disco de hoy, solo género) se omite.
- **Perfil mínimo:** al modelo solo se le dice instrumento y nivel. Sus gustos y su banda no entran (en la primera versión los gustos "jazz, rock" se copiaban a los géneros de 20 pedidos que no los nombraban).

**Pantalla Agentes:** 4 tarjetas en orden (Planificador → Buscador → Revisor → Clasificador) con Prender/Apagar, líneas en el registro y, en "Con qué variables corre", el bloque "Cómo lo entendió el planificador (opinión del modelo)": época y de dónde salió (la escribiste vos / la entendió el modelo), ánimo, instrumental, idioma, referencias y brief.

### Medición (`engine/eval/plan_bench.py`, 30 pedidos de `plan_cases.json`)

Pedidos escritos como los de un guitarrista argentino, etiquetados a mano (época, ánimo —varias respuestas válidas—, instrumental, idioma, país, "lo fundamental", géneros, referencias; `null` = el pedido no lo dice). Se compara **REGLAS** (`intent`, `genregate.detect` y las dos regex nuevas de época e instrumental) contra el **MODELO** (ya validado) y **REGLAS+MODELO** (el modelo llena donde las reglas no vieron). Ollama aparte, `temperature 0.1`, un pedido por vez. Celdas: aciertos / inventos o errores / faltantes (TP/FP/FN) sobre 30 pedidos.

| Campo (n esperados) | Reglas | gemma3:4b | gemma3:12b | qwen3:8b |
|---|---|---|---|---|
| Época (15) | 14 / 0 / 1 | 15 / 0 / 0 | 15 / 0 / 0 | 15 / 0 / 0 |
| Ánimo (10) | 0 / 0 / 10 | 8 / **19** / 2 | 9 / 0 / 1 | 8 / 0 / 2 |
| Instrumental (4) | 3 / 0 / 1 | 4 / **19** / 0 | 4 / 2 / 0 | 4 / 0 / 0 |
| Idioma (2) | 0 / 0 / 2 | 2 / 1 / 0 | 2 / 0 / 0 | 2 / 0 / 0 |
| País (11) | 9 / 0 / 2 | 11 / **1** / 0 | 10 / 0 / 1 | 7 / 0 / 4 |
| "Lo fundamental" (5) | 5 / 0 / 0 | 5 / **2** / 0 | 5 / 0 / 0 | 5 / 0 / 0 |
| Géneros (18) | 18 / 1 / 0 | 15 / 1 / 3 | 15 / 2 / 3 | 11 / 1 / 7 |
| Referencias (5) | 0 / 0 / 5 | 5 / 0 / 0 | 5 / 0 / 0 | 5 / 0 / 0 |
| Segundos por pedido (máx) | 0 | 0,62 (0,8) | 1,38 (9,0) | 0,85 (7,9) |
| Descartado por la validación (30 pedidos) | – | 4 | 2 | 1 |

(El máximo de 8-9 s del 12b y de qwen es la carga del modelo en la primera consulta; con el mismo modelo que el buscador `same` ya está cargado. En una búsqueda real el planificador tardó 1,2-1,5 s con el modelo ya cargado y 8,9 s en frío.)

**Con la primera versión del prompt** (que además le pasaba los gustos del perfil), los falsos positivos eran mucho peores: gemma3:4b 26 de instrumental, 20 de "fundamental", 20 de géneros y 17 de ánimo; gemma3:12b 28 de géneros y 8 de instrumental; qwen3:8b 18 de géneros y 4 de instrumental. Lo arreglaron tres cambios generales (sacar los gustos del perfil, valores neutros primero en cada enum y un ejemplo con todo neutro), **no** retoques por pedido; aun así el prompt se iteró sobre estos mismos 30 pedidos.

**Lectura honesta:**
- **Lo que las reglas ya ven, el modelo no lo mejora:** de 15 pedidos con época, las reglas (regex) aciertan 14 y los tres modelos 15; la diferencia es **un** pedido (*"de los últimos años"*, que las reglas no entienden y que se acepta con ±5 años). País: las reglas aciertan 9 de 11; el modelo grande suma 2 más ("rock nacional", "francesas": plurales y giros que `intent.COUNTRIES` no tiene). Para "lo fundamental" y género las reglas ya alcanzan (5/5 y 18/18).
- **Lo que solo ve el modelo** (ánimo, idioma, referencias, instrumental fuera de las palabras exactas) lo ven bien **gemma3:12b y qwen3:8b** (0 inventos en ánimo; instrumental 4/4 y 0 inventos en qwen). **gemma3:4b inventa mucho** (19 ánimos y 19 "instrumental" que nadie pidió, 1 país —Jamaica para un pedido de reggae— y 2 "fundamental"): con él el plan es ruido. Sus errores no rompen nada porque ánimo e instrumental solo orientan, pero es la razón de que **el país y "lo fundamental" del modelo no se apliquen** (`MODEL_ADDS`); un país inventado sería un filtro duro y vacío.
- **qwen3:8b es muy cauteloso:** 0 inventos pero deja pasar casi todos los países y géneros (7/11 y 11/18); los géneros del modelo no se usan para filtrar de todos modos (solo orientan).
- Algunos "inventos" de instrumental de gemma3:12b son pedidos de "que cante en inglés / portugués" donde dice "con voz": razonable, pero mi etiqueta decía `null`.

**Sesgos de la medición (no maquillar):** (1) etiquetas y regex de época/instrumental los escribió la misma persona en la misma sesión, mirando los casos: favorece a las reglas; (2) el prompt se iteró sobre los mismos 30 pedidos y no hay un grupo aparte: favorece al modelo; (3) n = 30: un pedido son 3 puntos; (4) mide **entender el pedido**, no si los discos que salen son mejores.

**Extremo a extremo (gemma3:12b, MusicBrainz real, 3 pedidos, perfil sintético; no es una evaluación):**
- *"algo tranquilo para tocar de noche, de los 70"*: con el planificador, 4 de 4 discos de 1970-1979 verificados con el año de MusicBrainz (Hejira 1976, Moondance 1970, Sugar Loaf Express 1977, New Morning 1970), +8,9 s en frío (planificador, incluye cargar el modelo). **Sin él también salieron 4 de 70-79** (1971-1978): el buscador ya respetaba la década; lo que cambia es que ahora está **comprobado y descartaría** a uno que no lo fuera (el 4 de 4 fue por azar del modelo).
- *"música tranquila sin voz para trabajar, parecida a Bill Evans"*: con planificador salió Metheny, Mehldau, Glasper (*In My Element*) y Lage; sin él, Bley, **Glasper Experiment (*Black Radio 2*, un disco con voces)**, Mehldau y Jarrett. Un caso, anecdótico: no alcanza para decir que mejora.
- *"jazz instrumental de los 60 como Wes Montgomery"*: 4 de 4 de 1964-1969, todos con el año verificado.

**Decisión:** **no se prende por defecto** (`recsPlanner` queda en `off`). Con datos: en lo verificable las reglas ya igualan al modelo (la época en regex acierta 14 de 15) y en lo que solo ve el modelo (ánimo, idioma, referencias) la mejora de la búsqueda **no está medida**, solo la comprensión; cuesta 1-9 s más por búsqueda y gemma3:4b, el modelo que sirve para GPUs chicas, **empeora** el plan con ruido. Si se lo prende, conviene con gemma3:12b o qwen3:8b. Lo que sí vale con certeza es la **época como filtro verificable con el año de MusicBrainz**, y eso sale de la regex, sin modelo: **hecho por decisión del usuario (2026-10-22): `planner.rule_era` se aplica SIEMPRE** (`recs.clean_request`), con o sin planificador: "de los 70" ya filtra con el año real de MusicBrainz (categorías `off_era` / `era_unknown`, `strict` por defecto; con `strict: false` solo orienta el prompt) y la pantalla Agentes lo muestra en "Qué pediste" ("la escribiste vos"). Un pedido que solo trae época es el tipo "De una época" (`planner.KINDS['epoca']`, sin penalizar por coincidencia de texto). El modelo queda solo para el brief y lo difuso. Riesgo conocido: una regex puede interpretar mal una frase rara ("los 70 minutos"): por eso la época mostrada dice de dónde salió y se puede pedir flexible.

## Modelos de recomendación por tamaño (artistas primero, 8 géneros, barrera estricta, 2026-10-22)

Corridas de `recs_genre.py` (una por género, perfil sintético; tiempos con la caché de MusicBrainz en distinto grado de calor: **comparables solo en orden de magnitud**).

| Modelo | VRAM | Corridas con 4 discos | Fuera de género mostrados | Propuestas descartadas (inexistentes / otro género) | s por búsqueda |
|---|---|---|---|---|---|
| mistral-nemo 12B | ~8 GB | 8 de 8 | 0 | 1 / 3 | 29 |
| gemma3 12B | ~13 GB | 8 de 8 | 0 | 6 / 5 | 22 |
| qwen3 8B (sin razonamiento) | ~10 GB | 7 de 8 | 0 | 18 / 27 | 20 |
| gemma3 4B | ~4,7 GB | 7 de 8 | 0 | 28 / 10 | 31 |

**Lectura:** el pipeline es **robusto al modelo**: ninguno dejó pasar un disco de otro género, porque la barrera y MusicBrainz verifican. Lo que cambia es el desperdicio: mistral-nemo propone mejor (casi
nada que descartar) y los de 4 a 8B inventan o se desvían mucho más, aunque igual llegan a 4 discos con más rondas. Para una GPU chica (8 GB) `gemma3:4b` ya alcanza.
`qwen3` hizo falta correrlo con `think: false` (si no, devolvía contenido vacío y fallaba en las 8 corridas): ya es el comportamiento por defecto de `models.chat`.

## Modelos y GPUs

El arnés compara varios modelos instalados (`--model a,b,c`) y reporta adherencia, tiempo y VRAM. Hoy solo está instalado `mistral-nemo`
(7,1 GB, medido arriba); **no se bajó ninguno otro** (regla del proyecto: los modelos se eligen en Ajustes). Medido arriba para 4 modelos; falta 27B y modelos más chicos de otras familias. Con artistas primero el modelo hace menos trabajo (una lista corta de artistas y una
elección entre números), así que un modelo más chico debería alcanzar: eso es lo primero que conviene probar.

## Pendiente (no hecho)

- Adaptador de OpenJev y su comparación contra el modo `llm` (arriba); el clasificador **todavía no se midió con datos reales**: hoy está probado con simulaciones.
- Clasificador de *clima* ("tranquilo", "instrumental") para los modos Concentrarme/Estudiar.
- **Disco de hoy y pedidos sin género** usan ahora artistas primero, pero **su variedad no se midió** (el diagnóstico de v3 era que salía casi solo
  jazz). Lo medido sin género fueron 3 pedidos sueltos con perfil sintético: discos reales, pero no variedad.
- Fuentes de gusto: ListenBrainz, Last.fm, Discogs (hacen falta cuentas o claves para probarlas). Spotify y YouTube Music se leen vía el
  catálogo y **no se probaron con cuentas reales**.
- Mapa visual (grafo): los datos ya salen en `memory/graph.json`; falta la pantalla.
- Observaciones generadas por el modelo en segundo plano (hoy solo reglas del código).
- Tabla de modelos por GPU y clasificador de audio opcional (arriba).
- Un `test_analysis` falla en este entorno por falta del módulo `soundfile` (anterior a estos cambios).

## Repaso de interfaz (hallazgos pendientes)

Hecho en esta sesión: desborde en celular (Recomendaciones medido en 390 px), portadas que no se recuperaban (motor y cliente; son las causas plausibles, el
síntoma al tocar la notificación de medios **no se pudo reproducir**), reordenado de acciones y reacciones. Sin hacer:
estados que quedan trabados si el motor se cae durante un pedido (`settings`, `separation`, `tidal`), el asistente de inicio que no bloquea el foco,
acciones que solo se ven con el cursor encima (Estudio, Stack), renombrar sección solo con clic derecho, fader de volumen oculto en celular,
`TagInput` que puede perder lo escrito al guardar enseguida, un solo `#poll` compartido en proveedores, el aviso de configuración que reaparece en
cada recarga y textos de desarrollo visibles en `TrackRow`.
