"""A cold pre-solver stretch of a W79 rerun job, timed: everything ``wadi2d run`` does before the solver's first step.

    python s01_cold_build.py <W79 job name> <label> [--keep-cache] [--code <folder holding a wadi2d package>]

``--code runs/code_before`` runs the engine as it was on ``feature/fast-products`` (``git archive`` of it), so a
before run is not changed under it by edits to this checkout.

Copies the W79 job, points its cache at ``runs/cache_<label>`` (the DEM chunk store hard-linked in from W79's cache,
so the pixels are decoded already, as they were for the reruns; no grid, strip, mask or edge-stream cache) and its run
folder at ``runs/<label>``, and runs the engine of THIS checkout on the CPU backend (the reruns hold the GPU) under a
20 GB commit cap. Every line of the engine's output is stamped with the seconds since the start into
``runs/<label>.log``; the process is stopped at the ``start`` event, the solver's first step. ``runs/<label>.json``
holds the wall time to that event and the process's peak commit.

Reads W79's job files only; writes nothing in W79.
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
W91 = HERE.parent
REPO = W91.parent
W79 = Path(r"D:\Mojtaba\Renardet\Wadi2D\W79 Block 2 four ways")
RUNS = W91 / "runs"
STORE = "dem_0bedda043cf08b5074aeaac6"
PYTHON = Path(r"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe")
CAP_GB = 20.0


class _Counters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def peak_gb(pid: int) -> tuple[float, float]:
    """(peak working set, peak commit) of a live process, GB."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    handle = k32.OpenProcess(0x0400 | 0x0010, False, pid)
    if not handle:
        return float("nan"), float("nan")
    c = _Counters()
    c.cb = ctypes.sizeof(c)
    psapi.GetProcessMemoryInfo(handle, ctypes.byref(c), c.cb)
    k32.CloseHandle(handle)
    return c.PeakWorkingSetSize / 2**30, c.PeakPagefileUsage / 2**30


def fresh_cache(label: str) -> Path:
    cache = RUNS / f"cache_{label}"
    if cache.exists():
        for item in cache.iterdir():
            if item.name != STORE:
                shutil.rmtree(item) if item.is_dir() else item.unlink()
    link = cache / STORE
    if not link.exists():
        shared = RUNS / "cache" / STORE  # hard links made once from W79's store
        link.mkdir(parents=True)
        for f in shared.iterdir():
            if f.name == "source.json":
                shutil.copy2(f, link / f.name)
            else:
                os.link(f, link / f.name)
    return cache


def main() -> None:
    name, label = sys.argv[1], sys.argv[2]
    keep = "--keep-cache" in sys.argv[3:]
    code = Path(sys.argv[sys.argv.index("--code") + 1]).resolve() if "--code" in sys.argv else REPO
    cfg = json.loads((W79 / "jobs" / f"{name}.json").read_text(encoding="utf-8"))
    cache = RUNS / f"cache_{label}" if keep else fresh_cache(label)
    cfg["grid"]["cache_dir"] = str(cache)
    job = RUNS / f"{label}.job.json"
    job.write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    out = RUNS / label
    if out.exists():
        shutil.rmtree(out)
    env = dict(os.environ, PYTHONPATH=str(code), PYTHONUNBUFFERED="1")
    command = [str(PYTHON), str(HERE / "capped_engine.py"), str(CAP_GB), "run", str(job), "--out", str(out),
               "--backend", "cpu"]  # fmt: skip
    t0 = time.time()
    reached = None
    with (RUNS / f"{label}.log").open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env,
                                cwd=str(REPO))  # fmt: skip
        for line in proc.stdout:
            log.write(f"{time.time() - t0:9.1f} {line}")
            log.flush()
            if line.startswith('{"ev": "start"'):
                reached = time.time() - t0
                break
        time.sleep(3.0)  # one more sample of the engine's own peaks (capped_engine.py writes them every 2 s)
        try:
            ws, commit = (float(v) for v in (RUNS / f"{label}.peak.tsv").read_text(encoding="utf-8").split())
        except (OSError, ValueError):
            ws = commit = float("nan")
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        proc.wait()
    result = {"job": name, "label": label, "to_start_s": reached, "peak_working_set_gb": ws, "peak_commit_gb": commit,
              "exit": proc.returncode}  # fmt: skip
    (RUNS / f"{label}.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
