"""How much a depth raster steps at the lattice's cell edges, against what it does inside the cells.

    python s04_steps.py RUN RASTER [RASTER ...]

For every pair of side-by-side pixels of the raster, east-west and north-south, the pair is at a cell edge when the
line between them is a lattice cell edge of RUN's grid. A surface with no step at the edges gives the same figures at
edges and inside: the share of pairs where one pixel is wet and the other dry, and the mean depth change between two
wet pixels. A step at the edges shows as a larger share, and a larger change, at the edges. Pixels of the aligned
cells are left out (their edges are not the lattice's).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import h5py
import numpy as np
import rasterio

NODATA = -9999.0


def steps(run: Path, raster: Path) -> dict:
    with h5py.File(run / "results.h5", "r") as f:
        x0, y0, dx = (float(f.attrs[n]) for n in ("x0", "y0", "dx"))
        mask = f["mask"][:]
    with rasterio.open(raster) as src:
        depth = src.read(1).astype(np.float64)
        t = src.transform
    pixel = t.a
    k = round(dx / pixel)
    ny, nx = depth.shape
    col0 = round((t.c - x0) / pixel)
    row0 = round((y0 - t.f) / pixel)
    rows = np.arange(ny) + row0
    cols = np.arange(nx) + col0
    cell_r, cell_c = rows // k, cols // k
    inside = (cell_r >= 0) & (cell_r < mask.shape[0])
    across = (cell_c >= 0) & (cell_c < mask.shape[1])
    lattice = np.zeros((ny, nx), bool)
    lattice[np.ix_(inside, across)] = mask[np.ix_(cell_r[inside], cell_c[across])]
    wet = depth != NODATA
    d = np.where(wet, depth, 0.0)
    out = {}
    for name, axis in (("east_west", 1), ("north_south", 0)):
        a = (slice(None), slice(0, -1)) if axis == 1 else (slice(0, -1), slice(None))
        b = (slice(None), slice(1, None)) if axis == 1 else (slice(1, None), slice(None))
        line = cols if axis == 1 else rows
        edge = (line[1:] % k) == 0  # the second pixel starts a cell
        edge = np.broadcast_to(edge[None, :] if axis == 1 else edge[:, None], d[a].shape)
        both_lattice = lattice[a] & lattice[b]
        either = (wet[a] | wet[b]) & both_lattice
        changes = (wet[a] != wet[b]) & both_lattice
        both_wet = wet[a] & wet[b] & both_lattice
        jump = np.abs(d[a] - d[b])
        for where, sel in (("edge", edge), ("inside", ~edge)):
            pairs = either & sel
            out[f"{name}_{where}_wet_dry_share"] = round(float((changes & sel).sum()) / max(int(pairs.sum()), 1), 4)
            wet_pairs = both_wet & sel
            out[f"{name}_{where}_mean_jump_m"] = round(float(jump[wet_pairs].mean()) if wet_pairs.any() else 0.0, 4)
            out[f"{name}_{where}_p99_jump_m"] = round(float(np.percentile(jump[wet_pairs], 99)) if wet_pairs.any() else 0.0, 4)
        # across the join of the squares and the aligned cells: one pixel on the lattice, the other on the strip
        across = lattice[a] != lattice[b]
        pairs = (wet[a] | wet[b]) & across
        out[f"{name}_join_wet_dry_share"] = round(float(((wet[a] != wet[b]) & across).sum()) / max(int(pairs.sum()), 1), 4)
        wet_pairs = wet[a] & wet[b] & across
        out[f"{name}_join_mean_jump_m"] = round(float(jump[wet_pairs].mean()) if wet_pairs.any() else 0.0, 4)
        out[f"{name}_join_p99_jump_m"] = round(float(np.percentile(jump[wet_pairs], 99)) if wet_pairs.any() else 0.0, 4)
    out["wet_pixels"] = int(wet.sum())
    return out


def main() -> None:
    run = Path(sys.argv[1])
    for raster in sys.argv[2:]:
        print(raster, json.dumps(steps(run, Path(raster))))


if __name__ == "__main__":
    main()
