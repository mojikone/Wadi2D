"""The watch of Block 2's strip, built on the CPU from the cached grid mask and strip (read only): its size, the time
to build it, and how far it reaches beyond a tile's eight neighbours.

    python block2_watch.py <grid cache .h5> <strip cache .pkl> <out .json>
"""

from __future__ import annotations

import json
import pickle
import sys
import time
from pathlib import Path

import h5py
import numpy as np

from wadi2d.grid.tiles import TileGrid
from wadi2d.solver.layout import HALO, STRIDE, STRIDE2, TILE
from wadi2d.strips.watch import build_watch


def main() -> None:
    grid_file, strip_file, out = (Path(a) for a in sys.argv[1:4])
    with h5py.File(grid_file, "r") as f:
        grid = TileGrid(float(f.attrs["x0"]), float(f.attrs["y0"]), float(f.attrs["dx"]), f["mask"][()])
    with open(strip_file, "rb") as f:
        mesh = pickle.load(f)["strip"].mesh
    ghost = np.asarray(mesh.ghost_state, np.int64)
    t, rem = ghost // STRIDE2, ghost % STRIDE2
    gj = grid.tiles[t, 0] * TILE + rem // STRIDE - HALO
    gi = grid.tiles[t, 1] * TILE + rem % STRIDE - HALO
    t0 = time.perf_counter()
    watch = build_watch(mesh, grid, gj, gi, 16)
    first = time.perf_counter() - t0
    t0 = time.perf_counter()
    watch = build_watch(mesh, grid, gj, gi, 16)
    again = time.perf_counter() - t0
    nt = grid.ntiles
    ring = np.zeros((nt, nt), bool)
    idx = np.arange(1, nt)
    ring[idx, idx] = True
    for k in range(8):
        ring[idx, grid.nbr[idx, k]] = True
    ring[:, 0] = False
    sq, st = watch.from_squares.toarray() > 0, watch.from_strip.toarray() > 0
    report = {
        "tiles": nt - 1, "strip_cells": int(mesh.real), "reach_cells": watch.reach,
        "build_s_first_call": round(first, 2), "build_s": round(again, 2),
        "entries_squares": int(watch.from_squares.nnz), "entries_strip": int(watch.from_strip.nnz),
        "tiles_whose_squares_reach_beyond_their_neighbours": int((sq & ~ring).any(axis=1).sum()),
        "pairs_of_squares_beyond_the_neighbours": int((sq & ~ring).sum()),
        "tiles_reached_by_a_strip_home_beyond_their_neighbours": int((st & ~ring).any(axis=1).sum()),
        "pairs_of_strip_homes_beyond_the_neighbours": int((st & ~ring).sum()),
        "largest_cell_area_m2": float(np.max(mesh.area[: mesh.real])), "lattice_cell_area_m2": grid.dx**2,
    }  # fmt: skip
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
