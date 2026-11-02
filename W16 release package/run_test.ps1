# Installs a built release as a user would and drives it through QGIS, three ways. Never touches an open QGIS window or the real profile.
# usage: powershell -File run_test.ps1 <unzipped release folder> <throwaway folder> <copy of the Block 2 HMS folder>
param(
    [Parameter(Mandatory = $true)][string]$Release,
    [Parameter(Mandatory = $true)][string]$Folder,
    [Parameter(Mandatory = $true)][string]$Hms,
    [int]$LimitMin = 30
)
$repo = Split-Path -Parent $PSScriptRoot
$here = $PSScriptRoot
$installer = Join-Path $Release 'install_wadi2d.ps1'
$version = ((Get-Content (Join-Path $Release 'BUILD.txt')) -split ' ')[1].TrimEnd(',')
$base = Join-Path $env:LOCALAPPDATA 'W2D test'  # short: a scratch folder is too deep for the engine, as the installer says
New-Item -ItemType Directory -Force -Path $base | Out-Null

function Install-Release([string]$Name, [string[]]$Options) {
    $start = Get-Date
    powershell -NoProfile -ExecutionPolicy Bypass -File $installer @Options *> (Join-Path $Folder "install_$Name.log")
    "install $Name exit $LASTEXITCODE, {0:N0} s" -f ((Get-Date) - $start).TotalSeconds
}

function Start-Check([string]$Mode, [string]$LocalAppData, [string]$Zip) {
    $work = Join-Path $Folder $Mode
    New-Item -ItemType Directory -Force -Path (Join-Path $work 'data') | Out-Null
    $bat = Join-Path $work 'start.bat'
    $lines = @('@echo off', "set WADI2D_MODE=$Mode", "set WADI2D_PLUG=$work", "set WADI2D_REPO=$repo", "set WADI2D_HMS=$Hms", "set WADI2D_VERSION=$version", "set WADI2D_ZIP=$Zip")
    if ($LocalAppData) { $lines += "set LOCALAPPDATA=$LocalAppData" }
    $lines += "call `"C:\Program Files\QGIS 3.44.8\bin\qgis-ltr.bat`" --nologo --noversioncheck --profiles-path `"$(Join-Path $work 'profiles')`" --code `"$here\dock_release.py`""
    $lines | Set-Content -Path $bat -Encoding ascii
    Start-Process -FilePath $bat -WindowStyle Minimized
    $log = Join-Path $work 'log.txt'
    $start = Get-Date
    while (((Get-Date) - $start).TotalMinutes -lt $LimitMin) {
        Start-Sleep -Seconds 10
        if ((Test-Path $log) -and (Select-String -Path $log -Pattern ' DONE$' -CaseSensitive -Quiet)) { break }
    }
    Start-Sleep -Seconds 8
    $summary = if (Test-Path $log) { (Select-String -Path $log -Pattern 'SUMMARY').Line } else { 'no log' }
    "{0} {1:N0} s; {2}" -f $Mode, ((Get-Date) - $start).TotalSeconds, $summary
    if (Test-Path $log) { Copy-Item $log (Join-Path $here "log_$Mode.txt") -Force }
}

$gpuRoot = Join-Path $base 'Wadi2D'
$cpuRoot = Join-Path $base 'cpu\Wadi2D'
$pluginsOf = { param($mode) Join-Path $Folder "$mode\profiles\profiles\default\python\plugins" }

Install-Release 'gpu' @('-EngineRoot', $gpuRoot, '-RecordRoot', $gpuRoot, '-PluginsDir', (& $pluginsOf 'gpu'))
Install-Release 'cpu' @('-EngineRoot', $cpuRoot, '-RecordRoot', $cpuRoot, '-PluginsDir', (& $pluginsOf 'cpu'), '-CpuOnly')

Start-Check 'gpu' '' ''

# Install from ZIP: the plugin knows the engine only through the shared record, here in a stand-in for the user's folder.
$zipHome = Join-Path $base 'zip home'
New-Item -ItemType Directory -Force -Path (Join-Path $zipHome 'Wadi2D') | Out-Null
Copy-Item (Join-Path $gpuRoot 'engine.txt') (Join-Path $zipHome 'Wadi2D\engine.txt') -Force
Start-Check 'zip' $zipHome (Get-ChildItem -LiteralPath $Release -Filter 'wadi2d_qgis-*.zip').FullName

Start-Check 'cpu' '' ''

# A developer's junction survives: only the link goes, never what it points at.
$target = Join-Path $Folder 'junction_target'
$plugins = Join-Path $Folder 'junction_plugins'
New-Item -ItemType Directory -Force -Path $target, $plugins | Out-Null
'keep me' | Set-Content (Join-Path $target 'keep.txt')
cmd /c mklink /J "$plugins\wadi2d_qgis" "$target" | Out-Null
Install-Release 'junction' @('-EngineRoot', $gpuRoot, '-RecordRoot', $gpuRoot, '-PluginsDir', $plugins)
"junction target kept: $(Test-Path (Join-Path $target 'keep.txt')); plugin copied: $(Test-Path "$plugins\wadi2d_qgis\metadata.txt")"
