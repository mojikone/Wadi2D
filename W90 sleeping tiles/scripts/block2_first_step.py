"""What wakes 3,487 of Block 2's 3,604 tiles at the first step (W79's run 4, read only): the rain or the strip?

    python block2_first_step.py <run folder> <grid cache .h5> <strip cache .pkl> <rain mask .npz> <out .json>

Counts, on the run's own grid: the tiles that hold a ghost cell of the aligned strip (a square the strip touches),
the tiles that hold a boundary cell, the tiles that hold a rained square (the 40 m rim, the coast strip), and each
set with its eight neighbours, which is what the stepper wakes for a tile it keeps awake. The stepper's first list is
rebuilt here by its own rule from the two static sets, to compare with the 3,487 of progress.jsonl.
"""

from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import h5py
import numpy as np

from wadi2d.config.schema import RunConfig
from wadi2d.engine.handback import sink_lines
from wadi2d.engine.inflow_lines import open_lines
from wadi2d.forcing import cells_along
from wadi2d.grid.tiles import TileGrid
from wadi2d.solver.layout import STRIDE2, TILE


def ring(grid: TileGrid, flags: np.ndarray) -> np.ndarray:
    out = flags.copy()
    out[grid.nbr[flags].ravel()] = True
    out[0] = False
    return out


def tiles_of(grid: TileGrid, j: np.ndarray, i: np.ndarray) -> np.ndarray:
    out = np.zeros(grid.ntiles, bool)
    out[grid.tile_of[j // TILE, i // TILE]] = True
    out[0] = False
    return out


def main() -> None:
    run, grid_file, strip_file, rain_file, out_file = (Path(a) for a in sys.argv[1:6])
    with h5py.File(grid_file, "r") as f:
        grid = TileGrid(float(f.attrs["x0"]), float(f.attrs["y0"]), float(f.attrs["dx"]), f["mask"][()])
    with open(strip_file, "rb") as f:
        mesh = pickle.load(f)["strip"].mesh
    cfg = RunConfig.model_validate_json((run / "config.resolved.json").read_text(encoding="utf-8"))
    nt = grid.ntiles

    ghost = np.zeros(nt, bool)
    ghost[np.unique(np.asarray(mesh.ghost_state) // STRIDE2)] = True
    boundary = np.zeros(nt, bool)
    lines = [*open_lines(cfg.boundaries), *sink_lines(cfg.hydrology.handbacks)]
    for b in lines:
        j, i = cells_along(grid, b.coordinates, cfg.grid.line_samples, b.snap_m)
        boundary |= tiles_of(grid, j, i)

    with np.load(rain_file) as f:
        jj, ii, rim, coast = f["jj"], f["ii"], f["rim"], f["coast"]
    rim_t, coast_t = tiles_of(grid, jj[rim], ii[rim]), tiles_of(grid, jj[coast], ii[coast])
    rain_t = tiles_of(grid, jj, ii)

    first = None
    with open(run / "progress.jsonl", encoding="utf-8") as lines_of:
        for line in lines_of:
            row = json.loads(line)
            if row.get("ev") == "step":
                first = row
                break

    def both(flags: np.ndarray) -> dict:
        return {"tiles": int(flags.sum()), "with_neighbours": int(ring(grid, flags).sum())}

    static = ring(grid, ghost | boundary)
    rain_ring = ring(grid, rain_t)
    report = {
        "tiles": nt - 1,
        "first_step_of_the_run": first,
        "ghost_cells": int(np.asarray(mesh.ghost_state).size),
        "strip_ghost": both(ghost),
        "boundary_lines": len(lines),
        "boundary": both(boundary),
        "ghost_or_boundary": both(ghost | boundary),
        "rained_squares": {"rim": int(rim.sum()), "coast": int(coast.sum()), "all": int(jj.size)},
        "rim_rain": both(rim_t),
        "coast_rain": both(coast_t),
        "rim_and_coast_rain": both(rain_t),
        "rain_tiles_that_hold_no_ghost_and_no_boundary": int((rain_t & ~(ghost | boundary)).sum()),
        "rain_ring_outside_the_static_list": int((rain_ring & ~static).sum()),
        "static_list_outside_the_rain_ring": int((static & ~rain_ring).sum()),
        "static_and_rain_ring_together": int((static | rain_ring).sum()),
    }
    out_file.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
