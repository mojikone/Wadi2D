# The test files this branch reaches, one at a time under a 10 GB cap on committed memory (W85's capped_pytest).
#   powershell -File s03_tests.ps1     (from the repository root; writes runs\tests.txt)
$py = "D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe"
$cap = "W85 what limits the time step\scripts\capped_pytest.py"
$out = "W92 centre mesh speed\runs\tests.txt"
$files = @(
  "tests/demstore/test_coarse.py", "tests/demstore/test_store.py", "tests/demstore/test_wiring.py", "tests/demstore/test_scratch.py",
  "tests/strips/test_centres.py", "tests/strips/test_gorge.py", "tests/strips/test_mesher.py", "tests/strips/test_banks.py",
  "tests/strips/test_geometry_precision.py", "tests/strips/test_objects.py", "tests/strips/test_tables.py", "tests/strips/test_hybrid.py",
  "tests/strips/test_sleeping.py", "tests/strips/test_speed_record.py",
  "tests/breaklines/test_suggest.py", "tests/breaklines/test_pixels.py",
  "tests/engine/test_strips_run.py", "tests/engine/test_strip_cache.py", "tests/engine/test_left_out.py",
  "tests/engine/test_breach_strips.py", "tests/engine/test_breach_oblique.py", "tests/engine/test_edge_valleys.py",
  "tests/engine/test_pit_rebuild.py", "tests/engine/test_inflow_lines.py", "tests/engine/test_sleeping_run.py",
  "tests/solver/test_poly.py", "tests/plugin/test_suggest_lines.py", "tests/plugin/test_breach_rows.py"
)
Set-Content -Path $out -Value "" -Encoding utf8
foreach ($f in $files) {
  $t0 = Get-Date
  $last = & $py $cap 10 $f -q -p no:cacheprovider 2>&1 | Select-Object -Last 1
  $s = [math]::Round(((Get-Date) - $t0).TotalSeconds)
  Add-Content -Path $out -Value "$f : $last ($s s)" -Encoding utf8
}
Add-Content -Path $out -Value "DONE" -Encoding utf8
