# Informe del agente: comparación de modelos (2026-10-21)

Resultados y tabla completos: `docs/model-comparison.md`. Crudos: `docs/agent-notes/model-eval-raw/` (quiz-*.json, recs-*.json, mb-cache.json).

## Qué hice
- Elegí 2 candidatos que entran en 16 GB y verifiqué sus tamaños en ollama.com/library: `gemma3:12b` (8,2 GB, Gemma Terms of Use) y `qwen3:14b` (9,3 GB, Apache 2.0). Tercer candidato descartado por tope: con 17,5 GB gastados quedaban 2,5 GB.
- Escribí `engine/eval/{common,mb,quiz,recs_eval}.py` (solo librería estándar). Quiz: 23 preguntas reales (jazz, gustos del usuario, teoría) + 5 trampas, temp 0,2, 2 corridas. Recs: prompt real de recs-last.json (solo lectura), 6 discos JSON, 3 corridas, temp 0,7, verificación en MusicBrainz a 1 consulta/s.
- Evalué de a uno (descargando los otros con keep_alive 0 entre tandas), incluyendo mistral-nemo como línea base con el mismo método.

## Cómo verifiqué
- Datos del quiz: años y artistas de los discos contra MusicBrainz (Kind of Blue 1959, Giant Steps 1960, A Love Supreme 1965, Baduizm 1997, New Amerykah 2008, Head Hunters 1973, Empyrean Isles 1964, Midnight Blue 1963, Bright Size Life 1976, créditos de Smokin' (Wynton Kelly Trio) y Sunday at the Village Vanguard (Scott LaFaro)). Personal de Kind of Blue, Take Five 5/4, modos y II-V-I salen de mi conocimiento, no de una fuente consultada.
- Las 5 trampas no existen en MusicBrainz (con controles positivos que sí aparecen).
- Revisé a mano las respuestas marcadas como erróneas o dudosas y corregí el regex (`5/4`, `dorio`).

## Resultados clave
- Quiz: mistral-nemo 36/46, gemma3:12b 34/46, qwen3:14b 27/46. Trampas: los 3 alucinaron 10/10.
- Recs: existencia 76,5 % / 77,8 % / 33,3 %; afinidad jazz-soul-funk sobre el total 35 % / 61 % / 22 %; JSON válido 3/3 en todos; ~106 / ~87 / ~85 tok/s.
- Recomendación: mantener mistral-nemo por defecto, no usar ningún modelo como fuente de datos, siempre verificar; gemma3:12b queda instalado como alternativa para probar. Propuesta para CATALOG en el doc principal.

## Descargas y disco
- Descargué `gemma3:12b` (8,2 GB nominal) y `qwen3:14b` (9,3 GB nominal) = 17,5 GB nominales de los 20 permitidos. `qwen3:14b` fue borrado. Quedan instalados: mistral-nemo (7,1 GB) y gemma3:12b (8,2 GB); la carpeta de modelos ocupa 15 GB. Todo vía `OLLAMA_HOST=127.0.0.1:11500`, nunca el servicio del sistema.
- /mnt/plexdata quedó con ~62 GB libres (cayó de 79 a 62 por mis descargas y por otros procesos; no medí cuánto fue de cada uno).

## No toqué
settings.json, mistral-nemo, el motor, Vite, proto/player, server.py, recs.py, settings.py, hardware.py. Sin ventanas visibles.

## No pude verificar / limitaciones
- Modelos de 24-30B (más conocimiento probable) no entran en la VRAM libre o en el tope de descargas; no medidos.
- Pocas corridas (2 y 3): Nemo vs Gemma está dentro del ruido. El criterio de existencia da falsos negativos por nombres de artista distintos en MusicBrainz.
- Durante mis pruebas otro agente usaba Ollama, así que las latencias en frío (primer pedido de cada tanda) pueden estar infladas por el cambio de modelo.
- Licencia de Gemma: leí el encabezado vía `ollama show --license`; no analicé el texto legal completo para uso público.
