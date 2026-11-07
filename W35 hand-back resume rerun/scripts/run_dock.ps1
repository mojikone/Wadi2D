# One W32 dock scenario on one backend, through tests\dock\run_check.ps1 (a throwaway QGIS 3.44.8 and profile).
# usage: powershell -File run_dock.ps1 <scenario file name> <gpu|cpu> [-Folder <throwaway root>] [-LimitMin 90]
# The CPU pass hides the card from CuPy with CUDA_VISIBLE_DEVICES=-1; the engine inherits it from QGIS. Never touches
# another QGIS window. The log and the numbers come back to ..\dock\.
param(
    [Parameter(Mandatory = $true)][string]$Scenario,
    [Parameter(Mandatory = $true)][ValidateSet('gpu', 'cpu')][string]$Backend,
    [string]$Folder = "$env:LOCALAPPDATA\Temp\claude\D--Mojtaba-Renardet-Wadi2D\563cf3f8-070b-42eb-82ea-489205b14695\scratchpad\w32\dock",
    [int]$LimitMin = 90
)
$w32 = Split-Path -Parent $PSScriptRoot
$repo = Split-Path -Parent $w32
$name = "$([IO.Path]::GetFileNameWithoutExtension($Scenario))_$Backend"
if ($Backend -eq 'cpu') { $env:CUDA_VISIBLE_DEVICES = '-1' } else { Remove-Item Env:CUDA_VISIBLE_DEVICES -ErrorAction SilentlyContinue }
New-Item -ItemType Directory -Force -Path $Folder, (Join-Path $w32 'dock') | Out-Null
powershell -NoProfile -File (Join-Path $repo 'tests\dock\run_check.ps1') (Join-Path $PSScriptRoot $Scenario) $Folder -Name $name -Copy (Join-Path $w32 'dock') -LimitMin $LimitMin
$numbers = Join-Path (Join-Path $Folder $name) 'w32_numbers.json'
if (Test-Path $numbers) { Copy-Item $numbers (Join-Path (Join-Path $w32 'dock') "numbers_$name.json") -Force }
Get-ChildItem (Join-Path $Folder $name) -Filter '*.png' | ForEach-Object { Copy-Item $_.FullName (Join-Path (Join-Path $w32 'dock') "$name`_$($_.Name)") -Force }
