"""A depth grid averaged over a catchment, as HMS does for a precipitation-frequency grid.

Interface: :class:`DepthGrid`. The mean takes every cell whose centre lies in the polygons, unweighted, which
reproduces the depths HMS logged for all 40 Block 2 points and for every subbasin of Majlas and Block 6, down to
subbasins holding one cell. Polygons are tested one by one and never unioned: the delineated subbasins of a real
basin model are not always valid enough for a union.

A raster in another coordinate system is read through its cell centres moved to the polygons' system; Majlas's PMP
grid is geographic under a UTM basin. A polygon holding no cell centre raises: no project reaches that case, so
what HMS does there is not known and nothing here guesses.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

import numpy as np
import rasterio
import shapely
from numpy.typing import NDArray
from rasterio.crs import CRS
from rasterio.warp import transform

from wadi2d.storm.base import FloatArray

CELL_CENTRE = 0.5


@dataclass(frozen=True, eq=False)
class DepthGrid:
    """Depths by cell, NaN where the raster has no data, with the coordinates of the cell centres."""

    depths: FloatArray
    x: FloatArray
    y: FloatArray

    @classmethod
    def load(cls, path: str | Path, crs: str | None = None) -> Self:
        """Read a single-band raster, in the units of its file; ``crs`` moves the cell centres to that system."""
        with rasterio.open(path) as raster:
            depths = raster.read(1, masked=True).astype(np.float64).filled(np.nan)
            columns, rows = np.meshgrid(np.arange(raster.width), np.arange(raster.height))
            x, y = raster.transform * (columns + CELL_CENTRE, rows + CELL_CENTRE)
            source = raster.crs
        if crs is None or source is None or source == CRS.from_user_input(crs):
            return cls(depths, np.asarray(x), np.asarray(y))
        moved_x, moved_y = transform(source, CRS.from_user_input(crs), np.ravel(x), np.ravel(y))
        return cls(depths, np.reshape(moved_x, depths.shape), np.reshape(moved_y, depths.shape))

    def cells_in(self, polygon: Any) -> NDArray[np.intp]:
        """The flat indices of the wet cells centred in a polygon."""
        left, bottom, right, top = shapely.bounds(polygon)
        near = (self.x >= left) & (self.x <= right) & (self.y >= bottom) & (self.y <= top)
        near &= np.isfinite(self.depths)
        candidates = np.flatnonzero(near)
        return candidates[shapely.contains_xy(polygon, self.x.flat[candidates], self.y.flat[candidates])]

    def mean_of(self, cells: Iterable[NDArray[np.intp]]) -> float:
        """The mean depth of these cells; a cell named twice counts once."""
        chosen = np.unique(np.concatenate([np.empty(0, dtype=np.intp), *cells]))
        if chosen.size == 0:
            raise ValueError("no grid cell is centred in these polygons")
        return float(self.depths.flat[chosen].mean())

    def mean_over(self, polygons: Iterable[Any]) -> float:
        """The mean depth of the cells centred in any of ``polygons``; shapely geometries in the grid's CRS."""
        return self.mean_of(self.cells_in(polygon) for polygon in polygons)
