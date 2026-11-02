"""How much the hazard depends on the map interval: the 5-minute maps of the full-extent run, all of them or every third.

Four readings at the 5 m pixel, class areas in km2: 300 s and 900 s of maps, each with and without the run's own
maxima. 300 s without maxima is the method of W2. Writes frames_sensitivity.json. Reads the W2 run, writes nothing
there. Usage: s03_frames.py <run folder> <table cache folder>.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

from wadi2d.config.schema import RunConfig
from wadi2d.products.frames import frame_names, read_frames, run_maxima
from wadi2d.products.ground import face_sills, read_cells
from wadi2d.products.hazard import classify
from wadi2d.products.pixels import PixelMaxima, array_module
from wadi2d.run import prepare_grid

HERE = Path(__file__).resolve().parent
RUN = Path(sys.argv[1])
CACHE = Path(sys.argv[2])  # a table cache of this script's own: the run folder stays untouched
OUT = HERE / "frames_sensitivity.json"
cfg = RunConfig.model_validate_json((RUN / "config.resolved.json").read_text(encoding="utf-8"))
t0 = time.time()
tables, _crs = prepare_grid(cfg, CACHE)
print(f"tables {time.time() - t0:.0f} s", flush=True)
rule = cfg.outputs.pixels
results = RUN / "results.h5"
peak = run_maxima(results)
keep = peak["mean_depth"] > rule.cell_depth
cells = read_cells(cfg, tables, keep)
print(f"ground {time.time() - t0:.0f} s, {cells.rows.size:,} cells, k {cells.k}", flush=True)
zmin = (tables.zmin - cells.datum).astype(np.float32)
sill_x, sill_y = face_sills(tables, cells.datum)
xp = array_module("auto")
names = frame_names(results)
print(len(names), "maps", xp.__name__, flush=True)


def maxima() -> PixelMaxima:
    return PixelMaxima(xp, cells, zmin, sill_x, sill_y, keep, rule)


every = maxima()
third = maxima()
for index, (depth, mean_depth, speed) in enumerate(read_frames(results, names)):
    every.add(depth, mean_depth, speed)
    if index % 3 == 0:
        third.add(depth, mean_depth, speed)
    if index % 20 == 0:
        print(f"map {index}, {time.time() - t0:.0f} s", flush=True)
km2 = cells.pixel**2 / 1e6
out = {"cells": int(cells.rows.size), "pixels": int(cells.rows.size * cells.k**2)}
saved = {}
for name, held in (("300 s", every), ("900 s", third)):
    d, v, dv = held.result()
    classes = classify(d, v, dv, rule)
    saved[name] = classes
    out[name] = {f"H{k}": round(float((classes == k).sum()) * km2, 1) for k in range(1, 7)}
    print(name, out[name], flush=True)
    held.add(peak["depth"], peak["mean_depth"], peak["speed"], moment=False)
    held.lift_dv(peak["hazard"])
    d, v, dv = held.result()
    classes = classify(d, v, dv, rule)
    saved[f"{name} with maxima"] = classes
    out[f"{name} with maxima"] = {f"H{k}": round(float((classes == k).sum()) * km2, 1) for k in range(1, 7)}
    print(name, "with maxima", out[f"{name} with maxima"], flush=True)
base = saved["300 s"]
for name, classes in saved.items():
    both = (base > 0) | (classes > 0)
    out[f"{name}, same class as 300 s, %"] = round(float((base[both] == classes[both]).mean() * 100.0), 2)
a, b = saved["300 s with maxima"], saved["900 s with maxima"]
both = (a > 0) | (b > 0)
out["with maxima, 900 s against 300 s, same class %"] = round(float((a[both] == b[both]).mean() * 100.0), 2)
print(json.dumps(out, indent=1), flush=True)
OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
