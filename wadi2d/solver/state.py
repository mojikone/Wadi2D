"""Host-side state: allocation, conversion between grid and tile-with-halo arrays, neighbour exchange maps."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from wadi2d.grid.tiles import TileGrid
from wadi2d.solver.layout import HALO, STATE_ARRAYS, STRIDE, STRIDE2, TILE, WORK_ARRAYS, local_index
from wadi2d.tables.builder import GridTables


def exchange_map(grid: TileGrid) -> tuple[np.ndarray, np.ndarray]:
    """(dst, src) index pairs that fill every tile's halo from the owning tile; both int32.

    Destination is a halo entry of tile t, source the own entry of the neighbour that holds the same cell. Tile
    0 is never a destination. A missing neighbour resolves to the void tile, whose entries stay zero.
    """
    nt = grid.ntiles
    if nt <= 1:
        return np.zeros(0, np.int32), np.zeros(0, np.int32)
    # offsets inside one tile: every halo position, and which neighbour holds it
    jj, ii = np.meshgrid(np.arange(STRIDE), np.arange(STRIDE), indexing="ij")
    own_j = (jj >= HALO) & (jj < HALO + TILE)
    own_i = (ii >= HALO) & (ii < HALO + TILE)
    halo = ~(own_j & own_i)
    hj, hi = jj[halo], ii[halo]
    dj = np.where(hj < HALO, -1, np.where(hj >= HALO + TILE, 1, 0))
    di = np.where(hi < HALO, -1, np.where(hi >= HALO + TILE, 1, 0))
    # own coordinates of the same cell in the neighbour
    sj = hj - dj * TILE
    si = hi - di * TILE
    from wadi2d.grid.tiles import NEIGHBOURS

    lookup = {d: n for n, d in enumerate(NEIGHBOURS)}
    nidx = np.array([lookup[(int(a), int(b))] for a, b in zip(dj, di, strict=True)])
    tiles = np.arange(1, nt)
    src_tile = grid.nbr[tiles][:, nidx]  # (nt-1, nhalo)
    dst = (tiles[:, None] * STRIDE2 + hj * STRIDE + hi).astype(np.int64)
    src = (src_tile * STRIDE2 + sj * STRIDE + si).astype(np.int64)
    return dst.ravel().astype(np.int32), src.ravel().astype(np.int32)


def own_slice() -> tuple[slice, slice]:
    return slice(HALO, HALO + TILE), slice(HALO, HALO + TILE)


@dataclass
class HostState:
    """State arrays on the host, tile-major with halos: (ntiles * STRIDE2,)."""

    grid: TileGrid
    arrays: dict[str, np.ndarray]

    @classmethod
    def allocate(cls, grid: TileGrid) -> HostState:
        n = grid.ntiles * STRIDE2
        return cls(grid, {a: np.zeros(n, np.float32) for a in STATE_ARRAYS + WORK_ARRAYS})

    def set_field(self, name: str, a: np.ndarray) -> None:
        """Write a (ny, nx) field into own cells and halos."""
        self.arrays[name][:] = self.to_state(a)

    def to_state(self, a: np.ndarray) -> np.ndarray:
        grid = self.grid
        out = np.zeros(grid.ntiles * STRIDE2, np.float32)
        ny, nx = grid.shape
        for t in range(1, grid.ntiles):
            tj, ti = grid.tiles[t]
            r = np.clip(np.arange(STRIDE) - HALO + tj * TILE, 0, ny - 1)
            c = np.clip(np.arange(STRIDE) - HALO + ti * TILE, 0, nx - 1)
            out[t * STRIDE2 : (t + 1) * STRIDE2] = a[np.ix_(r, c)].ravel()
        return out

    def field(self, name: str) -> np.ndarray:
        """A state array as a (ny, nx) grid."""
        return from_state(self.grid, self.arrays[name])


def from_state(grid: TileGrid, a: np.ndarray) -> np.ndarray:
    """Own cells of a tile-major array as a (ny, nx) grid."""
    ny, nx = grid.shape
    out = np.zeros((ny, nx), a.dtype)
    sj, si = own_slice()
    for t in range(1, grid.ntiles):
        tj, ti = grid.tiles[t]
        blk = a[t * STRIDE2 : (t + 1) * STRIDE2].reshape(STRIDE, STRIDE)[sj, si]
        out[tj * TILE : (tj + 1) * TILE, ti * TILE : (ti + 1) * TILE] = blk
    return out


def state_index(grid: TileGrid, j: np.ndarray, i: np.ndarray) -> np.ndarray:
    """State-array index of grid cells (own entries)."""
    tile = grid.tile_of[j // TILE, i // TILE]
    return local_index(tile, j % TILE + HALO, i % TILE + HALO)


def level_field(tables: GridTables, h: np.ndarray) -> np.ndarray:
    """Level above zmin for a (ny, nx) mean depth; float64 reference of the solver's lookup."""
    grid = tables.grid
    hc = grid.from_tiles(tables.hc)
    dtab = grid.from_tiles(tables.dtab)
    last = dtab.shape[-1] - 1
    out = np.array(h, dtype=np.float64)
    wet = hc > 0.0
    above = wet & (h >= hc)
    out[above] = dtab[above, last] + (h[above] - hc[above])
    mid = wet & ~above
    s = np.sqrt(h[mid] / hc[mid]) * last
    r = np.minimum(s.astype(int), last - 1)
    idx = np.arange(r.size)
    t = dtab[mid]
    out[mid] = t[idx, r] + (s - r) * (t[idx, r + 1] - t[idx, r])
    return out


def plan_field(tables: GridTables, h: np.ndarray) -> np.ndarray:
    """Wet share of the cell plan for a (ny, nx) mean depth; what the kernels call ``om``."""
    grid = tables.grid
    hc = grid.from_tiles(tables.hc)
    dtab = grid.from_tiles(tables.dtab)
    last = dtab.shape[-1] - 1
    out = np.ones(h.shape, np.float64)
    mid = (hc > 0.0) & (h < hc)
    s = np.sqrt(h[mid] / hc[mid]) * last
    r = np.minimum(s.astype(int), last - 1)
    idx = np.arange(r.size)
    t = dtab[mid]
    out[mid] = hc[mid] * (2 * r + 1) / last**2 / np.maximum(t[idx, r + 1] - t[idx, r], 1e-12)
    return out
