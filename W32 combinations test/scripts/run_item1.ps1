# Item 1: the four dock scenarios on one backend, one after another. usage: powershell -File run_item1.ps1 <gpu|cpu>
param([Parameter(Mandatory = $true)][ValidateSet('gpu', 'cpu')][string]$Backend)
$here = $PSScriptRoot
foreach ($s in 'dock_basin_bidah_w32.py', 'dock_mesh_controls_w32.py', 'dock_result_lines_w32.py', 'dock_storm_w32.py') {
    "=== $s $Backend $(Get-Date -Format 'HH:mm:ss')"
    powershell -NoProfile -File (Join-Path $here 'run_dock.ps1') $s $Backend
}
"=== all done $(Get-Date -Format 'HH:mm:ss')"
