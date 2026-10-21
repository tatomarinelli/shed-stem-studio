# Decisiones abiertas y riesgos

## Decisiones (con la propuesta actual)
| # | Decisión | Propuesta | Se decide con |
|---|---|---|---|
| 1 | Cáscara: Tauri o Electron | **Tauri 2**; Electron solo si falla el audio o el aislamiento de origen en WebView2 | Etapa 0 (E) y etapa 2.1 |
| 2 | Versión de Python en Windows | La que instale todo sin fallas: **3.14** (la de Linux) y, si no, **3.13** | Etapa 0 (A) |
| 3 | Instalador | **Chico** (≈ 100 MB) que baja entorno y modelos desde el asistente; uno completo sin conexión queda para después | Tamaños medidos |
| 4 | GPU en la v1 | **NVIDIA con CUDA** y **CPU** como respaldo; AMD/Intel con DirectML después, si la exportación a ONNX del modelo sirve | Etapa 0 (B): tiempo en CPU |
| 5 | Ollama | **Oficial**, instalado desde el asistente | Etapa 0 (F) |
| 6 | Firma de código | Beta sin firmar con aviso de SmartScreen; firmar antes de la versión estable | Presupuesto |
| 7 | Distribución | GitHub Releases primero; winget después | — |
| 8 | Token del motor | La cáscara lo genera por sesión y se lo pasa al motor y a la ventana | Etapa 2.2 |
| 9 | Estirador de audio por defecto | Si `rubberband-wasm` resulta "solo GPL-2.0", usar **SoundTouch** (LGPL) por defecto | Revisión de la licencia |

## Riesgos
- **No hay máquina con NVIDIA** para probar la ruta CUDA en Windows: queda "sin verificar" hasta que haya una o un colaborador.
- **Separación en CPU**: puede tardar mucho; la cifra de la etapa 0 (B) define qué se le promete al usuario.
- **WebView2 y el audio**: AudioWorklet, SharedArrayBuffer y la latencia pueden comportarse distinto.
- **Ruedas de Python 3.14 en Windows**: todas existen según PyPI, pero la instalación real no está probada.
- **Antivirus y SmartScreen** con un instalador nuevo y sin reputación.
- **Peso**: el entorno ocupa ≈ 8 GB con CUDA (menos con torch CPU) y los modelos varios GB; hay que comprobar el espacio antes de instalar.
- **Licencias**: Rubber Band (¿solo v2?) y términos de TIDAL.
- **Dos plataformas con poco equipo**: que el CI de Windows corra las pruebas del motor en cada cambio.
