# Shed Stem Studio: ideas y análisis de lo que ya existe

Documento **para pensar**. No hay nada de esto implementado. Lo que se dice de otras aplicaciones sale de fichas de tienda, reseñas y búsquedas del 2026-10-21; no probé ninguna, así que tomalo como orientación y verificá antes de decidir algo.

## 1. Qué existe hoy

**Separación y práctica con la canción**

| Producto | Qué hace | Relación con Shed Stem Studio |
|---|---|---|
| [Moises](https://apps.apple.com/app/id1515796612) | Separa en voz, batería, bajo, guitarra, piano y cuerdas; detecta acordes y tonalidad sobre los compases; BPM automático; cambia velocidad sin cambiar el tono y la tonalidad; metrónomo sincronizado con la canción; exporta stems y mezclas con click. Gratis con límites; Premium y Pro por suscripción ([reseña de julio de 2026](https://tooldirectory.ai/tools/moises)). | El competidor más directo. Es en la nube, con tus pistas subidas a su servicio; Shed Stem Studio corre en tu máquina y trabaja sobre tu biblioteca. |
| [Anytune](https://community.pianogroove.com/t/anytune-pro-app/2576) y Amazing Slow Downer | Velocidad sin cambiar el tono, loops y marcadores, transposición; Anytune suma ecualización y "reframe" para aislar o silenciar partes. Se compran una vez o por suscripción según la plataforma ([comparativa](https://www.songscription.ai/blog/best-apps-to-slow-down-music)). | Cubren lo que ya hace el DAW de Shed Stem Studio (velocidad, loops), sin separación propia ni recomendaciones. |
| Transcribe! | Loops, velocidad, marcadores y subdivisión automática para sacar de oído. | Mismo terreno que el Estudio. |
| [iReal Pro](https://symposium.music.org/index.php/current-issue/item/11610-ireal-pro-a-revolution-in-jazz-education-practice-tools) | Toca cifrados con acompañamiento (tempo, tonalidad, estilo, repeticiones). No usa grabaciones. | Complementario: es el "play-along sintético" de jazz. |
| Chordify y similares | Reconocimiento de acordes sobre grabaciones. | La investigación académica muestra que los acordes extendidos (maj7, m7, 7, m7b5) son bastante más difíciles que las tríadas, y que el audio mezclado es mucho más difícil que el aislado ([evaluación 2025](https://sol.sbc.org.br/index.php/sbcm/article/view/43948), [Fraunhofer](https://publica.fraunhofer.de/handle/publica/404977)). Ahí Shed Stem Studio tiene una ventaja: analiza stems separados. |

**Redes y comunidades musicales**

| Producto | Qué hace |
|---|---|
| [Smule](https://en.wikipedia.org/wiki/Smule_(app)) | Karaoke social con dúos (llamadas abiertas que la app une en un solo video) y concursos. El único con desafíos como función central, para voz. |
| BandLab y Soundtrap | BandLab es un estudio en la nube con feed social, remezclas y colaboración abierta; Soundtrap es colaboración por invitación, orientada a educación ([comparativa](https://www.techjockey.com/compare/bandlab-vs-soundtrap)). |
| [Jamloop](https://mwm.ai/apps/jamloop/6762392512), [Octero](https://rekkerd.org/?p=44018), [Tonic](https://theviolinchannel.com/vc-artist-ray-chen-launches-new-practice-app-tonic), SixString, klaep | Redes y apps de práctica: videos cortos de riffs y solos, registro de práctica con retos de constancia (Octero), salas de práctica y desafíos (Tonic), clips de guitarra (SixString), jams a pantalla dividida (klaep). Varias son recientes; no verifiqué cuánta gente las usa. |
| [CleverJazz](https://apps.apple.com/app/id6748681852) | La más parecida a tu idea: jazz con acordes, escalas, licks, entrenamiento de oído, registro diario y racha, y packs de licks de la comunidad que se publican y comparten. No encontré desafíos. |
| Guitar World Lick of the Day y bibliotecas de licks | Un lick nuevo por día como lección en video: catálogo cerrado, no comunidad. |

**Lo que no encontré combinado:** práctica sobre *tu propia biblioteca* con stems locales, análisis armónico, recomendación de qué escuchar según lo que querés aprender, y comunidad de licks con desafíos. Cada pieza existe por separado.

## 2. Dónde Shed Stem Studio puede diferenciarse

1. **Local primero.** Tu audio no sale de tu máquina. Moises y casi todos suben archivos a su nube.
2. **Tu biblioteca, no un catálogo cerrado.** Estudiás lo que escuchás, y la app aprende qué te sirve.
3. **Enseña teoría mientras practicás.** Para alguien flojo en modos: mostrar, sobre cada acorde, el modo o la escala que suena, y los tonos del acorde.
4. **Un solo recorrido:** escuchar, entender qué pasa, sacarlo de oído, practicarlo, y que la app proponga qué escuchar después.

## 3. Ideas de producto

**DAW y práctica** (las más cercanas a lo que ya hay)
- **Click y grilla de compases** alineados con el tempo detectado, con cuenta previa antes del loop y volumen propio. Es lo siguiente del análisis.
- **Transponer** sin cambiar la velocidad (cambiar la tonalidad de la pista para tocar en la del instrumento).
- **Entrenador de velocidad**: sube de a 5 % cada N vueltas del loop hasta el 100 %.
- **Loops y secciones guardados** en el motor (hoy se guardan solo en el navegador), con nombres y por tema.
- **Modo "oído primero"**: ocultar los acordes hasta que el usuario los marque, y recién después comparar con lo detectado.
- **Escala por acorde**: junto a cada acorde, el modo sugerido y las notas del acorde para improvisar encima.
- **Grabarte sobre los stems** y comparar tu toma con la original: ritmo (qué tan cerca del click) y afinación.
- **Transcripción asistida**: contorno de notas del stem de guitarra o piano, exportable a MIDI o a tablatura básica.
- **Registro de práctica y racha**: minutos por tema, qué loops y a qué velocidad; sin gamificación forzada.

**Recomendaciones y aprendizaje**
- **Plan de estudio** a partir de lo que declarás querer mejorar: por ejemplo, tres discos con vamp modal para oír dórico durante una semana, con un tema para sacar de oído por día.
- **Diario de escucha**: qué discos escuchaste, qué reacción tuviste, qué sacaste de oído.
- **Repetición espaciada** de licks y progresiones que ya sacaste.
- **Licks desde tu propia biblioteca**: segmentos de solos separados, etiquetados con tonalidad, tempo y acordes.

## 4. La idea de red social musical (para pensar)

**Qué sería:** una comunidad donde se comparten licks y se plantean desafíos, centrada en practicar y no en seguidores. Posibles piezas:
- **Lick:** una referencia a un tema (artista, título, disco y tramo en segundos), con su tonalidad, tempo y progresión, y opcionalmente tu toma grabada.
- **Desafíos:** "este lick, en 12 tonalidades", "tocalo a 60, 80 y 100 BPM", "improvisá sobre estos cuatro compases".
- **Retroalimentación**: comentarios sobre una toma, o una puntuación automática de ritmo (qué tan cerca del click) y de notas.
- **Colecciones y rachas**, como packs de licks que alguien publica.

**El problema central: derechos de autor.** No se puede distribuir el audio de discos comerciales ni sus stems separados. Eso cambia el diseño:
- Lo que se comparte es la **referencia** al tema (artista, título, disco, identificador y tramo en segundos), los **metadatos del análisis** (tonalidad, tempo, acordes, secciones) y, si quien la manda quiere, **su propia toma**. Nunca el archivo de la canción ni sus stems.
- **No hace falta ninguna pista de acompañamiento.** Cada cliente busca el tema en la fuente de audio que tenga configurada (sus archivos, TIDAL u otra) y trabaja sobre su propia copia. Es la abstracción de fuentes que ya está hecha: el tema es una referencia y el audio sale de la config global de cada usuario.
- Una pista sintética generada a partir de los acordes (a lo iReal Pro) solo se necesitaría para un desafío que **no parta de ninguna canción** (por ejemplo, "este lick en 12 tonalidades"). Es opcional, no un requisito.

**Qué ya existe y cómo se compara:** CleverJazz es lo más cercano en licks compartidos (sin desafíos, hasta donde pude ver); Tonic y Octero hacen desafíos y registro de práctica pero no en jazz; Smule demuestra que los desafíos funcionan para voz. Falta algo centrado en guitarra y jazz que conecte los desafíos con el análisis armónico.

**Decisiones abiertas para cuando se piense en serio**
1. **Local o servidor.** Local primero choca con una red social, que necesita un servicio. Opciones: servicio propio, o una red federada (por ejemplo, ActivityPub) donde cada instalación publica y sigue a otras.
2. **Moderación y cuentas.** Una comunidad pública exige responder por el contenido y proteger datos personales.
3. **Cómo se puntúa una toma** sin falsos negativos que desalienten: empezar solo con ritmo contra el click, que es medible.
4. **Si hace falta.** Probablemente no antes de tener una buena herramienta de práctica personal.

**Un camino prudente:** primero formatos de intercambio sin servidor. Exportar e importar un "paquete de referencia" (los metadatos del tema y del tramo, el análisis y, opcionalmente, una toma) como archivo o enlace; si la gente lo usa, recién ahí pensar en una red.

## 5. "Referencias con tiempo" (idea del usuario, estilo grupo de banda)

**El caso real:** una banda tiene un grupo de chat (por ejemplo de WhatsApp) donde se pasan referencias con el minuto exacto de algo que les gustó: un solo, una idea, un tipo de sonido.

**Una referencia es solo un puntero**, no audio:
- Qué tema es: artista, título, disco, y si se puede un identificador estable (ISRC o MusicBrainz) y la duración.
- De dónde a dónde: inicio y fin en segundos.
- Una nota corta y etiquetas (solo, groove, sonido, idea).
- Quién la mandó, y opcionalmente lo que el análisis detectó en ese tramo (tonalidad, tempo, acordes).

**Por qué encaja con lo que ya existe:**
- No hay derechos de autor en juego: lo que viaja es el puntero, y cada uno lo abre con **su propia copia**. Es justo la abstracción de fuentes de audio que ya está hecha: el receptor busca el tema en su orden de fuentes (archivos, TIDAL) y salta al tramo.
- Del lado de quien recibe sería un clic: abrir la referencia, que se cargue el tema y el tramo como loop (o como sección), con el análisis y las secciones a mano. Del lado de quien envía: un botón "Enviar a la banda" sobre un loop o una sección del DAW.
- Lleva el análisis a un uso concreto: una banda que comparte referencias con tonalidad y tempo ya puestos.

**Detalles a resolver**
1. **Versiones distintas** del mismo tema (remasterizada, en vivo, edición de radio) desfasan el tiempo. Guardar la duración y avisar si no coincide; permitir un ajuste de desfase.
2. **Identidad del tema entre servicios**: hoy se busca por artista y título; un identificador como el ISRC haría la coincidencia más confiable.
3. **Enlaces a servicios de streaming con tiempo**: no verifiqué cuáles soportan abrir en un minuto exacto; conviene comprobarlo antes de prometerlo.

## 6. Dónde viviría (para pensar)

La separación natural: **el audio y todo lo pesado se quedan locales; lo que se sincroniza es chico** (punteros, notas, secciones, perfiles). Eso baja el costo de la nube casi a cero por usuario y evita guardar música ajena.

| Qué | Dónde | Por qué |
|---|---|---|
| Audio, stems, análisis, modelos, gustos y memoria | Local (la app y el motor) | Privacidad, costo y derechos |
| Cuentas, grupos ("bandas"), referencias, comentarios, notificaciones | Nube (parte paga) | Necesita un servicio que esté siempre prendido |
| Secciones, loops, perfiles de recomendación, ajustes | Local, con **sincronización opcional** a la nube | Para usar la misma configuración en más de una máquina |

**Cuatro caminos, de menos a más infraestructura**

1. **Sin servidor: un formato de referencia que se pega en cualquier chat.** Un texto corto o un enlace (por ejemplo `stemshed://ref?...`) que la app interpreta. WhatsApp sigue siendo el transporte y la app agrega la parte útil: abrir el tema en el tramo exacto. Cuesta casi nada, se puede probar con la banda ya, y dice si esto se usa antes de invertir. **Es mi recomendación para empezar.**
2. **Servicio mínimo propio, de pago.** Cuentas, grupos y un feed de referencias, con la sincronización de secciones y perfiles. Como solo guarda metadatos pesa poco: un servicio administrado (por ejemplo, funciones sin servidor con una base de datos chica) alcanza. Lo caro no es el servidor sino soporte, moderación y cumplimiento de privacidad.
3. **Red federada** (Matrix o ActivityPub): cada banda es una sala, con cifrado de extremo a extremo en Matrix. Menos infraestructura propia, pero más complejidad para el usuario y para nosotros.
4. **Híbrido con modelo abierto:** todo lo local gratis y abierto; la nube como servicio de pago (sincronización, grupos, respaldo). Ojo con la licencia: Rubber Band es GPL, así que el proyecto abierto sería GPL; ofrecer un servicio alojado aparte es compatible, pero hay que revisarlo con cuidado antes de decidir.

**Qué tendría que existir antes de pagar nada**
- Un formato estable de referencia (el punto 1 sirve de prueba).
- Identidad de tema más sólida (ISRC o MusicBrainz).
- Decidir si los grupos son privados (cifrado de extremo a extremo, más difícil de moderar) o públicos.

## 7. Riesgos y deuda a tener presente

- **TIDAL por la vía no oficial**: sin verificar si puede ir en una versión pública; sin términos leídos.
- **Modelos de lenguaje locales** inventan datos musicales (medido): hay que seguir verificando todo contra un catálogo.
- **Análisis armónico**: los acordes extendidos y el audio denso son difíciles; hay que mostrar la confianza y no presentarlo como verdad.
- **Licencias de los pesos** de los modelos (Rubber Band es GPL; los pesos de separación y de lenguaje, a verificar antes de distribuir).
- **Medición pendiente de la Fase 0**: loop, seek y memoria con temas largos, y la prueba auditiva de calidad a 25, 50 y 75 %.
