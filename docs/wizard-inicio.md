# Asistente de primer inicio

Estado: **implementado** (2026-10-21) con las tres decisiones aprobadas (solo la primera vez y después un aviso; TIDAL antes del perfil; "Armar mi primer disco" requiere el modelo de chat). Ver "Qué se implementó" al final. Objetivo: que la primera vez que se abre Shed Stem Studio el usuario quede con todo configurado (entorno, modelos, música, TIDAL, perfil) sin tocar una terminal, y que cada paso sea explícito: nada se descarga solo.

## Principios

1. **Cada paso se puede saltar** ("Más tarde") y retomar desde Ajustes → *Configuración inicial*. Saltar un paso solo apaga lo que depende de él, y la app lo dice.
2. **Nada se baja sin un clic.** Antes de cada descarga se muestra el tamaño, el destino y el espacio libre. Hay barra con MB, velocidad y tiempo restante (componente `Progress`, ya existe).
3. **El estado sale del motor, no de la pantalla.** Si se cierra la pestaña a la mitad, al volver se retoma donde corresponde porque cada paso se calcula de lo que realmente está instalado.
4. **Las descargas siguen en segundo plano.** Mientras baja el entorno o un modelo, el usuario puede avanzar al paso siguiente; un chip "Descargando…" queda visible en todas las pantallas hasta que terminan.
5. **Textos cortos, en rioplatense, sin jerga** (nada de "venv", "CUDA", "Ollama" salvo como detalle opcional).

## Pasos

| # | Paso | Qué hace | Cómo sabe que está hecho | Si se salta |
|---|---|---|---|---|
| 0 | **Bienvenida** | Detecta el motor. Si no responde, muestra cómo iniciarlo (Docker o instalador) y reintenta solo. | `GET /engine/status` responde | No se puede continuar sin motor |
| 1 | **Tu equipo** | Muestra GPU, memoria y espacio libre. Avisa si no hay GPU (la separación irá lenta) o si falta disco. | `GET /engine/hardware` | — (informativo) |
| 2 | **Dónde guardar** | Carpetas de datos, modelos y entorno con la sugerencia según el espacio libre. En Docker las muestra de solo lectura con la variable que las cambia. | `settings` con rutas válidas | Se usan las rutas por defecto |
| 3 | **Separar en instrumentos** | Instalar el entorno (≈ 4 GB de descarga, ≈ 8 GB en disco) y descargar el modelo (700 MB). Dos botones, uno por cosa, con barra. | `env.present` y `sep_model_present` | No se puede separar; el resto funciona |
| 4 | **Tu música** | Agregar carpetas (selector que ya existe) y/o **conectar TIDAL** (código de dispositivo: la app muestra un código y un enlace, el usuario autoriza en el navegador). Al menos una fuente. | `musicFolders` no vacío o TIDAL conectado | Sin fuentes: Música vacía y recomendaciones sin historial |
| 5 | **Modelo de recomendaciones** | Sugiere el modelo que entra en el equipo (Mistral Nemo 12B si hay 12 GB libres de VRAM, uno más chico si no) y lo descarga a la carpeta elegida. Permite escribir otro nombre. | Hay un modelo de chat instalado | Recomendaciones apagadas |
| 6 | **Tu perfil** | Cuestionario corto (instrumento, qué querés mejorar, estilos que amás o evitás, artistas imprescindibles, cuánta música nueva). Si TIDAL está conectado, **viene pre-cargado** con lo que se dedujo de tus favoritos (marcado como "deducido, corregí lo que no cuadre"). Luego, el asistente de perfiles por horario ya existente (`PresetWizard`) para crear el primero. Opt-in explícito para hora y clima (solo se envía la ciudad). | `profile` completo y al menos un perfil | Se usa el perfil por defecto del motor |
| 7 | **Listo** | Resumen con tilde o aviso en cada paso, qué quedó pendiente y un botón **Armar mi primer disco**. Va a Recomendaciones. | — | — |

## Pantalla (esquema de un paso)

```
┌──────────────────────────────────────────────────────────────┐
│  Primeros pasos            ●──●──●──○──○──○──○     Paso 3 de 7│
├──────────────────────────────────────────────────────────────┤
│  Separar en instrumentos                                      │
│  Para estudiar con stems hacen falta dos cosas:               │
│                                                               │
│  ① Entorno de separación        8 GB en /mnt/plexdata/…  [Instalar]
│     ▓▓▓▓▓▓░░░░░░░░ 42 % · 1,9 GB de ≈ 4,6 GB · 21 MB/s · faltan 2 min
│  ② Modelo de separación         700 MB                  [Descargar]
│                                                               │
│  Hay espacio de sobra: 67 GB libres.                          │
│                                                               │
│  [Atrás]            [Más tarde]            [Siguiente]        │
└──────────────────────────────────────────────────────────────┘
```

- Barra de pasos arriba, clicable para volver. Un solo bloque de contenido por paso.
- "Siguiente" se habilita siempre que no haya un error; con una descarga en curso el paso se da por empezado y se puede avanzar.
- Foco y teclado: Enter avanza, Esc no cierra (hay que elegir "Más tarde").

## Piezas del motor

- `GET /engine/setup/status` → `{steps: [{id, state: "done"|"pending"|"running"|"error"|"skipped", detail}], ready: bool}`. Se calcula de lo real: entorno presente, modelo presente, fuentes, modelo de chat instalado, perfil completo. No guarda estado propio salvo los pasos saltados.
- `settings.setup = {done: bool, skipped: [ids]}` (nuevo campo validado) para recordar "ya vio el asistente" y qué saltó.
- `POST /engine/setup/skip` y `POST /engine/setup/finish`.
- Reutiliza lo que ya existe: `/engine/env/install`, `/engine/models/separation/download`, `/engine/models/<id>/pull`, `/engine/tidal/login/*`, `/engine/hardware`, `/engine/recs/profile`, `/engine/recs/presets`.
- **Pre-carga del perfil** desde TIDAL: ya existe la deducción en `seed_import`/`profile.py`; falta un `GET /engine/recs/profile/suggested` que la arme desde `sources.json` + géneros de MusicBrainz (con la etiqueta *deducido*).
- Descargas en segundo plano: ya corren en hilos; falta permitir **entorno + modelo de chat en paralelo** (hoy `pull_start` rechaza dos pulls simultáneos del mismo tipo, pero el entorno es independiente).

## Piezas de la interfaz

- `screens/Inicio.svelte` (pantalla completa, sin menú lateral) con `lib/setup.svelte.ts` (estado y navegación) y un componente por paso en `components/setup/`.
- Chip global **Descargas** en la barra de transporte o el menú, alimentado por `GET /engine/services` (ya devuelve los trabajos en curso).
- Reglas de arranque: al abrir la app, si `setup.done` es falso y falta algo esencial, se abre el asistente; si no, no molesta. Ajustes tiene "Repetir configuración inicial".
- Reutilizar `FolderPicker`, `Progress`, `ProfileForm`, `TagInput` y `PresetWizard` sin duplicarlos.

## Casos límite

- **Sin motor:** el paso 0 se queda esperando y explica cómo iniciarlo; no avanza.
- **Docker:** las rutas del paso 2 son de solo lectura; el modelo de chat necesita el perfil `llm` (el paso 5 lo detecta y explica el comando).
- **Sin GPU:** aviso claro en los pasos 1 y 3; se permite seguir.
- **Poco espacio:** el botón de descarga se bloquea con el motivo ("necesita 8 GB y hay 5 GB libres") y se sugiere otra carpeta.
- **Descarga que falla o sin internet:** mensaje con el motivo y botón *Reintentar*; el resto del asistente sigue.
- **TIDAL no autoriza a tiempo:** el código vence; se ofrece pedir otro.
- **Cierre de pestaña:** al volver se retoma; las descargas que seguían en el motor siguen.

## Verificación

- Pruebas del motor con datos sintéticos: `setup/status` para cada combinación (todo faltante, solo entorno, etc.).
- `uicheck.py` contra un motor **aislado y vacío** (carpeta de configuración temporal, rutas temporales, descargas simuladas con un servidor local): recorrer los 7 pasos con clics, saltar un paso, retomar, forzar un error de descarga.
- No se descarga nada real en las pruebas automáticas. La descarga real se prueba una vez, a mano, en el stack de Docker de prueba.
- Capturas del paso 3 (progreso), 6 (perfil pre-cargado) y 7 (resumen).

## Orden de trabajo

1. `setup/status` + campo `setup` en los ajustes + pruebas.
2. Chip global de descargas.
3. Esqueleto del asistente (navegación, barra de pasos, saltar/retomar) con los pasos 0 a 2.
4. Paso 3 (separación) y paso 5 (modelo de chat), con la elección según el equipo.
5. Paso 4 (música y TIDAL) reutilizando Fuentes.
6. Paso 6: perfil pre-cargado desde TIDAL y creación del primer perfil.
7. Paso 7 y arranque automático; "Repetir configuración inicial" en Ajustes.
8. Recorrido completo con motor vacío y capturas.

## Decisiones abiertas

1. ¿El asistente aparece solo en el primer inicio o también cuando falte algo esencial más adelante? (Propuesta: solo la primera vez; después, un aviso discreto con enlace.)
2. ¿Conectar TIDAL antes o después del perfil? (Propuesta: antes, para pre-cargar el perfil con tus favoritos.)
3. ¿Permitir *Armar mi primer disco* sin modelo de chat? (Propuesta: no; sin modelo ese botón se reemplaza por un enlace al paso 5.)

## Qué se implementó

- **Motor:** `engine/firstrun.py` (`GET /engine/setup/status`, `POST /engine/setup/{skip,unskip,finish,reset}`), campo `setup` en los ajustes (validado), `GET /engine/recs/profile/suggested` (perfil deducido de los favoritos). 7 pruebas nuevas.
- **Interfaz:** `screens/Inicio.svelte` (8 páginas, barra de pasos clicable, Atrás / Más tarde / Siguiente / Salir), `lib/setup.svelte.ts`, aviso discreto cuando se cerró el asistente con pasos pendientes, chip de descargas en el menú, "Repetir configuración inicial" en Ajustes. `ProfileForm` acepta un perfil pre-cargado.
- **Se abre solo** la primera vez que falta algo esencial; si todo ya está configurado no aparece. Al volver retoma en el primer paso sin resolver.
- **Verificado** con un motor aislado y vacío (configuración temporal, sin TIDAL ni Ollama) y Chromium sin ventana: bienvenida → equipo → carpetas → separación (botones habilitados/deshabilitados según corresponde) → "Más tarde" (persiste) → música → modelo (aviso de servidor apagado) → perfil (se guarda) → resumen → "Terminar igual" → aviso. Reapertura retomando en el paso correcto. También en el stack de Docker (rutas de solo lectura con su variable). Con la instalación real el asistente no aparece (todo completo).
- **Sin verificar:** conectar TIDAL desde el asistente (no se inició sesión real), la descarga real de un modelo desde el asistente (se usa el mismo código que Ajustes, ya probado con el entorno), el chip de descargas con una descarga en curso, el perfil pre-cargado de un usuario nuevo (con los favoritos de la instalación real devuelve 8 estilos y 10 artistas, pero parte viene de lo ya declarado; los géneros de un usuario recién conectado aparecen a medida que MusicBrainz los lee), y el espacio libre por carpeta dentro de Docker (muestra "?" mientras carga).
- **Pendiente del plan:** permitir instalar el entorno y descargar el modelo de chat a la vez sin que se pisen (los trabajos son independientes pero no se probaron en paralelo).

### Ajuste del 2026-10-21 (segunda vuelta)

- Las páginas pasaron de 8 a 6: **Bienvenida, Dónde guardar, Modelos, Tu música, Tu perfil, Listo**. "Tu equipo" ahora es un recuadro dentro de **Modelos**, y esa página reúne las tres piezas (entorno de separación, modelo de separación, modelo de recomendaciones), cada una con una línea que explica para qué sirve.
- "Más tarde" en Modelos salta los dos pasos del motor que cubre (`separacion` y `modelo`). Los pasos del motor no cambian.
- Los botones Atrás / Más tarde / Siguiente van dentro de la columna de contenido (centrada, 760 px) y quedan fijos abajo aunque la página sea larga.
- Dato aclarado: el **entorno** de separación pesa ≈ 8 GB en disco (medido: 7,6 GB); el **modelo** de separación pesa ≈ 700 MB (699 MB medido). Son dos cosas distintas.
