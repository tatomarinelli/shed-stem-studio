# 05. Asistente en Windows, matriz de pruebas y checklist de la beta

## Asistente de primeros pasos (cambios para Windows)
El asistente (`proto/player/src/screens/Inicio.svelte`, `engine/firstrun.py`) hoy conoce Docker y Linux. En Windows:

| Paso | Cambio |
|---|---|
| Bienvenida | Si el motor no responde, el mensaje no menciona Docker ni `npm run engine`; en la app de escritorio el motor lo lanza la cáscara. |
| Dónde guardar | Selector con unidades (`C:`, `D:`), espacio libre por unidad y sugerencia del disco con más espacio. Rutas con `\`. |
| Modelos: entorno | Elegir la variante **NVIDIA** o **CPU** según `nvidia-smi`; si no hay NVIDIA, mostrar la advertencia de velocidad con la cifra medida en la etapa 0 (B). Si hay NVIDIA pero el controlador es viejo, avisar con el enlace de descarga. |
| Modelos: separación | Igual que Linux (descarga de 700 MB con progreso). |
| Modelos: recomendación | Instalar **Ollama oficial** desde el asistente (descarga explícita, tamaño visible); carpeta de modelos elegida por el usuario (`OLLAMA_MODELS`). Si no hay GPU compatible, avisar que irá a CPU y sugerir un modelo más chico. |
| ffmpeg | Paso nuevo: comprobar `ffmpeg`; si falta, ofrecer descargarlo (con tamaño) a la carpeta de la app. |
| Fuentes | Igual (TIDAL por código de dispositivo, carpetas con selector). |
| Perfil | Igual. |

`engine/firstrun.py`: agregar `ffmpeg` y el estado de Ollama como pasos del motor; que `hardware.py` informe `os` y `gpuVendor` para decidir variantes.

## Matriz de pruebas
| Caso | Qué se comprueba |
|---|---|
| Windows 10 y Windows 11 | Instala, abre, WebView2 presente o instalado por el bootstrapper |
| Usuario con espacios y tildes (`C:\Users\José Pérez`) | Rutas del motor, del entorno, de la música |
| Disco de datos distinto al del sistema | Entorno y modelos en `D:` |
| Sin GPU compatible (AMD/Intel) | Variante CPU, advertencia, separación lenta pero correcta |
| Con NVIDIA (**otra máquina**) | Variante CUDA, controlador mínimo, velocidad |
| Controlador de NVIDIA viejo | Mensaje claro, no un error de CUDA |
| Sin internet en un paso | Mensaje y reintento, el resto sigue |
| Antivirus de Windows activo | El instalador y el motor no se bloquean |
| Instalación sobre una versión anterior | Conserva perfiles, memoria y sesión |
| Desinstalar con y sin borrar datos | Pregunta, no deja procesos |
| Cierre forzado del programa | No quedan procesos ni puertos ocupados al volver a abrir |
| Música en una carpeta de red o con enlaces | Escaneo y reproducción |

## Checklist de la beta pública
- [ ] Todas las etapas 0 a 5 con sus criterios cumplidos y anotados.
- [ ] Instalador firmado (o aviso de SmartScreen documentado en el README).
- [ ] Dudas legales resueltas: licencia de Rubber Band (¿solo v2 o v2 o posterior?; si fuera solo v2, usar SoundTouch por defecto) y términos de TIDAL (si lo prohíben, dejar fuera la descarga de audio de TIDAL en la versión pública).
- [ ] Avisos de licencias de terceros incluidos (`thirdparty`), con ffmpeg, uv, Python, torch, onnxruntime y Ollama.
- [ ] README con la sección de Windows (requisitos, tamaño, GPU, problemas comunes).
- [ ] Notas de la versión y guía de "si algo sale mal" (dónde están los registros).
- [ ] Sin datos personales en el instalador ni en el repo.
