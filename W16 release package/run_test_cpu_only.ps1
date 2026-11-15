# CPU-only install of the built release into throwaway folders, then the W16 dock checks 'cpu' and 'zip' in throwaway QGIS profiles.
# Adapted from W16 release package\run_test.ps1 without the GPU install (the card is busy). Never touches the real profile or engine record.
$ErrorActionPreference = 'Continue'
$scratch = 'C:\Users\mojtaba\AppData\Local\Temp\claude\0411bb1eda7ca588\563cf3f8-070b-42eb-82ea-489205b14695\scratchpad'
$repo = 'D:\Mojtaba\Renardet\Wadi2D\.claude\worktrees\agent-afef97861560c28a5'
$here = Join-Path $repo 'W16 release package'
$zipFile = Join-Path $repo 'dist\Wadi2D-0.4.0rc1-windows.zip'
$Folder = Join-Path $scratch 'rc1'
$unz = Join-Path $Folder 'unzipped'
Remove-Item -LiteralPath $Folder -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $unz | Out-Null
Expand-Archive -LiteralPath $zipFile -DestinationPath $unz
$Release = Join-Path $unz 'Wadi2D-0.4.0rc1-windows'
$installer = Join-Path $Release 'install_wadi2d.ps1'
$version = ((Get-Content (Join-Path $Release 'BUILD.txt')) -split ' ')[1].TrimEnd(',')
$base = Join-Path $env:LOCALAPPDATA 'W2D rc1'
New-Item -ItemType Directory -Force -Path $base | Out-Null
$cpuRoot = Join-Path $base 'cpu\Wadi2D'
$plugins = Join-Path $Folder 'cpu\profiles\profiles\default\python\plugins'

$start = Get-Date
powershell -NoProfile -ExecutionPolicy Bypass -File $installer -EngineRoot $cpuRoot -RecordRoot $cpuRoot -PluginsDir $plugins -CpuOnly *> (Join-Path $Folder 'install_cpu.log')
"install cpu exit $LASTEXITCODE, {0:N0} s" -f ((Get-Date) - $start).TotalSeconds

function Start-Check([string]$Mode, [string]$LocalAppData, [string]$Zip) {
    $work = Join-Path $Folder $Mode
    New-Item -ItemType Directory -Force -Path (Join-Path $work 'data') | Out-Null
    $bat = Join-Path $work 'start.bat'
    $lines = @('@echo off', 'set CUDA_VISIBLE_DEVICES=', "set WADI2D_MODE=$Mode", "set WADI2D_PLUG=$work", "set WADI2D_REPO=$repo", "set WADI2D_HMS=none", "set WADI2D_VERSION=$version", "set WADI2D_ZIP=$Zip")
    if ($LocalAppData) { $lines += "set LOCALAPPDATA=$LocalAppData" }
    $lines += "call `"C:\Program Files\QGIS 3.44.8\bin\qgis-ltr.bat`" --nologo --noversioncheck --profiles-path `"$(Join-Path $work 'profiles')`" --code `"$here\dock_release.py`""
    $lines | Set-Content -Path $bat -Encoding ascii
    Start-Process -FilePath $bat -WindowStyle Minimized
    $log = Join-Path $work 'log.txt'
    $t0 = Get-Date
    while (((Get-Date) - $t0).TotalMinutes -lt 30) {
        Start-Sleep -Seconds 10
        if ((Test-Path $log) -and (Select-String -Path $log -Pattern ' DONE$' -CaseSensitive -Quiet)) { break }
    }
    Start-Sleep -Seconds 8
    $summary = if (Test-Path $log) { (Select-String -Path $log -Pattern 'SUMMARY').Line } else { 'no log' }
    "{0} {1:N0} s; {2}" -f $Mode, ((Get-Date) - $t0).TotalSeconds, $summary
}

Start-Check 'cpu' '' ''
$zipHome = Join-Path $base 'zip home'
New-Item -ItemType Directory -Force -Path (Join-Path $zipHome 'Wadi2D') | Out-Null
Copy-Item (Join-Path $cpuRoot 'engine.txt') (Join-Path $zipHome 'Wadi2D\engine.txt') -Force
Start-Check 'zip' $zipHome (Get-ChildItem -LiteralPath $Release -Filter 'wadi2d_qgis-*.zip').FullName
'ALL DONE'
