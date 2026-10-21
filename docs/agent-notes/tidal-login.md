# Login de TIDAL: "El código del dispositivo ya expiró"

Líneas citadas = código **antes** del cambio (commit `e951ca6`).

## Qué dice tidalapi (medido)
Una sola solicitud real de código, sin autorizar, en una sesión vacía: `expires_in=300.0` (5 min), `interval=2.0`,
`verification_uri_complete='link.tidal.com/<CÓDIGO>'` (el enlace ya lleva el código). `login_oauth()` devuelve un `Future`
que sondea hasta vencer y **no se puede cancelar** (`session.py` `_check_link_login`, bucle `while expiry > 0`).

## Hipótesis
1. **Cierta (motor y interfaz).** `engine/tidal_source.py:123-153`: cada `login_start()` pide un código nuevo sin mirar si ya hay uno vigente.
   `tidal.svelte.ts:50` (`login()`) no se protegía de doble clic. Además la interfaz pierde el código al recargar o volver a montar
   (el estado vive solo en el navegador) mientras el motor sigue con uno pendiente: el usuario toca Conectar de nuevo y se genera otro.
2. **Cierta.** 300 s. La interfaz no tenía cuenta regresiva ni renovación; el aviso "vence a los 5 minutos" solo estaba en Fuentes, no en el asistente (`Inicio.svelte`).
   Al vencer, la pantalla quedaba en "sin sesión" y había que tocar de nuevo.
3. **Falsa.** Ya se usaba `verification_uri_complete` (`tidal_source.py:152`).
4. **Cierta.** Cada intento deja un hilo (`tidal_source.py:134-151`) que sondea hasta vencer; al terminar hace
   `_login.update(state="expired")` / `error` **sin comprobar que siga siendo el intento vigente** (líneas 147 y 149). Un hilo viejo podía
   marcar "venció" mientras el código nuevo estaba vivo, y la interfaz (`tidal.svelte.ts:65-71`) abandonaba el código nuevo.
5. **No probada / improbable.** `_login` está en memoria: un reinicio del motor vuelve a `idle`, no deja `pending`. Lo huérfano es el lado de la interfaz (punto 1).

Causa probable del mensaje: el usuario escribió un código que ya no era el vigente (pidió otro, o pasaron más de 5 min). No pude reproducir el
rechazo real de TIDAL sin autorizar; no sé si TIDAL invalida el código anterior al pedir otro.

## Qué cambió
- `engine/tidal_source.py`: un solo intento (`_attempt`). `login_start()` reutiliza el vigente (si le quedan más de 20 s) o, con `renew`, cancela el anterior
  y pide otro. Un hilo por intento, con `Event` de cancelación; un intento viejo no toca el estado (`_finish`). `status` devuelve `code`, `url`, `expiresAt`,
  `expiresIn`, `attempt`. `/engine/status` incluye `tidal.login` si hay un intento pendiente. Nuevo `login_cancel()`.
  El sondeo ya no usa el `Future` de tidalapi: usa `get_link_login` + `_check_link_login(link, False)` (API privada; si tidalapi la cambia, hay que revisar).
- `engine/server.py`: `POST /engine/tidal/login/start?renew=1` y `POST /engine/tidal/login/cancel`.
- `proto/player/src/lib/tidal.svelte.ts`: `login()` no hace nada si ya hay uno en curso; `connect()` retoma el código vigente del motor; cuenta regresiva;
  al vencer pide otro solo (máx. 2 veces seguidas, después avisa) con "Pedimos un código nuevo."; `renew()` a mano; `cancelLogin()` avisa al motor.
- `proto/player/src/components/TidalLogin.svelte` (nuevo, usado en Fuentes y en el asistente): código, "Vence en m:ss", aviso, Abrir TIDAL, Pedir otro código, Cancelar.
- Nada dispara un login solo: `connect()` en `onMount`/`$effect` solo lee estado; el login empieza únicamente con el botón Conectar TIDAL.

## Pruebas
- `engine/tests/test_tidal_login.py` (10 pruebas, `tidalapi` simulado): campos, reutilización, renovación, hilo viejo cortado, hilo viejo sin pisar estado,
  vencimiento, autorización con guardado, cancelación, `status` con login pendiente, 6 pedidos concurrentes = 1 intento. Suite completa: 93 OK.
- `svelte-check`: 0 errores, 0 advertencias.
- Interfaz con `uicheck.py` contra motor aislado (puerto 8775, config temporal) y un `tidalapi` falso con códigos de 12 s: triple clic en Conectar = un solo código;
  cuenta regresiva (0:11, 0:07); a los ~12 s pasa solo a otro código con "Pedimos un código nuevo."; recargar en otro navegador retoma el mismo código; 0 errores de consola.

## Sin verificar
- Login real completo (no se autorizó nada) y qué hace TIDAL con el código viejo al pedir uno nuevo.
- Que la renovación automática se vea bien en el paso Fuentes del asistente (se probó en la pantalla Fuentes; usan el mismo componente).
- Comportamiento tras un reinicio de Docker.
