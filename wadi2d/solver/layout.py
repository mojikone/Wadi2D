"""The array contract shared by both backends, the table builder and the HDF5 writer.

State lives tile-major and compact: only tiles that touch the domain are allocated, so a long thin catchment
does not pay for its bounding box. A tile holds ``TILE`` x ``TILE`` own cells inside a ``HALO`` ring of copies
from its neighbours, so kernels use plain offsets and never test for a tile edge.

Index convention. Tile ``t``, row ``j`` southward, column ``i`` eastward, both counted from the halo corner:
``k = t * STRIDE2 + j * STRIDE + i``. Own cells have ``HALO <= i, j < HALO + TILE``.

Faces. ``u[k]`` is the west face of cell ``k``, ``v[k]`` its north face. Own faces are those of own cells. The
east face of the last own column is a halo entry, refreshed by the exchange. Positive velocity points to
increasing ``i`` or ``j``. Tile 0 is the void tile: all dry and closed, the neighbour of every missing tile.

Static tables have no halo: ``(ntiles, TILE, TILE, ...)``, addressed by ``t * TILE2 + (j-HALO) * TILE + (i-HALO)``.
"""

from __future__ import annotations

TILE = 32
HALO = 2
STRIDE = TILE + 2 * HALO
STRIDE2 = STRIDE * STRIDE
TILE2 = TILE * TILE

STATE_ARRAYS = ("h", "d", "u", "v", "mx", "my", "qx", "qy")
"""Mean depth, level above zmin, face velocities, face momenta, face discharges."""

WORK_ARRAYS = ("u1", "v1", "mx1", "my1", "qx1", "qy1", "r", "src")
"""Next face state, positivity ratio, net source rate (m/s)."""

CELL_ARRAYS = ("Hc", "dtab")
"""Top of the hbar axis per cell, level table per cell (rows)."""

FACE_ARRAYS = ("fl", "fr", "gl", "gr", "ef", "cw")
"""Per face: invert over zmin of the cell on either side; invert over the mean bed on either side; table top;
crest coefficient (0 for an ordinary face). Each exists for x faces and for y faces, shape (ntiles, TILE, TILE)."""

FACE_TABLE = "ftab"
"""(ntiles, TILE, TILE, rows, 2): area, and conveyance to the power 3/5 (linear in depth for a wide section)."""

CLOSED = 1.0e9
"""Invert over zmin of a closed face; no level reaches it, so a wall needs no logic in a kernel."""


def local_index(t, j, i):
    """Index of cell (j, i), halo-based, in tile t of a state array."""
    return t * STRIDE2 + j * STRIDE + i


def table_index(t, j, i):
    """Index of own cell (j, i), halo-based, in tile t of a static array."""
    return t * TILE2 + (j - HALO) * TILE + (i - HALO)
