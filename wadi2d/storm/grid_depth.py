"""A depth grid averaged over a catchment, as HMS does for a precipitation-frequency grid.

Interface: :class:`DepthGrid`. The mean takes every cell whose centre lies in the polygons, unweighted, which
reproduces the depths HMS logged for all 40 Block 2 points. Polygons are tested one by one and never unioned: the
delineated subbasins of a real basin model are not always valid enough for a union.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

import numpy as np
import rasterio
import shapely

from wadi2d.storm.base import FloatArray

CELL_CENTRE = 0.5


@dataclass(frozen=True, eq=False)
class DepthGrid:
    """Depths by cell, NaN where the raster has no data, with the coordinates of the cell centres."""

    depths: FloatArray
    x: FloatArray
    y: FloatArray

    @classmethod
    def load(cls, path: str | Path) -> Self:
        """Read a single-band raster, in the units of its file."""
        with rasterio.open(path) as raster:
            depths = raster.read(1, masked=True).astype(np.float64).filled(np.nan)
            columns, rows = np.meshgrid(np.arange(raster.width), np.arange(raster.height))
            x, y = raster.transform * (columns + CELL_CENTRE, rows + CELL_CENTRE)
        return cls(depths, np.asarray(x), np.asarray(y))

    def mean_over(self, polygons: Iterable[Any]) -> float:
        """The mean depth of the cells centred in any of ``polygons``; shapely geometries in the grid's CRS."""
        inside = np.zeros(self.depths.shape, dtype=bool)
        for polygon in polygons:
            inside |= shapely.contains_xy(polygon, self.x, self.y)
        chosen = self.depths[inside & np.isfinite(self.depths)]
        if chosen.size == 0:
            raise ValueError("no grid cell is centred in these polygons")
        return float(chosen.mean())
