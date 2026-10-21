# Shed Stem Studio para Windows: plan de trabajo

Estado: **plan listo para ejecutar** (2026-10-21). Está escrito para seguirse desde una **PC con Windows**, con una sesión de Claude Code que no vio la conversación donde se armó. Todo lo que hay que saber está en estos archivos y en el repo.

Visión general y decisiones de arquitectura: [`../windows-instalable.md`](../windows-instalable.md).

## Cómo usar este plan

1. Cloná el repo en la PC con Windows (ver [`01-preparacion.md`](01-preparacion.md)).
2. Abrí Claude Code en la carpeta del repo y pegá el texto de [`PROMPT-INICIAL.md`](PROMPT-INICIAL.md).
3. Seguí los archivos en orden. Cada uno termina con **criterios de aceptación**: no se pasa al siguiente sin cumplirlos o sin anotar por qué no.
4. Anotá todo lo que midas en [`RESULTADOS.md`](RESULTADOS.md). Ese archivo es lo que hay que traer de vuelta (por ejemplo, pegándolo en la conversación original o subiéndolo al repo) para decidir los siguientes pasos.

## Archivos

| Archivo | Qué contiene |
|---|---|
| [`PROMPT-INICIAL.md`](PROMPT-INICIAL.md) | Texto para pegar en una sesión nueva de Claude Code en Windows |
| [`00-contexto.md`](00-contexto.md) | Qué es el proyecto, cómo está armado, reglas, qué está verificado y qué no |
| [`01-preparacion.md`](01-preparacion.md) | Herramientas a instalar, cómo clonar, diagnóstico de la máquina |
| [`02-etapa0-prototipos.md`](02-etapa0-prototipos.md) | Pruebas de riesgo: entorno de Python, separación en CPU, análisis, ventana, Ollama |
| [`03-motor-portable.md`](03-motor-portable.md) | Cambios del motor para que corra en Windows, con archivo y función |
| [`04-ventana-e-instalador.md`](04-ventana-e-instalador.md) | Cáscara de escritorio (Tauri), motor empaquetado, instalador, firma, actualizaciones, CI |
| [`05-asistente-y-pruebas.md`](05-asistente-y-pruebas.md) | Asistente de primeros pasos en Windows, matriz de pruebas y checklist de la beta |
| [`DECISIONES.md`](DECISIONES.md) | Decisiones abiertas, con la propuesta de cada una, y riesgos |
| [`RESULTADOS.md`](RESULTADOS.md) | Plantilla para anotar mediciones y hallazgos |

Herramientas de apoyo (en `tools/windows/`): `diagnostico.ps1`, `serve-check.py` y `webview-check.html`. Listas de dependencias (borradores sin probar): `engine/requirements-env.win-cpu.txt` y `engine/requirements-env.win-nvidia.txt`.

## Máquina de prueba prevista

Notebook con Windows y **placa AMD** (sin CUDA). Permite probar todo salvo la ruta NVIDIA: la separación va a **CPU**. La ruta NVIDIA necesita otro equipo o un colaborador; hasta entonces queda marcada como "sin verificar en Windows".

## Reglas de trabajo (resumen; el detalle está en `00-contexto.md`)

- **Nada se descarga solo.** Cada descarga pesada (entorno, modelos) se hace en un paso explícito y se anota su tamaño y duración.
- **No tocar el comportamiento en Linux.** Los cambios del motor usan ramas por plataforma (`sys.platform == "win32"`); el resto sigue igual. Las pruebas de Linux se vuelven a correr en la máquina Linux.
- **Un cambio, un commit**, con mensaje en español que diga qué y por qué.
- **Sin datos personales en el repo** (rutas con el nombre de usuario, perfiles de gustos, sesiones). Los resultados de las mediciones se anotan sin el nombre de usuario.
- **Verificar con datos antes de afirmar**; lo que no se pudo probar se escribe como "sin verificar".
- Textos de la interfaz en español rioplatense, cortos.
