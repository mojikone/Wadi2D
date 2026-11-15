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
from wadi2d.tables.core import (
    centre_beds,
    tile_local_radius,
    tile_local_radius_serial,
    tile_tables,
    tile_tables_serial,
)
from wadi2d.tables.parallel import ThreadBeds, run_all, table_workers


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
        return np.asarray(self.z[np.ix_(r, c)], dtype=np.float64)  # the indexed block is already its own copy

    @property
    def span(self) -> int:
        """Pixels along the bed's longer side. A face's line that reaches this far past its ends has passed every
        pixel the bed holds; whatever lies further is a repeat of its edge pixel."""
        return int(max(self.z.shape))

    def levels(self) -> tuple[float, float]:
        return float(self.z.min()), float(self.z.max())


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
    zcx: np.ndarray
    """The bed on each cell's centre line across x, above the cell's lowest pixel (W47): an x face reads its section
    at the upwind cell's depth over this bed, carried to the face. Zero on a cell of one pixel."""
    zcy: np.ndarray
    """The same on the centre line across y, for y faces."""

    @property
    def rows(self) -> int:
        return self.dtab.shape[-1]


@dataclass
class RawFaces:
    """What a fresh build knows before it closes the faces (W91), per cell on the grid, float64: the mean bed over the
    lowest pixel, the absolute face inverts of the west and north faces, and the centre-line beds over the lowest
    pixel before they are clamped. A table read from the cache has none: only a build carries it, so a rebuild of a
    few tiles (``build_tables(base=...)``) can close every face again exactly as a whole build does."""

    rel: np.ndarray
    zfx: np.ndarray
    zfy: np.ndarray
    zcx: np.ndarray
    zcy: np.ndarray


def build_tables(
    grid: TileGrid,
    bed: BedSource,
    cfg: Tables,
    manning: float | np.ndarray = 0.035,
    crest: CrestFaces | None = None,
    edit=None,
    lining=None,
    workers: int | None = None,
    base: GridTables | None = None,
    only=None,
    keep_raw: bool = False,
) -> GridTables:
    """Build all tables. ``manning`` is one value or a (ny, nx) grid; ``edit(z, row0, col0)`` edits pixels in place.

    ``lining(z, n, row0, col0)`` writes a Manning n per pixel into ``n``, which starts as NaN, after the edits.
    ``workers`` threads build the tiles (``table_workers``: all physical cores unless told), each tile into its own
    slots, so the tables do not depend on it (W81). ``edit`` and ``lining`` are called from those threads.

    ``base`` and ``only`` rebuild the tiles ``only`` and take every other tile's slots from ``base`` (W91: the pit
    fills touch a few tiles of thousands): ``base`` must be a fresh build (it carries :class:`RawFaces`) of the same grid
    whose other tiles these arguments would give unchanged. The faces are then closed on the whole grid as a whole
    build closes them, so the result is the whole build's to the digit. ``keep_raw`` keeps those on the result as
    ``raw`` (five arrays of the grid's size), for a rebuild to follow; else ``raw`` is None.
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

    if base is None:
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
        zcx_g = np.zeros((ny, nx))
        zcy_g = np.zeros((ny, nx))
        todo = range(1, nt)
    else:
        raw = getattr(base, "raw", None)
        if raw is None:
            raise ValueError("a partial rebuild needs base tables from a build that kept its raw faces")
        if base.grid.shape != grid.shape or base.rows != rows or not np.array_equal(base.grid.mask, grid.mask):
            raise ValueError("a partial rebuild needs the base tables of the same grid and table rows")
        zmin_g = base.zmin.copy()
        rel_g, zfx_g, zfy_g, zcx_g, zcy_g = (a.copy() for a in (raw.rel, raw.zfx, raw.zfy, raw.zcx, raw.zcy))
        hc, dtab, efx, efy, ftabx, ftaby = (
            a.copy() for a in (base.hc, base.dtab, base.efx, base.efy, base.ftabx, base.ftaby)
        )
        todo = sorted(int(t) for t in only)

    local = cfg.face_conveyance == "local_radius"
    margin = tile_margin(cfg, bed)
    threads = table_workers(workers)
    cells, radius = (tile_tables_serial, tile_local_radius_serial) if threads > 1 else (tile_tables, tile_local_radius)
    beds = ThreadBeds(bed)

    def one(t: int) -> None:
        """Tile ``t``'s tables, into its own slots (W81: tiles run on threads, each on its own handle of the bed)."""
        src = beds.get()
        # per tile scratch in float64; the solver's float32 is taken at the very end
        w_zmin, w_rel, w_hc = (np.zeros((TILE, TILE)) for _ in range(3))
        w_dtab = np.zeros((TILE, TILE, rows))
        w_zfx, w_efx, w_zfy, w_efy = (np.zeros((TILE, TILE)) for _ in range(4))
        w_ftabx = np.zeros((TILE, TILE, rows, 2))
        w_ftaby = np.zeros((TILE, TILE, rows, 2))
        npix = np.full((1, 1), np.nan)
        tj, ti = grid.tiles[t]
        j0, i0 = int(tj) * TILE, int(ti) * TILE
        if local:
            zbig = src.read(j0 * k - 1 - margin, i0 * k - 1 - margin, TILE * k + 1 + 2 * margin, TILE * k + 1 + 2 * margin)
            if edit is not None:
                edit(zbig, j0 * k - 1 - margin, i0 * k - 1 - margin)
            z = np.ascontiguousarray(zbig[margin : margin + TILE * k + 1, margin : margin + TILE * k + 1])
        else:
            z = src.read(j0 * k - 1, i0 * k - 1, TILE * k + 1, TILE * k + 1)
            if edit is not None:
                edit(z, j0 * k - 1, i0 * k - 1)
        if lining is not None:
            npix = np.full(z.shape, np.nan)
            lining(z, npix, j0 * k - 1, i0 * k - 1)
        sl = (slice(j0, j0 + TILE), slice(i0, i0 + TILE))
        cells(
            z, k, TILE, bed.pixel, nman[sl], npix,
            crest.xz[sl], crest.xlen[sl], crest.yz[sl], crest.ylen[sl],
            cfg.face_depth_min, cfg.face_depth_max,
            w_zmin, w_rel, w_hc, w_dtab, w_zfx, w_efx, w_ftabx, w_zfy, w_efy, w_ftaby,
        )  # fmt: skip
        if local:
            radius(
                zbig, margin, k, TILE, bed.pixel, nman[sl], npix, crest.xz[sl], crest.xlen[sl], crest.yz[sl], crest.ylen[sl],
                w_zfx, w_efx, w_ftabx, w_zfy, w_efy, w_ftaby, cfg.local_radius_beta, cfg.face_depth_max,
            )  # fmt: skip
        zmin_g[sl], rel_g[sl], zfx_g[sl], zfy_g[sl] = w_zmin, w_rel, w_zfx, w_zfy
        cx_bed, cy_bed = centre_beds(z, k, TILE)
        zcx_g[sl], zcy_g[sl] = cx_bed - w_zmin, cy_bed - w_zmin
        hc[t], dtab[t], efx[t], efy[t], ftabx[t], ftaby[t] = w_hc, w_dtab, w_efx, w_efy, w_ftabx, w_ftaby

    try:
        run_all(todo, one, threads)
    finally:
        beds.close()

    raw = RawFaces(rel_g, zfx_g, zfy_g, zcx_g, zcy_g)
    zbar_g = zmin_g + rel_g
    active = grid.mask
    zcx_g, zcy_g = (np.nan_to_num(np.maximum(a, 0.0), nan=0.0, posinf=0.0, neginf=0.0) for a in (zcx_g, zcy_g))
    fx = _faces(zfx_g, zmin_g, zbar_g, active, 1, crest.xc, cfg.crest_tolerance, crest.xwall)
    fy = _faces(zfy_g, zmin_g, zbar_g, active, 0, crest.yc, cfg.crest_tolerance, crest.ywall)
    tables = GridTables(
        grid, zmin_g, zbar_g, hc, dtab,
        *(grid.to_tiles(a) for a in fx[:4]), efx, grid.to_tiles(fx[4]), ftabx,
        *(grid.to_tiles(a) for a in fy[:4]), efy, grid.to_tiles(fy[4]), ftaby,
        grid.to_tiles(zcx_g).astype(np.float32), grid.to_tiles(zcy_g).astype(np.float32),
    )  # fmt: skip
    tables.raw = raw if keep_raw else None  # not a field: the cache neither writes nor reads it
    return tables


def tile_margin(cfg: Tables, bed: BedSource) -> int:
    """Pixels a tile's window reaches past the tile's own pixels and the one row and column before them (W49): a
    face's line runs this far past its ends for the local hydraulic radius; none for the strips sum."""
    if cfg.face_conveyance != "local_radius":
        return 0
    margin = int(np.ceil(cfg.local_radius_beta * cfg.face_depth_max / bed.pixel))
    # W85: and no further than a bed in memory is long. The reach is 144 m whatever the pixel: on a bed of 5 mm pixels
    # that was 28,800 px a side, a window of 24.8 GiB per tile for every thread, all but 4 m of it repeats of the edge
    return min(margin, getattr(bed, "span", margin))


def tiles_reading(grid: TileGrid, k: int, margin: int, boxes: np.ndarray) -> set[int]:
    """The tiles whose pixel window (as ``build_tables`` reads it, ``k`` pixels a cell and ``margin`` past the edge)
    holds a pixel of any of ``boxes``, (n, 4) rows of (row0, col0, row1, col1) in bed pixels from the grid origin,
    the ends exclusive (W91)."""
    if len(boxes) == 0:
        return set()
    b = np.asarray(boxes, np.int64)
    tj, ti = grid.tiles[1:, 0].astype(np.int64), grid.tiles[1:, 1].astype(np.int64)
    r0 = tj * TILE * k - 1 - margin
    c0 = ti * TILE * k - 1 - margin
    span = TILE * k + 1 + 2 * margin
    hit = (
        (r0[:, None] < b[None, :, 2]) & (b[None, :, 0] < (r0 + span)[:, None])
        & (c0[:, None] < b[None, :, 3]) & (b[None, :, 1] < (c0 + span)[:, None])
    )  # fmt: skip
    return {int(t) + 1 for t in np.flatnonzero(hit.any(axis=1))}


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
    cw = np.where(crest_c != 0.0, crest_c, np.where(natural, CRITICAL_WEIR_COEFF, 0.0))
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
