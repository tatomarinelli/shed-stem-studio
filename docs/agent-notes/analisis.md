# Informe: análisis de tonalidad, tempo y acordes

Hecho por un agente; verificado por mí en lo siguiente: los 13 tests pasan (21 s, `cd engine && /mnt/plexdata/tidal-stems/venv/bin/python -m unittest tests.test_analysis`), los 6 resultados reales existen en `/mnt/plexdata/stemshed/analysis/` y sus valores coinciden con la tabla de abajo. La exactitud contra fuentes externas es la que reportó el agente; no la rehice.

## Exactitud medida

**Tempo y pulsos (prioridad 1)**
- Sintético dentro de la muestra (9 casos con los que se ajustó): BPM dentro de ±2 % en 8/8 de tempo fijo; F1 de pulsos 0,98 a 1,00; el accelerando se marca `stable: false`; la balada con hi-hat en corcheas no se duplica.
- Sintético reservado (otras semillas, transpuesto, tempo ±7 %): BPM 8/8, F1 de pulsos ≥ 0,98 en 9/9, el 1 del compás bien en 8/9 (falló el jazz con swing).
- Real: 3 temas coinciden con la fuente y 2 discrepan por un factor de 2. La decisión de octava es lo más frágil y se ajustó en parte mirando los temas reales.

**Tonalidad (prioridad 2)**: sintético 9/9 dentro y 9/9 reservado (incluye dórico Dm7-G7, eólico, blues mixolidio, ii-V menor). Real: la tónica coincide con la fuente en 5/5 de los temas con referencia.

**Acordes (prioridad 3)**: sintético 0,94 del tiempo con raíz y calidad exactas dentro, 0,96 reservado. Real: no hay verdad cuadro por cuadro; solo coherencia. La prueba sintética es fácil (bombo en 1 y 3, cambios justo en la barra).

## Comparación con fuentes reales

Las referencias se anotaron antes de terminar de ajustar, pero algunas de songbpm se bajaron a mitad del ajuste del tempo.

| Tema | Tonalidad estimada | Referencia | BPM estimado | Referencia de BPM |
|---|---|---|---|---|
| On & On (Erykah Badu) | Mi menor | Em según Jamzone y UBC | 80,4 | 80 (songbpm, Jamzone, Traktor) |
| root (grabación propia) | Do♯ menor (conf. 0,48) | sin referencia | 117,0 | sin referencia |
| Idle Moments (Grant Green) | Do menor | C menor (New York Jazz Workshop, songbpm) | 62,2, variable 72 a 57 | 64 |
| Chitlins Con Carne (Kenny Burrell) | Do blues | C blues (jazzleadsheets) | 132,2 | 133 (un backing comercial dice 122) |
| Alive (Pearl Jam) | La mixolidio | A mayor (Musicnotes) | 152,6, `stable: false` | octava distinta de Musicnotes; coincide con Mixmeister (152) |
| Hit It and Quit It (Funkadelic) | Mi♭ blues/dórico; afinación +43,5 cents | Ebm (tab de UG, fuente débil) | 74,0 | la mitad de songbpm (146) |

**Coherencia de acordes reales:** Chitlins se repite cada 12 compases (blues de manual: C C C C | F F C C | G F C C); Idle Moments cada 16 compases con Cm, Dm7b5, G7, Fm y Ab, coherentes con Do menor; On & On alterna Em/B (la fuente educativa dice Em9 y Bm7: las raíces coinciden, la calidad de B probablemente no).

## Variantes medidas
- Fuente del pulso: batería + bajo y "todo" rinden igual; solo batería falla en Idle Moments (brushes a −45 dB, da el doble); solo bajo falla en On & On y Chitlins.
- Sin el stem de bajo, Chitlins pasa a "Fa mixolidio" (empeora). Sumar la voz a la armonía es neutro o algo peor.

## Qué no se pudo verificar
- No hay verdad de acordes compás a compás en ningún tema real.
- Las referencias de BPM de Alive y Hit It discrepan entre sí.
- No detecta compases distintos de 4/4.
- El 1 del compás es poco fiable con brushes o funk sincopado (`downbeatConfidence` 0,03 en Idle Moments y en Hit It).
- Sin evaluación auditiva. Las tensiones (9, 13, #9) no se informan.

## Parámetros ajustables por variable de entorno
`STEMSHED_CHG=4` (costo de cambiar de acorde), `STEMSHED_CHG_DOWN=0.25`, `STEMSHED_CHG_HALF=0.5`, `STEMSHED_RARE=0.05` (penalización de modos raros), `STEMSHED_WFIRST=0.2` (peso del primer compás como tónica), `STEMSHED_SNARE_HZ=4000`.

## Fuentes consultadas
[songbpm Alive](https://songbpm.com/@pearl-jam/alive), [songbpm Chitlins](https://songbpm.com/@kenny-burrell/chitlins-con-carne), [songbpm Hit It](https://songbpm.com/@funkadelic/hit-it-and-quit-it), [songbpm Idle Moments](https://songbpm.com/@grant-green/idle-moments), [songbpm On & On](https://songbpm.com/@erykah-badu/on-on), [Musicnotes Alive](https://www.musicnotes.com/sheetmusic/pearl-jam/alive/MN0134893), [Jamzone On & On](https://jamzone.musicwill.org/songs/on-on), [UBC On & On](https://www.cs.ubc.ca/%7Edavet/music/track/HOTTRACK_038/HOTTRACK_038-12.html), [jazzleadsheets Chitlins](https://jazzleadsheets.com/chitlins-con-carne.html), [NY Jazz Workshop Idle Moments](https://newyorkjazzworkshop.com/?p=25479), [UG Hit It](https://pt.ultimate-guitar.com/tab/funkadelic/hit-it-and-quit-it-chords-5094664).
