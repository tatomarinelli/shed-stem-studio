# Diagnóstico para preparar la versión de Windows de Shed Stem Studio.
# No instala ni cambia nada, no usa internet y no envía datos: escribe un archivo de texto en el Escritorio.
# Uso: clic derecho sobre este archivo -> "Ejecutar con PowerShell".  (o:  powershell -ExecutionPolicy Bypass -File diagnostico.ps1)

$ErrorActionPreference = 'SilentlyContinue'
$salida = Join-Path ([Environment]::GetFolderPath('Desktop')) 'diagnostico-shed-stem-studio.txt'
$l = New-Object System.Collections.Generic.List[string]
function Add($t) { $l.Add($t) }

$os = Get-CimInstance Win32_OperatingSystem
Add "== Sistema"
Add "Windows: $($os.Caption) $($os.Version) (build $($os.BuildNumber)), $($os.OSArchitecture)"
Add "Usuario: $env:USERNAME  | Carpeta personal: $env:USERPROFILE"

$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
Add "== Procesador"
Add "$($cpu.Name) | $($cpu.NumberOfCores) núcleos, $($cpu.NumberOfLogicalProcessors) hilos"

Add "== Memoria"
Add ("RAM total: {0:N1} GB | libre: {1:N1} GB" -f ($os.TotalVisibleMemorySize / 1MB), ($os.FreePhysicalMemory / 1MB))

Add "== Placas de video"
Get-CimInstance Win32_VideoController | ForEach-Object {
  $vram = if ($_.AdapterRAM) { '{0:N1} GB (según Windows; puede subestimar)' -f ($_.AdapterRAM / 1GB) } else { 'sin dato' }
  Add "$($_.Name) | controlador $($_.DriverVersion) ($($_.DriverDate)) | VRAM $vram"
}
$nv = Get-Command nvidia-smi -ErrorAction SilentlyContinue
Add ("nvidia-smi: " + $(if ($nv) { 'presente' } else { 'no encontrado (no hay controlador de NVIDIA)' }))

Add "== Discos"
Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | ForEach-Object {
  Add ("{0} libres {1:N0} GB de {2:N0} GB ({3})" -f $_.DeviceID, ($_.FreeSpace / 1GB), ($_.Size / 1GB), $_.FileSystem)
}

Add "== Componentes que usa la app"
$wv = @('HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
        'HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
        'HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}')
$ver = $null
foreach ($k in $wv) { $p = (Get-ItemProperty $k).pv; if ($p) { $ver = $p; break } }
Add ("WebView2 Runtime: " + $(if ($ver) { $ver } else { 'no encontrado' }))
foreach ($c in 'python', 'py', 'ffmpeg', 'git', 'node', 'ollama', 'winget') {
  $x = Get-Command $c -ErrorAction SilentlyContinue
  Add ("{0}: {1}" -f $c, $(if ($x) { $x.Source } else { 'no encontrado' }))
}
if (Get-Command python -ErrorAction SilentlyContinue) { Add ("Versión de Python: " + (& python --version 2>&1)) }

Add "== Antivirus"
Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct | ForEach-Object { Add $_.displayName }

Add "== Idioma y rutas"
Add "Cultura: $((Get-Culture).Name) | ¿Nombre de usuario con espacios o tildes?: $(if ($env:USERNAME -match '[^\x00-\x7F ]|\s') { 'sí' } else { 'no' })"

$l | Set-Content -Path $salida -Encoding UTF8
Write-Host "Listo. Se guardó en: $salida"
Write-Host "Pegá el contenido de ese archivo en la conversación."
