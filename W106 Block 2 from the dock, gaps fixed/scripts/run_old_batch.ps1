# The ten older dock scenarios W99 and W101 used, one after the other, each in its own throwaway QGIS, from one copy
# of the code. usage: powershell -File run_old_batch.ps1 <copy of the repository> <throwaway folder> <folder for the logs>
param(
    [Parameter(Mandatory = $true)][string]$Repo,
    [Parameter(Mandatory = $true)][string]$Out,
    [Parameter(Mandatory = $true)][string]$Logs
)
$scenarios = @(
    'W17 cell grid layer\dock_cell_grid.py',
    'W18 boundary table\dock_boundary_table.py',
    'W22 profile editor\dock_profile_editor.py',
    'W23 mesh controls\dock_mesh_controls.py',
    'W26 suggested breaklines\dock_suggest.py',
    'W34 reservoir start level\dock_dam_start.py',
    'W61 inflow hydrograph lines\dock_flow_line.py',
    'W68 layer groups and dock rows\dock_breach.py',
    'W73 basin points and editing\dock_basin_points.py',
    'W77 rain gauges and storm map\dock_gauges.py'
)
New-Item -ItemType Directory -Force -Path $Out, $Logs | Out-Null
foreach ($scenario in $scenarios) {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $Repo 'tests\dock\run_check.ps1') (Join-Path $Repo $scenario) $Out -Copy $Logs -LimitMin 40
}
