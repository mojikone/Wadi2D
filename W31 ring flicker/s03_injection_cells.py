"""Where each lumped subbasin's hydrograph enters the 40 m grid, against the ring drawn round it.

For every subbasin with a ring: the cells within ``inject_radius`` of its outlet, their lowest bed, which of them lie
inside the ring, and the lowest one. Reads the grid cache of ``s02`` (``runs/cache_block2``). Writes
``injection_cells.json`` beside this file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import shapely

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from s02_block2_40m import job  # noqa: E402

from wadi2d.forcing import line_faces  # noqa: E402
from wadi2d.run import prepare_grid  # noqa: E402


def main() -> None:
    cfg = job({})
    tables, _crs = prepare_grid(cfg, Path(cfg.grid.cache_dir))
    grid = tables.grid
    jj, ii = np.nonzero(grid.mask)
    x, y = grid.xy_of(jj, ii)
    rings = {ln.name: ln for ln in cfg.outputs.lines if ln.name.endswith("ring")}
    out = {}
    for sub in cfg.hydrology.subbasins:
        ring = rings.get(f"{sub.name} ring")
        if ring is None or sub.outlet is None:
            continue
        polygon = shapely.Polygon(ring.coordinates)
        dist = np.hypot(x - sub.outlet[0], y - sub.outlet[1])
        near = np.nonzero(dist <= cfg.hydrology.inject_radius)[0]
        if near.size == 0:
            near = np.array([int(np.argmin(dist))])
        zmin = tables.zmin[jj[near], ii[near]]
        lowest = int(np.argmin(zmin))
        faces = line_faces(grid, ring.coordinates)
        cells = []
        for n, k in enumerate(near):
            cells.append({
                "j": int(jj[k]), "i": int(ii[k]), "zmin": round(float(zmin[n]), 2),
                "inside_ring": bool(polygon.contains(shapely.Point(x[k], y[k]))),
                "lowest": n == lowest, "offset_m": round(float(dist[k]), 1),
            })  # fmt: skip
        out[sub.name] = {
            "outlet": list(sub.outlet),
            "grid_origin": [float(grid.x0), float(grid.y0)],
            "ring_faces": int(faces.xfaces.size + faces.yfaces.size),
            "cells": cells,
            "cells_inside": sum(c["inside_ring"] for c in cells),
            "lowest_inside": cells[lowest]["inside_ring"],
        }
        print(sub.name, json.dumps(out[sub.name]))
    (HERE / "injection_cells.json").write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
