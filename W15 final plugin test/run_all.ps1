# Runs the five dock checks in turn, each in its own QGIS 3.44.8 with a throwaway profile. It never touches an open QGIS window.
# usage: powershell -File run_all.ps1 <throwaway folder> <copy of the Block 2 HMS folder>
param([Parameter(Mandatory = $true)][string]$Folder, [Parameter(Mandatory = $true)][string]$Hms, [int]$LimitMin = 50)
$repo = Split-Path -Parent $PSScriptRoot
foreach ($name in 'dock_options', 'dock_terrain', 'dock_outputs', 'dock_mesh', 'dock_mesh_maps') {
    $work = Join-Path $Folder $name
    if (Test-Path $work) { Remove-Item -Recurse -Force $work }
    New-Item -ItemType Directory -Force -Path $work, (Join-Path $work 'profiles'), (Join-Path $work 'data') | Out-Null
    @"
import sys
sys.path.insert(0, r'$repo')
from wadi2d.engine.cli import main
raise SystemExit(main())
"@ | Set-Content -Path (Join-Path $work 'engine.py') -Encoding ascii
    $bat = Join-Path $work 'start.bat'
    @"
@echo off
set WADI2D_PLUG=$work
set WADI2D_REPO=$repo
set WADI2D_HMS=$Hms
call "C:\Program Files\QGIS 3.44.8\bin\qgis-ltr.bat" --nologo --noversioncheck --profiles-path "$(Join-Path $work 'profiles')" --code "$PSScriptRoot\$name.py"
"@ | Set-Content -Path $bat -Encoding ascii
    Start-Process -FilePath $bat -WindowStyle Minimized
    $log = Join-Path $work 'log.txt'
    $start = Get-Date
    while (((Get-Date) - $start).TotalMinutes -lt $LimitMin) {
        Start-Sleep -Seconds 10
        if ((Test-Path $log) -and (Select-String -Path $log -Pattern ' DONE$' -CaseSensitive -Quiet)) { break }
    }
    Start-Sleep -Seconds 8
    $summary = if (Test-Path $log) { (Select-String -Path $log -Pattern 'SUMMARY').Line } else { 'no log' }
    $fails = if (Test-Path $log) { @(Select-String -Path $log -Pattern ' FAIL ').Count } else { -1 }
    "{0} {1:N0} s; {2}; fail lines {3}" -f $name, ((Get-Date) - $start).TotalSeconds, $summary, $fails
    if (Test-Path $log) { Copy-Item $log (Join-Path $PSScriptRoot "log_$name.txt") -Force }
}
