"""When does the far size change the mesh? Tiles are 32 cells and the 2:1 balance makes rings of its own, so a short band
hides it. One straight line at several positions on a large synthetic lattice, near 10 m, coarsest 80 m; no terrain, no solver.
"""

from __future__ import annotations

import numpy as np

from wadi2d.config.schema import RefineLine
from wadi2d.grid.quad import QuadGrid
from wadi2d.mesh.refine import Lattice, band_levels
from wadi2d.solver.layout import TILE

DX = 10.0
TOP = 3
SIDE = 128
ROWS = (2, 4, 8, 16, 32, 64, 128)
FARS = (10.0, 20.0, 40.0, 80.0)
OFFSETS = (0.0, 37.0, 160.0, 283.0, 512.0, 700.0)


def cells(y: float, rows: int, far: float) -> int:
    size = SIDE * TILE * DX
    line = RefineLine(coordinates=[(200.0, y), (size - 200.0, y)], near_dx=DX, rows=rows, far_dx=far)
    wanted = band_levels([line], Lattice(0.0, size, DX, SIDE, SIDE), TOP)
    return QuadGrid.from_levels(np.ones((SIDE * TILE, SIDE * TILE), bool), 0.0, size, DX, wanted).cell_count


def main() -> None:
    middle = SIDE * TILE * DX / 2.0
    print("cells, thousand, mean of six line positions; last column: share of positions where far 40 differs from far 10")
    print("rows  " + "  ".join(f"far {far:>3g}" for far in FARS))
    for rows in ROWS:
        row = {far: [cells(middle + off, rows, far) for off in OFFSETS] for far in FARS}
        means = "  ".join(f"{np.mean(row[far]) / 1e3:7.0f}" for far in FARS)
        moved = np.mean([a != b for a, b in zip(row[10.0], row[40.0], strict=True)])
        print(f"{rows:>4}  {means}   {moved:.2f}")


if __name__ == "__main__":
    main()
