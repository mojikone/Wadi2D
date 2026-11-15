"""W85: the pit check on the whole of Block 2, from the tables W79's full 2D run was built on.

    python s09_block2_pits.py <grid cache .h5> <out folder>

Reads the cached tables (CPU, about 3 GB), finds the pits at the default thresholds and at a few others, times the
check, writes ``block2_pits.json`` and ``block2_pits.geojson`` (the pits at the defaults, as points) and says which of
the four cells the frames named are among them.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

from wadi2d.config.schema import Terrain
from wadi2d.io.cache import load_tables
from wadi2d.terrain.pits import find_pits

NAMED = {
    "the hole at the cliff": (414791.0, 2722485.0),
    "the hole by the building": (438521.0, 2739036.0),
    "low pixels at the flat patch": (432961.0, 2740036.0),
    "low pixels, the fourth": (451501.0, 2721316.0),
}
VARIANTS = ((2.0, 5.0), (2.0, 3.0), (2.0, 10.0), (1.0, 5.0), (5.0, 5.0))
"""(pit_max_cells, pit_min_depth) to count at; the first is the default."""


def main() -> None:
    cache, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    tables = load_tables(cache, cache.stem.removeprefix("grid_"))
    loaded = time.time() - t0
    dx = tables.grid.dx
    record = {"cells": int(tables.grid.mask.sum()), "dx": dx, "load_s": round(loaded, 1), "variants": []}
    first = None
    for cells, depth in VARIANTS:
        t0 = time.time()
        pits = find_pits(tables, Terrain(pit_max_cells=cells, pit_min_depth=depth))
        took = time.time() - t0
        row = {
            "pit_max_cells": cells, "pit_min_depth": depth, "pits": len(pits), "cells": sum(len(p.cells) for p in pits),
            "volume_m3": round(sum(p.volume_m3 for p in pits), 0), "check_s": round(took, 2),
        }  # fmt: skip
        record["variants"].append(row)
        print(row, flush=True)
        if first is None:
            first = pits
    near = {}
    for name, (x, y) in NAMED.items():
        hit = [p for p in first if abs(p.x - x) <= 1.5 * dx and abs(p.y - y) <= 1.5 * dx]
        near[name] = [
            {"x": p.x, "y": p.y, "depth_m": round(p.depth_m, 2), "area_m2": round(p.area_m2, 1)} for p in hit
        ]
        print(name, "->", near[name] or "not a pit at the defaults")
    record["named"] = near
    record["deepest"] = [
        {"x": p.x, "y": p.y, "depth_m": round(p.depth_m, 2), "area_m2": round(p.area_m2, 1), "volume_m3": round(p.volume_m3, 1),
         "spill_m": round(p.spill_m, 2), "cells": len(p.cells)}
        for p in first[:25]
    ]  # fmt: skip
    for p in record["deepest"][:12]:
        print("  ", p)
    (out / "block2_pits.json").write_text(json.dumps(record, indent=1))
    cells = np.array([c for p in first for c in p.cells], np.int64).reshape(-1, 2)
    np.savez(
        out / "block2_pit_cells.npz", j=cells[:, 0], i=cells[:, 1]
    )  # for s04's "with the pits filled" scenario
    features = [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [p.x, p.y]},
         "properties": {"depth_m": round(p.depth_m, 2), "area_m2": round(p.area_m2, 1), "volume_m3": round(p.volume_m3, 1),
                        "spill_m": round(p.spill_m, 2), "cells": len(p.cells)}}
        for p in first
    ]  # fmt: skip
    (out / "block2_pits.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": features}))


if __name__ == "__main__":
    main()
