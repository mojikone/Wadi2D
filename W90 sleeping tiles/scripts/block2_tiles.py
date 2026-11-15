"""Block 2 at 20 m on the aligned mesh (W79's saved runs, read only): which tiles the strip's ghosts hold awake, and
which tiles and strip cells the water ever needed, frame by frame.

    python block2_tiles.py <run folder> <grid cache .h5> <strip cache .pkl> <out .json>

A tile is "needed" in a frame when it or one of its eight neighbours holds water on the lattice or in a strip cell
whose centre lies in it: the rule the stepper has always used for the squares, extended to the strip. The frames are
15 minutes apart, so the count is an estimate between them; the steps of each interval come from progress.jsonl.
"""

from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import h5py
import numpy as np

from wadi2d.grid.tiles import TileGrid
from wadi2d.solver.layout import STRIDE2, TILE


def ring(grid: TileGrid, flags: np.ndarray) -> np.ndarray:
    out = flags.copy()
    out[grid.nbr[flags].ravel()] = True
    out[0] = False
    return out


BAND = 18
"""Cells from a tile's edge within which water wakes the neighbour on that side: the steps between two checks and a
margin. The rule as built wakes all eight neighbours of a wet tile; this is the finer rule it could have."""


def band_rule(grid: TileGrid, wet_cells: np.ndarray) -> np.ndarray:
    """Tiles awake under the finer rule: a wet tile, and a neighbour only where water lies within ``BAND`` cells of
    the shared edge (a corner neighbour: within the band of both edges)."""
    nty, ntx = grid.tile_of.shape
    w = wet_cells.reshape(nty, TILE, ntx, TILE)
    rows = w.any(axis=3)  # (nty, TILE, ntx): which rows of each tile hold water
    cols = w.any(axis=1)  # (nty, ntx, TILE)
    north, south = rows[:, :BAND, :].any(axis=1), rows[:, TILE - BAND :, :].any(axis=1)
    west, east = cols[:, :, :BAND].any(axis=2), cols[:, :, TILE - BAND :].any(axis=2)
    nw = w[:, :BAND, :, :BAND].any(axis=(1, 3))
    ne = w[:, :BAND, :, TILE - BAND :].any(axis=(1, 3))
    sw = w[:, TILE - BAND :, :, :BAND].any(axis=(1, 3))
    se = w[:, TILE - BAND :, :, TILE - BAND :].any(axis=(1, 3))
    awake = w.any(axis=(1, 3))
    out = awake.copy()
    out[:-1, :] |= north[1:, :]
    out[1:, :] |= south[:-1, :]
    out[:, :-1] |= west[:, 1:]
    out[:, 1:] |= east[:, :-1]
    out[:-1, :-1] |= nw[1:, 1:]
    out[:-1, 1:] |= ne[1:, :-1]
    out[1:, :-1] |= sw[:-1, 1:]
    out[1:, 1:] |= se[:-1, :-1]
    flags = np.zeros(grid.ntiles, bool)
    flags[grid.tile_of[out]] = True
    flags[0] = False
    return flags


def main() -> None:
    run, grid_file, strip_file, out_file = (Path(a) for a in sys.argv[1:5])
    with h5py.File(grid_file, "r") as f:
        grid = TileGrid(float(f.attrs["x0"]), float(f.attrs["y0"]), float(f.attrs["dx"]), f["mask"][()])
    with open(strip_file, "rb") as f:
        held = pickle.load(f)
    mesh = held["strip"].mesh
    n = mesh.nreal
    ntiles = grid.ntiles
    nty, ntx = grid.tile_of.shape
    report: dict = {"tiles": ntiles - 1, "lattice_cells": int(grid.mask.sum()), "strip_cells": int(n), "strip_faces": int(mesh.left.size)}

    # ---- what the strip holds awake
    ghost_tiles = np.zeros(ntiles, bool)
    ghost_tiles[np.unique(np.asarray(mesh.ghost_state) // STRIDE2)] = True
    report["ghosts"] = int(np.asarray(mesh.ghost_state).size)
    report["tiles_with_a_ghost"] = int(ghost_tiles.sum())
    report["tiles_with_a_ghost_and_neighbours"] = int(ring(grid, ghost_tiles).sum())

    # ---- each strip cell's home tile: the tile its centre lies in
    j = ((grid.y0 - mesh.cy[:n]) // grid.dx).astype(np.int64)
    i = ((mesh.cx[:n] - grid.x0) // grid.dx).astype(np.int64)
    home = grid.tile_of[np.clip(j // TILE, 0, nty - 1), np.clip(i // TILE, 0, ntx - 1)]
    sj, si = np.clip(j, 0, grid.shape[0] - 1), np.clip(i, 0, grid.shape[1] - 1)
    report["strip_cells_with_no_home_tile"] = int((home == 0).sum())
    cells_in = np.bincount(home, minlength=ntiles)
    report["tiles_with_strip_cells"] = int((cells_in[1:] > 0).sum())

    # ---- the steps of each frame interval
    steps_at: list[tuple[float, int]] = [(0.0, 0)]
    with open(run / "progress.jsonl", encoding="utf-8") as lines_of:
        for line in lines_of:
            row = json.loads(line)
            if row.get("ev") in ("step", "done"):
                steps_at.append((float(row["t"]), int(row["steps"])))
    ts, ss = np.array([a for a, _ in steps_at]), np.array([b for _, b in steps_at], float)

    ever_tile = np.zeros(ntiles, bool)
    ever_strip = np.zeros(n, bool)
    ever_flow = np.zeros(ntiles, bool)
    rows = []
    with h5py.File(run / "results.h5", "r") as f:
        names = sorted(f["maps"], key=lambda k: float(f["maps"][k].attrs["t_s"]))
        t_prev = 0.0
        for name in names:
            g = f["maps"][name]
            t = float(g.attrs["t_s"])
            h = g["mean_depth"][()]
            wet_cells = h > 0.0
            occ = wet_cells.reshape(nty, TILE, ntx, TILE).any(axis=(1, 3))
            lattice = np.zeros(ntiles, bool)
            lattice[grid.tile_of[occ]] = True
            lattice[0] = False
            sw = g["strip_mean_depth"][0, :n] > 0.0
            strip_tiles = np.zeros(ntiles, bool)
            strip_tiles[np.unique(home[sw])] = True
            strip_tiles[0] = False
            wet = lattice | strip_tiles
            needed = ring(grid, wet)
            ever_tile |= wet
            ever_strip |= sw
            groups = ring(grid, strip_tiles | lattice)  # a strip group steps where its tile is needed
            both_wet = wet_cells.copy()  # the strip's wet cells at their centres, with the squares'
            both_wet[sj[sw], si[sw]] = True
            fine = band_rule(grid, both_wet)
            # where water moves: a face discharge on the lattice, a speed in a strip cell
            moving = (g["qx"][()] != 0.0) | (g["qy"][()] != 0.0)
            flow = np.zeros(ntiles, bool)
            flow[grid.tile_of[moving.reshape(nty, TILE, ntx, TILE).any(axis=(1, 3))]] = True
            flow[np.unique(home[g["strip_speed"][0, :n] > 0.0])] = True
            flow[0] = False
            ever_flow |= flow
            steps = float(np.interp(t, ts, ss) - np.interp(t_prev, ts, ss))
            rows.append(
                {
                    "t": t, "steps": steps, "lattice_wet_tiles": int(lattice.sum()), "strip_wet_tiles": int(strip_tiles.sum()),
                    "wet_tiles": int(wet.sum()), "needed_tiles": int(needed.sum()), "wet_lattice_cells": int(wet_cells.sum()),
                    "wet_strip_cells": int(sw.sum()), "strip_cells_in_needed_tiles": int(cells_in[groups].sum()),
                    "flowing_tiles": int(flow.sum()), "flowing_with_neighbours": int(ring(grid, flow).sum()),
                    "band_rule_tiles": int(fine.sum()), "strip_cells_in_band_rule_tiles": int(cells_in[fine].sum()),
                }
            )  # fmt: skip
            t_prev = t
    total = sum(r["steps"] for r in rows)
    all_tiles = ntiles - 1
    report["frames"] = len(rows)
    report["steps"] = total
    report["tiles_ever_wet"] = int(ever_tile.sum())
    report["tiles_ever_needed"] = int(ring(grid, ever_tile).sum())
    report["strip_cells_ever_wet"] = int(ever_strip.sum())
    report["needed_tile_steps_share"] = sum(r["steps"] * r["needed_tiles"] for r in rows) / max(total * all_tiles, 1)
    report["needed_strip_cell_steps_share"] = sum(r["steps"] * r["strip_cells_in_needed_tiles"] for r in rows) / max(total * n, 1)
    report["tiles_ever_flowing"] = int(ever_flow.sum())
    report["flowing_tile_steps_share"] = sum(r["steps"] * r["flowing_with_neighbours"] for r in rows) / max(total * all_tiles, 1)
    report["band_rule_tile_steps_share"] = sum(r["steps"] * r["band_rule_tiles"] for r in rows) / max(total * all_tiles, 1)
    report["band_rule_strip_cell_steps_share"] = sum(r["steps"] * r["strip_cells_in_band_rule_tiles"] for r in rows) / max(total * n, 1)
    report["wet_tile_steps_share"] = sum(r["steps"] * r["wet_tiles"] for r in rows) / max(total * all_tiles, 1)
    report["wet_lattice_cell_steps_share"] = sum(r["steps"] * r["wet_lattice_cells"] for r in rows) / max(total * report["lattice_cells"], 1)
    report["wet_strip_cell_steps_share"] = sum(r["steps"] * r["wet_strip_cells"] for r in rows) / max(total * n, 1)
    report["largest_needed_tiles"] = max(r["needed_tiles"] for r in rows)
    report["rows"] = rows
    out_file.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=1))
    for r in rows[:: max(len(rows) // 24, 1)]:
        print(r)


if __name__ == "__main__":
    main()
