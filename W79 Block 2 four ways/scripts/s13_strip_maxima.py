"""The aligned (strip) cells' maxima as a polygon layer: what the cell-map rasters leave blank along the wadis.

Usage: s13_strip_maxima.py <run number> ... Reads the run's ``maps/strip_mesh.gpkg`` (layer ``strip_cells``, one polygon
per strip cell, its index in ``cell``) and the strip's own maxima in ``results.h5`` (``maxima/strip_depth``,
``strip_mean_depth``, ``strip_speed``, ``strip_hazard``: the same quantities as the lattice's cell maps), and writes
``maps/strip_maxima.gpkg`` (layer ``strip_maxima``) with the cells that were ever wet (strip depth >= 0.01 m):
max_depth_m (level above the cell's lowest pixel, as the cell map's max depth), max_mean_depth_m, max_speed_ms, max_dv
(depth x speed, the quantity of the cell map's hazard raster), hazard (H1 to H6 by the run's own rule on the three
maxima), area_m2. It also writes ``maps/strip_maxima.json``: counts, and the cells whose max speed is over 10 and 100 m/s.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import h5py
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from w79 import RUN_NAMES, RUNS  # noqa: E402

from wadi2d.config.schema import RunConfig  # noqa: E402
from wadi2d.products.hazard import classify  # noqa: E402

WET_M = 0.01


def main(number: int) -> None:
    import geopandas as gpd

    folder = RUNS / RUN_NAMES[number]
    cfg = RunConfig.model_validate_json((folder / "config.resolved.json").read_text(encoding="utf-8"))
    with h5py.File(folder / "results.h5", "r") as f:
        m = f["maxima"]
        depth, mean, speed, dv = (m[f"strip_{k}"][0].astype(np.float64) for k in ("depth", "mean_depth", "speed", "hazard"))
    cells = gpd.read_file(folder / "maps" / "strip_mesh.gpkg", layer="strip_cells",
                          columns=["cell", "corridor", "kind", "zmin_m", "area_m2"])
    index = cells["cell"].to_numpy()
    assert index.max() < depth.size, (index.max(), depth.size)
    d, s = depth[index], speed[index]
    cells["max_depth_m"] = d.round(3)
    cells["max_mean_depth_m"] = mean[index].round(3)
    cells["max_speed_ms"] = s.round(3)
    cells["max_dv"] = dv[index].round(3)
    cells["hazard"] = classify(d, s, dv[index], cfg.outputs.pixels).astype(int)
    wet = cells[d >= WET_M].copy()
    out = folder / "maps" / "strip_maxima.gpkg"
    out.unlink(missing_ok=True)
    wet.to_file(out, layer="strip_maxima", driver="GPKG")
    fast = wet["max_speed_ms"]
    small = wet["area_m2"]
    report = {
        "run": number, "cells": int(len(cells)), "wet_cells": int(len(wet)),
        "speed_over_10": int((fast > 10).sum()), "speed_over_100": int((fast > 100).sum()),
        "max_speed_ms": float(fast.max()), "speed_p999": float(np.percentile(fast, 99.9)),
        "median_area_m2_of_cells_over_100": float(small[fast > 100].median()) if (fast > 100).any() else None,
        "median_area_m2_all_wet": float(small.median()),
        "kinds_of_cells_over_100": wet.loc[fast > 100, "kind"].value_counts().to_dict(),
    }
    (folder / "maps" / "strip_maxima.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        main(int(arg))
