# Comparación de modelos locales para Recomendaciones

Fecha: 2026-10-21. Máquina: RTX 5080 (16 GB, ~1,4 GB ya usados por el escritorio), Ollama propio en 127.0.0.1:11500. Scripts reproducibles en `engine/eval/` (`quiz.py`, `recs_eval.py`, `common.py`, `mb.py`); resultados crudos en `docs/agent-notes/model-eval-raw/`.

## Recomendación

1. **Ningún modelo local de este tamaño sirve como fuente de datos de música.** Los tres inventaron con total seguridad los 5 datos trampa (discos/artista que no existen) en las 2 corridas: 0 de 10 admisiones. Ninguno es confiable para decir "quién tocó", "en qué disco está" ni "qué modo es".
2. **Usarlos solo como proponedores de candidatos y verificar siempre** (MusicBrainz, como ya hace `recs.verify`). Con esa regla, lo que importa es qué tan buenos son los candidatos: existencia ~77 % y afinidad con el perfil.
3. **Mantener `mistral-nemo` como modelo por defecto**: es el que más acertó en el cuestionario (36/46 contra 34/46 de Gemma, diferencia dentro del ruido), el más rápido (~106 tok/s), con licencia Apache 2.0 (importa para una versión pública) y propone candidatos más variados.
4. **Dejé instalado `gemma3:12b` como alternativa para probar a ojo**: tiene el mismo porcentaje de existencia pero propuso bastante más discos de jazz/soul/funk (61 % contra 35 % de todos los candidatos). Contras: repite casi los mismos discos entre corridas (11 únicos en 18), es ~18 % más lento y su licencia (Gemma Terms of Use) tiene restricciones de uso y obligaciones de redistribución. No lo propongo como default sin que el usuario lo compare en la app real.
5. `qwen3:14b` quedó descartado y borrado: peor en el cuestionario (27/46) y solo 33 % de sus candidatos existen.

La palanca más fuerte no es el modelo sino el prompt: el perfil de gustos guardado de la prueba casi no tenía jazz, así que cualquier modelo tira hacia sus géneros dominantes salvo que la consigna de perfil lo empuje explícitamente a otro estilo.

## Tabla

| | mistral-nemo (referencia) | gemma3:12b | qwen3:14b (borrado) |
|---|---|---|---|
| Tamaño en disco (Q4_K_M) | 7,1 GB | 8,2 GB | 9,3 GB |
| Licencia de los pesos | Apache 2.0 | Gemma Terms of Use (Google, propia, con restricciones de uso) | Apache 2.0 |
| VRAM cargado (`/api/ps`) | 7,5 GB | 8,1 GB (nvidia-smi total ~10,4 GB con el escritorio) | 9,7 GB (nvidia-smi ~10,8 GB) |
| Velocidad (tok/s) | ~106 | ~87 | ~85 |
| Carga en frío | ~5 s | ~9 s | ~42 s |
| Quiz: aciertos (23 preguntas reales x 2 corridas) | **36/46 (78 %)** | 34/46 (74 %) | 27/46 (59 %) |
| Trampas: alucinó (5 x 2 corridas) | 10/10 | 10/10 | 10/10 |
| Recs: candidatos que existen en MusicBrainz | 76,5 % (13/17) | 77,8 % (14/18) | 33,3 % (6/18) |
| Recs: existen y año coincide (±1) | 64,7 % | 66,7 % | 27,8 % |
| Recs: afines a jazz/soul/funk (de los que tienen géneros) | 50 % (6/12) | 78,6 % (11/14) | 66,7 % (4/6) |
| Recs: afines sobre el total de candidatos | 35,3 % | 61,1 % | 22,2 % |
| Recs: discos únicos en 3 corridas | 12 de 17 | 11 de 18 | 18 de 18 |
| Recs: JSON válido | 3/3 | 3/3 | 3/3 |
| Latencia por pedido de 6 discos (sin carga) | ~3 s | ~3,5 s | ~3 s |
| Veredicto | Default; solo proponedor | Alternativa a probar; solo proponedor | Descartado |

Notas de la tabla: el 78,6 % de Gemma es sobre solo 14 candidatos y el de Qwen sobre 6, así que son indicativos, no estadística. La velocidad es `eval_count/eval_duration` de Ollama en la RTX 5080. Los tiempos con carga en frío (primer pedido de cada tanda) fueron 7 s, 12 s y 45 s.

## Errores típicos en el cuestionario (23 preguntas reales + 5 trampas, temperatura 0,2, 2 corridas)

- Los tres fallaron las dos veces Cantaloupe Island (Empyrean Isles, 1964; dijeron My Favorite Things, My Funny Valentine, Blow-By-Blow, Maiden Voyage), el acompañante de Wes Montgomery en Smokin' at the Half Note (Wynton Kelly Trio) y la cantidad de alteraciones de Re dórico (ninguna).
- Mistral Nemo: además falló el II-V-I en las 2 corridas (puso Fa en vez de Sol, o Do menor), acertó el modo de So What y el mixolidio solo 1 de 2 veces. Acertó bajista, baterista, Head Hunters, Midnight Blue y Bright Size Life.
- Gemma: además falló Midnight Blue (Stanley Turrentine; dijo Paul Gonsalves) y el bajista de Bright Size Life (Jaco Pastorius); So What y lidio acertados solo 1 de 2 veces; acertó el II-V-I y el mixolidio.
- Qwen: además falló batería y bajo de Kind of Blue (Jimmy Cobb y Paul Chambers; dijo Philly Joe Jones y Ron Carter), Head Hunters (Mwandishi/Maiden Voyage), Midnight Blue, lidio, mixolidio y II-V-I. Fue el único que acertó So What (dórico) las 2 veces.
- Trampas: ninguno dijo "no conozco ese disco" sin inventar. Hubo 2 respuestas con admisión parcial (Mistral con "Calle Seis": admitió no conocer el disco pero inventó el artista como "guitarrista puertorriqueño"; Gemma con "Copper Lungs": describió el disco y recién al final dijo que no hay información). Las conté como alucinación tras revisarlas a mano. Se verificó en MusicBrainz que los 5 nombres no existen (y que los controles positivos sí aparecen).

## Cómo se evaluó (reproducible)

- `python3 engine/eval/quiz.py --model <m> --runs 2` (temperatura 0,2, semillas 1 y 2, system prompt que pide admitir si no se sabe). Corrección automática por regex sobre texto sin tildes; las dudosas se revisaron a mano. El regex es estricto: en la primera pasada ajusté `5/4` y `dorio` tras revisar respuestas correctas mal marcadas.
- `python3 engine/eval/recs_eval.py --model <m> --runs 3` (temperatura 0,7 como la app, el prompt real de `recs-last.json`, 6 discos en JSON). Existencia con el mismo criterio que `recs.verify` (lógica copiada en `engine/eval/mb.py`, 1 consulta/s, User-Agent `ShedStemStudio/0.0.1 (prototipo local)`, caché local). Géneros: `release-group?inc=genres+tags`; afín = algún género contiene jazz, soul, funk, r&b, fusion o bop. Cuando MusicBrainz no devuelve géneros el candidato no entra en el 78,6 %/50 %/66,7 %.
- Límites: el criterio de existencia es estricto y puede dar falsos negativos (por ejemplo, "Godspeed You! Black Emperor" y Fela Kuti "Zombie" salieron como inexistentes aunque los discos son reales; el nombre del artista en MusicBrainz difiere). Afecta parejo a todos los modelos. Con 2 corridas del quiz y 3 de recs la diferencia Nemo/Gemma no es significativa.

## Cambio propuesto para `engine/hardware.py` (no lo toqué)

```python
CATALOG = [
    {"id": "mistral-nemo", "label": "Mistral Nemo 12B", "module": "recomendaciones", "gb": 7.1,
     "note": "Apache 2.0. Medido: 78 % del cuestionario, inventa datos; usar solo para proponer y verificar."},
    {"id": "gemma3:12b", "label": "Gemma 3 12B", "module": "recomendaciones", "gb": 8.2,
     "note": "Licencia Gemma (restricciones). Medido: 74 %, propone más jazz/soul/funk pero repite; usar solo para proponer y verificar."},
]
```
No incluir `qwen3:14b` (59 % del cuestionario, 33 % de candidatos reales).

## Qué no se pudo probar

- Modelos más grandes con más conocimiento (gemma3:27b de 17 GB, qwen3:30b de 19 GB, mistral-small de ~14 GB cuantizado) no entran con holgura en 16 GB menos el escritorio, o excedían el tope de descargas de 20 GB. Es probable que un 27B-30B sepa más, pero no se midió.
- Llama 3.1 8B (4,9 GB) y Qwen3 8B no se bajaron porque con los 17,5 GB ya gastados no cabían en el tope de 20 GB.
- No se midió la velocidad compartiendo la GPU con la separación de stems (no coexisten).
