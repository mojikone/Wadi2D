"""The ground round the cells that take S5's and S11's hydrographs: the lowest bed of the 7 x 7 cells about them and
the inverts of the faces between, from the 40 m tables of ``s02``. Tells whether the 9 m pond at S5 is a gorge.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from s02_block2_40m import job  # noqa: E402

from wadi2d.run import prepare_grid  # noqa: E402

HALF = 3


def main() -> None:
    cfg = job({})
    tables, _crs = prepare_grid(cfg, Path(cfg.grid.cache_dir))
    grid = tables.grid
    found = json.loads((HERE / "injection_cells.json").read_text(encoding="utf-8"))
    efx = grid.from_tiles(tables.efx)
    efy = grid.from_tiles(tables.efy)
    np.set_printoptions(linewidth=200, precision=1, suppress=True)
    for name in ("S5", "S11", "S6"):
        cells = found[name]["cells"]
        j0, i0 = cells[0]["j"], cells[0]["i"]
        base = min(c["zmin"] for c in cells)
        rows, cols = slice(j0 - HALF, j0 + HALF + 1), slice(i0 - HALF, i0 + HALF + 1)
        print(
            f"== {name}: cells {[(c['j'], c['i'], c['zmin']) for c in cells]}, lowest {base}; rows south, columns east"
        )
        print("zmin - lowest (7 x 7 about the first cell):")
        print(np.where(grid.mask[rows, cols], tables.zmin[rows, cols] - base, np.nan))
        print("west-face invert - lowest (face at the west of each cell):")
        print(np.where(grid.mask[rows, cols], efx[rows, cols] - base, np.nan))
        print("north-face invert - lowest (face at the north of each cell):")
        print(np.where(grid.mask[rows, cols], efy[rows, cols] - base, np.nan))


if __name__ == "__main__":
    main()
