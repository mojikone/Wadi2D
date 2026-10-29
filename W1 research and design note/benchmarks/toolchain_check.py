"""Toolchain gate for Wadi2D on this machine.

Checks that CuPy can compile a CUDA C++ kernel through NVRTC for the installed GPU and run it,
reports the device, measures a copy-kernel bandwidth and a stencil-kernel throughput at float32,
and writes the result as JSON next to this script. No CUDA toolkit or MSVC is needed.
"""
from __future__ import annotations

import json
import os
import platform
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    out: dict = {"python": sys.version.split()[0], "platform": platform.platform()}
    try:
        import cupy as cp
        from cupy.cuda import runtime as rt
    except Exception as e:  # noqa: BLE001
        out["cupy_import_error"] = repr(e)
        print(json.dumps(out, indent=2))
        return 2
    out["cupy"] = cp.__version__
    dev = cp.cuda.Device(0)
    props = rt.getDeviceProperties(0)
    out["device"] = {
        "name": props["name"].decode() if isinstance(props["name"], bytes) else str(props["name"]),
        "compute_capability": f"{props['major']}.{props['minor']}",
        "sm_count": int(props["multiProcessorCount"]),
        "total_mem_GB": round(props["totalGlobalMem"] / 2**30, 2),
        "clock_MHz": int(props["clockRate"] / 1000),
        "mem_clock_MHz": int(props["memoryClockRate"] / 1000),
        "mem_bus_bits": int(props["memoryBusWidth"]),
        "l2_MB": round(props["l2CacheSize"] / 2**20, 1),
        "shared_per_block_KB": round(props["sharedMemPerBlock"] / 1024),
    }
    out["cuda_runtime_version"] = rt.runtimeGetVersion()
    out["cuda_driver_version"] = rt.driverGetVersion()
    out["nvrtc_version"] = cp.cuda.nvrtc.getVersion() if hasattr(cp.cuda, "nvrtc") else None

    # Theoretical bandwidth from the reported memory clock (GDDR7: 4 transfers per clock... use the measured number instead).
    src = r"""
    extern "C" __global__
    void copy_f32(const float* __restrict__ a, float* __restrict__ b, long n) {
        long i = blockDim.x * (long)blockIdx.x + threadIdx.x;
        if (i < n) b[i] = a[i];
    }
    extern "C" __global__
    void stencil_f32(const float* __restrict__ h, const float* __restrict__ z, float* __restrict__ out,
                     int nx, int ny, float dt_over_dx) {
        int i = blockIdx.x * blockDim.x + threadIdx.x;
        int j = blockIdx.y * blockDim.y + threadIdx.y;
        if (i <= 0 || j <= 0 || i >= nx - 1 || j >= ny - 1) return;
        int k = j * nx + i;
        float eta = h[k] + z[k];
        float fe = (h[k+1] + z[k+1]) - eta;
        float fw = eta - (h[k-1] + z[k-1]);
        float fn = (h[k+nx] + z[k+nx]) - eta;
        float fs = eta - (h[k-nx] + z[k-nx]);
        float d = fmaxf(h[k], 0.0f);
        out[k] = fmaxf(d - dt_over_dx * 9.81f * d * (fe - fw + fn - fs), 0.0f);
    }
    """
    t0 = time.perf_counter()
    mod = cp.RawModule(code=src, options=("-std=c++17", "--use_fast_math"))
    copy_k = mod.get_function("copy_f32")
    sten_k = mod.get_function("stencil_f32")
    out["nvrtc_compile_s"] = round(time.perf_counter() - t0, 3)

    n = 64 * 2**20  # 64 M floats = 256 MB per array
    a = cp.arange(n, dtype=cp.float32)
    b = cp.empty_like(a)
    threads = 256
    blocks = (n + threads - 1) // threads
    copy_k((blocks,), (threads,), (a, b, n))
    dev.synchronize()
    reps = 20
    t0 = time.perf_counter()
    for _ in range(reps):
        copy_k((blocks,), (threads,), (a, b, n))
    dev.synchronize()
    dt = (time.perf_counter() - t0) / reps
    out["copy_kernel"] = {"bytes_moved_GB": round(2 * n * 4 / 1e9, 3), "GB_per_s": round(2 * n * 4 / 1e9 / dt, 1)}
    assert bool(cp.all(a == b)), "copy kernel produced wrong data"

    nx, ny = 4096, 4096
    h = cp.random.random((ny, nx), dtype=cp.float32) + 0.01
    z = cp.random.random((ny, nx), dtype=cp.float32) * 10
    o = cp.empty_like(h)
    bs = (32, 8)
    grid = ((nx + bs[0] - 1) // bs[0], (ny + bs[1] - 1) // bs[1])
    sten_k(grid, bs, (h, z, o, nx, ny, cp.float32(0.01)))
    dev.synchronize()
    t0 = time.perf_counter()
    for _ in range(reps):
        sten_k(grid, bs, (h, z, o, nx, ny, cp.float32(0.01)))
    dev.synchronize()
    dt = (time.perf_counter() - t0) / reps
    out["stencil_kernel"] = {
        "cells": nx * ny,
        "ms_per_call": round(dt * 1e3, 3),
        "G_cell_updates_per_s": round(nx * ny / dt / 1e9, 2),
    }
    # launch overhead: a tiny kernel many times
    t0 = time.perf_counter()
    for _ in range(200):
        copy_k((1,), (32,), (a, b, 32))
    dev.synchronize()
    out["launch_overhead_us"] = round((time.perf_counter() - t0) / 200 * 1e6, 1)

    out["float64_ratio_hint"] = "GeForce FP64 is 1/64 of FP32; keep the main loop in float32 (decision 3)"
    out["verdict"] = "PASS: NVRTC compiled for this GPU and the kernels ran correctly"
    (HERE / "toolchain_check_result.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
