# Monitor de recursos

Muestra en Ajustes → Recursos (y en una barra del menú lateral cuando hay un trabajo activo) qué consume la máquina mientras la app trabaja: CPU, memoria, placa de video, discos y los procesos de la app. Nació para dejar de medir a mano con `nvidia-smi` (el pico de la separación con BS-Roformer-SW fue ≈ 2,7 GiB).

## Cómo funciona

- **Motor:** `engine/resources.py` (solo librería estándar). Un muestreador en un hilo toma 1 muestra por segundo y guarda un buffer circular de 5 minutos (300 muestras).
- **Solo corre con interesados:** cada pedido a `GET /engine/resources` cuenta como una suscripción y renueva un plazo. A los 10 s sin pedidos el hilo se apaga solo, cierra el `nvidia-smi` persistente y borra los valores "actuales" (el historial queda, con un hueco). Un pedido nuevo lo vuelve a arrancar.
- **Interfaz:** `lib/resources.svelte.ts` sondea cada 1 s con `?since=<último t>` solo mientras haya alguien mirando (panel de Ajustes abierto o barra del menú con trabajo activo) **y** la pestaña esté visible. El motor no hace streaming.
- Las memorias se muestran en base 1024 con la etiqueta "GB" (igual que `nvidia-smi`, que da MiB).

## Qué mide y de dónde

| Métrica | Linux (verificado) | Windows (sin verificar) |
|---|---|---|
| CPU % total y núcleos | diferencias de `/proc/stat` (ocupado = todo menos idle+iowait) | `GetSystemTimes` por `ctypes` (ocupado = kernel+user−idle) |
| RAM usada/total/disponible | `/proc/meminfo` (`MemAvailable`) | `GlobalMemoryStatusEx` |
| Placa NVIDIA: uso, memoria, temperatura, potencia | **un solo** `nvidia-smi ... -lms 1000` persistente, leído por un hilo | el mismo `nvidia-smi` (se busca en `PATH` y en `System32`/`NVSMI`) |
| Memoria de video por proceso | `nvidia-smi --query-compute-apps=pid,used_memory` cada 2 s (una consulta suelta) | igual (en WDDM suele dar `[N/A]`: queda en null) |
| Placa AMD (solo si no hay NVIDIA) | `/sys/class/drm/card*/device/gpu_busy_percent`, `mem_info_vram_*` y, si hay, `hwmon` (temperatura, potencia) | no |
| Discos | `shutil.disk_usage` de `dataDir`, `separationEnvDir`, `separationModelsDir`, `ollamaModelsDir` (de `settings.effective()`), deduplicados por disco; si la carpeta no existe se usa su primer padre que exista | igual |
| Procesos | `/proc/<pid>/stat` (ticks, ppid, inicio) y `/proc/<pid>/status` (`VmRSS`) | no (lista vacía) |

Otra plataforma: respuesta con campos nulos, sin excepción.

**Procesos.** Se muestran el motor y todos sus descendientes (separación `audio-separator`, análisis, `ffmpeg`, el Ollama que levantó el motor) y, aparte, cualquier proceso **ajeno** que figure en `query-compute-apps` (marcado "fuera de la app", `inApp: false`): así se ve un Ollama de systemd o una separación lanzada a mano. El rol sale de la línea de comandos (`audio-separator` → Separación, `analyze` → Análisis, `ollama` → Ollama). Nuestras propias consultas a `nvidia-smi` no figuran. El CPU por proceso es "100 % = un núcleo" y se calcula con diferencias, indexadas por `(pid, inicio del proceso)` para que un pid reutilizado no dé basura; la primera vez que se ve un proceso da null. Los pids de la placa que no existen en nuestro `/proc` (otro espacio de procesos, p. ej. Docker) se omiten.

Los trabajos activos salen de `services.active_jobs()`.

## API

`GET /engine/resources[?since=<t en ms>]` (con la validación de Origen de siempre; un `since` inválido se ignora):

```
{ "now": 1792598824726,          // ms desde epoch
  "intervalMs": 1000,
  "platform": "linux",
  "cpu":  { "percent": 2.7, "cores": 16 },
  "ram":  { "totalBytes", "usedBytes", "availableBytes", "percent" },
  "gpus": [ { "index", "name", "vendor": "nvidia"|"amd", "utilPercent", "memUsedBytes", "memTotalBytes", "tempC", "powerW", "unverified"? } ],
  "disks": [ { "path", "keys": ["dataDir", ...], "totalBytes", "freeBytes", "usedPercent" } ],
  "processes": [ { "pid", "role", "name", "inApp", "cpuPercent", "rssBytes", "gpuMemBytes" } ],
  "jobs": [ { "kind", "label", "percent"?, "step"? } ],
  "errors": ["gpu"],             // fuentes que fallaron en la última muestra
  "history": { "t": [ms...], "cpu": [%], "ram": [%], "gpuUtil": [%], "gpuMem": [bytes] } }
```

- Todo valor que no se pudo medir es `null`; `gpus` vacío = no hay placa medible.
- `history` es de la primera placa (índice 0). Con `since`, solo trae las muestras con `t > since`.
- Los valores "actuales" (cpu, ram, gpus, discos, procesos) llegan vacíos en el primer pedido tras un apagado, hasta la primera muestra (~1 s). El CPU % necesita dos lecturas.
- Procesos y memoria de video por proceso se refrescan cada 2 s; discos cada 10 s.

## Decisiones

- **Hilo con plazo, no streaming:** la interfaz ya sondea otras cosas; un sondeo de 1 s es simple, funciona detrás del proxy de Vite y no deja conexiones abiertas.
- **Un único `nvidia-smi -lms 1000`:** lanzar uno por segundo cuesta mucho más. Si el proceso muere, se reintenta cada 30 s mientras haya interesados. Mientras `nvidia-smi` está vivo pero todavía no dio su primera línea, no se cae a AMD (en esta máquina la iGPU AMD del procesador quedaba "primera" en la ventana de arranque).
- **Fallas aisladas:** cada fuente va en su propio `try`; una que falla deja null y se anota en `errors`, las demás siguen.
- **Estructura multiplataforma:** `LinuxPlatform`, `WindowsPlatform` y `NullPlatform` con la misma interfaz chica (`cpu_times`, `cores`, `memory`, `processes`, `describe`). `windll` se busca de forma perezosa (`getattr(ctypes, "windll", None)`): importar el módulo en Linux nunca falla.
- **Barra del menú:** aparece con un trabajo activo (el sondeo de servicios que ya existe más `separation.busy`), muestra la memoria de video (o la RAM si no hay placa) y se desmonta sola al terminar. Se oculta en el ancho de celular (el menú pasa a ser una barra inferior).

## Qué se verificó

- 23 pruebas en `engine/tests/test_resources.py`: CPU por diferencias, parseo de `nvidia-smi` (incluido `[N/A]` en potencia y basura), buffer circular y `since`, apagado sin suscriptores (hilo y proceso `nvidia-smi` falso que muere), ausencia de GPU, falla de una fuente sin tumbar las demás, procesos hijos con `/proc` falso (reuso de pid, `nvidia-smi` propio excluido, procesos ajenos con GPU), discos deduplicados, AMD con carpeta falsa, Windows con `kernel32` simulado, plataforma desconocida.
- En vivo, con la RTX 5080 y un motor aislado: los números del monitor coinciden con `nvidia-smi`. Separando un clip sintético de 75 s con BS-Roformer-SW, el monitor mostró el proceso de separación con **2,7 GB** de video (`nvidia-smi`: 2784 MiB), la placa al 99–100 % y 11,6 GB de memoria de video en total (`nvidia-smi`: 11 889 MiB).

- **Cómo se vio la separación:** la lancé a mano con `audio-separator` (el motor aislado de la prueba no tiene un venv), por eso en la tabla figuró como "Separación (fuera de la app)", detectada por la ruta de `query-compute-apps`. En vivo solo se confirmó la fila "Motor"; la detección de **descendientes** del motor (`inApp: true`, con sus CPU/RAM) está cubierta por las pruebas con `/proc` falso, no con una separación lanzada por el motor.
- **Costo del propio monitor** (misma página, Ajustes, 60 s, en % de un núcleo; resolución 0,017 %): con Recursos abierto, motor 0,10 % y `nvidia-smi` 0,00 % (un solo proceso `nvidia-smi` vivo); con Recursos cerrado, motor 0,00 % y ningún `nvidia-smi`. A los 10 s de cerrar el panel o la página no queda ninguno, y matar el motor con SIGTERM mientras muestrea también se lleva al `nvidia-smi`.
- Ajuste de paso: en Ajustes, la lista "Tu equipo" (`.hw`) desbordaba el ancho de celular con rutas largas; ahora parte la línea.

## Qué NO se verificó

- **AMD:** se probó con una carpeta falsa. Además, esta máquina tiene la iGPU del procesador AMD y el monitor la leyó por sysfs (uso, 0,5 GB de memoria, temperatura), lo que confirma que las rutas existen en un kernel real, pero **no** se probó una placa AMD dedicada bajo carga ni la potencia (`power1_average`). Se marca `unverified: true` y la interfaz avisa "Lectura de AMD sin verificar en hardware real".
- **Windows:** `GetSystemTimes`/`GlobalMemoryStatusEx` por `ctypes` y la búsqueda de `nvidia-smi.exe` están escritos pero probados solo con simulaciones; los procesos de la app no están implementados.
- **Docker:** el `/proc` es el del contenedor; la memoria de video por proceso solo calza si el contenedor ve los pids del equipo (normalmente no). Solo se comprobó el comportamiento esperado, no con un contenedor.
- Varias placas NVIDIA: se parsea y se muestra cada una, pero el historial es solo de la primera.
- Sin Intel.

## v2 (fuera de alcance de esta versión)

- Alertas: "poca memoria de video para el modelo elegido", "disco por llenarse".
- Historial persistente (hoy se pierde al apagar el muestreador/motor).
- Red y velocidad de descarga.
- Métricas AMD/Intel en Windows (contadores de rendimiento).
- NVML por `ctypes` (evita el proceso `nvidia-smi` y la consulta suelta por procesos).
- Procesos de la app en Windows.
