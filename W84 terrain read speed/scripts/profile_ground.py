"""Where the products' ground stage spends its threads' time: the read, the pick of the kept cells, the rest.

Args: tables_folder store_folder. The run and its kept cells are time_ground.py's.
"""

import sys
import threading
import time
from pathlib import Path

import h5py
import numpy as np

import wadi2d.products.ground as ground_mod
from wadi2d.config.schema import RunConfig
from wadi2d.run import prepare_grid

RUN = Path(r"D:\Mojtaba\Renardet\Wadi2D\W79 Block 2 four ways\runs\run1_full_2d")
held, store = Path(sys.argv[1]), Path(sys.argv[2])
cfg = RunConfig.model_validate_json((RUN / "config.resolved.json").read_text(encoding="utf-8"))
cfg = cfg.model_copy(update={"grid": cfg.grid.model_copy(update={"cache_dir": str(held)})})
tables, _crs = prepare_grid(cfg, held)
with h5py.File(RUN / "results.h5", "r") as f:
    keep = f["maxima"]["mean_depth"][:] > cfg.outputs.pixels.cell_depth

spent: dict[str, float] = {}
calls: dict[str, int] = {}
lock = threading.Lock()


def timed(owner, name, label):
    f = getattr(owner, name, None)
    if f is None:
        return

    def wrap(*a, **k):
        t0 = time.perf_counter()
        try:
            return f(*a, **k)
        finally:
            dt = time.perf_counter() - t0
            with lock:
                spent[label] = spent.get(label, 0.0) + dt
                calls[label] = calls.get(label, 0) + 1

    setattr(owner, name, wrap)


timed(ground_mod, "_raw", "_raw (threads)")
timed(ground_mod, "_picked", "_picked (threads)")
timed(ground_mod, "_pick_into", "_pick_into (threads)")
timed(ground_mod, "_any_picked", "_any_picked (threads)")
timed(ground_mod, "_filled_near", "_filled_near (threads)")
timed(ground_mod._ThreadBeds, "_tile", "_tile (threads)")
timed(ground_mod._ThreadBeds, "pick", "pick (wall)")
timed(ground_mod, "_whole_strip", "_whole_strip (wall)")
timed(ground_mod, "apply_objects", "apply_objects (wall)")
timed(np, "nonzero", "np.nonzero (wall)")
t0 = time.perf_counter()
cells = ground_mod.read_cells(cfg, tables, keep, cache=store)
print("ground", round(time.perf_counter() - t0, 1), "s,", cells.rows.size, "cells")
for label, seconds in sorted(spent.items(), key=lambda item: -item[1]):
    print(f"  {label:26s}{seconds:8.1f} s in {calls[label]:6d} calls")
