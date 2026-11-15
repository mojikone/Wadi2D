"""Build a rerun job's grid tables into the shared cache before its run, on the CPU, while another worker holds the GPU.

Usage: s08_tables.py <run number>. Calls ``wadi2d.run.prepare_grid``, the function ``wadi2d run`` itself calls first, on
the job's own cache folder, so the run then reads the same tables from the cache (its own ``tables_s`` is the load).
Writes ``runs/<run>.tables.json`` with the wall time and the process's peak memory.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from w79 import CACHE, JOBS, RUN_NAMES, RUNS, write_json  # noqa: E402

from wadi2d.run import load_job, prepare_grid  # noqa: E402


def peak_gb() -> float:
    """The process's peak working set (Windows), GB."""
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                                           "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                                           "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")
        ]

    c = Counters()
    c.cb = ctypes.sizeof(c)
    ctypes.windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(c), c.cb)
    return max(c.PeakWorkingSetSize, c.PeakPagefileUsage) / 1e9


def main(number: int) -> None:
    name = RUN_NAMES[number]
    cfg = load_job(JOBS / f"{name}.json")
    t0 = time.perf_counter()
    tables, _crs = prepare_grid(cfg, CACHE)
    wall = time.perf_counter() - t0
    strip = getattr(tables, "strip", None)
    report = {"run": number, "job": name, "tables_s": wall, "peak_gb": peak_gb(), "cache": str(CACHE),
              "pixel_stride": cfg.terrain.pixel_stride,
              "strip_cells": int(strip.mesh.n_cells) if strip is not None and hasattr(strip.mesh, "n_cells") else None}
    write_json(RUNS / f"{name}.tables.json", report)
    print(report)


if __name__ == "__main__":
    main(int(sys.argv[1]))
