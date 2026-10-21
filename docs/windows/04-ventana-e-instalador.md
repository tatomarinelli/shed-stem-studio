# 04. Ventana de escritorio, motor empaquetado e instalador

Se empieza **después** de aprobar la etapa 0 (`02-etapa0-prototipos.md`) y la 03 (motor portable). Visión y decisiones: [`../windows-instalable.md`](../windows-instalable.md).

## Etapa 2: ventana + motor empaquetado

### 2.1 Prototipo mínimo con Tauri 2
- Instalar Rust y las herramientas de C++ de Visual Studio (ver `01-preparacion.md`).
- Crear la cáscara en `desktop/` (nuevo): `npm create tauri-app@latest` (plantilla vanilla, sin framework) y reemplazar la interfaz por una **ventana que carga `http://127.0.0.1:<puerto>/`**, donde la sirve el motor.
- El motor sirve la interfaz construida (`proto/player/dist`) con los encabezados `Cross-Origin-Opener-Policy: same-origin` y `Cross-Origin-Embedder-Policy: require-corp`. **Hoy la sirve nginx en Docker**: hay que agregar al motor una ruta estática (`GET /` y archivos de `dist/`) con esos encabezados, y un tipo MIME correcto para `.wasm` y `.js` (el worklet).
- Comprobar dentro de **WebView2 real**: `webview-check.html` (todo "sí"), el reproductor con un tema separado (audio, loop, velocidad, click) y la sincronía del cabezal.
- **Decisión**: si el audio o el aislamiento de origen fallan → probar Electron con la misma estructura (la ventana carga la misma URL).

### 2.2 Motor como proceso hijo
- La cáscara elige un **puerto libre** y un **token aleatorio**, lanza `python engine\server.py <puerto>` con `STEMSHED_HOST=127.0.0.1`, `STEMSHED_ORIGINS=http://127.0.0.1:<puerto>`, y le pasa el token por variable de entorno; la ventana lo usa en sus pedidos. (Falta implementar la validación del token en el motor: es el "emparejamiento" de `docs/publicacion.md`, versión de escritorio.)
- Espera `/engine/status` antes de mostrar la ventana, con pantalla de carga y mensaje si no arranca en N segundos (con el registro del motor a mano).
- Al cerrar la ventana: pregunta si apaga el motor; al salir, `POST /engine/shutdown` y, si no responde, termina el árbol de procesos.
- Una sola instancia (si ya hay una, la trae al frente).
- Ícono en la bandeja: Abrir / Apagar el motor / Salir.

### 2.3 Python embebido
- Incluir una distribución de Python "standalone" (por ejemplo la de `python-build-standalone` de Astral) dentro de la aplicación, con `engine/` como archivos `.py`, y `uv.exe`.
- El entorno de separación **no** va dentro: se crea en `%LOCALAPPDATA%\ShedStemStudio\env` desde el asistente con `uv` y `engine\requirements-env.win-cpu.txt` o `...win-nvidia.txt` según la GPU detectada.
- Elegir la variante: NVIDIA con controlador reciente → `win-nvidia` (CUDA 12.8; **verificar versión mínima del controlador**); cualquier otro caso → `win-cpu` con una advertencia de velocidad.

### Criterios de aceptación (etapa 2)
- [ ] Una ventana que lanza el motor y muestra la interfaz; al salir no quedan procesos.
- [ ] El reproductor funciona con audio dentro de la ventana.
- [ ] Sin Python instalado en el sistema, el motor arranca con el Python embebido.

## Etapa 3: instalador por usuario
- **Instalador**: el empaquetador de Tauri genera NSIS (`.exe`) y MSI (`.msi`). Usar **NSIS**, instalación **por usuario** (`%LOCALAPPDATA%\Programs\Shed Stem Studio`), sin pedir administrador.
- Accesos directos en el menú Inicio y opcionalmente en el Escritorio; entrada en "Aplicaciones instaladas".
- **Desinstalador**: borra el programa y **pregunta** si se borran también `%APPDATA%\ShedStemStudio` y las carpetas del entorno y modelos (decenas de GB); nunca lo hace solo.
- WebView2: incluir el bootstrapper de Microsoft (`Evergreen`) para Windows 10 si no está.
- Tamaño objetivo del instalador: del orden de 100 MB (a medir).
- Probar: instalar, abrir, actualizar encima, desinstalar con y sin borrar datos.

### Criterios de aceptación (etapa 3)
- [ ] El `.exe` instala, abre y desinstala limpio en una VM o PC sin herramientas de desarrollo.
- [ ] Rutas con tildes y espacios en el nombre de usuario.
- [ ] El desinstalador pregunta por los datos.

## Etapa 5: firma y actualizaciones
- **Firma de código** (Authenticode): sin firma, SmartScreen avisa a los usuarios nuevos. Opciones: certificado OV/EV, o el servicio de firma de Microsoft; decisión abierta (`DECISIONES.md`). Firmar el instalador y el ejecutable de la cáscara.
- **Actualizaciones de la app**: el actualizador de Tauri (par de claves propio, la clave privada **nunca** va al repo) con publicación en GitHub Releases: comprobar al iniciar, descargar con aviso, instalar al cerrar.
- **Entorno de separación**: versión fijada; si una versión nueva de la app necesita otra, el asistente ofrece "Actualizar entorno" (descarga explícita).
- Probar una actualización de la versión N a N+1.

## Integración continua (borrador)
Archivo `.github/workflows/windows.yml` (aún no creado):
```yaml
name: windows
on: [push, pull_request]
jobs:
  engine:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.13" }
      - run: python -m unittest discover -s engine/tests
  ui:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: lts/* }
      - run: npm ci && npm run build
        working-directory: proto/player
```
Más adelante: construir el instalador, instalarlo en silencio y consultar `/engine/status`. Las pruebas con GPU no pueden correr en los ejecutores de GitHub.
