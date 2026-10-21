# Shed Stem Studio: plan de la pantalla de Ajustes

Estado: **propuesta**. Es la cuarta sección del menú lateral (después de Fuentes, Recomendaciones y Estudio). Responde tres preguntas: **qué modelo usa cada módulo, cuánto espacio ocupa y dónde está instalado**.

## Qué se ve

```
 Ajustes
 ┌ Modelos por módulo ──────────────────────────────────────────────────────┐
 │ Módulo            Modelo                 Dónde corre   Tamaño   Instalado en                  │
 │ Separación        RoFormer (BS-Roformer-SW)  GPU local   699 MB   /mnt/plexdata/tidal-stems/models │
 │                   Demucs 6 stems             GPU local    55 MB   /mnt/plexdata/tidal-stems/models │
 │ Recomendaciones   (modelo local de Ollama)   GPU local   ~7 GB   /mnt/plexdata/stemshed/models/ollama │
 │ Velocidad         Rubber Band (WASM)         Navegador   265 KB   incluido en la app          │
 │                   SoundTouch                 Navegador   ~30 KB   incluido en la app          │
 │ [Cambiar modelo]  [Probar]  [Abrir carpeta]  [Desinstalar]                                     │
 └──────────────────────────────────────────────────────────────────────────┘
 ┌ Almacenamiento ──────────────────────────────────────────────────────────┐
 │ /mnt/plexdata  ███████████████████░  85 GB libres de 916 GB               │
 │ /  (y /home)   ███████████████████░  16 GB libres de 229 GB   ← aviso    │
 │ Stems nuevos        92 MB   /mnt/plexdata/stemshed/cache      [Limpiar]    │
 │ Stems anteriores   411 MB   /mnt/plexdata/tidal-stems/cache   (solo lectura)│
 │ Entorno de separación 7,4 GB /mnt/plexdata/tidal-stems/venv                 │
 │ Sesión de TIDAL      4 KB   ~/.config/stemshed                [Desconectar] │
 │ Tope de la caché de stems: [ 40 GB ]                                        │
 └──────────────────────────────────────────────────────────────────────────┘
 ┌ Motor y conexiones ──────────────────────────────────────────────────────┐
 │ Motor local: activo en 127.0.0.1:8770 · TIDAL: conectado · MusicBrainz: ok  │
 └──────────────────────────────────────────────────────────────────────────┘
```

(Los números de arriba son los medidos hoy en esta máquina, salvo el modelo de recomendaciones, que todavía no está instalado.)

## Módulos y qué muestra cada uno

| Módulo | Qué configura | Dato por modelo |
|---|---|---|
| **Separación** | Modelo por defecto (RoFormer o Demucs), tope de caché | nombre, tamaño, ruta, si está presente, tiempo típico por tema |
| **Recomendaciones** | Proveedor: local (Ollama), clave propia o motor | modelo, tamaño, ruta, si responde, botón **Probar** con una pregunta corta |
| **Velocidad (estirador)** | Rubber Band rápido, fino o SoundTouch | CPU medida, licencia (Rubber Band es GPL) |
| **Verificación** | Catálogo (MusicBrainz) | estado y límite de consultas |

Cada fila muestra el estado con palabras ("Instalado", "Falta", "No responde") y la acción que corresponde. Un modelo ausente no rompe la pantalla: dice qué falta y ofrece instalarlo.

## Detección de hardware y recomendación de modelos

La propia app detecta la máquina y recomienda qué descargar; el usuario confirma cada descarga.

- **Qué detecta el motor** (`GET /engine/hardware`, ya implementado): GPU y VRAM (vía `nvidia-smi`), RAM total y disponible, CPU e hilos, y espacio libre de los discos que usa la app. En esta máquina: RTX 5080 con 15,9 GB, 30,5 GB de RAM, 16 hilos, `/` con 17 GB libres (93 % lleno) y `/mnt/plexdata` con 91 GB.
- **Qué detecta el navegador** (para el nivel A, sin motor): `navigator.hardwareConcurrency`, `navigator.deviceMemory` y el adaptador de WebGPU. Sirve para decidir si ofrece un modelo liviano en el navegador.
- **Cómo recomienda:** para cada modelo del catálogo compara peso + margen de memoria contra la VRAM, y el peso contra el disco de destino. Marca "cabe" o explica por qué no ("necesita unos 9 GB de VRAM y la GPU tiene 8 GB"). También indica si **cabe junto con la separación**: en esta GPU un modelo de 12B y la separación con RoFormer **no caben a la vez**, así que se turnan.
- **Catálogo:** hoy tiene un solo candidato (Mistral Nemo 12B, 7,1 GB según una guía de terceros). Cada modelo se prueba con un cuestionario corto de artistas, discos y teoría antes de recomendarlo como bueno: ninguna fuente que encontré mide cuánto sabe de música. Los tamaños se confirman al descargar.
- **Instalación sin tocar el sistema:** la app levanta su propia instancia de Ollama con los modelos en `/mnt/plexdata/stemshed/models/ollama`, en vez de usar el servicio del sistema (que guarda en el disco casi lleno).

## Reglas

- **Archivos grandes siempre en `/mnt/plexdata`.** La pantalla avisa si algo apunta a `/` o `/home`, que hoy están al 94 %.
- **Instalar o desinstalar pide confirmación** y dice cuánto espacio libera o usa.
- **La caché anterior es de solo lectura:** se muestra pero no ofrece Limpiar.
- **Nada borra la sesión de TIDAL sin que lo pidas.**

## Qué necesita el motor

Un endpoint `GET /engine/storage` que devuelva, por módulo, `{ modelo, proveedor, ruta, bytes, presente }`, más el espacio libre de cada disco. Para Ollama, el tamaño y la ruta se leen de su propia API (`/api/tags`), no se adivinan.

## Orden de construcción

1. Endpoint `/engine/storage` con lo que ya existe (separación, cachés, sesión).
2. Pantalla de solo lectura (esta tabla), con el aviso de disco lleno.
3. Instalación y cambio de modelo local desde la pantalla.
4. Tope de caché y limpieza.

## Pendiente de decidir

1. Qué modelo local usar para recomendaciones (ver abajo).
2. Si se agrega la sección en el menú o va dentro de un ícono de engranaje abajo del menú. Propongo una cuarta entrada, **Ajustes**.

## Nota sobre Ollama en esta máquina

Ollama corre como **servicio del sistema** (usuario `ollama`) y guarda sus modelos en `/usr/share/ollama`, en el disco que tiene 16 GB libres. Para respetar la regla de `/mnt/plexdata` sin tocar la configuración del sistema, el motor puede levantar **su propia instancia** de Ollama con `OLLAMA_MODELS=/mnt/plexdata/stemshed/models/ollama` en otro puerto. Es el mismo criterio que con el entorno de separación.
