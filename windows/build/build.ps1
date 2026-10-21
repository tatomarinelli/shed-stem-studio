<#
 Arma la versión de Windows: carpeta portable (zip) e instalador NSIS por usuario.
 Uso:  powershell -ExecutionPolicy Bypass -File windows\build\build.ps1 [-SkipInstaller] [-SkipUi]
 Requisitos en esta máquina: Node, Rust (cargo) y las herramientas de C++ de Visual Studio. No instala nada del sistema.
 Descarga (una vez, queda en build\cache): Python embebible de python.org y la rueda de tzdata.
 Salida: windows\build\out\ShedStemStudio-portable-<versión>.zip  y, si no se omite, el instalador .exe.
#>
param([switch]$SkipInstaller, [switch]$SkipUi)
$ErrorActionPreference = "Stop"
$PyVersion = "3.13.12"
$Root   = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Win    = Join-Path $Root "windows"
$Cache  = Join-Path $PSScriptRoot "cache"
$Stage  = Join-Path $PSScriptRoot "stage"
$Out    = Join-Path $PSScriptRoot "out"
$Shell  = Join-Path $Win "shell"
$Version = (Get-Content (Join-Path $Shell "src-tauri\tauri.conf.json") -Raw | ConvertFrom-Json).version
$env:Path = [Environment]::GetEnvironmentVariable("Path","User") + ";" + [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + $env:Path

function Step($t) { Write-Host "`n== $t" -ForegroundColor Cyan }

New-Item -ItemType Directory -Force $Cache, $Out | Out-Null
if (Test-Path $Stage) { Remove-Item -Recurse -Force $Stage }
$Rt = Join-Path $Stage "runtime"
New-Item -ItemType Directory -Force (Join-Path $Rt "python"), (Join-Path $Rt "engine"), (Join-Path $Rt "ui") | Out-Null

if (-not $SkipUi) {
  Step "Interfaz (proto\player)"
  Push-Location (Join-Path $Root "proto\player")
  if (-not (Test-Path node_modules)) { npm ci }
  npm run build
  if ($LASTEXITCODE) { throw "falló la compilación de la interfaz" }
  Pop-Location
}
Copy-Item -Recurse -Force (Join-Path $Root "proto\player\dist\*") (Join-Path $Rt "ui")

Step "Python embebido $PyVersion"
$zip = Join-Path $Cache "python-$PyVersion-embed-amd64.zip"
if (-not (Test-Path $zip)) { Invoke-WebRequest "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-embed-amd64.zip" -OutFile $zip }
Expand-Archive $zip (Join-Path $Rt "python") -Force
$pth = Get-ChildItem (Join-Path $Rt "python") -Filter "python3*._pth" | Select-Object -First 1
# Con ._pth el intérprete ignora PYTHONPATH y la carpeta del script: se declara todo acá.
Set-Content $pth.FullName -Encoding ascii -Value @(($pth.BaseName + ".zip"), ".", "..\engine", "Lib\site-packages")

Step "tzdata (Windows no trae la base de husos horarios)"
$whl = Get-ChildItem $Cache -Filter "tzdata-*.whl" | Select-Object -First 1
if (-not $whl) { python -m pip download tzdata --no-deps -d $Cache | Out-Null; $whl = Get-ChildItem $Cache -Filter "tzdata-*.whl" | Select-Object -First 1 }
$sp = Join-Path $Rt "python\Lib\site-packages"
New-Item -ItemType Directory -Force $sp | Out-Null
Copy-Item $whl.FullName "$sp\tzdata.zip"; Expand-Archive "$sp\tzdata.zip" $sp -Force; Remove-Item "$sp\tzdata.zip"

Step "Dependencias del motor (tidalapi)"
$wheels = Join-Path $Cache "wheels"
$reqEngine = Join-Path $Root "engineequirements-engine.txt"
New-Item -ItemType Directory -Force $wheels | Out-Null
# pyaes y ratelimit solo existen como código fuente: se compilan a wheel (Python puro) con el pip del sistema; el resto se resuelve para el Python embebido.
python -m pip wheel -r $reqEngine -w $wheels --quiet
if ($LASTEXITCODE) { throw "falló la preparación de las dependencias del motor" }
python -m pip install --target $sp --no-compile --only-binary=:all: --platform win_amd64 --python-version 3.13 --implementation cp --find-links $wheels -r $reqEngine --quiet
if ($LASTEXITCODE) { throw "falló la instalación de las dependencias del motor" }

Step "Motor (engine\*.py, sin pruebas)"
Get-ChildItem (Join-Path $Root "engine") -File | Where-Object { $_.Extension -in ".py", ".txt", ".json" } | Copy-Item -Destination (Join-Path $Rt "engine")
Copy-Item (Join-Path $Root "LICENSE") $Rt
"Python $PyVersion (PSF), tzdata (Apache-2.0). Shed Stem Studio es GPL-3.0-or-later: ver LICENSE y el repositorio del proyecto para el código fuente." | Set-Content (Join-Path $Rt "AVISOS.txt") -Encoding utf8

Step "Prueba del runtime armado (sin ventana)"
$py = Join-Path $Rt "python\python.exe"
& $py -I -c "import sys; sys.path.insert(0, r'$Rt\engine'); import osenv, webui, server, tidalapi; from zoneinfo import ZoneInfo; ZoneInfo('America/Argentina/Buenos_Aires'); print('runtime ok')"
if ($LASTEXITCODE) { throw "el runtime no importa el motor" }

Step "Cáscara (Tauri, release)"
Push-Location $Shell
if (-not (Test-Path node_modules)) { npm ci }
$bundle = if ($SkipInstaller) { @("--no-bundle") } else { @() }
npx tauri build @bundle
if ($LASTEXITCODE) { throw "falló la compilación de la cáscara" }
Pop-Location

Step "Zip portable"
$rel = Join-Path $Shell "src-tauri\target\release"
$pkg = Join-Path $Out "ShedStemStudio"
if (Test-Path $pkg) { Remove-Item -Recurse -Force $pkg }
New-Item -ItemType Directory $pkg | Out-Null
Copy-Item (Join-Path $rel "shed-stem-studio.exe") (Join-Path $pkg "ShedStemStudio.exe")
Copy-Item -Recurse $Rt (Join-Path $pkg "runtime")
$zipOut = Join-Path $Out "ShedStemStudio-portable-$Version.zip"
if (Test-Path $zipOut) { Remove-Item $zipOut }
Compress-Archive -Path $pkg -DestinationPath $zipOut
Get-ChildItem $zipOut | ForEach-Object { "{0}  {1:N1} MB" -f $_.FullName, ($_.Length / 1MB) }
if (-not $SkipInstaller) {
  Get-ChildItem (Join-Path $rel "bundle\nsis") -Filter *.exe | ForEach-Object { Copy-Item $_.FullName $Out; "{0}  {1:N1} MB" -f (Join-Path $Out $_.Name), ($_.Length / 1MB) }
}
