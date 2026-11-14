"""A depth grid averaged over a catchment, as HMS does for a precipitation-frequency grid.

Interface: :class:`DepthGrid`. The mean takes every cell whose centre lies in the polygons, unweighted, which
reproduces the depths HMS logged for all 40 Block 2 points and for every subbasin of Majlas and Block 6, down to
subbasins holding one cell. Polygons are tested one by one and never unioned: the delineated subbasins of a real
basin model are not always valid enough for a union.

A raster in another coordinate system is read through its cell centres moved to the polygons' system; Majlas's PMP
grid is geographic under a UTM basin.

Polygons that hold no cell centre between them read the one cell whose centre lies nearest their centroid (the
area-weighted mean of the polygons' own centroids, the union's centroid for polygons that do not overlap). Measured on
Block 2's Basin 3 (2026-11-11), where ten subbasins of 0.35 to 1.35 km2 under the 958 m PMP grid hold no centre:
the three analysis points whose upstream polygons hold none, BID-J17 (one subbasin), BID-J19 (one) and BID-J45
(two), read HMS's logged depth to 0.001 mm by this rule, and BID-J45 rules out a cell per polygon. Where the
polygons hold at least one centre, an empty polygon adds nothing, as all 94 other points of that analysis show. A
centroid farther than a cell spacing from every wet centre is off the grid and still raises.
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

    def nearest_cell(self, x: float, y: float) -> int:
        """The flat index of the wet cell whose centre lies nearest a point that lies on the grid.

        A point farther from every wet centre than one cell spacing is off the grid (or in another coordinate
        system, Majlas's failure) and raises: the rule is for a small catchment inside the grid, nothing else.
        """
        distance = np.where(np.isfinite(self.depths), (self.x - x) ** 2 + (self.y - y) ** 2, np.inf)
        nearest = int(np.argmin(distance))
        if not distance.flat[nearest] <= self.spacing**2:
            raise ValueError("no grid cell is centred in these polygons, and their centroid lies off the grid")
        return nearest

    @property
    def spacing(self) -> float:
        """The largest median distance between neighbouring cell centres, along the rows or the columns."""
        steps = [np.hypot(np.diff(self.x, axis=axis), np.diff(self.y, axis=axis)) for axis in (0, 1)]
        return float(max((np.median(step) for step in steps if step.size), default=np.inf))

    def mean_of(self, cells: Iterable[NDArray[np.intp]], centroid: tuple[float, float] | None = None) -> float:
        """The mean depth of these cells, a cell named twice counting once; none, the cell nearest ``centroid``."""
        chosen = np.unique(np.concatenate([np.empty(0, dtype=np.intp), *cells]))
        if chosen.size == 0:
            if centroid is None:
                raise ValueError("no grid cell is centred in these polygons")
            return float(self.depths.flat[self.nearest_cell(*centroid)])
        return float(self.depths.flat[chosen].mean())

    def mean_over(self, polygons: Iterable[Any]) -> float:
        """The mean depth of the cells centred in any of ``polygons``; shapely geometries in the grid's CRS."""
        shapes = list(polygons)
        return self.mean_of((self.cells_in(polygon) for polygon in shapes), centroid_of(shapes))


def centroid_of(polygons: Iterable[Any]) -> tuple[float, float]:
    """The area-weighted mean of the polygons' centroids; no union, so an invalid polygon cannot stop it."""
    shapes = list(polygons)
    if not shapes:
        raise ValueError("no polygon to take a centroid of")
    areas = np.array([shape.area for shape in shapes])
    points = [shape.centroid for shape in shapes]
    xs = np.array([point.x for point in points])
    ys = np.array([point.y for point in points])
    return float((areas * xs).sum() / areas.sum()), float((areas * ys).sum() / areas.sum())
