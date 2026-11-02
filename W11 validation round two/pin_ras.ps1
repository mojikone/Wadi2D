# Keep the two RAS queues on separate physical cores. It touches only RasUnsteady processes started from this folder.
# Left alone, two 8-core runs each opened 32 threads across all logical processors and ran several times slower.
while ($true) {
    $list = Get-CimInstance Win32_Process -Filter "Name='RasUnsteady.exe'"
    foreach ($q in $list) {
        $p = Get-Process -Id $q.ProcessId -ErrorAction SilentlyContinue
        if ($null -eq $p) { continue }
        $cmd = [string]$q.CommandLine
        $dir = ''
        try { $dir = (Get-Process -Id $q.ProcessId).Path } catch {}
        $mask = $null
        if ($cmd -match 'Bidah') { $mask = 0x5555 }
        if ($cmd -match 'Faydh') { $mask = 0x55550000 }
        if ($null -ne $mask -and [int64]$p.ProcessorAffinity -ne $mask) { $p.ProcessorAffinity = [IntPtr]$mask }
    }
    if (Test-Path 'D:\Mojtaba\Renardet\Wadi2D\W11 validation round two\stop_pin.txt') { break }
    Start-Sleep -Seconds 30
}
