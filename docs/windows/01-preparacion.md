# 01. Preparación de la PC con Windows

Objetivo: tener las herramientas, el repo y un diagnóstico de la máquina. No se descarga nada pesado en esta etapa.

## 1. Datos de la máquina
1. Corré `tools\windows\diagnostico.ps1` (clic derecho → *Ejecutar con PowerShell*, o `powershell -ExecutionPolicy Bypass -File tools\windows\diagnostico.ps1`). No instala nada ni usa internet: escribe `diagnostico-shed-stem-studio.txt` en el Escritorio.
2. Pegá su contenido en la sección "Máquina" de [`RESULTADOS.md`](RESULTADOS.md) (sin el nombre de usuario de Windows).

## 2. Herramientas (con `winget`; no requieren administrador salvo donde se indica)

| Para qué | Comando | Pesa aprox. |
|---|---|---|
| Git | `winget install Git.Git` | 60 MB |
| Python (para el motor y las pruebas) | `winget install Python.Python.3.13` y también 3.14 si se quiere probar la misma versión que Linux | 30 MB c/u |
| uv (crea el entorno de separación) | `winget install astral-sh.uv` | 30 MB |
| Node 22 LTS o más nuevo (interfaz) | `winget install OpenJS.NodeJS.LTS` | 30 MB |
| ffmpeg (decodificar archivos locales) | `winget install Gyan.FFmpeg` | 100 MB |
| WebView2 Runtime (si el diagnóstico dice "no encontrado") | `winget install Microsoft.EdgeWebView2Runtime` | 2 MB (bootstrapper) |
| Rust + MSVC (solo para la etapa de la ventana Tauri; **más adelante**) | `winget install Rustlang.Rustup` y `winget install Microsoft.VisualStudio.2022.BuildTools` con la carga de trabajo de C++ | varios GB |

Reabrí la terminal después de instalar para que tome el `PATH`. Verificá: `git --version`, `python --version`, `uv --version`, `node --version`, `ffmpeg -version`.

> Si un identificador de `winget` cambió, buscalo con `winget search <nombre>`. Anotá en `RESULTADOS.md` los que no funcionaron.

## 2 bis. PowerShell
Los comandos de estos archivos son de **PowerShell** (no `cmd`). Las variables de entorno se ponen con `$env:NOMBRE = "valor"` y valen para esa ventana.

## 3. Repo
```powershell
cd $HOME
git clone https://github.com/tatomarinelli/shed-stem-studio.git
cd shed-stem-studio
git checkout -b windows
```
Trabajá en la rama `windows`; no subas nada a `main` hasta decidirlo.

Si el repo es privado o falta acceso, copiá la carpeta del equipo Linux (sin `node_modules`, `.git` opcional).

## 4. Carpetas de trabajo (fuera del repo)
```powershell
$base = "$env:LOCALAPPDATA\ShedStemStudio"
New-Item -ItemType Directory -Force "$base\env","$base\models","$base\data","$base\config" | Out-Null
```
Todo lo pesado (entorno, modelos) va a `$base`. Si el disco `C:` tiene poco espacio, usá otro disco (por ejemplo `D:\ShedStemStudio`) y ajustá `$base`.

## 5. Audio de prueba
- Una **canción real** de 3 a 5 minutos (mejor con batería, bajo y guitarra) copiada a `$HOME\Music\prueba\`, para medir tiempos de separación realistas.
- Un clip sintético corto se genera con `tools\windows\` más adelante (ver etapa 0).

## Criterios de aceptación
- [ ] Diagnóstico pegado en `RESULTADOS.md`.
- [ ] Herramientas instaladas y verificadas.
- [ ] Repo clonado y rama `windows` creada.
- [ ] Hay una canción real de prueba.
