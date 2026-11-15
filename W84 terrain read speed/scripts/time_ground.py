"""Time the products' ground stage (``read_cells``) on a finished Block 2 run, and hash what it read.

Args: tables_folder store_folder|none [workers]. The run is W79's squares run (20 m, 0.5 m pixels, 821,602 cells
kept), read only; its tables are built once into ``tables_folder`` (a grid cache of this script's own) and loaded from
there afterwards. The kept cells are the run's own. Works on the old package too (``none``: no store folder is passed
to ``read_cells``).
"""

import hashlib
import json
import sys
import time
from pathlib import Path

import h5py
import numpy as np

import wadi2d.products.ground as ground_mod
from wadi2d.config.schema import RunConfig
from wadi2d.run import prepare_grid

RUN = Path(r"D:\Mojtaba\Renardet\Wadi2D\W79 Block 2 four ways\runs\run1_full_2d")
held = Path(sys.argv[1])
store = None if sys.argv[2] == "none" else Path(sys.argv[2])
workers = int(sys.argv[3]) if len(sys.argv) > 3 else None

cfg = RunConfig.model_validate_json((RUN / "config.resolved.json").read_text(encoding="utf-8"))
cfg = cfg.model_copy(update={"grid": cfg.grid.model_copy(update={"cache_dir": str(held)})})
t0 = time.perf_counter()
tables, _crs = prepare_grid(cfg, held)
print("tables in", round(time.perf_counter() - t0, 1), "s (built the first time, loaded after)")
with h5py.File(RUN / "results.h5", "r") as f:
    keep = f["maxima"]["mean_depth"][:] > cfg.outputs.pixels.cell_depth

if workers is not None:
    real = ground_mod._ThreadBeds.__init__
    ground_mod._ThreadBeds.__init__ = lambda self, *a: real(self, *a, workers=workers)

t0 = time.perf_counter()
if store is None:
    cells = ground_mod.read_cells(
        cfg.model_copy(update={"grid": cfg.grid.model_copy(update={"cache_dir": None})}), tables, keep
    )
else:
    cells = ground_mod.read_cells(cfg, tables, keep, cache=store)
wall = time.perf_counter() - t0
print("ground in", round(wall, 1), "s")
digest = hashlib.sha256()
for part in (cells.rows, cells.cols, cells.ground):
    digest.update(np.ascontiguousarray(part).view(np.uint8).reshape(-1))
print(
    json.dumps(
        {
            "store": str(store),
            "workers": workers or ground_mod.READ_WORKERS,
            "ground_s": round(wall, 1),
            "cells": int(cells.rows.size),
            "pixels": int(cells.ground.size),
            "k": cells.k,
            "datum": cells.datum,
            "sha256": digest.hexdigest(),
        }
    )
)
