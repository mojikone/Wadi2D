"""W85: W79's tables, built on 16 threads, against a one-thread rebuild of a window round a dam.

    python s11_w79_crest_check.py <W79 run folder> <its grid cache .h5> <out folder>

The window is 2 km by 1.4 km round Bidah 03's crest lines and spillway, on the run's own lattice, with the run's own
terrain objects, built here on one thread (``workers=1`` through ``WADI2D_TABLE_WORKERS``). Every cell of the window
two cells or more inside its edge is compared with the same cell of the cached tables: the cell tables, the face
inverts and the crest coefficients, to the digit. Also says which of the job's objects edit pixels at all: only those
rasterise on the table threads.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ["WADI2D_TABLE_WORKERS"] = "1"

import numpy as np

from wadi2d.config.schema import RunConfig
from wadi2d.io.cache import load_tables
from wadi2d.run import prepare_grid
from wadi2d.terrain.objects import TERRAIN_OBJECTS

EXTENT = (437251.0, 2726205.8, 439251.0, 2727605.8)
"""Round Bidah 03 (crest lines x 437,553 to 438,865, y 2,726,532 to 2,727,265). The engine snaps the west edge down
and the north edge up to a DEM pixel, which puts these on W79's cell edges (x ...250.99, y ...605.89); the script
checks that the two lattices coincide before it compares anything."""
RIM = 2
CELL = ("zmin", "zbar")
TILES = (
    "hc",
    "dtab",
    "flx",
    "frx",
    "glx",
    "grx",
    "efx",
    "cwx",
    "ftabx",
    "fly",
    "fry",
    "gly",
    "gry",
    "efy",
    "cwy",
    "ftaby",
    "zcx",
    "zcy",
)


def main() -> None:
    run, cache, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    data = json.loads((run / "config.resolved.json").read_text(encoding="utf-8"))
    cfg = RunConfig.model_validate(data)
    kinds = sorted({o.kind for o in cfg.terrain.objects})
    edits = {k: TERRAIN_OBJECTS.build(k).pixels(None, None, 0.5, cfg.terrain) is not None for k in kinds}
    print(
        "object kinds of the job, and whether each edits pixels (only those rasterise on the table threads):",
        edits,
    )
    x0, y0, x1, y1 = EXTENT
    inside = [
        o for o in data["terrain"]["objects"] if all(x0 < x < x1 and y0 < y < y1 for x, y in o["coordinates"])
    ]
    print("objects wholly in the window:", [o["name"] for o in inside])
    data["terrain"]["objects"] = inside
    data["grid"].update(domain=None, extent=list(EXTENT), cache_dir=str(out / "cache"))
    window_cfg = RunConfig.model_validate(data)
    small, _crs = prepare_grid(window_cfg, out / "cache")
    big = load_tables(cache, cache.stem.removeprefix("grid_"))
    g, G = small.grid, big.grid
    jj, ii = np.nonzero(g.mask)
    lo_j, hi_j, lo_i, hi_i = jj.min() + RIM, jj.max() - RIM, ii.min() + RIM, ii.max() - RIM
    keep = (jj >= lo_j) & (jj <= hi_j) & (ii >= lo_i) & (ii <= hi_i)
    jj, ii = jj[keep], ii[keep]
    x, y = g.xy_of(jj, ii)
    J = np.floor((G.y0 - y) / G.dx).astype(np.int64)
    I = np.floor((x - G.x0) / G.dx).astype(np.int64)  # noqa: E741
    X, Y = G.xy_of(J, I)
    print(
        f"window {g.shape} cells, {jj.size} compared; lattice offset {float(np.abs(X - x).max()):.6f} m, {float(np.abs(Y - y).max()):.6f} m"
    )
    assert (
        float(np.abs(X - x).max()) < 1e-6 and float(np.abs(Y - y).max()) < 1e-6
    ), "the window is not on W79's lattice"
    assert np.all(G.mask[J, I]), "every compared cell is active in the W79 grid"
    report = {
        "cells": int(jj.size),
        "kinds_edit_pixels": edits,
        "objects": [o["name"] for o in inside],
        "arrays": {},
    }
    worst = 0
    for name in CELL:
        a, b = getattr(small, name)[jj, ii], getattr(big, name)[J, I]
        report["arrays"][name] = int((a != b).sum())
    for name in TILES:
        a = g.from_tiles(getattr(small, name)[: g.ntiles])[jj, ii]
        b = G.from_tiles(getattr(big, name)[: G.ntiles])[J, I]
        report["arrays"][name] = (
            int((a != b).any(axis=tuple(range(1, a.ndim))).sum()) if a.ndim > 1 else int((a != b).sum())
        )
    for name, n in report["arrays"].items():
        worst = max(worst, n)
        print(f"   {name:6s} {'equal to the digit' if n == 0 else f'DIFFERS in {n} cells'}")
    cw = np.concatenate(
        [g.from_tiles(small.cwx[: g.ntiles])[jj, ii], g.from_tiles(small.cwy[: g.ntiles])[jj, ii]]
    )
    crest = int((cw != 0.0).sum())
    report["crest_faces"] = crest
    print(
        f"faces with a crest coefficient among them (dam, spillway and natural crests): {crest}; cells that differ in any array: {worst}"
    )
    (out / "w79_crest_check.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
