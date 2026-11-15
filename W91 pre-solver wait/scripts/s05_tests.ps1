# The test files this branch's changes reach, one file at a time under W85's 10 GB commit cap; GPU files left out
# (W79's reruns hold the card). Writes runs\tests.log: one line per file with its pytest summary.
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repo
$env:PYTHONPATH = $repo
$py = "D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe"
$cap = "D:\Mojtaba\Renardet\Wadi2D\W85 what limits the time step\scripts\capped_pytest.py"
$log = Join-Path $PSScriptRoot "..\runs\tests.log"
$files = @(
    "tests\engine\test_pit_rebuild.py", "tests\terrain\test_survey_boxes.py", "tests\engine\test_fill_pits.py",
    "tests\terrain\test_pits.py", "tests\terrain\test_volumes.py", "tests\tables\test_local_radius.py",
    "tests\tables\test_parallel.py", "tests\engine\test_strip_cache.py", "tests\engine\test_strips_run.py",
    "tests\engine\test_mesh_earthworks.py", "tests\engine\test_terrain.py", "tests\engine\test_edge_valleys.py",
    "tests\engine\test_left_out.py", "tests\engine\test_breach_strips.py", "tests\engine\test_step_limiter.py",
    "tests\demstore\test_wiring.py", "tests\strips\test_banks.py", "tests\strips\test_centres.py",
    "tests\strips\test_geometry_precision.py", "tests\strips\test_gorge.py", "tests\strips\test_hybrid.py",
    "tests\strips\test_mesher.py", "tests\strips\test_objects.py", "tests\strips\test_pixels.py",
    "tests\strips\test_speed_record.py", "tests\strips\test_tables.py", "tests\terrain\test_checks.py",
    "tests\terrain\test_faces.py", "tests\terrain\test_geometry.py", "tests\terrain\test_lining.py",
    "tests\terrain\test_rasterise.py", "tests\terrain\test_section_input.py", "tests\engine\test_run.py"
)
Set-Content $log "" -Encoding ascii
foreach ($f in $files) {
    $out = & $py $cap 10 $f -q -p no:randomly 2>&1 | Out-String
    $summary = ($out -split "`n" | Where-Object { $_ -match "passed|failed|error" } | Select-Object -Last 1)
    Add-Content $log "$f :: $($summary.Trim())" -Encoding ascii
    if ($out -match "failed|error") { Add-Content $log $out -Encoding ascii }
}
Add-Content $log "DONE" -Encoding ascii
