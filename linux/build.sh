#!/usr/bin/env bash
# Arma el release de Linux en linux/build/out/ShedStemStudio-linux-<versión>.tar.gz
# (cáscara Electron + interfaz compilada + motor + tidalapi + instalador). La versión sale de proto/player/package.json.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
lx="$root/linux"
ver="$(node -p "require('$root/proto/player/package.json').version")"
name="ShedStemStudio-linux-$ver"
payload="$lx/build/payload"; stage="$lx/build/stage"; out="$lx/build/out"
rm -rf "$payload" "$stage"; mkdir -p "$payload" "$stage" "$out"

(cd "$root/proto/player" && npm ci --silent && npm run build --silent)
cp -r "$root/proto/player/dist" "$payload/ui"
rsync -a --exclude __pycache__ --exclude tests --exclude eval "$root/engine/" "$payload/engine/"
python3 -m pip install --quiet --target "$payload/lib" --no-compile -r "$root/engine/requirements-engine.txt"

# Cáscara: Electron fijado en electron/package.json. Se descomprime a mano (el postinstall y el empaquetador fallan en silencio con Node 26).
(cd "$lx/electron" && npm version "$ver" --no-git-tag-version --allow-same-version >/dev/null && npm install --silent --no-audit --no-fund --ignore-scripts)
zip="$(cd "$lx/electron" && node -e "require('@electron/get').downloadArtifact({version:require('./package.json').devDependencies.electron,artifactName:'electron',platform:'linux',arch:'x64'}).then(console.log)")"
app="$stage/app"; mkdir -p "$app"; unzip -q "$zip" -d "$app"
mv "$app/electron" "$app/shed-stem-studio"; rm -f "$app/resources/default_app.asar"
mkdir -p "$app/resources/app"; cp "$lx/electron/"{main.js,package.json} "$app/resources/app/"
cp -r "$payload"/{engine,ui,lib} "$app/resources/"; cp "$lx/app-icon.png" "$app/resources/"
[ -x "$app/shed-stem-studio" ] || { echo "No se generó la aplicación"; exit 1; }

# Prueba: el motor del release arranca con su propia interfaz
res="$app/resources"; port=18770; home="$(mktemp -d)"
HOME="$home" PYTHONPATH="$res/lib" STEMSHED_UI="$res/ui" python3 "$res/engine/server.py" $port >/dev/null 2>&1 &
pid=$!; ok=0
for _ in $(seq 40); do curl -sf "http://127.0.0.1:$port/engine/status" >/dev/null && ok=1 && break; sleep 0.5; done
curl -sf "http://127.0.0.1:$port/" | grep -q "<div" || ok=0
kill $pid 2>/dev/null || true; wait $pid 2>/dev/null || true; rm -rf "$home"
[ $ok = 1 ] || { echo "El motor del release no arrancó"; exit 1; }

mkdir -p "$stage/$name"; mv "$app" "$stage/$name/app"; cp "$lx/install.sh" "$root/LICENSE" "$stage/$name/"
tar -C "$stage" -czf "$out/$name.tar.gz" "$name"
(cd "$out" && sha256sum "$name.tar.gz" > "$name.sha256")
echo "Listo: $out/$name.tar.gz"
