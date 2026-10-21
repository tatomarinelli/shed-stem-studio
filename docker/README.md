# Shed Stem Studio en Docker

Levanta el motor (con GPU) y la interfaz, todo en tu máquina: los puertos se publican solo en `127.0.0.1`.

```
cd docker
docker compose up -d --build        # sin configurar nada: todo queda en docker/data/
```

Abrí `http://127.0.0.1:5173` (o el puerto de `STEMSHED_WEB_PORT`).

## Qué NO hace solo
Nada se descarga solo. Desde **Ajustes** elegís y bajás:
- **Entorno de separación** (≈ 8 GB en disco; los programas que corren la IA en tu placa de video): botón *Instalar*.
- **Modelo de separación** (BS-Roformer, 700 MB): botón *Descargar*.
- **Modelos de recomendación** (Ollama): del catálogo o escribiendo cualquier nombre.

## Carpetas (dónde se guarda cada cosa)
Se definen en `docker/.env` y se cambian volviendo a levantar (también se pueden pasar al levantar:
`STEMSHED_SEP_MODELS=/ruta docker compose up -d`). Ajustes las muestra con su ruta real del equipo.

| Variable | Qué guarda |
|---|---|
| `STEMSHED_CONFIG` | perfiles, memoria, sesión de TIDAL |
| `STEMSHED_DATA` | stems y análisis |
| `STEMSHED_ENV` | entorno de separación (torch, CUDA) |
| `STEMSHED_SEP_MODELS` | modelos de separación |
| `STEMSHED_LLM_MODELS` | modelos de Ollama |
| `STEMSHED_MUSIC` | tu música (solo lectura) |

La imagen del motor es chica (≈ 1 GB) a propósito: lo pesado vive en estos volúmenes, no en el disco de Docker.

## GPU
Usa CDI (`devices: nvidia.com/gpu=all`), que pide `nvidia-container-toolkit` en el equipo. Sin GPU, borrá esa línea (la separación va a CPU y es muy lenta).

## Servidor de modelos (Ollama)
Es parte del `docker compose up` (tercer servicio). Su imagen pesa ≈ 3,4 GB comprimida y se baja la primera vez. Los modelos se eligen y se descargan desde Ajustes, a la carpeta de `STEMSHED_LLM_MODELS`.

## Apagar y encender
- Ajustes → *Qué está corriendo* → **Apagar el motor** (no se reinicia solo).
- Para volver a prenderlo: `docker compose up -d`.

## Origen del sitio publicado
Si la web se sirve desde otro dominio, agregalo a `STEMSHED_ORIGINS` (separado por comas). El motor solo acepta esos orígenes.
