# Guía para agentes: trabajar en la versión de Windows

Para quien retome el trabajo (persona o agente de IA) sin el contexto de las sesiones anteriores. Léela junto con `CLAUDE.md`, `PLAN.md` (Fase 6) y `docs/windows-instalable.md` (el plan completo).

## Objetivo y prioridad
Una app nativa de Windows (instalador `.exe`, ventana propia, sin Docker). **Docker en Windows se probó y no sirve** (passthrough de GPU complejo, recursos mal asignados, interfaz lentísima): no invertir tiempo en arreglarlo, salvo que se pida.

## Principio central: un solo código
- La interfaz (`proto/player`, Svelte) y el motor (`engine/`, Python con librería estándar) son **los mismos** en Linux, Docker y Windows. Nada de ramas ni copias por plataforma.
- Todo lo que depende del sistema operativo vive en **`engine/osenv.py`**: rutas del venv (`venv/bin` vs `venv\Scripts\*.exe`), carpeta de configuración, carpetas prohibidas, `chmod`, flags de subprocesos, RAM/CPU, DPAPI y Job Object. **Si un módulo necesita saber en qué sistema corre, se agrega ahí**, nunca un `if sys.platform` suelto.
- Para cambios de UI, usabilidad o motor: se hacen una vez y llegan a Windows al reconstruir el instalador. Los textos que mencionan Docker o `npm run engine` hay que condicionarlos por plataforma (pendiente).

## Estado (2026-10-21)
| Hecho (probado solo con simulaciones desde Linux) | Pendiente |
|---|---|
| `osenv.py` y su uso en todos los módulos; `tests/test_osenv.py`; 136 tests pasan en Linux | **Correr los tests en Windows real** |
| Sesión de TIDAL cifrada con DPAPI (`protect_file`, `read_protected`) | Verificar DPAPI en Windows |
| Job Object que mata los hijos al terminar el motor (`kill_children_on_exit`) | Verificar que no quedan procesos huérfanos |
| `tools/windows/` : `diagnostico.ps1`, `serve-check.py`, `webview-check.html` | Correrlos y registrar resultados |
| | `services.open_folder` en Windows; entorno de separación (`requirements-env.win-*.txt`); cáscara; instalador; CI de Windows |

Lo marcado "SIN VERIFICAR EN WINDOWS" en el código lo está de verdad: **no afirmar que funciona hasta correrlo en Windows** y registrar el resultado en este archivo.

## Primer paso en una máquina Windows
1. Python 3.12 o 3.13 (no 3.14: es la versión con más riesgo de dependencias sin rueda).
2. `cd engine` y `python -m unittest discover -s tests`. `test_analysis` necesita el entorno de separación (numpy, librosa): se espera que falle sin él. Los demás fallos son el trabajo de la etapa 1: corregir en `osenv.py` o en el módulo, no con parches por prueba.
3. `tools\windows\diagnostico.ps1` (no instala nada ni usa internet) y `tools\windows\serve-check.py` con `webview-check.html` en Edge y en una ventana WebView2. Con eso se decide Tauri o Electron.
4. `python server.py` en `engine` y consultar `http://127.0.0.1:8770/engine/status`.

## Reglas específicas
- No instalar el entorno de separación (≈ 8 GB) ni modelos sin avisar y sin que el usuario elija la carpeta (fuera del disco del sistema si hay otro).
- Rutas con tildes y espacios (`C:\Users\José Pérez`) deben funcionar: probarlas.
- Cada cambio de plataforma lleva su prueba en `engine/tests` (simulando con `osenv.WINDOWS`) y se verifica también en Linux, donde no debe cambiar nada.
- Avisar antes de abrir ventanas visibles; las pruebas de interfaz usan Chromium sin ventana (`proto/tools/uicheck.py`).
- Windows con GPU AMD/Intel: separación en CPU (lenta, sin medir). NVIDIA: torch cu128; hace falta un equipo con NVIDIA para verificar esa ruta.
- Los datos de cada máquina (versión de Windows, GPU, Python, carpeta de datos) se anotan en el registro del final de este archivo, no en archivos locales: así los ve la próxima sesión.

## Equipos de prueba
(Una fila por equipo: Windows, GPU, RAM, Python, carpeta de datos.)

| Equipo | Windows | GPU | RAM | Python | Datos en |
|---|---|---|---|---|---|
| (pendiente) | | | | | |

## Registro de verificaciones en Windows
(Agregar fecha, equipo, qué se corrió y el resultado. Vacío hasta la primera corrida.)
