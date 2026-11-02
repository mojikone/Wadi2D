# Runs one dock scenario in its own QGIS 3.44.8 with a throwaway profile, on this checkout. Never touches an open QGIS window.
# usage: powershell -File run_check.ps1 <scenario.py> <throwaway folder> [-Name log name] [-Copy folder for the log] [-LimitMin 40]
param(
    [Parameter(Mandatory = $true)][string]$Scenario,
    [Parameter(Mandatory = $true)][string]$Folder,
    [string]$Name = '',
    [string]$Copy = '',
    [int]$LimitMin = 40
)
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $Name) { $Name = [IO.Path]::GetFileNameWithoutExtension($Scenario) }
$work = Join-Path $Folder $Name
if (Test-Path $work) { Remove-Item -Recurse -Force $work }
New-Item -ItemType Directory -Force -Path $work, (Join-Path $work 'profiles') | Out-Null
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
set WADI2D_SCENARIO=$Scenario
call "C:\Program Files\QGIS 3.44.8\bin\qgis-ltr.bat" --nologo --noversioncheck --profiles-path "$(Join-Path $work 'profiles')" --code "$PSScriptRoot\harness.py"
"@ | Set-Content -Path $bat -Encoding ascii
Start-Process -FilePath $bat -WindowStyle Minimized
$log = Join-Path $work 'log.txt'
$start = Get-Date
while (((Get-Date) - $start).TotalMinutes -lt $LimitMin) {
    Start-Sleep -Seconds 5
    if ((Test-Path $log) -and (Select-String -Path $log -Pattern ' DONE$' -CaseSensitive -Quiet)) { break }
}
Start-Sleep -Seconds 6
$summary = if (Test-Path $log) { (Select-String -Path $log -Pattern 'SUMMARY').Line } else { 'no log' }
"{0} {1:N0} s; {2}" -f $Name, ((Get-Date) - $start).TotalSeconds, $summary
if ($Copy -and (Test-Path $log)) { Copy-Item $log (Join-Path $Copy "log_$Name.txt") -Force }
