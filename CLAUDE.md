# Shed Stem Studio

Webapp local-first (y luego app de escritorio) para estudiar música con stems separados por IA y recibir una recomendación diaria. Leé `PLAN.md` (plan operativo) y `docs/architecture.md` (arquitectura) antes de trabajar.

Trabajo en la versión de Windows (nativa, sin Docker): leé `docs/windows-agentes.md`.

## Idioma
Interfaz y textos en español rioplatense (voseo), cortos y sin verbosidad.

## Reglas
- Sin código, binarios, credenciales ni caché de TIDAL en este repo.
- Nada se descarga solo: el entorno de separación y los modelos se eligen y se bajan desde Ajustes, a la carpeta que indique el usuario.
- Archivos grandes y modelos fuera del disco raíz.
- Las escrituras en cuentas externas (guardar en TIDAL) van solo con confirmación explícita y nunca borran nada.
- El modelo de recomendación solo propone; todo se verifica en MusicBrainz y el motivo mostrado nunca es texto inventado.
- Reacciones por ítem, nunca por género. La banda o proyecto propio del usuario (campo `ownArtists` del perfil) nunca se recomienda ni cuenta como gusto.
- Verificar con datos antes de afirmar; avisar antes de abrir ventanas visibles (las pruebas de interfaz usan Chromium sin ventana).

## Cómo se verifica
- Motor: `cd engine && python3 -m unittest discover -s tests`.
- Interfaz: `cd proto/player && npx svelte-check --tsconfig ./tsconfig.json`.
- Interfaz con clics reales y sin ventana: `proto/tools/uicheck.py`.
- Portadas al salir y volver a una pantalla (que no queden cargadas pero invisibles): `proto/tools/covercheck.py`.

## Notas locales
Las preferencias personales y las rutas de la máquina de quien desarrolla van en `CLAUDE.local.md` (no se versiona).
