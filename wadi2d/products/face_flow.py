"""Discharge through the faces a line crosses, read from the saved frames: the faces, the signs and the sum of an upfront line.

A run that keeps ``outputs.face_discharge`` saves ``qx`` and ``qy`` with every map, the discharge through each cell's
west face, positive eastward, and through its north face, positive southward, m3/s, as the solver holds them. A line is
rasterised onto the face lattice as a staircase, as an upfront line is, and the signed discharges of the faces it crosses
are summed, positive to the line's right. So a line read here is the upfront line at the frame times, and sees nothing
between two frames.

On a quadtree the maps are on the finest raster and a coarse cell's discharge is painted onto every finest cell under it.
A coarse face is read once: of its staircase edges only those on the coarse cell's own boundary count, each a share of
the face, so a line that crosses the whole face reads the whole discharge and one that crosses part of it reads that part.
An edge inside a coarse cell is no face and counts nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

import h5py
import numpy as np

from wadi2d.grid.tiles import TileGrid
from wadi2d.io.results import FACE_FIELDS
from wadi2d.solver.layout import TILE
from wadi2d.terrain.crest import NORTH, staircase

FLOW_FACES, FLOW_ESTIMATE = "faces", "estimate"
"""What a line's flow was read from: the saved face discharges, or depth and speed."""
X_FACES, Y_FACES = FACE_FIELDS


@dataclass
class FaceCrossing:
    """The faces of the saved maps a line crosses: cell rows and columns per axis, with a signed weight each."""

    x_rows: np.ndarray
    x_columns: np.ndarray
    x_weight: np.ndarray
    y_rows: np.ndarray
    y_columns: np.ndarray
    y_weight: np.ndarray

    @property
    def count(self) -> int:
        return self.x_rows.size + self.y_rows.size


def frames_have_faces(f: h5py.File, names: list[str]) -> bool:
    """Whether every saved map holds both face discharges; a run resumed from an older checkpoint may hold some."""
    return bool(names) and all(all(field in f["maps"][name] for field in FACE_FIELDS) for name in names)


def face_crossing(
    mask: np.ndarray, x0: float, y0: float, dx: float, coordinates: list, tiles: np.ndarray
) -> FaceCrossing:
    """The staircase of a line on the lattice of the saved maps, kept to active cells and to real faces.

    ``tiles`` is the cell size in finest cells per tile of the finest lattice, 1 everywhere on a uniform grid. The sign
    is the staircase's own, positive to the right of the line, and the weight is that sign over the cell size.
    """
    grid = TileGrid(x0, y0, dx, mask)
    st = staircase(grid, coordinates)
    rows, columns = st.j.astype(np.int64), st.i.astype(np.int64)
    keep = grid.mask[rows, columns]
    sizes = tiles[rows // TILE, columns // TILE]
    north = st.axis == NORTH
    on_face = np.where(north, rows % sizes == 0, columns % sizes == 0)
    weight = st.side.astype(np.float64) / sizes
    x = keep & ~north & on_face
    y = keep & north & on_face
    return FaceCrossing(rows[x], columns[x], weight[x], rows[y], columns[y], weight[y])


def face_flow(qx: np.ndarray, qy: np.ndarray, crossing: FaceCrossing) -> float:
    """Signed flow through the line, m3/s, from the face discharges read at the crossing's cells in its order."""
    along_x = np.dot(qx.astype(np.float64), crossing.x_weight)
    along_y = np.dot(qy.astype(np.float64), crossing.y_weight)
    return float(along_x + along_y)
