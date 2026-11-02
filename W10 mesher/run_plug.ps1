# Starts plug_mesh.py in a separate QGIS 3.44.8 with a throwaway profile. It never touches an open QGIS window.
# usage: powershell -File run_plug.ps1 <throwaway folder>
param([Parameter(Mandatory = $true)][string]$Folder)
$repo = Split-Path -Parent $PSScriptRoot
New-Item -ItemType Directory -Force -Path $Folder, (Join-Path $Folder 'profiles') | Out-Null
$engine = Join-Path $Folder 'engine.py'
@"
import sys
sys.path.insert(0, r'$repo')
from wadi2d.engine.cli import main
raise SystemExit(main())
"@ | Set-Content -Path $engine -Encoding ascii
$bat = Join-Path $Folder 'start.bat'
@"
@echo off
set WADI2D_PLUG=$Folder
set WADI2D_REPO=$repo
call "C:\Program Files\QGIS 3.44.8\bin\qgis-ltr.bat" --nologo --noversioncheck --profiles-path "$(Join-Path $Folder 'profiles')" --code "$PSScriptRoot\plug_mesh.py"
"@ | Set-Content -Path $bat -Encoding ascii
Start-Process -FilePath $bat -WindowStyle Minimized
"started"
