"""The real cell grid for the map: one line feature per tile, the cells the solver stepped.

A polygon per cell would be 17 M features on the full extent, and no GIS draws that. Lines per tile are about 17,000
features, a few MB, and they show a coarse tile as coarse and a cell left out by the domain as left out. A line runs
along every edge that touches an active cell of the tile, and straight runs of edges join, so a full tile is 66 lines.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import shapely

from wadi2d.io.geopackage import LINES, VectorLayer, write_geopackage
from wadi2d.products.smooth import crs_text
from wadi2d.solver.layout import TILE

CELL_GRID_FILE = "cell_grid.gpkg"
CELL_GRID_LAYER = "cell_grid"


def _runs(along: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Straight stretches of True in each row: (row, first, one past the last)."""
    steps = np.diff(np.pad(along.astype(np.int8), ((0, 0), (1, 1))), axis=1)
    row, first = np.nonzero(steps == 1)
    _, stop = np.nonzero(steps == -1)
    return row, first, stop


def _edges(on: np.ndarray) -> np.ndarray:
    """(lines + 1, length): an edge is there when a cell on either side of it is."""
    wide = np.zeros((on.shape[0] + 2, on.shape[1]), bool)
    wide[1:-1] = on
    return wide[:-1] | wide[1:]


def tile_lines(cells: np.ndarray) -> np.ndarray:
    """The lines of one tile as (n, 2, 2) in cells, column then row, from the tile's north-west corner."""
    across, first, stop = _runs(_edges(cells))  # lines along the rows, at a row edge
    west_east = np.stack((np.stack((first, across), 1), np.stack((stop, across), 1)), 1)
    across, first, stop = _runs(_edges(cells.T))  # lines along the columns, at a column edge
    north_south = np.stack((np.stack((across, first), 1), np.stack((across, stop), 1)), 1)
    return np.concatenate((west_east, north_south)).astype(np.float64)


def _tiles(grid):
    """(tile row, tile column, cell size, level, active cells) of every tile, uniform or quadtree alike."""
    quad = getattr(grid, "quad", False)
    for t in range(1, grid.ntiles):
        tj, ti = (int(v) for v in grid.tiles[t])
        if quad:
            yield tj, ti, float(grid.tile_dx[t]), int(grid.level[t]), grid.cells[t]
        else:
            y, x = tj * TILE, ti * TILE
            yield tj, ti, grid.dx, 0, grid.mask[y : y + TILE, x : x + TILE]


def cell_grid_layer(grid) -> VectorLayer:
    lines, owner, rows = [], [], []
    full = tile_lines(np.ones((TILE, TILE), bool))
    for n, (tj, ti, size, level, cells) in enumerate(_tiles(grid)):
        count = int(cells.sum())
        drawn = full if count == TILE * TILE else tile_lines(cells)
        corner = np.array((grid.x0 + ti * TILE * grid.dx, grid.y0 - tj * TILE * grid.dx))
        lines.append(corner + drawn * (size, -size))
        owner.append(np.full(drawn.shape[0], n))
        rows.append((size, level, count, tj, ti))
    columns = {"cell_m": float, "level": int, "cells": int, "tile_row": int, "tile_column": int}
    if not rows:
        return VectorLayer(CELL_GRID_LAYER, columns, [], [], LINES)
    shapes = shapely.multilinestrings(shapely.linestrings(np.concatenate(lines)), indices=np.concatenate(owner))
    return VectorLayer(CELL_GRID_LAYER, columns, rows, list(shapes), LINES)


def write_cell_grid(grid, crs, out: Path) -> Path:
    return write_geopackage(out / CELL_GRID_FILE, [cell_grid_layer(grid)], crs_text(crs))
