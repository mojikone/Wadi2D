# Wadi2D installer: which engine this PC can run. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
# Dot-sourced by install_wadi2d.ps1. The GPU engine ships CUDA 12, which needs an NVIDIA driver of 527.41 or later on
# Windows (CUDA 12 minor-version compatibility) and a card of compute capability 5.0 or later (CUDA 12 dropped Kepler).
# The card and driver are read from nvidia-smi wherever the driver put it, else from Windows' list of display adapters,
# so a PC whose nvidia-smi is not on the PATH is still seen, and an old card or driver never downloads the CUDA stack.

$GpuDriverMin = [version]'527.41'
$GpuComputeMin = [version]'5.0'

function Find-NvidiaSmi {
    $candidates = @()
    $onPath = Get-Command 'nvidia-smi' -ErrorAction SilentlyContinue
    if ($onPath) { $candidates += $onPath.Source }
    if ($env:SystemRoot) { $candidates += (Join-Path $env:SystemRoot 'System32\nvidia-smi.exe') }
    if ($env:ProgramFiles) { $candidates += (Join-Path $env:ProgramFiles 'NVIDIA Corporation\NVSMI\nvidia-smi.exe') }
    foreach ($path in $candidates) { if ($path -and (Test-Path -LiteralPath $path)) { return $path } }
    return $null
}

function ConvertFrom-WindowsDriverVersion([string]$Text) {
    # Windows writes an NVIDIA driver as 31.0.15.2802 for 528.02: the last five digits are the NVIDIA version.
    $digits = ($Text -replace '[^0-9]', '')
    if ($digits.Length -lt 5) { return '' }
    $tail = $digits.Substring($digits.Length - 5)
    return ('{0}.{1}' -f [int]$tail.Substring(0, 3), $tail.Substring(3))
}

function Read-NvidiaCard {
    # The first NVIDIA card as @{Name; Driver; Compute}, Compute empty when the driver cannot tell; or $null.
    $ErrorActionPreference = 'Continue'
    $smi = Find-NvidiaSmi
    if ($smi) {
        $line = @(& $smi '--query-gpu=name,driver_version,compute_cap' '--format=csv,noheader' 2>$null)
        if ($LASTEXITCODE -eq 0 -and $line.Count -ge 1 -and $line[0]) {
            $parts = $line[0] -split ',\s*'
            if ($parts.Count -ge 3) { return @{ Name = $parts[0].Trim(); Driver = $parts[1].Trim(); Compute = $parts[2].Trim() } }
        }
        $line = @(& $smi '--query-gpu=name,driver_version' '--format=csv,noheader' 2>$null)  # old drivers: no compute_cap
        if ($LASTEXITCODE -eq 0 -and $line.Count -ge 1 -and $line[0]) {
            $parts = $line[0] -split ',\s*'
            if ($parts.Count -ge 2) { return @{ Name = $parts[0].Trim(); Driver = $parts[1].Trim(); Compute = '' } }
        }
    }
    $card = @(Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'NVIDIA' })
    if ($card.Count -ge 1) {
        return @{ Name = $card[0].Name; Driver = (ConvertFrom-WindowsDriverVersion $card[0].DriverVersion); Compute = '' }
    }
    return $null
}

function Select-Engine($Card) {
    # @{Gpu = $true or $false; Why = one line for the user}. Unknown compute capability passes on the driver alone:
    # every driver of 527.41 or later that cannot run CUDA 12 on its card is caught by the check after the install.
    if (-not $Card) { return @{ Gpu = $false; Why = 'No NVIDIA card: CPU engine, tens of times slower' } }
    $name = $Card.Name
    $driver = $null
    try { $driver = [version]$Card.Driver } catch { $driver = $null }
    if (-not $driver) {
        return @{ Gpu = $false; Why = "$name, driver version unreadable: CPU engine. Update the NVIDIA driver and run this again for the GPU." }
    }
    if ($driver -lt $GpuDriverMin) {
        return @{ Gpu = $false; Why = "$name, driver $($Card.Driver): older than $GpuDriverMin, which the GPU engine needs. CPU engine; update the driver and run this again for the GPU." }
    }
    if ($Card.Compute) {
        $compute = $null
        try { $compute = [version]$Card.Compute } catch { $compute = $null }
        if ($compute -and $compute -lt $GpuComputeMin) {
            return @{ Gpu = $false; Why = "$name (compute capability $($Card.Compute)) is too old for the GPU engine: CPU engine." }
        }
    }
    return @{ Gpu = $true; Why = "$name, driver $($Card.Driver): GPU engine" }
}
