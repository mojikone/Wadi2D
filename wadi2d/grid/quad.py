"""QuadGrid: block-uniform quadtree. Each tile keeps 32 x 32 cells of one size; neighbours differ by at most 2:1.

Positions count in the *lattice*: squares of 32 finest cells. A tile of level ``s`` has cells 2^s finest cells wide and
covers 2^s x 2^s lattice squares, aligned to its own size. The grid answers like a ``TileGrid`` where the rest of the
engine asks: rasters are at the finest cell size, and a coarse cell paints all the finest cells it covers.

An *interface* is a side of a fine tile that faces a coarser tile. Its 32 fine faces are the only faces there; the coarse
tile's faces on that side are closed and take the sum of the two fine faces beside each. A row of ``interfaces`` is
(fine tile, side of the fine tile, coarse tile, number, offset, table id of its first face, step of the table id). Sides:
0 west, 1 north, 2 east, 3 south. ``offset`` is the coarse cell the fine side starts at, along the coarse side.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from wadi2d.solver.layout import HALO, STRIDE, STRIDE2, TILE, TILE2

ACTIVE_SHARE = 0.5
"""A coarse cell is in the domain when at least this share of the finest cells under it are."""
SIDES = ((0, -1), (-1, 0), (0, 1), (1, 0))
"""(row, column) step of each side."""
MAX_NEIGHBOURS = 12
"""Two along each side and four corners, for a tile with finer neighbours everywhere."""


def balance(level: np.ndarray, top: int) -> np.ndarray:
    """The coarsest levels at or under ``level`` that are aligned blocks, 2:1 across every side and corner."""
    out = level.copy()
    while True:
        before = out.copy()
        for s in range(top, 0, -1):
            size = 1 << s
            for j in range(0, out.shape[0], size):
                for i in range(0, out.shape[1], size):
                    block = out[j : j + size, i : i + size]
                    if block.max() >= s and block.min() < s:
                        block[block >= s] = s - 1
        pad = np.pad(out, 1, mode="edge")
        lowest = np.min(
            [pad[1 + a : pad.shape[0] - 1 + a or None, 1 + b : pad.shape[1] - 1 + b or None]
             for a in (-1, 0, 1) for b in (-1, 0, 1)],
            axis=0,
        )  # fmt: skip
        out = np.minimum(out, lowest + 1)
        if np.array_equal(out, before):
            return out


@dataclass
class QuadGrid:
    """Built by ``from_levels``. ``level`` is per compact tile; entry 0 is the void tile."""

    x0: float
    y0: float
    dx: float
    mask: np.ndarray
    tiles: np.ndarray
    level: np.ndarray
    tile_of: np.ndarray
    cells: np.ndarray
    """(ntiles, TILE, TILE) True on active cells."""
    nbr: np.ndarray = field(init=False)
    """(ntiles, MAX_NEIGHBOURS) ids of the tiles that touch, padded with the void tile."""
    same: np.ndarray = field(init=False)
    """(ntiles, 4) the neighbour of the same cell size on each side, else the void tile."""
    interfaces: np.ndarray = field(init=False)
    pseudo: int = field(init=False)
    """Extra table tiles, holding the faces of east and south interfaces."""

    quad = True

    def __post_init__(self) -> None:
        self._links()

    @classmethod
    def from_levels(cls, mask: np.ndarray, x0: float, y0: float, dx: float, level: np.ndarray) -> QuadGrid:
        """``mask`` is on the finest cells, whole lattice squares; ``level`` the wanted level per lattice square."""
        ny, nx = mask.shape
        top = int(level.max())
        side = TILE << top
        if ny % side or nx % side:
            raise ValueError(f"mask shape must be a multiple of {side}; use pad_to_lattice")
        wanted = balance(level.astype(np.int32), top)
        nty, ntx = ny // TILE, nx // TILE
        rows, levels, stamps = [], [], []
        tile_of = np.zeros((nty, ntx), np.int32)
        out_mask = np.zeros_like(mask)
        for s in range(top + 1):
            size = 1 << s
            for tj, ti in np.argwhere((wanted == s) & _aligned(wanted.shape, size)):
                y, x = tj * TILE, ti * TILE
                block = mask[y : y + TILE * size, x : x + TILE * size]
                share = block.reshape(TILE, size, TILE, size).mean(axis=(1, 3))
                on = share >= ACTIVE_SHARE
                if on.any():
                    rows.append((tj, ti))
                    levels.append(s)
                    stamps.append(on)
                    tile_of[tj : tj + size, ti : ti + size] = len(rows)
                    out_mask[y : y + TILE * size, x : x + TILE * size] = np.kron(
                        on, np.ones((size, size), bool)
                    )
        tiles = np.vstack([np.array([[-1, -1]], np.int32), np.array(rows, np.int32).reshape(-1, 2)])
        cells = np.zeros((tiles.shape[0], TILE, TILE), bool)
        cells[1:] = np.array(stamps).reshape(-1, TILE, TILE)
        return cls(x0, y0, dx, out_mask, tiles, np.array([0, *levels], np.int32), tile_of, cells)

    def _links(self) -> None:
        n = self.ntiles
        self.nbr = np.zeros((n, MAX_NEIGHBOURS), np.int32)
        self.same = np.zeros((n, 4), np.int32)
        nty, ntx = self.tile_of.shape
        rows: list[list[int]] = []
        for t in range(1, n):
            tj, ti = int(self.tiles[t, 0]), int(self.tiles[t, 1])
            s = int(self.level[t])
            size = 1 << s
            around: set[int] = set()
            for j in range(tj - 1, tj + size + 1):
                for i in range(ti - 1, ti + size + 1):
                    if 0 <= j < nty and 0 <= i < ntx and self.tile_of[j, i] not in (0, t):
                        around.add(int(self.tile_of[j, i]))
            self.nbr[t, : len(around)] = sorted(around)
            for side, (dj, di) in enumerate(SIDES):
                j2 = tj + (dj if dj < 0 else size * dj)
                i2 = ti + (di if di < 0 else size * di)
                if not (0 <= j2 < nty and 0 <= i2 < ntx):
                    continue
                other = int(self.tile_of[j2, i2])
                if other == 0:
                    continue
                if self.level[other] == s:
                    self.same[t, side] = other
                elif self.level[other] == s + 1:
                    along = (tj - self.tiles[other, 0]) if di else (ti - self.tiles[other, 1])
                    rows.append([t, side, other, len(rows), int(along) * (TILE >> (s + 1)), 0, 0])
        self.interfaces = np.array(rows, np.int32).reshape(-1, 7)
        self._table_ids()

    def _table_ids(self) -> None:
        """West and north interfaces use the fine tile's own table slots; east and south ones have no slot, so they
        take strips in extra table tiles after the real ones."""
        rows = self.interfaces
        spare = 0
        for r in range(rows.shape[0]):
            t, side = rows[r, 0], rows[r, 1]
            if side == 0:
                rows[r, 5], rows[r, 6] = t * TILE2, TILE
            elif side == 1:
                rows[r, 5], rows[r, 6] = t * TILE2, 1
            else:
                rows[r, 5], rows[r, 6] = (self.ntiles + spare // TILE) * TILE2 + (spare % TILE) * TILE, 1
                spare += 1
        self.pseudo = int(np.ceil(spare / TILE))

    @property
    def ntiles(self) -> int:
        return self.tiles.shape[0]

    @property
    def shape(self) -> tuple[int, int]:
        return self.mask.shape

    @property
    def tile_scale(self) -> np.ndarray:
        """Finest cells per cell, per tile."""
        return 1 << self.level

    @property
    def tile_dx(self) -> np.ndarray:
        return self.dx * (1 << self.level).astype(np.float64)

    @property
    def cell_count(self) -> int:
        return int(self.cells.sum())

    def cell_of(self, x: float, y: float) -> tuple[int, int]:
        """Raster (row, column) of a point."""
        return int((self.y0 - y) // self.dx), int((x - self.x0) // self.dx)

    def xy_of(self, j: np.ndarray, i: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Centre coordinates of raster cells."""
        return self.x0 + (i + 0.5) * self.dx, self.y0 - (j + 0.5) * self.dx

    def locate_raster(self, j: np.ndarray, i: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(tile, own row, own column) of raster cells."""
        t = self.tile_of[np.asarray(j) // TILE, np.asarray(i) // TILE]
        scale = self.tile_scale[t]
        tj, ti = self.tiles[t, 0], self.tiles[t, 1]
        return t, (j - tj * TILE) // scale, (i - ti * TILE) // scale

    def state_index(self, j: np.ndarray, i: np.ndarray) -> np.ndarray:
        """State index of the cell that covers raster cells; a coarse cell answers for all of them."""
        t, oj, oi = self.locate_raster(j, i)
        return t * STRIDE2 + (oj + HALO) * STRIDE + oi + HALO

    def cells_of(self, chosen: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """The cells under a raster selection: (rows, columns, state indices, areas in m2).

        A cell's row and column are the raster cell at its centre, so a polygon or a raster sampled there reads the cell
        and not its north-west corner.
        """
        jj, ii = np.nonzero(chosen)
        index = np.asarray(self.state_index(jj, ii), np.int64)
        unique, first = np.unique(index, return_index=True)
        tiles = unique // STRIDE2
        half = self.tile_scale[tiles] // 2
        t, oj, oi = self.locate_raster(jj[first], ii[first])
        scale = self.tile_scale[t]
        rows = self.tiles[t, 0] * TILE + oj * scale + half
        cols = self.tiles[t, 1] * TILE + oi * scale + half
        return rows, cols, unique, self.tile_dx[tiles] ** 2

    def from_tiles(self, a: np.ndarray, fill: float = 0.0) -> np.ndarray:
        """Paint (ntiles, TILE, TILE, ...) onto the finest raster."""
        ny, nx = self.shape
        out = np.full((ny, nx) + a.shape[3:], fill, dtype=a.dtype)
        for t in range(1, self.ntiles):
            size = 1 << int(self.level[t])
            y, x = self.tiles[t, 0] * TILE, self.tiles[t, 1] * TILE
            out[y : y + TILE * size, x : x + TILE * size] = np.repeat(
                np.repeat(a[t], size, axis=0), size, axis=1
            )
        return out

    def to_tiles(self, a: np.ndarray, dtype=np.float32) -> np.ndarray:
        """Mean of the raster over each cell, as (ntiles, TILE, TILE)."""
        out = np.zeros((self.ntiles, TILE, TILE), dtype=dtype)
        for t in range(1, self.ntiles):
            size = 1 << int(self.level[t])
            y, x = self.tiles[t, 0] * TILE, self.tiles[t, 1] * TILE
            block = a[y : y + TILE * size, x : x + TILE * size]
            out[t] = block.reshape(TILE, size, TILE, size).mean(axis=(1, 3))
        return out

    def cell_areas(self) -> np.ndarray:
        """Area of a cell in each tile, m2."""
        return self.tile_dx**2


@dataclass
class LatticeView:
    """The finest tiles under a QuadGrid, for what walks tiles of one size: a coarse tile is several of them."""

    x0: float
    y0: float
    dx: float
    shape: tuple[int, int]
    tiles: np.ndarray

    @property
    def ntiles(self) -> int:
        return self.tiles.shape[0]


def lattice_view(grid: QuadGrid) -> LatticeView:
    rows = [[-1, -1]]
    for t in range(1, grid.ntiles):
        size = 1 << int(grid.level[t])
        tj, ti = int(grid.tiles[t, 0]), int(grid.tiles[t, 1])
        rows += [[tj + a, ti + b] for a in range(size) for b in range(size)]
    return LatticeView(grid.x0, grid.y0, grid.dx, grid.shape, np.array(rows, np.int32))


def _aligned(shape: tuple[int, int], size: int) -> np.ndarray:
    rows = np.arange(shape[0]) % size == 0
    cols = np.arange(shape[1]) % size == 0
    return rows[:, None] & cols[None, :]


def pad_to_lattice(mask: np.ndarray, top: int) -> tuple[np.ndarray, int, int]:
    """Pad ``mask`` to whole squares of the coarsest tile, with one cell of margin. Returns (mask, rows, columns) added."""
    side = TILE << top
    ny, nx = mask.shape
    nyp = int(np.ceil((ny + 2) / side)) * side
    nxp = int(np.ceil((nx + 2) / side)) * side
    out = np.zeros((nyp, nxp), bool)
    out[1 : 1 + ny, 1 : 1 + nx] = mask
    return out, 1, 1


def halo_maps(grid: QuadGrid) -> dict[str, np.ndarray]:
    """Where each halo slot of each tile reads, per kind of value.

    ``cell`` is for values held at cell centres, ``u`` and ``v`` for values on west and north faces, ``qu`` and ``qv`` the
    factor on a discharge read through the same slots: a coarse face is two fine faces wide. A slot that holds the
    tile's own interface face reads itself. All are (ntiles - 1, nhalo).
    """
    jj, ii = np.meshgrid(np.arange(STRIDE), np.arange(STRIDE), indexing="ij")
    own = (jj >= HALO) & (jj < HALO + TILE) & (ii >= HALO) & (ii < HALO + TILE)
    hj, hi = jj[~own], ii[~own]
    slot = (hj * STRIDE + hi).astype(np.int32)
    n = grid.ntiles - 1
    shape = (n, slot.size)
    cell, u, v = (np.zeros(shape, np.int32) for _ in range(3))
    qu, qv = np.ones(shape, np.float32), np.ones(shape, np.float32)
    nty, ntx = grid.tile_of.shape
    held = {(int(t), int(s)) for t, s in grid.interfaces[:, :2]}
    coarse_held = {(int(c), int(s) ^ 2) for s, c in grid.interfaces[:, 1:3]}

    def lookup(y: np.ndarray, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """(tile, own row, own column, tile's scale) at raster position (y, x), void off the grid."""
        off = (y < 0) | (x < 0) | (y >= nty * TILE) | (x >= ntx * TILE)
        tile = np.where(
            off, 0, grid.tile_of[np.clip(y, 0, nty * TILE - 1) // TILE, np.clip(x, 0, ntx * TILE - 1) // TILE]
        )
        scale = grid.tile_scale[tile]
        oj = (y - grid.tiles[tile, 0] * TILE) // scale
        oi = (x - grid.tiles[tile, 1] * TILE) // scale
        return tile, oj, oi, scale

    for t in range(1, grid.ntiles):
        size = 1 << int(grid.level[t])
        y0, x0 = int(grid.tiles[t, 0]) * TILE, int(grid.tiles[t, 1]) * TILE
        rj, ri = hj - HALO, hi - HALO
        ycell, xcell = y0 + rj * size + size // 2, x0 + ri * size + size // 2
        y_w, x_w = ycell, x0 + ri * size
        y_n, x_n = y0 + rj * size, xcell
        base = t * STRIDE2
        for kind, (y, x) in enumerate(((ycell, xcell), (y_w, x_w), (y_n, x_n))):
            tile, oj, oi, scale = lookup(y, x)
            src = tile * STRIDE2 + (oj + HALO) * STRIDE + oi + HALO
            src = np.where(tile == 0, 0, src)
            ratio = (size / scale).astype(np.float32)
            if kind == 0:
                cell[t - 1] = src
            elif kind == 1:
                u[t - 1], qu[t - 1] = src, ratio
            else:
                v[t - 1], qv[t - 1] = src, ratio
        for side, axis, last in ((2, "u", ri == TILE), (3, "v", rj == TILE)):
            if (t, side) in held or (t, side) in coarse_held:
                along = (rj >= 0) & (rj < TILE) if axis == "u" else (ri >= 0) & (ri < TILE)
                pick = last & along
                target = u if axis == "u" else v
                factor = qu if axis == "u" else qv
                target[t - 1, pick] = base + slot[pick]
                factor[t - 1, pick] = 1.0
    return {"slot": slot, "cell": cell, "u": u, "v": v, "qu": qu, "qv": qv}


__all__ = ["ACTIVE_SHARE", "QuadGrid", "balance", "halo_maps", "pad_to_lattice"]
