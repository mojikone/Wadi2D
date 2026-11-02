"""The whole step on the full-extent run, without writing there: a folder of its own holds a hard link to results.h5.

Usage: s07_full_step.py <run folder> <work folder> <table cache>. The work folder must be on the same drive as the run.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

from wadi2d.config.schema import RunConfig
from wadi2d.products.step import Watch, make_products
from wadi2d.run import prepare_grid

RUN, WORK, CACHE = (Path(a) for a in sys.argv[1:4])
WORK.mkdir(parents=True, exist_ok=True)
link = WORK / "results.h5"
if not link.exists():
    os.link(RUN / "results.h5", link)
shutil.copy(RUN / "config.resolved.json", WORK)
cfg = RunConfig.model_validate_json((WORK / "config.resolved.json").read_text(encoding="utf-8"))
t0 = time.time()
tables, crs = prepare_grid(cfg, CACHE)
print(f"tables {time.time() - t0:.0f} s", flush=True)
last = [None]


def emit(event, **fields):
    tag = (event, fields.get("stage"))
    if tag != last[0] or fields.get("done", 1) % 20 == 0:
        print(f"{time.time() - t0:7.0f} {event} {fields}", flush=True)
        last[0] = tag


if len(sys.argv) > 4:  # the drawing alone, from the rasters already written
    import numpy as np
    import rasterio

    from wadi2d.products.smooth import make_drawings
    from wadi2d.products.step import HAZARD_FILE, PIXEL_DIR

    folder = WORK / PIXEL_DIR
    with rasterio.open(folder / HAZARD_FILE) as src:
        classes = src.read(1)
        t = src.transform
    with rasterio.open(folder / "pixel_depth.tif") as src:
        depth = src.read(1, masked=True).filled(0.0).astype(np.float32)
    from wadi2d.io.geotiff import raster_profile

    written = {"classes": classes, "profile": raster_profile(classes.shape, t.a, t.c, t.f, crs)}
    stats = make_drawings(cfg, tables, written, depth, folder, crs, Watch(emit, lambda: False))
else:
    stats = make_products(cfg, tables, crs, WORK, Watch(emit, lambda: False), "auto")
stats["step_s"] = round(time.time() - t0)
print(json.dumps(stats, indent=1), flush=True)
