"""build_tables: bed source + grid + terrain edits -> every static array the solver reads.

Absolute elevations stop here. The solver sees only heights over a cell's lowest point and over the face invert,
so float32 keeps its resolution at any datum.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from wadi2d.config.constants import CRITICAL_WEIR_COEFF
from wadi2d.config.schema import Tables
from wadi2d.grid.tiles import TileGrid
from wadi2d.solver.layout import CLOSED, TILE
from wadi2d.tables.core import tile_tables


class BedSource(Protocol):
    """Anything that returns bed pixels for a grid-aligned window."""

    pixel: float

    def read(self, row0: int, col0: int, nrows: int, ncols: int) -> np.ndarray:
        """Bed pixels, float64, ``row0`` and ``col0`` counted from the grid origin (may be negative)."""
        ...


@dataclass
class ArrayBed:
    """A bed already in memory, with pixels aligned to the grid origin."""

    z: np.ndarray
    pixel: float
    row_offset: int = 0
    col_offset: int = 0

    def read(self, row0: int, col0: int, nrows: int, ncols: int) -> np.ndarray:
        r = np.clip(np.arange(row0, row0 + nrows) + self.row_offset, 0, self.z.shape[0] - 1)
        c = np.clip(np.arange(col0, col0 + ncols) + self.col_offset, 0, self.z.shape[1] - 1)
        return self.z[np.ix_(r, c)].astype(np.float64)


@dataclass
class CrestFaces:
    """Faces edited by terrain objects, as (ny, nx) grids; NaN means untouched. A wall face is closed."""

    xz: np.ndarray
    xlen: np.ndarray
    xc: np.ndarray
    yz: np.ndarray
    ylen: np.ndarray
    yc: np.ndarray
    xwall: np.ndarray | None = None
    ywall: np.ndarray | None = None

    @classmethod
    def empty(cls, shape: tuple[int, int]) -> CrestFaces:
        nan = np.full(shape, np.nan)
        one = np.ones(shape)
        zero = np.zeros(shape)
        return cls(nan.copy(), one.copy(), zero.copy(), nan.copy(), one.copy(), zero.copy())


@dataclass
class GridTables:
    """Everything static. Tile arrays are (ntiles, TILE, TILE, ...); suffix x is west faces, y north faces."""

    grid: TileGrid
    zmin: np.ndarray
    zbar: np.ndarray
    hc: np.ndarray
    dtab: np.ndarray
    flx: np.ndarray
    frx: np.ndarray
    glx: np.ndarray
    grx: np.ndarray
    efx: np.ndarray
    cwx: np.ndarray
    ftabx: np.ndarray
    fly: np.ndarray
    fry: np.ndarray
    gly: np.ndarray
    gry: np.ndarray
    efy: np.ndarray
    cwy: np.ndarray
    ftaby: np.ndarray

    @property
    def rows(self) -> int:
        return self.dtab.shape[-1]


def build_tables(
    grid: TileGrid,
    bed: BedSource,
    cfg: Tables,
    manning: float | np.ndarray = 0.035,
    crest: CrestFaces | None = None,
    edit=None,
    lining=None,
) -> GridTables:
    """Build all tables. ``manning`` is one value or a (ny, nx) grid; ``edit(z, row0, col0)`` edits pixels in place.

    ``lining(z, n, row0, col0)`` writes a Manning n per pixel into ``n``, which starts as NaN, after the edits.
    """
    k = round(grid.dx / bed.pixel)
    if abs(k * bed.pixel - grid.dx) > 1e-6 * grid.dx:
        raise ValueError(f"cell size {grid.dx} is not a multiple of the pixel {bed.pixel}")
    ny, nx = grid.shape
    crest = crest or CrestFaces.empty((ny, nx))
    nman = (
        np.full((ny, nx), float(manning)) if np.isscalar(manning) else np.asarray(manning, dtype=np.float64)
    )
    nt, rows = grid.ntiles, cfg.rows

    zmin_g = np.zeros((ny, nx))
    rel_g = np.zeros((ny, nx))
    zfx_g = np.zeros((ny, nx))
    zfy_g = np.zeros((ny, nx))
    hc = np.zeros((nt, TILE, TILE), np.float32)
    dtab = np.zeros((nt, TILE, TILE, rows), np.float32)
    efx = np.ones((nt, TILE, TILE), np.float32)
    efy = np.ones((nt, TILE, TILE), np.float32)
    ftabx = np.zeros((nt, TILE, TILE, rows, 2), np.float32)
    ftaby = np.zeros((nt, TILE, TILE, rows, 2), np.float32)

    # per tile scratch in float64; the solver's float32 is taken at the very end
    w_zmin, w_rel, w_hc = (np.zeros((TILE, TILE)) for _ in range(3))
    w_dtab = np.zeros((TILE, TILE, rows))
    w_zfx, w_efx, w_zfy, w_efy = (np.zeros((TILE, TILE)) for _ in range(4))
    w_ftabx = np.zeros((TILE, TILE, rows, 2))
    w_ftaby = np.zeros((TILE, TILE, rows, 2))
    npix = np.full((1, 1), np.nan)
    for t in range(1, nt):
        tj, ti = grid.tiles[t]
        j0, i0 = int(tj) * TILE, int(ti) * TILE
        z = bed.read(j0 * k - 1, i0 * k - 1, TILE * k + 1, TILE * k + 1)
        if edit is not None:
            edit(z, j0 * k - 1, i0 * k - 1)
        if lining is not None:
            npix = np.full(z.shape, np.nan)
            lining(z, npix, j0 * k - 1, i0 * k - 1)
        sl = (slice(j0, j0 + TILE), slice(i0, i0 + TILE))
        tile_tables(
            z, k, TILE, bed.pixel, nman[sl], npix,
            crest.xz[sl], crest.xlen[sl], crest.yz[sl], crest.ylen[sl],
            cfg.face_depth_min, cfg.face_depth_max,
            w_zmin, w_rel, w_hc, w_dtab, w_zfx, w_efx, w_ftabx, w_zfy, w_efy, w_ftaby,
        )  # fmt: skip
        zmin_g[sl], rel_g[sl], zfx_g[sl], zfy_g[sl] = w_zmin, w_rel, w_zfx, w_zfy
        hc[t], dtab[t], efx[t], efy[t], ftabx[t], ftaby[t] = w_hc, w_dtab, w_efx, w_efy, w_ftabx, w_ftaby

    zbar_g = zmin_g + rel_g
    active = grid.mask
    fx = _faces(zfx_g, zmin_g, zbar_g, active, 1, crest.xc, cfg.crest_tolerance, crest.xwall)
    fy = _faces(zfy_g, zmin_g, zbar_g, active, 0, crest.yc, cfg.crest_tolerance, crest.ywall)
    return GridTables(
        grid, zmin_g, zbar_g, hc, dtab,
        *(grid.to_tiles(a) for a in fx[:4]), efx, grid.to_tiles(fx[4]), ftabx,
        *(grid.to_tiles(a) for a in fy[:4]), efy, grid.to_tiles(fy[4]), ftaby,
    )  # fmt: skip


def _faces(zf, zmin, zbar, active, axis, crest_c, tol, wall=None):
    """Invert over zmin and over the mean bed on both sides; closed faces; natural crests.

    ``axis`` 1: x faces, the neighbour is (j, i-1). ``axis`` 0: y faces, the neighbour is (j-1, i).
    """
    zmin_n = np.roll(zmin, 1, axis=axis)
    zbar_n = np.roll(zbar, 1, axis=axis)
    act_n = np.roll(active, 1, axis=axis)
    open_face = active & act_n
    if wall is not None:
        open_face = open_face & ~wall
    fl = np.where(open_face, zf - zmin_n, CLOSED)
    fr = np.where(open_face, zf - zmin, CLOSED)
    gl = np.where(open_face, zf - zbar_n, 0.0)
    gr = np.where(open_face, zf - zbar, 0.0)
    natural = open_face & (gl > tol) & (gr > tol)
    cw = np.where(crest_c > 0.0, crest_c, np.where(natural, CRITICAL_WEIR_COEFF, 0.0))
    cw = np.where(open_face, cw, 0.0)
    return fl, fr, gl, gr, cw


def hbar_at_level(
    level: float | np.ndarray, zmin: np.ndarray, hc: np.ndarray, dtab: np.ndarray
) -> np.ndarray:
    """Mean depth that gives exactly this level through the table (the inverse of the solver's lookup)."""
    rows = dtab.shape[-1]
    last = rows - 1
    d = np.maximum(np.asarray(level, dtype=np.float64) - zmin, 0.0)
    out = np.where(hc <= 0.0, d, 0.0)
    top = dtab[..., last]
    above = (hc > 0.0) & (d >= top)
    out = np.where(above, hc + (d - top), out)
    inside = (hc > 0.0) & (d < top) & (d > 0.0)
    if inside.any():
        di = d[inside]
        tab = dtab[inside]
        r = np.clip(np.sum(tab <= di[:, None], axis=1) - 1, 0, last - 1)
        idx = np.arange(tab.shape[0])
        lo, hi = tab[idx, r], tab[idx, r + 1]
        s = r + (di - lo) / np.maximum(hi - lo, 1e-30)
        out[inside] = hc[inside] * (s / last) ** 2
    return out
