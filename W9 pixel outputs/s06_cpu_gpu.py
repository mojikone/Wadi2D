"""The CPU path against the GPU path, on the whole hybrid run: every saved map, the run's peaks, the classes.

Usage: s06_cpu_gpu.py <run folder>. Writes cpu_gpu.json. The two share one source; this measures what floating point
leaves between them on real ground.
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
cfg = RunConfig.model_validate_json((RUN / "config.resolved.json").read_text(encoding="utf-8"))
tables, _crs = prepare_grid(cfg, Path(cfg.grid.cache_dir))
rule = cfg.outputs.pixels
results = RUN / "results.h5"
peak = run_maxima(results)
keep = peak["mean_depth"] > rule.cell_depth
cells = read_cells(cfg, tables, keep)
zmin = (tables.zmin - cells.datum).astype(np.float32)
sill_x, sill_y = face_sills(tables, cells.datum)
names = frame_names(results)
out = {}
found = {}
for label, xp in (("gpu", array_module("gpu")), ("cpu", np)):
    t0 = time.time()
    held = PixelMaxima(xp, cells, zmin, sill_x, sill_y, keep, rule)
    for depth, mean_depth, speed in read_frames(results, names):
        held.add(depth, mean_depth, speed)
    held.add(peak["depth"], peak["mean_depth"], peak["speed"], moment=False)
    held.lift_dv(peak["hazard"])
    found[label] = held.result()
    out[f"{label}_s"] = round(time.time() - t0, 1)
    print(label, out[f"{label}_s"], flush=True)
a, b = found["gpu"], found["cpu"]
ca, cb = classify(*a, rule), classify(*b, rule)
out["pixels"] = int(ca.size)
out["pixels_with_another_class"] = int((ca != cb).sum())
for name, x, y in zip(("depth_m", "speed_ms", "dv_m2s"), a, b, strict=True):
    out[f"largest_difference_{name}"] = float(np.abs(x - y).max())
print(json.dumps(out, indent=1))
(HERE / "cpu_gpu.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
