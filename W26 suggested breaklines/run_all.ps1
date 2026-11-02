# The bank-line runs in order, each appending to results.jsonl; a failed run does not stop the next.
$py = "D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe"
$script = Join-Path $PSScriptRoot "bank_runs.py"
$runs = @(
    @("bidah", "bidah_20_none", "20"), @("bidah", "bidah_20_lines", "20", "lines"),
    @("bidah", "bidah_10_none", "10"), @("bidah", "bidah_10_lines", "10", "lines"),
    @("bidah", "bidah_05_none", "5"),
    @("faydh", "faydh_20_none", "20"), @("faydh", "faydh_20_lines", "20", "lines"),
    @("faydh", "faydh_10_none", "10"), @("faydh", "faydh_10_lines", "10", "lines"),
    @("faydh", "faydh_05_none", "5")
)
foreach ($r in $runs) {
    & $py $script $r[0] run $r[1] $r[2] $r[3] 2>&1 | Select-Object -Last 1
}
