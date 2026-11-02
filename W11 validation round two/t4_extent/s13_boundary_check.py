"""Real boundary cells of every W11 job, on the engine's own grid at f976c23. usage: s13_boundary_check.py JOB.json ...

Passes when cells >= 0.7 x line length / dx on every line. It also reports the cells' span along the line, because a line
that turns can hold enough cells and still leave a stretch shut.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import shapely

from wadi2d.forcing import cells_along
from wadi2d.grid.tiles import TileGrid
from wadi2d.run import domain_mask, grid_window, load_job
from wadi2d.terrain import RasterBed

out = {}
for arg in sys.argv[1:]:
    p = Path(arg)
    cfg = load_job(p)
    with RasterBed(cfg.terrain.dem, cfg.terrain.pixel_stride) as bed:
        window = grid_window(cfg, bed)
        mask = domain_mask(cfg, bed, window)
        grid = TileGrid.from_mask(mask, window.x0, window.y0, cfg.grid.dx)
    dx = cfg.grid.dx
    rows = []
    worst = 1e9
    for b in cfg.boundaries:
        c = list(b.coordinates)
        L = shapely.LineString(c).length
        j, i = cells_along(grid, c, cfg.grid.line_samples)
        x = grid.x0 + (i + 0.5) * dx
        y = grid.y0 - (j + 0.5) * dx
        line = shapely.LineString(c)
        s = np.sort(shapely.line_locate_point(line, shapely.points(x, y)))
        gap = float(np.max(np.diff(np.concatenate(([0.0], s, [L]))))) if s.size else L
        ratio = j.size * dx / L
        worst = min(worst, ratio)
        rows.append({"length_km": round(L / 1e3, 2), "cells": int(j.size), "cells_x_dx_over_length": round(ratio, 3), "largest_gap_m": round(gap, 1)})
    out[p.stem] = {"dx": dx, "active_cells": int(mask.sum()), "lines": rows, "pass": bool(worst >= 0.7)}
    print(p.stem, dx, rows, "PASS" if worst >= 0.7 else "THROTTLED")
Path("boundary_check.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
