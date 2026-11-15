"""Time the phases of prepare_grid on Block 2 (CPU, no solver), after W81's harness; works on the old package too.

Args: mode(squares|strips) extent(full|<half_km>) stride cache_folder [--save file.npz] [--hash file.json]
      [--mesh file.pkl] [--workers n]

The grid cache (tables, mask, strip) is emptied before the run, so every phase is built; the DEM store under the
same folder (``dem_*``) is left, so a second run on the same folder reads a warm store. ``--save`` writes every table
array for a comparison, ``--hash`` their SHA-256 alone (the whole block's arrays are 10 GB); ``--workers`` sets the
threads of the tables, of the old mask read and of the store's fill; ``--mesh`` keeps the aligned mesh of ``mask_for_strips`` (twelve minutes on one core, and not
what is timed here) in a pickle and reads it back on the next run.
"""

import ctypes
import hashlib
import json
import os
import pickle
import sys
import time
from ctypes import wintypes
from pathlib import Path

import numpy as np

import wadi2d.run as run
import wadi2d.strips.build as sb
from wadi2d.run import load_job, prepare_grid

JOB = r"D:\Mojtaba\Renardet\Wadi2D\W79 Block 2 four ways\jobs\run1_full_2d_aligned.json"
mode, extent, stride, cache = sys.argv[1], sys.argv[2], int(sys.argv[3]), Path(sys.argv[4])
save = Path(sys.argv[sys.argv.index("--save") + 1]) if "--save" in sys.argv else None
mesh = Path(sys.argv[sys.argv.index("--mesh") + 1]) if "--mesh" in sys.argv else None
hashes = Path(sys.argv[sys.argv.index("--hash") + 1]) if "--hash" in sys.argv else None
if "--workers" in sys.argv:
    workers = int(sys.argv[sys.argv.index("--workers") + 1])
    os.environ["WADI2D_TABLE_WORKERS"] = str(workers)
    import wadi2d.terrain.dem as dem_mod

    dem_mod.SAMPLE_WORKERS = workers
    try:
        import wadi2d.demstore.chunks as chunks_mod

        chunks_mod.FILL_WORKERS = workers
    except ImportError:
        pass  # the old package

cfg = load_job(JOB)
d = cfg.model_dump()
if extent != "full":
    half = float(extent) * 1000.0
    faydh = next(o for o in cfg.terrain.objects if o.name == "Faydh 01")
    xy = np.asarray(faydh.coordinates, float)[:, :2].mean(axis=0)
    d["grid"]["domain"] = None
    d["grid"]["extent"] = [xy[0] - half, xy[1] - half, xy[0] + half, xy[1] + half]
    d["boundaries"] = []
    d["terrain"]["objects"] = [
        o
        for o in d["terrain"]["objects"]
        if (np.abs(np.asarray(o["coordinates"], float)[:, :2] - xy) < half - 500).all()
    ]
cache.mkdir(parents=True, exist_ok=True)
for pattern in ("grid_*.h5", "mask_*.npz", "strip_*.pkl", "*.tmp"):
    for held in cache.glob(pattern):
        held.unlink()
d["grid"]["cache_dir"] = str(cache)
d["terrain"]["pixel_stride"] = stride
d["strips"]["enabled"] = mode == "strips"
cfg = type(cfg).model_validate(d)

times: dict[str, float] = {}


def timed(mod, name):
    f = getattr(mod, name)

    def wrap(*a, **k):
        t0 = time.perf_counter()
        try:
            return f(*a, **k)
        finally:
            times[name] = times.get(name, 0.0) + time.perf_counter() - t0

    setattr(mod, name, wrap)


if mesh is not None:
    made = sb.mask_for_strips

    def kept_mesh(*a, **k):
        if mesh.is_file():
            with open(mesh, "rb") as f:
                return pickle.load(f)
        out = made(*a, **k)
        with open(mesh, "wb") as f:
            pickle.dump(out, f, protocol=pickle.HIGHEST_PROTOCOL)
        return out

    sb.mask_for_strips = kept_mesh

timed(run, "build_tables")
timed(run, "kept_domain_mask")
timed(sb, "strip_tables")
timed(sb, "mask_for_strips")


class PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
        (n, ctypes.c_size_t)
        for n in (
            "PeakWorkingSetSize",
            "WorkingSetSize",
            "a",
            "b",
            "c",
            "d",
            "PagefileUsage",
            "PeakPagefileUsage",
        )
    ]


def peak_bytes() -> tuple[int, int]:
    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    k32 = ctypes.WinDLL("kernel32")
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    ps = ctypes.WinDLL("psapi")
    ps.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
    assert ps.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
    return pmc.PeakWorkingSetSize, pmc.PeakPagefileUsage


t0 = time.perf_counter()
tables, _crs = prepare_grid(cfg, cache)
wall = time.perf_counter() - t0
strip = getattr(tables, "strip", None)
store = sum(f.stat().st_size for f in cache.glob("dem_*/*")) / 2**30
ws, commit = peak_bytes()
print(
    mode, extent, "stride", stride, "total s", round(wall, 1), {k: round(v, 1) for k, v in times.items()},
    "cells", int(tables.grid.mask.sum()), "tiles", tables.grid.ntiles,
    "strip cells", 0 if strip is None else int(strip.mesh.area.size),
    "peak working set GB", round(ws / 2**30, 2), "peak commit GB", round(commit / 2**30, 2),
    "store GB", round(store, 2),
)  # fmt: skip
if save is not None or hashes is not None:
    arrays = {k: v for k, v in vars(tables).items() if isinstance(v, np.ndarray)}
    arrays["mask"] = tables.grid.mask
    if strip is not None:
        for owner, name in ((strip, "strip"), (strip.mesh, "mesh"), (getattr(strip, "strip", None), "geo")):
            for k, v in vars(owner).items() if owner is not None and hasattr(owner, "__dict__") else ():
                if isinstance(v, np.ndarray):
                    arrays[f"{name}.{k}"] = v
    if save is not None:
        np.savez(save, **arrays)
        print("saved", len(arrays), "arrays to", save)
    if hashes is not None:
        found = {
            k: [
                str(v.dtype),
                list(v.shape),
                hashlib.sha256(np.ascontiguousarray(v).view(np.uint8).reshape(-1)).hexdigest(),
            ]
            for k, v in sorted(arrays.items())
        }
        hashes.write_text(json.dumps(found, indent=1), encoding="utf-8")
        print(
            "hashed",
            len(found),
            "arrays,",
            round(sum(v.nbytes for v in arrays.values()) / 2**30, 2),
            "GB, to",
            hashes,
        )
