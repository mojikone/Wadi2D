# Wadi2D installer. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
# Sets up the engine in a Python environment of its own and puts the plugin into QGIS. Asks nothing; run it again to update.
param(
    [string]$EngineRoot = (Join-Path $env:LOCALAPPDATA 'Wadi2D'),
    [string]$PluginsDir = (Join-Path $env:APPDATA 'QGIS\QGIS3\profiles\default\python\plugins'),
    [string]$RecordRoot = (Join-Path $env:LOCALAPPDATA 'Wadi2D'),
    [string]$Python = '',
    [switch]$CpuOnly
)

$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$PluginName = 'wadi2d_qgis'
$PythonVersions = @('3.12', '3.13')
$NeededGB = 4
$WindowsPathLimit = 260
$DeepestFile = 145  # characters from the engine root to the deepest file CuPy ships, with a margin
$Encoding = New-Object System.Text.UTF8Encoding $false  # no byte-order mark: the plugin reads this file as plain text

function Stop-Install([string]$Text) {
    Write-Host ''
    Write-Host "NOT INSTALLED: $Text" -ForegroundColor Red
    exit 1
}

function Test-Interpreter([string[]]$Command) {
    # The full path of an interpreter of a supported version, or nothing. The Windows Store stub fails here too.
    $ErrorActionPreference = 'Continue'
    $program = $Command[0]
    $arguments = @($Command | Select-Object -Skip 1)
    $probe = "import sys; print(sys.executable); print('%d.%d' % sys.version_info[:2])"
    try {
        $answer = @(& $program @arguments -c $probe 2>$null)
    } catch {
        return $null
    }
    if ($LASTEXITCODE -eq 0 -and $answer.Count -ge 2 -and $PythonVersions -contains $answer[1]) { return $answer[0] }
    return $null
}

function Find-Interpreter {
    if ($Python) { return Test-Interpreter @($Python) }
    foreach ($version in $PythonVersions) {
        $found = Test-Interpreter @('py', "-$version")
        if ($found) { return $found }
    }
    $found = Test-Interpreter @('python')
    if ($found) { return $found }
    # QGIS carries its own Python, newest QGIS first: engineers have QGIS and often nothing else.
    $qgis = @(Get-ChildItem -LiteralPath $env:ProgramFiles -Filter 'QGIS*' -Directory -ErrorAction SilentlyContinue) +
        @(Get-Item 'C:\OSGeo4W*' -ErrorAction SilentlyContinue)
    foreach ($folder in ($qgis | Sort-Object Name -Descending)) {
        foreach ($python in @(Get-ChildItem (Join-Path $folder.FullName 'apps\Python3*\python.exe') -ErrorAction SilentlyContinue)) {
            $found = Test-Interpreter @($python.FullName)
            if ($found) { return $found }
        }
    }
    return $null
}

function Invoke-Checked([string]$Failure, [string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { Stop-Install $Failure }
}

function Remove-OldPlugin([string]$Path) {
    # A developer's junction goes alone: emptying it would empty the repository it points at.
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        [IO.Directory]::Delete($Path)
    } else {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

Remove-Item Env:PYTHONHOME, Env:PYTHONPATH -ErrorAction SilentlyContinue

Write-Host 'Wadi2D installer'
$Wheel = @(Get-ChildItem -LiteralPath $Here -Filter 'wadi2d-*.whl')
$PluginZip = @(Get-ChildItem -LiteralPath $Here -Filter "$PluginName-*.zip")
$Constraints = Join-Path $Here 'constraints.txt'
if ($Wheel.Count -ne 1 -or $PluginZip.Count -ne 1 -or -not (Test-Path -LiteralPath $Constraints)) {
    Stop-Install 'Files are missing. Unzip the whole release into a folder and run this from there.'
}
$Wheel = $Wheel[0].FullName
$PluginZip = $PluginZip[0].FullName

Write-Host '[1/5] Looking for Python'
$Base = Find-Interpreter
if (-not $Base) {
    Stop-Install 'Python 3.12 was not found. Install it from https://www.python.org/downloads/ and run this again. Or give one: install_wadi2d.bat -Python C:\path\python.exe'
}
Write-Host "      $Base"

$FullRoot = [IO.Path]::GetFullPath($EngineRoot)
if ($FullRoot.Length + $DeepestFile -ge $WindowsPathLimit) {
    Stop-Install "This folder is too long for Windows: $FullRoot. Give a shorter one: install_wadi2d.bat -EngineRoot C:\Wadi2D"
}
$Drive = [IO.Path]::GetPathRoot($FullRoot)
$FreeGB = (New-Object IO.DriveInfo $Drive).AvailableFreeSpace / 1GB
if ($FreeGB -lt $NeededGB) { Stop-Install ("{0:N1} GB free on {1}, about {2} GB needed." -f $FreeGB, $Drive, $NeededGB) }

$Gpu = $false
if (-not $CpuOnly) {
    $smi = Get-Command 'nvidia-smi' -ErrorAction SilentlyContinue
    $Gpu = [bool]$smi
}
$Extras = if ($Gpu) { 'gpu,mesh,vector' } else { 'mesh,vector' }
Write-Host ("      {0}" -f $(if ($Gpu) { 'NVIDIA card found: GPU engine' } else { 'No NVIDIA card: CPU engine, tens of times slower' }))

Write-Host "[2/5] Making the engine's environment in $EngineRoot"
$Venv = Join-Path $EngineRoot 'engine'
$EnginePython = Join-Path $Venv 'Scripts\python.exe'
New-Item -ItemType Directory -Force -Path $EngineRoot | Out-Null
if (Test-Path -LiteralPath $EnginePython) {
    if (-not (Test-Interpreter @($EnginePython))) { Remove-Item -LiteralPath $Venv -Recurse -Force }
}
if (-not (Test-Path -LiteralPath $EnginePython)) {
    Invoke-Checked 'The environment could not be made.' $Base @('-m', 'venv', $Venv)
}

Write-Host '[3/5] Installing the engine, about 2 GB to download on the first run'
$Log = Join-Path $EngineRoot 'install.log'
$Spec = $Wheel + '[' + $Extras + ']'
$Pip = @('-m', 'pip', 'install', '--disable-pip-version-check', '--log', $Log)
Invoke-Checked "The packages did not install. See $Log" $EnginePython ($Pip + @('--constraint', $Constraints, $Spec))
Invoke-Checked "The engine did not install. See $Log" $EnginePython ($Pip + @('--force-reinstall', '--no-deps', $Wheel))

Write-Host '[4/5] Checking the engine'
Invoke-Checked 'The engine does not start.' $EnginePython @('-m', 'wadi2d.engine.cli', 'doctor')
if ($Gpu) {
    $ErrorActionPreference = 'Continue'
    & $EnginePython -c 'import cupy; print(int(cupy.ones(4).sum()))' 2>$null | Out-Null
    $worked = $LASTEXITCODE -eq 0
    $ErrorActionPreference = 'Stop'
    if (-not $worked) { Write-Host 'WARNING: the card did not answer, so runs will use the CPU. Update the NVIDIA driver.' -ForegroundColor Yellow }
}
$ErrorActionPreference = 'Continue'
& $EnginePython -c 'import whitebox; whitebox.WhiteboxTools().version()' 2>$null | Out-Null
$worked = $LASTEXITCODE -eq 0
$ErrorActionPreference = 'Stop'
if (-not $worked) { Write-Host 'WARNING: WhiteboxTools did not load, so the Mesh section will not work. Everything else will.' -ForegroundColor Yellow }

Write-Host "[5/5] Putting the plugin into QGIS: $PluginsDir"
$Record = '"{0}" -m wadi2d.engine.cli' -f $EnginePython
New-Item -ItemType Directory -Force -Path $RecordRoot | Out-Null  # always here, wherever the engine went: Install from ZIP looks here
[IO.File]::WriteAllText((Join-Path $RecordRoot 'engine.txt'), "$Record`n", $Encoding)
$Target = Join-Path $PluginsDir $PluginName
try {
    New-Item -ItemType Directory -Force -Path $PluginsDir | Out-Null
    Remove-OldPlugin $Target
    Expand-Archive -LiteralPath $PluginZip -DestinationPath $PluginsDir
    [IO.File]::WriteAllText((Join-Path $Target 'engine.txt'), "$Record`n", $Encoding)
} catch {
    Stop-Install "The plugin could not be copied. Close QGIS and run this again. ($($_.Exception.Message))"
}

Write-Host ''
Write-Host 'Installed.' -ForegroundColor Green
Write-Host 'If QGIS is open, close it. Open QGIS, go to Plugins > Manage and Install Plugins > Installed, and tick Wadi2D.'
Write-Host 'The dock then opens from its toolbar button, or from Plugins > Wadi2D > Wadi2D.'
exit 0
