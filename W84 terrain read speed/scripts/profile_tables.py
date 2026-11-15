"""Where a table build's time goes: the seconds its threads spend in the read, in each kernel and in the rest.

Args: extent(<half_km>|full) cache_folder workers [stride]. The squares of W79's Block 2 job at the DEM's pixel
(stride 1, 0.5 m; the job itself asks for 2); the grid cache is emptied first and the DEM store left. Thread-seconds are summed over the worker threads, so they exceed the wall
time by about the number of threads that were busy.
"""

import os
import sys
import threading
import time
from pathlib import Path

import numpy as np

extent, cache, workers = sys.argv[1], Path(sys.argv[2]), int(sys.argv[3])
stride = int(sys.argv[4]) if len(sys.argv) > 4 else 1
os.environ["WADI2D_TABLE_WORKERS"] = str(workers)

import wadi2d.run as run
import wadi2d.tables.builder as builder
from wadi2d.run import load_job, prepare_grid
from wadi2d.terrain.dem import RasterBed

JOB = r"D:\Mojtaba\Renardet\Wadi2D\W79 Block 2 four ways\jobs\run1_full_2d_aligned.json"
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
d["strips"]["enabled"] = False
d["terrain"]["pixel_stride"] = stride
cfg = type(cfg).model_validate(d)

try:  # an experiment's knob: how many chunks the store keeps mapped
    import wadi2d.demstore.chunks as chunks_mod

    chunks_mod.OPEN_CHUNKS = int(os.environ.get("W84_OPEN_CHUNKS", chunks_mod.OPEN_CHUNKS))
except ImportError:
    pass  # the old package

spent: dict[str, float] = {}
lock = threading.Lock()


def timed(owner, name, label):
    f = getattr(owner, name)

    def wrap(*a, **k):
        t0 = time.perf_counter()
        try:
            return f(*a, **k)
        finally:
            dt = time.perf_counter() - t0
            with lock:
                spent[label] = spent.get(label, 0.0) + dt

    setattr(owner, name, wrap)


for kernel in (
    "tile_tables",
    "tile_tables_serial",
    "tile_local_radius",
    "tile_local_radius_serial",
    "centre_beds",
):
    timed(builder, kernel, kernel)
timed(RasterBed, "read", "bed.read")
timed(builder, "run_all", "all tiles (wall)")
timed(run, "build_tables", "build_tables (wall)")
timed(run, "save_tables", "save_tables (wall)")
timed(run, "kept_domain_mask", "domain mask (wall)")
timed(run, "apply_objects", "apply_objects (wall)")

t0 = time.perf_counter()
tables, _crs = prepare_grid(cfg, cache)
print(
    "stride",
    stride,
    "workers",
    workers,
    "tiles",
    tables.grid.ntiles,
    "total",
    round(time.perf_counter() - t0, 1),
    "s",
)
for label, seconds in sorted(spent.items(), key=lambda item: -item[1]):
    print(f"  {label:28s} {seconds:8.1f} s")
