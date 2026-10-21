# Windows

Todo lo que es exclusivo de la app de escritorio para Windows. La interfaz (`proto/player`) y el motor (`engine/`) son los mismos de siempre: acá solo vive lo que los envuelve. Guía para agentes: `docs/windows-agentes.md`; plan: `docs/windows-instalable.md`.

## Qué se entrega
- **Zip portable**: `ShedStemStudio.exe` + `runtime/` (Python embebido, motor, interfaz). Se descomprime en cualquier carpeta y se ejecuta; no instala nada.
- **Instalador** NSIS por usuario (sin administrador) con el mismo contenido.

El entorno de separación (≈ 8 GB) y los modelos **no** vienen: se eligen y se bajan desde Ajustes.

## Estructura
```
windows/
  shell/        Cáscara Tauri 2 (Rust): lanza el motor, espera /engine/status y muestra la interfaz que él sirve
    ui/           pantalla de carga (la única interfaz propia de la cáscara)
    src-tauri/    código Rust, tauri.conf.json, íconos
  build/        build.ps1 arma runtime/, compila la cáscara y genera el zip y el instalador
    cache/ stage/ out/   (no se versionan)
```

## Cómo funciona
1. La cáscara busca `runtime/` junto al `.exe` (o, en desarrollo, el repo con el Python del sistema).
2. Lanza `python engine/server.py <puerto>` sin consola, en el puerto 8770 (o uno libre si está ocupado), con `STEMSHED_UI` apuntando a la interfaz compilada. Registro en `%LOCALAPPDATA%\ShedStemStudio\logs\engine.log`.
3. Cuando `/engine/status` responde, la ventana (WebView2) navega a `http://127.0.0.1:<puerto>/`. El motor sirve la interfaz con COOP/COEP (`engine/webui.py`).
4. Al cerrar, mata el árbol de procesos del motor; un Job Object lo cubre si la cáscara muere de golpe.

## Desarrollo en caliente
`python windows/dev.py` y abrir http://127.0.0.1:5173/. La interfaz (Vite) se actualiza al guardar; el motor se reinicia solo al guardar un `.py`. No hace falta compilar ni armar el zip: eso es solo para entregar.

## Construir
Requisitos: Node, Rust (`rustup`) y las herramientas de C++ de Visual Studio.
```
powershell -ExecutionPolicy Bypass -File windows\build\build.ps1            # zip + instalador
powershell -ExecutionPolicy Bypass -File windows\build\build.ps1 -SkipInstaller
```
Descarga una vez (a `build/cache`): Python embebible de python.org, `tzdata`, las dependencias del motor (`engine/requirements-engine.txt`) y `uv` (versión fijada y verificada con el `.sha256` de su release). El runtime se prueba solo (importa el motor y arranca `uv`) antes de compilar la cáscara.

Estado y lo que falta: `docs/estado-windows.md`.

## Pendiente
Ver el registro de `docs/windows-agentes.md`. Sin hacer: instalación del entorno de separación con `uv`, asistente de primeros pasos en Windows, bandeja, diálogo nativo de carpetas, firma de código, actualizaciones.
