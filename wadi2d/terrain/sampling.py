"""A raster read at the cell centres, in the raster's own coordinate system.

Cell centres move to the raster's system when the two differ, so a curve-number or depth raster in another CRS
reads its true values and not NaN. A raster and a DEM of which only one has a CRS cannot be matched: refused.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.warp import transform
from rasterio.windows import Window

from wadi2d.grid.tiles import TileGrid


def _same_system(raster: CRS | None, dem: str, name: str) -> bool:
    if raster is None and not dem:
        return True
    if raster is None or not dem:
        raise ValueError(f"{name}: one of this raster and the DEM has no CRS, so they cannot be matched")
    return raster == CRS.from_user_input(dem)


def raster_at_cells(path: str | Path, grid: TileGrid, crs: str) -> np.ndarray:
    """Nearest value at each active cell centre on a (ny, nx) grid; NaN off the raster, on nodata and off the mask."""
    jj, ii = np.nonzero(grid.mask)
    out = np.full(grid.shape, np.nan)
    if jj.size == 0:
        return out
    x, y = grid.xy_of(jj, ii)
    with rasterio.open(path) as src:
        if not _same_system(src.crs, crs, Path(path).name):
            moved = transform(CRS.from_user_input(crs), src.crs, x.tolist(), y.tolist())
            x, y = np.asarray(moved[0]), np.asarray(moved[1])
        inverse = ~src.transform
        fx = inverse.a * x + inverse.b * y + inverse.c
        fy = inverse.d * x + inverse.e * y + inverse.f
        usable = np.isfinite(fx) & np.isfinite(fy)
        cols = np.floor(np.where(usable, fx, -1.0)).astype(np.int64)
        rows = np.floor(np.where(usable, fy, -1.0)).astype(np.int64)
        inside = (cols >= 0) & (cols < src.width) & (rows >= 0) & (rows < src.height)
        if not inside.any():
            return out
        c0, c1 = int(cols[inside].min()), int(cols[inside].max()) + 1
        r0, r1 = int(rows[inside].min()), int(rows[inside].max()) + 1
        band = src.read(1, window=Window(c0, r0, c1 - c0, r1 - r0), masked=True)
    values = band.astype(np.float64).filled(np.nan)
    out[jj[inside], ii[inside]] = values[rows[inside] - r0, cols[inside] - c0]
    return out
