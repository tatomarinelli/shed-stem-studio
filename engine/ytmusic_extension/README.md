# Extensión de Shed Stem Studio para YouTube Music

Opcional. Evita copiar y pegar los encabezados a mano: cuando tocás **Conectar** en Fuentes, esta extensión toma la sesión de
music.youtube.com y se la pasa a la app local (`127.0.0.1`). No manda nada a otro lado y no hace nada si no hay un
emparejamiento pendiente (el botón Conectar crea un token de un solo uso que vale 10 minutos).

Cargarla una vez:
- **Chrome / Edge / Chromium**: `chrome://extensions` → activar *Modo de desarrollador* → *Cargar descomprimida* → elegir esta carpeta (o la del zip descomprimido).
- **Firefox**: `about:debugging#/runtime/this-firefox` → *Cargar complemento temporal* → elegir `manifest.json`. Es temporal: se pierde al cerrar Firefox.
