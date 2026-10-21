# 02. Etapa 0: pruebas de riesgo

Objetivo: decidir con datos si el plan es viable en Windows y con qué versión de Python y qué cáscara. **Todo se anota en [`RESULTADOS.md`](RESULTADOS.md).** Antes de cada descarga grande, avisá qué se baja, cuánto pesa y adónde.

Variables comunes (PowerShell):
```powershell
$base = "$env:LOCALAPPDATA\ShedStemStudio"
$py   = "$base\env\venv\Scripts\python.exe"
```

## A. Entorno de Python y dependencias (≈ 3 a 4 GB de descarga con torch CPU)
Objetivo: comprobar que todo se instala y se importa en Windows. Probá primero **Python 3.14** (la versión con la que se midió en Linux) y, si falla, **3.13**.

```powershell
uv python install 3.14
uv venv "$base\env\venv" --python 3.14
uv pip install --python $py --no-deps -r engine\requirements-env.win-cpu.txt
& $py -c "import torch, audio_separator, librosa, numba, soundfile, scipy, sklearn; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())"
```
- Si `uv` no resuelve el índice de PyTorch con `--extra-index-url` dentro del archivo, probá `--index-strategy unsafe-best-match` o `pip` (`& $py -m ensurepip` y `& $py -m pip install --no-deps -r ...`).
- **Anotá**: versión de Python usada, tiempo de instalación, tamaño de `$base\env` y **todo paquete que no se pudo instalar o importar** (con el mensaje de error). Lo esperado: todos instalan (ver `00-contexto.md`); `diffq` ya no está en la lista.
- Si falla por una dependencia, anotá cuál y probá la otra versión de Python antes de seguir.

Criterio: `import torch, audio_separator, librosa, numba` funciona → **A aprobada**.

## B. Separación en CPU (descarga ≈ 700 MB del modelo)
1. Modelo (descarga explícita):
   ```powershell
   & "$base\env\venv\Scripts\audio-separator.exe" --download_model_only --model_filename BS-Roformer-SW.ckpt --model_file_dir "$base\models"
   ```
   Anotá cuánto tardó y el tamaño de `BS-Roformer-SW.ckpt` (esperado: 699 MB).
2. Separar una **canción real** y medir:
   ```powershell
   $t = Measure-Command { & "$base\env\venv\Scripts\audio-separator.exe" "$HOME\Music\prueba\cancion.flac" --model_filename BS-Roformer-SW.ckpt --model_file_dir "$base\models" --output_dir "$base\data\out" --output_format FLAC }
   "{0:N0} segundos" -f $t.TotalSeconds
   ```
3. Mientras corre, mirá el Administrador de tareas: uso de CPU, RAM máxima y si hay actividad en la GPU (esperado: ninguna).
4. **Anotá**: duración de la canción, tiempo total, **veces tiempo real** (tiempo / duración), RAM máxima, hilos del CPU y si salieron los 6 stems (`guitar, bass, drums, piano, vocals, other`).

Referencia en Linux con RTX 5080: un clip de 90 s tarda ≈ 11 s. En CPU se espera mucho más; lo importante es el número real para decidir qué decirle al usuario.

Criterio: salen los 6 stems y hay una cifra de tiempo → **B aprobada** (aunque sea lenta; la lentitud se documenta).

## C. Análisis (tonalidad, tempo, acordes)
```powershell
$env:STEMSHED_DATA = "$base\data"
& $py engine\analyze.py "$base\data\out" --out "$base\data\analisis.json"
```
(la carpeta debe tener los `.flac` de los stems; si `analyze.py` espera otra estructura, mirá `engine\analysis.py` y adaptá la prueba). Anotá el tiempo, el JSON resultante (tonalidad, tempo, cantidad de acordes) y los errores de `numba`/`librosa`.

## D. Pruebas del motor en Windows (sin entorno pesado)
```powershell
cd engine
python -m unittest discover -s tests 2>&1 | Tee-Object "$base\data\tests-windows.txt"
```
Esperado: **varias fallas** por supuestos de Linux. Guardá la lista (módulo, prueba, mensaje) en `RESULTADOS.md`: es el punto de partida de [`03-motor-portable.md`](03-motor-portable.md). Algunas pruebas necesitan `soundfile`/`librosa` (usá `$py` en lugar de `python` para esas).

Arrancar el motor en una carpeta aislada:
```powershell
$env:XDG_CONFIG_HOME = "$base\config"; $env:STEMSHED_DATA = "$base\data"; $env:STEMS_ENV = "$base\env"
$env:STEMSHED_OLLAMA = "http://127.0.0.1:11999"; $env:STEMSHED_NO_SCHEDULER = "1"
python engine\server.py 8770
```
En otra terminal: `curl http://127.0.0.1:8770/engine/status`. Anotá el error si no arranca (se espera algo en `hardware.py` o en rutas).

## E. Ventana: el navegador del sistema y WebView2
1. Servidor de comprobación (solo Python, sin dependencias):
   ```powershell
   python tools\windows\serve-check.py
   ```
2. Abrí `http://127.0.0.1:8899/webview-check.html` en **Edge** y copiá el resultado (botón "Copiar resultado") a `RESULTADOS.md`.
3. Abrí la misma página como **ventana de aplicación** con el motor de WebView2:
   ```powershell
   msedge --app=http://127.0.0.1:8899/webview-check.html
   ```
4. Hacé clic en "Reproducir un tono" en cada una y confirmá si **se oye**.
5. Lo que decide: `crossOriginIsolated`, `SharedArrayBuffer`, `AudioWorklet`, latencia de audio y WebGPU. Si algo de lo anterior es "no" en WebView2/Edge, anotá la causa probable.

> `msedge --app` usa el mismo Chromium que WebView2, pero **no es WebView2 real**. La prueba definitiva es una ventana Tauri (ver `04-ventana-e-instalador.md`, etapa 2). Si preferís hacerla ya: `winget` de Rust + MSVC y un proyecto mínimo de Tauri que cargue esa URL.

## F. Ollama en Windows (descarga ≈ 1 GB de instalador + el modelo que elijas)
1. Instalá Ollama (`winget install Ollama.Ollama`) y verificá si el instalador admite instalación silenciosa (anotá la opción que funcione).
2. Carpeta de modelos elegida por el usuario:
   ```powershell
   [Environment]::SetEnvironmentVariable("OLLAMA_MODELS", "$base\models\ollama", "User")
   ```
   Reiniciá Ollama (cerrar desde la bandeja y abrirlo).
3. Un modelo **chico** para medir (por ejemplo `ollama pull llama3.2:3b`) y luego `ollama run llama3.2:3b --verbose "Decime tres discos de jazz"`. Anotá **tokens por segundo**.
4. `ollama ps`: ¿usa la placa AMD ("GPU") o el CPU? Anotá el procesador que muestra y el modelo de la placa.
5. **Opcional** (solo si hay RAM ≥ 16 GB): `ollama pull mistral-nemo` y medir tokens por segundo; el motor usa ese modelo por defecto.

Criterio: Ollama corre, se elige la carpeta de modelos y hay cifras de velocidad.

## Resumen para decidir (completar al terminar)
| Pregunta | Respuesta |
|---|---|
| ¿Qué versión de Python usar en Windows? | |
| ¿Instalan todas las dependencias (CPU)? | |
| ¿Cuánto tarda separar una canción de 4 min en CPU? | |
| ¿WebView2/Edge: aislamiento de origen, AudioWorklet y audio funcionan? | |
| ¿Ollama anda y a qué velocidad? | |
| ¿Cuáles son las fallas del motor en Windows? | |

Con esto se decide: Tauri o Electron, Python 3.13 o 3.14, y qué advertencia mostrar a quien no tiene NVIDIA.
