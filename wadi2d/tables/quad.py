"""Tables for a QuadGrid: every tile at its own cell size, from the same pixels.

A tile's own cells and faces come from ``tile_tables``, as on the uniform grid. What is new sits at tile sides. The side of
a coarse tile that faces finer tiles is closed. The side of a fine tile that faces a coarser one is 32 fine faces, each
with its own ground profile, whose inverts are measured from the coarse cell's lowest point and mean bed on that side.
East and south interface faces have no slot in the fine tile, so they live in extra table tiles after the real ones.
"""

from __future__ import annotations

import numpy as np

from wadi2d.config.constants import CRITICAL_WEIR_COEFF
from wadi2d.config.schema import Tables
from wadi2d.grid.quad import QuadGrid
from wadi2d.solver.layout import CLOSED, TILE
from wadi2d.tables.builder import BedSource, CrestFaces, GridTables
from wadi2d.tables.core import (
    _face_table,
    _lined,
    _local_radius_conveyance,
    centre_beds,
    tile_local_radius,
    tile_local_radius_serial,
    tile_tables,
    tile_tables_serial,
    window_top,
)
from wadi2d.tables.parallel import ThreadBeds, run_all, table_workers

HALF = TILE // 2


def _opening(zf, zmin_a, zbar_a, zmin_b, zbar_b, open_face, tol, crest_c=None):
    """fl, fr, gl, gr, cw of faces between side a (low) and side b (high); the formulas of ``builder._faces``."""
    fl = np.where(open_face, zf - zmin_a, CLOSED)
    fr = np.where(open_face, zf - zmin_b, CLOSED)
    gl = np.where(open_face, zf - zbar_a, 0.0)
    gr = np.where(open_face, zf - zbar_b, 0.0)
    natural = open_face & (gl > tol) & (gr > tol)
    given = np.zeros(np.shape(zf)) if crest_c is None else crest_c
    # a negative coefficient is a shaped crest, which reads the energy head: it is a crest, not an absence of one
    cw = np.where(given != 0.0, given, np.where(natural, CRITICAL_WEIR_COEFF, 0.0))
    return fl, fr, gl, gr, np.where(open_face, cw, 0.0)


def _coarse_cells(row: np.ndarray) -> np.ndarray:
    """Along-side index of the coarse cell beside each of the 32 fine faces."""
    return int(row[4]) + np.arange(TILE) // 2


def _strip(z, npix, k, pixel, side, nman, crest, length, e_lo, e_hi, rows, zbig=None, margin=0, beta=9.0):
    """Faces along a fine tile's east or south edge: invert and table top per face, and the tables.

    With ``zbig`` (the block of ``z`` with ``margin`` more pixels on every side) each face takes the local hydraulic
    radius along its own line, read past its ends, as the tile's own faces do (W49); crest faces keep their table."""
    zf = np.zeros(TILE)
    ef = np.zeros(TILE)
    tab = np.zeros((TILE, rows, 2))
    edge = 1 + TILE * k
    prof = np.empty(k)
    weight = np.ones(k)
    lined = npix.shape[0] > 1
    for q in range(TILE):
        start = 1 + q * k
        for m in range(k):
            near = (start + m, edge - 1) if side == 2 else (edge - 1, start + m)
            far = (start + m, edge) if side == 2 else (edge, start + m)
            prof[m] = max(z[near], z[far])
            if lined:
                weight[m] = _lined(npix[far] if z[far] > z[near] else npix[near], nman[q])
        zf[q], ef[q] = _face_table(
            prof, crest[q], pixel, 1.0 / nman[q], weight, length[q], e_lo, e_hi, tab[q]
        )
        if zbig is not None and np.isnan(crest[q]):
            full = np.array(
                [
                    max(zbig[start + t, margin + edge - 1], zbig[start + t, margin + edge])
                    if side == 2
                    else max(zbig[margin + edge - 1, start + t], zbig[margin + edge, start + t])
                    for t in range(k + 2 * margin)
                ]
            )
            top = window_top(full, zf[q], ef[q], e_hi)
            if top > ef[q]:
                zf[q], ef[q] = _face_table(prof.copy(), crest[q], pixel, 1.0 / nman[q], weight, length[q], top, e_hi, tab[q])
            e = min(margin, int(np.ceil(beta * ef[q] / pixel)))
            _local_radius_conveyance(
                full[margin - e : margin + k + e], e, e + k, zf[q], ef[q], pixel, 1.0 / nman[q], weight, length[q], beta, tab[q]
            )
    return zf, ef, tab


def build_quad_tables(
    grid: QuadGrid,
    bed: BedSource,
    cfg: Tables,
    manning: float | np.ndarray = 0.035,
    crest: CrestFaces | None = None,
    edit=None,
    lining=None,
    workers: int | None = None,
) -> GridTables:
    """All static arrays. ``crest`` and a Manning grid are on the finest raster; crests must lie in finest tiles.

    ``edit`` and ``lining`` are the hooks of ``build_tables``: they work on pixels, so they do not care for the cell size.
    ``workers`` threads build the tiles, as in ``build_tables`` (W81).
    """
    k0 = round(grid.dx / bed.pixel)
    if abs(k0 * bed.pixel - grid.dx) > 1e-6 * grid.dx:
        raise ValueError(f"cell size {grid.dx} is not a multiple of the pixel {bed.pixel}")
    ny, nx = grid.shape
    crest = crest or CrestFaces.empty((ny, nx))
    _check_crests(grid, crest)
    nman = np.full((ny, nx), float(manning)) if np.isscalar(manning) else np.asarray(manning, np.float64)
    nman_t = grid.to_tiles(nman, np.float64)
    nt, rows, extra = grid.ntiles, cfg.rows, grid.pseudo
    total = nt + extra

    zmin, rel, zfx, zfy = (np.zeros((nt, TILE, TILE)) for _ in range(4))
    zcx, zcy = np.zeros((nt, TILE, TILE)), np.zeros((nt, TILE, TILE))
    hc = np.zeros((nt, TILE, TILE), np.float32)
    dtab = np.zeros((nt, TILE, TILE, rows), np.float32)
    efx, efy = np.ones((total, TILE, TILE), np.float32), np.ones((total, TILE, TILE), np.float32)
    ftabx = np.zeros((total, TILE, TILE, rows, 2), np.float32)
    ftaby = np.zeros((total, TILE, TILE, rows, 2), np.float32)
    east_south = {(int(r[0]), int(r[1])): r for r in grid.interfaces if r[1] >= 2}
    fx, fy = np.zeros((total, TILE, TILE, 2)), np.zeros((total, TILE, TILE, 2))
    """Invert of the extra faces, per table tile; the second layer marks a used face."""
    local = cfg.face_conveyance == "local_radius"
    margin = int(np.ceil(cfg.local_radius_beta * cfg.face_depth_max / bed.pixel)) if local else 0
    """W49: every tile is read this many pixels wider on each side, for the local hydraulic radius's window."""
    threads = table_workers(workers)
    cells, radius = (tile_tables_serial, tile_local_radius_serial) if threads > 1 else (tile_tables, tile_local_radius)
    beds = ThreadBeds(bed)

    def one(t: int) -> None:
        """Tile ``t``'s tables and its east and south interface faces, into their own slots (W81: on threads)."""
        src = beds.get()
        w_hc, w_efx, w_efy = (np.zeros((TILE, TILE)) for _ in range(3))
        w_dtab = np.zeros((TILE, TILE, rows))
        w_ftabx, w_ftaby = np.zeros((TILE, TILE, rows, 2)), np.zeros((TILE, TILE, rows, 2))
        npix = np.full((1, 1), np.nan)
        zbig = None
        size = 1 << int(grid.level[t])
        k = k0 * size
        j0, i0 = int(grid.tiles[t, 0]) * TILE, int(grid.tiles[t, 1]) * TILE
        row0, col0 = j0 * k0 - 1, i0 * k0 - 1
        if local:
            n_big = TILE * k + 2 + 2 * margin
            zbig = src.read(row0 - margin, col0 - margin, n_big, n_big)
            if edit is not None:
                edit(zbig, row0 - margin, col0 - margin)
            z = np.ascontiguousarray(zbig[margin : margin + TILE * k + 2, margin : margin + TILE * k + 2])
        else:
            z = src.read(row0, col0, TILE * k + 2, TILE * k + 2)
            if edit is not None:
                edit(z, row0, col0)
        if lining is not None:
            npix = np.full(z.shape, np.nan)
            lining(z, npix, row0, col0)
        if size == 1:
            sl = (slice(j0, j0 + TILE), slice(i0, i0 + TILE))
            cxz, cxl, cyz, cyl = crest.xz[sl], crest.xlen[sl], crest.yz[sl], crest.ylen[sl]
        else:
            cxz, cxl = np.full((TILE, TILE), np.nan), np.ones((TILE, TILE))
            cyz, cyl = cxz, cxl
        cells(
            z, k, TILE, bed.pixel, nman_t[t], npix, cxz, cxl, cyz, cyl, cfg.face_depth_min, cfg.face_depth_max,
            zmin[t], rel[t], w_hc, w_dtab, zfx[t], w_efx, w_ftabx, zfy[t], w_efy, w_ftaby,
        )  # fmt: skip
        if local:
            radius(
                zbig, margin, k, TILE, bed.pixel, nman_t[t], npix, cxz, cxl, cyz, cyl,
                zfx[t], w_efx, w_ftabx, zfy[t], w_efy, w_ftaby, cfg.local_radius_beta, cfg.face_depth_max,
            )  # fmt: skip
        hc[t], dtab[t], efx[t], efy[t], ftabx[t], ftaby[t] = w_hc, w_dtab, w_efx, w_efy, w_ftabx, w_ftaby
        cx_bed, cy_bed = centre_beds(z, k, TILE)  # at the tile's own cell size (W47)
        zcx[t], zcy[t] = cx_bed - zmin[t], cy_bed - zmin[t]
        for side in (2, 3):
            row = east_south.get((t, side))
            if row is None:
                continue
            target_crest, target_len = _edge_crest(grid, crest, t, side)
            line = nman_t[t, :, -1] if side == 2 else nman_t[t, -1, :]
            zf, ef, tab = _strip(
                z,
                npix,
                k,
                bed.pixel,
                side,
                line,
                target_crest,
                target_len,
                cfg.face_depth_min,
                cfg.face_depth_max,
                rows,
                zbig if local else None,
                margin,
                cfg.local_radius_beta,
            )
            base = int(row[5])
            pt, rw = base // (TILE * TILE), (base % (TILE * TILE)) // TILE
            (efx if side == 2 else efy)[pt, rw] = ef
            (ftabx if side == 2 else ftaby)[pt, rw] = tab
            (fx if side == 2 else fy)[pt, rw, :, 0] = zf
            (fx if side == 2 else fy)[pt, rw, :, 1] = 1.0

    try:
        run_all(range(1, nt), one, threads)
    finally:
        beds.close()
    zbar = zmin + rel
    x = _face_arrays(grid, cfg, zmin, zbar, zfx, fx, 0, crest)
    y = _face_arrays(grid, cfg, zmin, zbar, zfy, fy, 1, crest)
    zcx, zcy = (np.nan_to_num(np.maximum(a, 0.0), nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32) for a in (zcx, zcy))
    return GridTables(
        grid, grid.from_tiles(zmin), grid.from_tiles(zbar), hc, dtab,
        *x[:4], efx, x[4], ftabx, *y[:4], efy, y[4], ftaby, zcx, zcy,
    )  # fmt: skip


def _check_crests(grid: QuadGrid, crest: CrestFaces) -> None:
    edited = ~np.isnan(crest.xz) | ~np.isnan(crest.yz)
    if crest.xwall is not None:
        edited = edited | crest.xwall | crest.ywall
    if not edited.any():
        return
    j, i = np.nonzero(edited)
    tiles = grid.tile_of[j // TILE, i // TILE]
    coarse = (grid.level[tiles] > 0) & (tiles > 0)
    if coarse.any():
        raise ValueError(
            f"{int(coarse.sum())} crest or wall faces lie in coarse tiles: the mesh must refine along them"
        )


def _edge_crest(grid: QuadGrid, crest: CrestFaces, t: int, side: int):
    """Crest elevation and length factor of the raster faces along a finest tile's east or south edge."""
    j0, i0 = int(grid.tiles[t, 0]) * TILE, int(grid.tiles[t, 1]) * TILE
    if grid.level[t] > 0:
        return np.full(TILE, np.nan), np.ones(TILE)
    ny, nx = grid.shape
    if side == 2 and i0 + TILE < nx:
        sl = (slice(j0, j0 + TILE), i0 + TILE)
        return crest.xz[sl], crest.xlen[sl]
    if side == 3 and j0 + TILE < ny:
        sl = (j0 + TILE, slice(i0, i0 + TILE))
        return crest.yz[sl], crest.ylen[sl]
    return np.full(TILE, np.nan), np.ones(TILE)


def _face_arrays(grid: QuadGrid, cfg: Tables, zmin, zbar, zf, extra, axis: int, crest: CrestFaces):
    """fl, fr, gl, gr, cw of all own faces and the extra table tiles. ``axis`` 0: x faces, the low side is west."""
    nt = grid.ntiles
    total = nt + grid.pseudo
    tol = cfg.crest_tolerance
    out = [np.zeros((total, TILE, TILE), np.float32) for _ in range(5)]
    out[0][:] = CLOSED
    out[1][:] = CLOSED
    side_low = 0 if axis == 0 else 1
    rows_low = {int(r[0]): r for r in grid.interfaces if r[1] == side_low}
    for t in range(1, nt):
        zmin_a, zbar_a, on_a = _low_side(grid, zmin, zbar, t, axis, rows_low.get(t), side_low)
        open_face = grid.cells[t] & on_a
        given, wall = _crest_arrays(grid, crest, t, axis)
        if wall is not None:
            open_face = open_face & ~wall
        parts = _opening(zf[t], zmin_a, zbar_a, zmin[t], zbar[t], open_face, tol, given)
        for n, a in enumerate(parts):
            out[n][t] = a
    side_high = side_low + 2
    for r in grid.interfaces[grid.interfaces[:, 1] == side_high]:
        _high_interface(grid, r, zmin, zbar, extra, axis, tol, out, crest)
    return out


def _low_side(grid, zmin, zbar, t, axis, row, side_low):
    """Bed of the cell on the low side of each own face, and whether that cell exists."""
    roll = 1 if axis == 0 else 0
    zmin_a = np.roll(zmin[t], 1, axis=roll)
    zbar_a = np.roll(zbar[t], 1, axis=roll)
    on_a = np.roll(grid.cells[t], 1, axis=roll)
    edge = (slice(None), 0) if axis == 0 else (0, slice(None))
    far = (slice(None), -1) if axis == 0 else (-1, slice(None))
    other = int(grid.same[t, side_low])
    if other:
        zmin_a[edge], zbar_a[edge], on_a[edge] = zmin[other][far], zbar[other][far], grid.cells[other][far]
    elif row is not None:
        c = _coarse_cells(row)
        coarse = int(row[2])
        at = (c, -1) if axis == 0 else (-1, c)
        zmin_a[edge], zbar_a[edge], on_a[edge] = zmin[coarse][at], zbar[coarse][at], grid.cells[coarse][at]
    else:
        on_a[edge] = False
    return zmin_a, zbar_a, on_a


def _high_interface(grid, row, zmin, zbar, extra, axis, tol, out, crest) -> None:
    """The extra faces on a fine tile's east or south side; a crest or a wall there holds as on any other face."""
    t, coarse, base = int(row[0]), int(row[2]), int(row[5])
    pt, rw = base // (TILE * TILE), (base % (TILE * TILE)) // TILE
    c = _coarse_cells(row)
    near = (slice(None), -1) if axis == 0 else (-1, slice(None))
    at = (c, 0) if axis == 0 else (0, c)
    open_face = grid.cells[t][near] & grid.cells[coarse][at] & (extra[pt, rw, :, 1] > 0.0)
    given, wall = _edge_faces(grid, crest, t, axis)
    if wall is not None:
        open_face = open_face & ~wall
    parts = _opening(
        extra[pt, rw, :, 0],
        zmin[t][near],
        zbar[t][near],
        zmin[coarse][at],
        zbar[coarse][at],
        open_face,
        tol,
        given,
    )
    for n, a in enumerate(parts):
        out[n][pt, rw] = a


def _edge_faces(grid, crest, t, axis):
    """Crest coefficient and wall of the raster faces along a tile's east (axis 0) or south (axis 1) edge."""
    if grid.level[t] > 0:
        return None, None
    j0, i0 = int(grid.tiles[t, 0]) * TILE, int(grid.tiles[t, 1]) * TILE
    ny, nx = grid.shape
    if (axis == 0 and i0 + TILE >= nx) or (axis == 1 and j0 + TILE >= ny):
        return None, None
    sl = (slice(j0, j0 + TILE), i0 + TILE) if axis == 0 else (j0 + TILE, slice(i0, i0 + TILE))
    given = crest.xc[sl] if axis == 0 else crest.yc[sl]
    wall = crest.xwall if axis == 0 else crest.ywall
    return given, None if wall is None else wall[sl]


def _crest_arrays(grid, crest, t, axis):
    """Crest coefficient and wall of a tile's own faces, from the finest raster."""
    if grid.level[t] > 0:
        return None, None
    j0, i0 = int(grid.tiles[t, 0]) * TILE, int(grid.tiles[t, 1]) * TILE
    sl = (slice(j0, j0 + TILE), slice(i0, i0 + TILE))
    given = crest.xc[sl] if axis == 0 else crest.yc[sl]
    wall = crest.xwall if axis == 0 else crest.ywall
    return given, None if wall is None else wall[sl]


__all__ = ["build_quad_tables"]
