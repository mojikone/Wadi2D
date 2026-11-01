"""TileGrid: maps a uniform raster-aligned grid onto compact tiles with neighbour links.

Rows run south, as in the DEM and the GeoTIFFs. The grid is padded so the domain never touches its edge, and
the void tile 0 stands in for every missing neighbour.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from wadi2d.solver.layout import TILE

NEIGHBOURS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
"""(row, column) offsets of the eight neighbours, in the order of ``TileGrid.nbr``."""


@dataclass
class TileGrid:
    """Grid geometry and tile bookkeeping. ``mask`` is True on active cells, shape (ny, nx)."""

    x0: float
    y0: float
    dx: float
    mask: np.ndarray
    tile_of: np.ndarray = field(init=False)
    """(nty, ntx) compact tile id, 0 where no tile is allocated."""
    tiles: np.ndarray = field(init=False)
    """(ntiles, 2) grid tile coordinates (tj, ti) of each compact tile; entry 0 is the void tile."""
    nbr: np.ndarray = field(init=False)
    """(ntiles, 8) compact ids of the neighbours."""

    def __post_init__(self) -> None:
        ny, nx = self.mask.shape
        if ny % TILE or nx % TILE:
            raise ValueError("mask shape must be a multiple of the tile size; use TileGrid.from_mask")
        nty, ntx = ny // TILE, nx // TILE
        occ = self.mask.reshape(nty, TILE, ntx, TILE).any(axis=(1, 3))
        self.tile_of = np.zeros((nty, ntx), dtype=np.int32)
        cells = np.argwhere(occ)
        self.tile_of[occ] = np.arange(1, cells.shape[0] + 1, dtype=np.int32)
        self.tiles = np.vstack([np.array([[-1, -1]], dtype=np.int32), cells.astype(np.int32)])
        self.nbr = np.zeros((self.ntiles, 8), dtype=np.int32)
        for t in range(1, self.ntiles):
            tj, ti = self.tiles[t]
            for n, (dj, di) in enumerate(NEIGHBOURS):
                j2, i2 = tj + dj, ti + di
                if 0 <= j2 < nty and 0 <= i2 < ntx:
                    self.nbr[t, n] = self.tile_of[j2, i2]

    @classmethod
    def from_mask(cls, mask: np.ndarray, x0: float, y0: float, dx: float) -> TileGrid:
        """Pad ``mask`` to whole tiles with one cell of margin on every side.

        ``x0`` is the west edge and ``y0`` the north edge of ``mask``. The padding moves the origin.
        """
        ny, nx = mask.shape
        pad_n = pad_w = 1
        nyp = int(np.ceil((ny + 2) / TILE)) * TILE
        nxp = int(np.ceil((nx + 2) / TILE)) * TILE
        m = np.zeros((nyp, nxp), dtype=bool)
        m[pad_n : pad_n + ny, pad_w : pad_w + nx] = mask
        return cls(x0 - pad_w * dx, y0 + pad_n * dx, dx, m)

    @property
    def ntiles(self) -> int:
        return self.tiles.shape[0]

    @property
    def shape(self) -> tuple[int, int]:
        return self.mask.shape

    def cell_of(self, x: float, y: float) -> tuple[int, int]:
        """Grid (row, column) of a point."""
        return int((self.y0 - y) // self.dx), int((x - self.x0) // self.dx)

    def xy_of(self, j: np.ndarray, i: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Cell centre coordinates of grid (row, column)."""
        return self.x0 + (i + 0.5) * self.dx, self.y0 - (j + 0.5) * self.dx

    def locate(self, j: int, i: int) -> tuple[int, int, int]:
        """Compact tile and own local (row, column), counted from the first own cell."""
        return int(self.tile_of[j // TILE, i // TILE]), j % TILE, i % TILE

    def to_tiles(self, a: np.ndarray, dtype=np.float32) -> np.ndarray:
        """Cut a (ny, nx) grid into (ntiles, TILE, TILE); the void tile is zero."""
        out = np.zeros((self.ntiles, TILE, TILE) + a.shape[2:], dtype=dtype)
        for t in range(1, self.ntiles):
            tj, ti = self.tiles[t]
            out[t] = a[tj * TILE : (tj + 1) * TILE, ti * TILE : (ti + 1) * TILE]
        return out

    def from_tiles(self, a: np.ndarray, fill: float = 0.0) -> np.ndarray:
        """Paste (ntiles, TILE, TILE) back into a (ny, nx) grid."""
        ny, nx = self.shape
        out = np.full((ny, nx) + a.shape[3:], fill, dtype=a.dtype)
        for t in range(1, self.ntiles):
            tj, ti = self.tiles[t]
            out[tj * TILE : (tj + 1) * TILE, ti * TILE : (ti + 1) * TILE] = a[t]
        return out
