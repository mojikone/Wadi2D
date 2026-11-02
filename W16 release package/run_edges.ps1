# The installer's edges: the .bat itself, no Python on the PATH, no Python anywhere, a half-unzipped folder.
# usage: powershell -File run_edges.ps1 <unzipped release folder> <throwaway folder>
param([Parameter(Mandatory = $true)][string]$Release, [Parameter(Mandatory = $true)][string]$Folder)
$base = Join-Path $env:LOCALAPPDATA 'W2D test\edges'
New-Item -ItemType Directory -Force -Path $base, $Folder | Out-Null
$bat = Join-Path $Release 'install_wadi2d.bat'
$ps1 = Join-Path $Release 'install_wadi2d.ps1'
$systemPath = 'C:\Windows\System32;C:\Windows;C:\Windows\System32\WindowsPowerShell\v1.0'

# The .bat, as a double-click runs it; its pause reads nothing and goes on.
$out = cmd /c "`"$bat`" -EngineRoot `"$base\bat\Wadi2D`" -PluginsDir `"$Folder\bat_plugins`" -CpuOnly < nul" 2>&1 | Out-String
"bat: installed $($out -match 'Installed\.'); plugin $(Test-Path "$Folder\bat_plugins\wadi2d_qgis\metadata.txt")"

# Neither py nor python on the PATH: the installer has to find QGIS's own.
$saved = $env:Path
$env:Path = $systemPath
powershell -NoProfile -ExecutionPolicy Bypass -File $ps1 -EngineRoot "$base\qgis\Wadi2D" -PluginsDir "$Folder\qgis_plugins" -CpuOnly *> "$Folder\install_qgis_python.log"
"no python on PATH: exit $LASTEXITCODE; $((Get-Content "$base\qgis\Wadi2D\engine\pyvenv.cfg" | Select-String '^home').Line)"

# No Python at all. Windows gives every child its own ProgramFiles, so QGIS cannot be hidden here; a bad path takes the same way out.
$out = powershell -NoProfile -ExecutionPolicy Bypass -File $ps1 -Python 'C:\no such\python.exe' -EngineRoot "$base\none\Wadi2D" -PluginsDir "$Folder\none_plugins" -CpuOnly *>&1 | Out-String
"no python: exit $LASTEXITCODE; $(($out -split "`n" | Select-String 'NOT INSTALLED').Line); engine folder made: $(Test-Path "$base\none")"
$env:Path = $saved

# The installer alone, as a user gets it by opening it from inside the zip.
$alone = Join-Path $Folder 'alone'
New-Item -ItemType Directory -Force -Path $alone | Out-Null
Copy-Item $ps1 $alone
$out = powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $alone 'install_wadi2d.ps1') -EngineRoot "$base\alone\Wadi2D" -PluginsDir "$Folder\alone_plugins" *>&1 | Out-String
"installer alone: exit $LASTEXITCODE; $(($out -split "`n" | Select-String 'NOT INSTALLED').Line)"
