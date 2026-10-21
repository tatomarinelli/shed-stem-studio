# Línea de base de recomendaciones (pipeline actual, 2026-10-21)

Script: `engine/eval/recs_variety.py --runs 3`. Entorno aislado (copia de la memoria en una carpeta temporal, sin guardar, sin TIDAL, sin contexto de Wikipedia). Modelo: mistral-nemo. 6 perfiles × 3 corridas; se miden los 4 discos que se le muestran al usuario por corrida. Datos crudos: `docs/recs-baseline.json`. Los archivos reales de `~/.config/stemshed` quedaron sin cambios (hashes antes y después).

| Perfil | Familia dominante (promedio por corrida) | Familias distintas | Verificados en MusicBrainz | Segundos | Discos únicos / total | Composición |
|---|---|---|---|---|---|---|
| Estudio de jazz | 100 % | 1,0 | 75 % | 27 | 6 / 12 | jazz 12 |
| Trabajo | 50 % | 2,3 | 36 % | 73 | 10 / 12 | electrónica 5, jazz 4, rock 3 |
| Para sacar de oído | **75 %** | 1,7 | 79 % | 33 | 11 / 12 | **jazz 9**, funk/soul 3 |
| Mate y guitarra | 50 % | 3,0 | 51 % | 53 | 10 / 12 | reggae 4, folk 3, rock 3, jazz 1 |
| Inspiración | 50 % | 2,7 | 75 % | 35 | 11 / 12 | electrónica 5, rock 5, jazz 1, funk 1 |
| Descubrir | 67 % | 2,3 | **29 %** | 91 | 8 / 10 | **jazz 6**, funk 2, sin familia 2 |
| **Total** | **47 % jazz (33 de 70)** | | 58 % | | 53 / 70 | |

Lectura:
- **Jazz domina fuera de donde corresponde**: "Para sacar de oído" pide funk y soul con guitarra y recibe 9 de 12 de jazz; "Descubrir" pide ethio-jazz, bossa y música argentina y 6 de 10 son jazz.
- **"Estudio de jazz"** es 100 % jazz, lo esperado; sirve de control.
- **Repetidos**: 53 discos únicos entre 70; el perfil Estudio de jazz repite la mitad (6 de 12).
- **Verificación baja** en Trabajo (36 %) y Descubrir (29 %): el modelo propone discos que MusicBrainz no encuentra.
- **Violaciones de "evitar"** con filtro duro: 0 (los "evitar" largos no se filtran en código).
- Sin datos propios todavía: variedad entre días (cada corrida repite las mismas condiciones).

Metas para la versión nueva (sección 6 de `recs-plan-v3.md`): familia dominante ≤ 40 % en los perfiles que no son de jazz, ≥ 4 familias distintas entre 8 propuestas, verificación ≥ 58 %, repetidos entre corridas ≤ 1 de 12.
