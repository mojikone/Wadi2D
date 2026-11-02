"""A 1 m pixel bed on a 10 m grid, flat unless asked: every expected number below can be worked by hand."""

from __future__ import annotations

import numpy as np

from wadi2d.config.schema import Terrain, TerrainObject
from wadi2d.grid import TileGrid
from wadi2d.tables import ArrayBed
from wadi2d.terrain import Ground, apply_objects

GROUND = 100.0
SIZE = 320
"""Pixels along each side of the test bed; pixel centres fall on .5."""


def grid_of(cells: int = SIZE // 10) -> TileGrid:
    return TileGrid.from_mask(np.ones((cells, cells), bool), 0.0, float(cells * 10), 10.0)


def obj(kind: str, coordinates, **fields) -> TerrainObject:
    return TerrainObject(kind=kind, coordinates=coordinates, **fields)


def flat_bed(level: float = GROUND, cells: int = SIZE // 10) -> ArrayBed:
    """A bed covering the whole padded grid, read from the grid origin."""
    grid = grid_of(cells)
    return ArrayBed(np.full((grid.shape[0] * 10, grid.shape[1] * 10), level), 1.0)


def edited(objects, bed: ArrayBed | None = None, cfg: Terrain | None = None) -> tuple[np.ndarray, TileGrid]:
    """The new ground of a whole grid, in pixels, as the table builder would make it."""
    grid = grid_of()
    bed = bed or flat_bed()
    z = bed.z.astype(np.float64).copy()
    edits = apply_objects(grid, objects, 1.0, cfg or Terrain(), Ground(bed, grid.x0, grid.y0))
    edits.edit(z, 0, 0)
    return z, grid


def at(z: np.ndarray, grid: TileGrid, x: float, y: float) -> float:
    """The pixel holding the point (x, y)."""
    return float(z[int((grid.y0 - y) // 1.0), int((x - grid.x0) // 1.0)])
