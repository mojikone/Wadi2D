# The line runs on the lines as shipped, plus the Faydh 5 m reference. The first line runs, on lines before the
# tributary and meander rules, are kept in results_first_lines.jsonl; the no-line rows carry over, since lines do not
# touch them.
$py = "D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe"
$script = Join-Path $PSScriptRoot "bank_runs.py"
$first = Join-Path $PSScriptRoot "results_first_lines.jsonl"
$results = Join-Path $PSScriptRoot "results.jsonl"
if (-not (Test-Path $first)) {
    Move-Item $results $first
    Get-Content $first | Where-Object { $_ -match '"lines": 0' } | Set-Content -Path $results -Encoding utf8
}
$names = @("bidah_20_lines", "bidah_10_lines", "bidah_10_lines_below", "faydh_20_lines", "faydh_10_lines", "faydh_05_none")
foreach ($name in $names) {
    $folder = Join-Path $PSScriptRoot ("runs\" + $name)
    if (Test-Path $folder) { Remove-Item -Recurse -Force $folder }
}
$runs = @(
    @("bidah", "bidah_20_lines", "20", "lines"), @("bidah", "bidah_10_lines", "10", "lines"),
    @("bidah", "bidah_10_lines_below", "10", "lines", "-1.0"),
    @("faydh", "faydh_20_lines", "20", "lines"), @("faydh", "faydh_10_lines", "10", "lines"),
    @("faydh", "faydh_05_none", "5")
)
foreach ($r in $runs) {
    & $py $script $r[0] run $r[1] $r[2] $r[3] $r[4] 2>&1 | Select-Object -Last 1
}
