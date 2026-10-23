#!/usr/bin/env bash
# Instala Shed Stem Studio para tu usuario (sin root): ~/.local/opt/shed-stem-studio + entrada en el menú + comando `shedstem`.
set -euo pipefail
src="$(cd "$(dirname "$0")" && pwd)"
data="${XDG_DATA_HOME:-$HOME/.local/share}"
dest="$HOME/.local/opt/shed-stem-studio"; apps="$data/applications"
mkdir -p "$apps" "$HOME/.local/bin" "$dest"
rm -rf "$dest/app"; cp -r "$src/app" "$dest/app"
ln -sf "$dest/app/shed-stem-studio" "$HOME/.local/bin/shedstem"
# El nombre del .desktop es el id de ventana de Electron (package.json: desktopName): así la barra de tareas muestra el ícono propio
rm -f "$apps/chrome-127.0.0.1__-Default.desktop"
cat > "$apps/shed-stem-studio.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Shed Stem Studio
Comment=Estudiá música con stems separados por IA
Exec=$dest/app/shed-stem-studio
Icon=$dest/app/resources/app-icon.png
Terminal=false
Categories=AudioVideo;Audio;Music;
StartupWMClass=shed-stem-studio
DESK
command -v update-desktop-database >/dev/null && update-desktop-database "$apps" || true
echo "Listo. Abrilo desde el menú (Shed Stem Studio) o con: shedstem"
