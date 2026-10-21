# Recomendaciones v3: plan de memoria, perfiles y generación

Estado: **plan, sin implementar** (2026-10-21). Parte de un problema medido: salen casi solo discos de jazz.

## 1. Diagnóstico (medido sobre el estado real)

- Los 4 discos mostrados por un perfil de trabajo: 3 de jazz y 1 de easy listening. Es un solo disco real generado; **la variedad entre perfiles nunca se midió**.
- `recs-last.json` → prompt: un artista con un solo "Me encantó" quedó en 6,0 contra 2,0 para todos los demás. Esa reacción suma +3 al artista y +1 a cada uno de sus 5 géneros (jazz, hard bop, bebop, cool jazz, modal jazz). Una reacción pesa más que tu perfil entero.
- Los géneros de la familia jazz aparecen 5 veces en el prompt ("jazz contemporáneo de Londres", bebop, hard bop, jazz...) y los demás gustos una vez cada uno.
- El perfil Trabajo pide "jazz contemporáneo de Londres" y lista 6 referencias; el modelo las repite (3 de 8 propuestas eran esas referencias y MusicBrainz no las halló).
- "Evitar" con frases largas ("discos didácticos de jazz clásico") solo va al texto: *Kind of Blue* pasó.
- El prompt trunca texto: el historial importado corta en "Yusse"; la lista de exclusión corta en "Kill". Hay duplicados (el mismo disco dos veces) y frases repetidas ("mayormente instrumentales" dos veces).
- El motivo mostrado sigue diciendo "de tus favoritos" en las alternativas.
- El puntaje mide **cercanía a los gustos** (`fit`): premia lo que ya se parece a lo pesado, o sea más jazz. No hay ninguna fuerza que busque variedad.

## 2. Memoria: señales separadas y con tope

Hoy todo se suma en un solo peso por artista y por género. Propuesta:

1. **Tres fuentes con tope propio** por artista y por género: declarado (perfil), conducta (favoritos, playlists, historial de otras apps) y reacciones. Cada una se normaliza a [0,1] y se combina con pesos fijos (declarado 0,4, conducta 0,4, reacciones 0,2). Una reacción nunca supera a las otras dos juntas.
2. **Rendimientos decrecientes**: el peso de un artista crece como `log(1+x)`, no lineal. Seis reacciones no valen seis veces una.
3. **Reparto entre géneros**: una reacción reparte +1 entre los géneros del disco (no +1 a cada uno).
4. **Áreas de gusto** (clusters): las 7 de tu perfil (reggae y roots, rock e indie argentino, funk-groove-soul, acústica y surf, rock clásico y blues, electrónica y dub, jazz contemporáneo de Londres) más las que aparezcan. Cada género y artista pertenece a un área (por similitud de embeddings, que ya existe en `genresim.py`, y por la lista del perfil). La memoria guarda un peso **por área**, no solo por género.
5. **Familias** de géneros (jazz = jazz, bebop, hard bop, cool, modal, contemporary...) con tope de participación: en el prompt y en la selección, una familia no pasa del 35 % del peso.
6. Decaimiento como hoy (vida media configurable); lo declarado no decae. Una reacción "No me va" baja el peso del artista, nunca el del género (regla ya aprobada).
7. Un archivo de resumen legible (`memory.md`) con las áreas y sus pesos, para que el usuario vea y corrija.

## 3. Perfiles: una mezcla de áreas, no solo texto

Cada perfil tiene hoy: horario, intención, favorecer, referencias, evitar, consigna. Se agrega lo que falta:

- **Mezcla de áreas**: qué porcentaje de los discos sale de cada área (ej. Trabajo: 40 % electrónica y dub, 30 % jazz de Londres, 30 % funk-soul instrumental; Descubrir: 20 % de cada una + 40 % afuera). Por defecto sale de los pesos de la memoria con tope por familia; el asistente permite ajustarla con controles, sin escribir porcentajes a mano.
- **Evitar en dos niveles**: *estilos* (filtro duro en código, géneros de MusicBrainz) y *notas blandas* (texto al modelo y penalización en el puntaje). El asistente pregunta cuál es cuál.
- **Referencias de ejemplo = solo anclas, no candidatas**: se excluyen de las propuestas (el modelo las repite) y se usan como "parecidos a".
- **Variedad como parámetro**: un campo "cuán variado" (poca / media / mucha) que fija el tope por familia (60 / 40 / 25 %).
- La memoria sigue siendo compartida; el perfil solo reordena qué áreas pesan.

## 4. Generación: cupos por área en vez de una sola pregunta

Hoy: un prompt grande, 8 discos, el modelo elige las áreas. Propuesta:

1. **El motor decide los cupos** (código determinístico): de la mezcla del perfil sale, por ejemplo, 8 cupos = 3 electrónica/dub, 2 jazz de Londres, 2 funk-soul, 1 exploración. Máximo 2 por familia entre los 8.
2. **Una pregunta corta por cupo**: "Un disco del área *electrónica y dub*, parecido a *Rhythm & Sound* o *Tom Misch* (ancla elegida al azar entre las del área, ponderada), instrumental, que no sea ninguno de [lista corta]". El modelo de 12B responde mejor con preguntas estrechas y ancla; el prompt baja de ~1200 tokens a ~300 por cupo.
3. **Verificación igual que hoy** (MusicBrainz, sin compilados, sin repetidos).
4. **Puntaje con dos términos**: cercanía al área del cupo + un bono por aportar una familia que todavía no está en la selección. Reordenar con un criterio de diversidad (selección voraz: cada disco nuevo se penaliza si repite familia).
5. Candidatos que no dependan del modelo (para probar, no asumido): MusicBrainz por etiquetas (`tag:` + `type:album`) dentro de cada área, y artistas relacionados de MusicBrainz, ordenados por cantidad de votos. El modelo pasa de "inventor" a "filtro y desempate". **Sin verificar** que la búsqueda por etiqueta rinda candidatos buenos; hay que medirlo antes.
6. Motivos: sin "de tus favoritos"; el motivo muestra el área ("Del área electrónica y dub") y, si hay, el contexto del disco.

## 5. Cómo se va a ver el prompt (por cupo)

```
Sistema: curador de discos, solo reales, JSON con esquema.
Quién es: guitarrista, nivel, objetivos.            (una línea)
Área del cupo: electrónica y dub.
Parecido a: Rhythm & Sound, Tom Misch.              (anclas)
Condición: instrumental; para concentrarse.
Evitar: [estilos duros y notas blandas, completos]
No proponer: [exclusión relevante para el área, sin truncar, sin duplicados]
Proponé 3 discos de artistas distintos.
```

Cambios frente al actual: se quitan los números de peso, las playlists, el historial importado en bloque y las referencias como candidatas; la exclusión se filtra por área en vez de cortarse a mitad de nombre.

## 6. Evaluación (antes de dar nada por bueno)

Un script que corre, en un motor **aislado** (carpeta de memoria temporal, `STEMSHED_SAVE_DRYRUN=1`, sin tocar tu memoria real), los 6 perfiles × 3 corridas y mide:
- porcentaje de la familia más frecuente (meta: ≤ 40 % por perfil; hoy ~75 % en el único caso real);
- cantidad de familias distintas entre los 8 (meta: ≥ 4);
- tasa de verificación en MusicBrainz (hoy 62 a 79 %; meta: no empeorar);
- repetidos entre corridas y violaciones de "evitar" (meta: 0);
- tiempo por corrida (hoy ~75 s).
La comparación va contra el pipeline actual, con las mismas semillas y el mismo modelo.

## 7. Orden de trabajo

1. Script de evaluación + línea de base del pipeline actual (primero medir).
2. Memoria con tope y áreas (`memory.py`, tests con datos sintéticos).
3. Perfiles con mezcla y "evitar" en dos niveles (migración de `presets.json` sin pisar lo editado).
4. Cupos por área + puntaje con diversidad.
5. Interfaz: mezcla en el asistente, vista de áreas en "Mi perfil".
6. Repetir la evaluación; si no mejora, no se activa.

## Riesgos
- Con una sola reacción real, cualquier ajuste de pesos se prueba solo con datos sintéticos; el efecto sobre tu uso real se ve con el tiempo.
- Las áreas dependen de los géneros de MusicBrainz (aportados por usuarios, pobres para música poco conocida): los artistas sin géneros caen en "sin área" y usan solo el perfil.
- Más llamadas al modelo (una por cupo): sube el tiempo; se compensa con prompts cortos y en paralelo de a pocos (un solo GPU).

## 8. Mezcla de modelos (agregado)

Un clasificador sirve si se le asigna un trabajo que pueda aprender. Con 2 reacciones reales **no hay etiquetas para entrenar "le va a gustar"**; sí sirve para tareas sin etiquetas del usuario. Reparto propuesto:

| Etapa | Modelo | Etiquetas necesarias | Estado |
|---|---|---|---|
| Proponer candidatos | LLM local (Mistral Nemo) o búsqueda por etiquetas en MusicBrainz | ninguna | existe (el LLM) |
| Verificar | MusicBrainz (no es un modelo) | ninguna | existe |
| Asignar área a un disco/artista | embeddings de texto (`nomic-embed-text`) contra las anclas de cada área, o clasificación zero-shot | ninguna | embeddings existen; falta el clasificador |
| Puntuar "cuánto le va a gustar" | regresión logística chica sobre rasgos (similitud al área, familia, década, artista conocido, voz/instrumental) | sí: reacciones y favoritos | **diferido**: se activa cuando haya ~30 reacciones; antes, el puntaje a mano |
| Diversidad | selección voraz (MMR) sobre los vectores | ninguna | a construir |
| Oído (más adelante) | embeddings de audio (CLAP, MERT, familia Essentia) de los temas de tu biblioteca y de los candidatos | ninguna | **sin verificar**: necesita audio de cada candidato y revisar licencias (creo que varios modelos de Essentia son no comerciales) |

Descartados antes con medición (`docs/memory-format.md`): clasificador LLM de gustos, agrupamiento, Open-Jev-2B y JEV 27B.

Los favoritos de TIDAL (cientos de discos) sirven como positivos sin pedirte reacciones; faltan negativos, así que un clasificador entrenado solo con ellos tiende a decir "sí" a todo lo que se parezca al jazz. Hay que evaluarlo con los pares reales antes de usarlo.

## 9. Memoria por área (agregado)

Un archivo por área de gusto en `~/.config/stemshed/memory/areas/<area>.md` (más un `index.md` con las áreas y sus pesos), en vez de un único `taste.json` con pesos sueltos.

Cada archivo guarda **evidencia de ítems**, no un veredicto sobre el género:
- artistas y discos del área, con su origen (declarado, favorito, playlist, reacción) y fecha;
- reacciones **por disco** ("Me encantó: X", "No me va: Y") con su decaimiento;
- anclas (los 3 a 5 artistas más representativos, para "parecido a");
- cuántas veces se recomendó algo del área y cómo respondió el usuario (tasa de aciertos del área, solo informativa);
- notas editables por el usuario.

Reglas:
- **"No me va" nunca baja el área**, solo el disco o el artista (regla ya aprobada: reacciones por ítem, no por género). Un disco malo de jazz no enfría el jazz.
- Un disco pertenece a una o dos áreas (la más cercana por embeddings y, si es cercana, una segunda); sus reacciones se cuentan una vez en cada una, repartidas.
- El prompt de un cupo lee **solo el archivo de su área** (anclas, lo ya clasificado para excluir), así el contexto se mantiene corto aunque la memoria crezca.
- Áreas nuevas nacen de dos formas: las declara el usuario en un perfil, o el motor propone una cuando 5 o más ítems no encajan en ninguna (el usuario la confirma o la descarta).
- Las áreas chicas o sin actividad se compactan como hoy (decaimiento y poda); el archivo conserva un resumen.
- El `index.md` guarda la mezcla global; cada perfil la reordena (sección 3).

Migración: se arma desde `taste.json`, `events.jsonl` y `sources.json` sin borrar nada; los archivos viejos quedan como respaldo.

## 10. Modelos de decisión (Kev, Laya, NanoJev) para el clasificador de áreas

Dato de fuentes secundarias (blogs de reseña; **no probé ninguno**): reciben un texto y preguntas tipadas (sí/no, opción múltiple, puntaje) y devuelven probabilidades calibradas en vez de prosa.
- **Kev** (0.8B, 4B, 9B y quizás 27B, Apache-2.0, sobre Qwen3.5): compatible con la API de Jev. Su propio MMLU-Pro es mucho peor que el de Jev (0,565 en 4B): **saben poco de hechos**, razonan sobre el texto que se les da.
- **Laya** (~421 M, ModernBERT-large, Apache-2.0, checkpoint multilingüe): 13 a 35 ms según el equipo. Bueno en decisiones binarias; flojo en 10 clases (0,52 en un ruteo de tickets).
- **NanoJev** (0,6B): pruebas chicas, no sirve de evidencia.
- **OpenJev 27B**: CC BY-NC 4.0; sigue descartado por licencia y tamaño.

Uso propuesto (solo sobre texto que ya tenemos: extracto de Wikipedia, géneros y etiquetas de MusicBrainz, nombre del artista; nunca como fuente de hechos sobre un disco):
- "¿Este disco es instrumental?", "¿Es un disco didáctico de jazz clásico?" (filtro blando de "evitar").
- "¿A cuál de estas áreas pertenece?" (cupo por área), con probabilidades que se usan como pesos.
- "¿Encaja con la consigna del perfil?" como un término más del puntaje.

Límites: sin texto (discos poco conocidos) no hay nada que clasificar y el disco cae en "sin área"; dos o tres preguntas por candidato suman tiempo; la API de Kev/Jev es compatible con el SDK de TypeSafe, que no instalaría sin revisar.

Prueba antes de adoptar: armar ~40 discos de tu biblioteca con el área puesta a mano (la revisás vos), correr Kev-4B y Laya contra los embeddings actuales y comparar aciertos, tiempo y VRAM. Si no ganan, quedan los embeddings.

## 11. Tres modelos con roles separados (decisión de diseño)

Cada rol es un **módulo con su propio modelo configurable** (Ajustes → Modelos por módulo, con el badge "Recomendado" como hoy). Se pueden cambiar por separado y cada uno puede quedar desactivado con una alternativa sin modelo.

| Módulo | Trabajo | Entra | Sale | Modelo inicial | Alternativa sin modelo |
|---|---|---|---|---|---|
| **Separación** | stems del tema | audio | stems | RoFormer (audio-separator, ya en uso) | ninguna |
| **Clasificación** | etiquetar texto con probabilidades | extracto/géneros/artista del disco | área(s), instrumental sí/no, "didáctico" sí/no, encaje con la consigna | a decidir por la prueba: Kev-4B, Laya o embeddings (`nomic-embed-text`) | embeddings + géneros de MusicBrainz (hoy) |
| **Recomendación** | proponer candidatos y, si se pide, redactar | cupo + anclas + exclusiones | `[{artista, disco}]` | Mistral Nemo (ya en uso) | búsqueda por etiqueta en MusicBrainz |

Regla de oro: **el recomendador propone, el clasificador decide, MusicBrainz verifica.** El recomendador nunca puntúa ni decide el área; el clasificador nunca inventa discos.

### Flujo de una recomendación
1. Motor (código): lee perfil + memoria por área y reparte los cupos.
2. **Recomendación**: por cupo, 3 candidatos.
3. MusicBrainz: existe, no es compilado, no repetido.
4. **Clasificación**: sobre el texto del disco (Wikipedia/MusicBrainz) calcula área, instrumental, "evitar"; descarta los que violan un "evitar" y puntúa el encaje.
5. Motor: selección con tope por familia; elige el disco y las alternativas.
6. **Recomendación** (otra vez, solo si el usuario lo pide): redacta el contexto del disco con el extracto de Wikipedia, validado como hoy.

### VRAM (16 GB, 1,2 GB en uso ahora)
- Separación y recomendación (12B) **no caben juntas**: se turnan, como hoy.
- Clasificación debería ser chica (Laya ~0,4 B, embeddings 0,27 GB, Kev-0.8B/4B): cabe junto a cualquiera de las dos. Kev-9B sería una decisión aparte según lo que quede libre.
- Orden de carga: la clasificación corre al final de cada ronda de verificación, con el recomendador ya descargado si hace falta; la separación tiene prioridad sobre ambas, como hoy.

### Lo que cambia en el código
- `engine/classify.py` nuevo, con una interfaz mínima `classify(text, questions) -> probabilidades`. Hoy la implementa `genresim` (embeddings); mañana, un backend Kev/Laya detrás de la misma interfaz. Los pesos que ya usa `recs` no cambian de forma, solo de dónde salen.
- `settings.py`: `classifierModel` (vacío = embeddings) junto a `llmModel` y el modelo de separación; `models.report()` lista el módulo "Clasificación" con tamaño y dónde está instalado.
- Pantalla Ajustes: una fila más en Modelos por módulo.

### Qué prueba decide cada rol
- Clasificación: la comparación de los ~40 discos con área a mano (sección 10). Métricas: aciertos de área, aciertos de instrumental, tiempo por disco, VRAM.
- Recomendación: la línea de base del script de evaluación (sección 6). Se compara Mistral Nemo contra Gemma 3 12B con las mismas semillas y la misma métrica de variedad.
- Separación: sin cambios.

### Orden (reemplaza la sección 7)
1. Script de evaluación + línea de base.
2. Interfaz `classify` con el backend actual de embeddings (sin cambiar resultados).
3. Memoria por área + topes.
4. Perfiles con mezcla; cupos y selección con tope por familia.
5. Prueba de clasificadores (Kev, Laya) contra los ~40 discos; adoptar solo si ganan.
6. Ajustes y asistente.
7. Segunda evaluación: no se activa lo nuevo si no mejora la variedad sin bajar la tasa de verificación.
