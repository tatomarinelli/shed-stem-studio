# Spotify y YouTube Music como fuentes (etapa 1)

Estado: base lista y probada con respuestas simuladas; **sin probar contra las cuentas reales** (necesita que el usuario registre sus apps). Código: `engine/providers.py` (interfaz común, OAuth PKCE, almacén), `engine/spotify_source.py`, `engine/ytmusic_source.py`; interfaz en Ajustes → "Cuentas de música".

## Decisiones

1. **Los conectores viven en el motor, no en el navegador** (cambia lo que decía `architecture.md` §4). Motivo: guardar los tokens con el almacén del sistema (DPAPI / llavero), igual que TIDAL, y que el mismo código sirva a la web y a la app de escritorio. El navegador solo abre la autorización y consulta al motor.
2. **Interfaz común** (`providers.Provider`): `status()`, `library()` → `{albums, tracks, playlists}`, `playlist_tracks(id)`, `auth_start()`, `logout()`, más `capabilities` (`audio`, `albums`, `playlists`, `savedTracks`, `write`). TIDAL entra por un adaptador (`TidalProvider`) y conserva su login por código de dispositivo.
3. **Cada usuario registra su propia app** (Client ID en Ajustes). Nada de credenciales en el repo; el Client ID (y, en Google, el Client Secret) se guardan cifrados en `providers-apps.json`.
4. **Solo lectura, estructural**: solo se piden permisos de lectura (`user-library-read`, `playlist-read-private`, `playlist-read-collaborative`; `youtube.readonly`), así que no hay forma de escribir en la cuenta. Si más adelante se agrega "guardar playlist", va con confirmación explícita y sin borrar nada (regla del proyecto).
5. **Desconectar** borra la sesión local (y la entrada del llavero). No llama a la red: revocar el permiso se hace desde la cuenta del servicio.
6. **Fecha de guardado**: Spotify (`added_at` de `/me/albums`, `/me/tracks` y de cada tema de playlist) y YouTube (`publishedAt` del ítem en la lista de Me gusta) vienen ordenados del más nuevo al más viejo (`newest_first`). Las playlists de Spotify no tienen fecha (quedan en el orden de la cuenta); las de YouTube usan su fecha de creación. TIDAL: **pendiente** (`tidalapi` admite `order=DATE`, sin probar).
7. Se guardan `isrc` (temas) y `upc` (discos) de Spotify para coincidir después con archivos locales y MusicBrainz.

## Autenticación

| | Spotify | YouTube Music |
|---|---|---|
| Vía | Web API oficial, OAuth Authorization Code + PKCE (sin secreto) | YouTube Data API v3 oficial, OAuth de Google (cliente de escritorio) + PKCE |
| Redirección | `http://127.0.0.1:<puerto>/engine/oauth/callback` (Spotify no acepta `localhost`; la IP literal por HTTP sí) | la misma. Google documenta solo `http://127.0.0.1:<puerto>` sin ruta: **verificar que acepte la ruta** al probar con una cuenta real; si no, hay que atender `?code&state` en `/` |
| Secreto | ninguno | Google lo marca opcional en el intercambio para clientes de escritorio, pero hoy el motor lo pide y lo manda si está (sin verificar si hace falta) |
| Límites | Desde marzo de 2026, apps nuevas en modo desarrollo: dueño con **Premium**, 5 usuarios por app | Sin verificar la app, Google muestra la pantalla de "app no verificada"; en modo prueba solo entran usuarios de prueba cargados (**sin verificar**: caducidad de 7 días del refresh token en modo prueba, se informa en las fuentes de la comunidad pero no lo pude confirmar en la doc oficial). Cuota 10.000 unidades diarias |

Seguridad del flujo: `state` aleatorio, de un solo uso y con vencimiento de 10 minutos; `code_verifier` solo en memoria; la página de vuelta escapa todo, no cachea y no manda referer; la renovación de tokens va con candado (los refresh tokens pueden rotar); los `next` de paginación solo se siguen si son del mismo host de la API.

## Qué da cada API (límites reales)

- **Spotify**: álbumes y temas guardados (con fecha), playlists. Desde 2026 los temas de una playlist solo se leen en las **propias o colaborativas** (`/playlists/{id}/items`); en las ajenas la interfaz lo explica (`readable: false`). El motor acepta las dos formas de respuesta (`item` y `track`).
- **YouTube Music**: la API oficial **no expone** los álbumes guardados ni la biblioteca de Music. Da las playlists y la lista de "Me gusta" (videos); se filtran los de categoría Música (`videos.list`, categoría 10) y el artista sale del canal "Artista - Topic". Los álbumes de YT Music quedan sin cubrir.
- **`ytmusicapi`** (no oficial: cookies o encabezados del navegador) sí lee la biblioteca completa de Music, pero depende de endpoints internos que cambian y va contra los términos. Según `PLAN.md` (Fase 5) solo como complemento aparte, nunca en la versión pública. **No implementado.**

## Audio: no se puede obtener, y no se elude

Ni Spotify ni YouTube Music entregan audio para procesar (DRM y términos de uso). Por eso `capabilities.audio` es `false`, ninguno entra en `audioSources` (`settings.validate` ya rechaza ids desconocidos) y no se agregó ninguna descarga. Alternativa implementada por diseño: un tema de Spotify/YouTube es una referencia (artista, título, disco, ISRC, duración) y "Enviar al estudio" lo busca en los **archivos locales** (`sources.resolve_track`). Pendiente: usar ISRC y duración para mejorar esa coincidencia, y mostrar "no lo tenés en tus archivos" con los datos de la fuente.

## Guardado de credenciales por plataforma (`osenv.write_protected`)

| Plataforma | Dónde queda | Verificado |
|---|---|---|
| Windows | cifrado con DPAPI en el archivo (se cifra en memoria y se escribe a un temporal que reemplaza al archivo: nunca hay texto plano en disco) | solo simulado (`_dpapi` reemplazado); sin correr en Windows real |
| Linux con llavero (`secret-tool`/libsecret) | el secreto va al llavero; el archivo solo guarda una marca | probado con el llavero real de esta máquina (guardar, leer, borrar) y simulado en las pruebas |
| Linux sin llavero | archivo con permisos 600, **sin cifrar** (el motor nunca tuvo otro almacén en Linux; TIDAL sigue igual) | probado; la interfaz lo avisa |

La sesión de TIDAL todavía usa `protect_file` (texto plano brevemente); migrarla a `write_protected` queda pendiente.

## Pendiente (próximas etapas)

1. Probar el flujo real con una app de Spotify y una de Google (hace falta el usuario) y registrar el resultado aquí.
2. Integrar las bibliotecas a `catalog.py` (hoy el catálogo solo junta archivos locales y TIDAL): instantánea en disco por fuente, filtro por fuente y orden "guardado reciente" en Música, con origen por ítem.
3. Coincidencia con archivos locales por ISRC/duración; "Enviar al estudio" para temas de Spotify/YT.
4. Fecha de guardado de TIDAL; migrar su sesión a `write_protected`.
5. Decidir si se agrega `ytmusicapi` como complemento no público.
6. Verificar en Windows real: DPAPI de `write_protected`, el flujo OAuth (puerto y firewall) y la apertura del navegador desde la ventana WebView2.
7. Tarjetas de Spotify/YT en Fuentes con conteos (hoy solo conectar/desconectar en Ajustes).
