"""The faces a breach cuts, their pixels, and their tables rebuilt as it grows (W63).

A dam line's faces are crest faces: the table builder read the ground along each face, raised it to the crest
(:func:`wadi2d.tables.core._face_table`) and wrote an invert, a table top and a table of area and conveyance. A breach
rebuilds exactly that from the same pixels with the crest lowered to the breach's surface, never below the ground
without the dam: the DEM under a crest line, the DEM before the edits under an embankment. Nothing else in the tables
moves, so the cells either side keep their storage; the face's weir cap takes the breach weir coefficient.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import shapely

from wadi2d.config.schema import TerrainObject
from wadi2d.solver.layout import CLOSED, TILE, TILE2
from wadi2d.tables.builder import GridTables
from wadi2d.tables.core import _face_table
from wadi2d.terrain.crest import NORTH, WEST

INVERT_TOLERANCE_M = 1.0e-3
"""How far the rebuilt invert of an unbreached face may stand from the built one before the breach refuses its faces."""


@dataclass
class BreachFaces:
    """Faces of one dam line, in face order; per-pixel arrays are (n, k)."""

    axis: np.ndarray
    j: np.ndarray
    i: np.ndarray
    fid: np.ndarray
    s: np.ndarray
    """Station of each pixel along the dam line, m."""
    crested: np.ndarray
    """The ground along the face raised to the crest: what the tables were built on."""
    free: np.ndarray
    """The ground without the dam, the lowest a breach cuts."""
    zmin_l: np.ndarray
    zmin_r: np.ndarray
    zbar_l: np.ndarray
    zbar_r: np.ndarray
    n_inv: np.ndarray
    length: np.ndarray
    cw0: np.ndarray
    pixel: float

    @property
    def size(self) -> int:
        return int(self.axis.size)

    def cells(self, n: int) -> tuple[tuple[int, int], tuple[int, int]]:
        """(j, i) of the cell before face ``n`` (west or north) and of its own cell."""
        j, i = int(self.j[n]), int(self.i[n])
        return ((j, i - 1) if self.axis[n] == WEST else (j - 1, i)), (j, i)


def _static(tables: GridTables, axis: int) -> tuple:
    if axis == WEST:
        return tables.flx, tables.frx, tables.glx, tables.grx, tables.efx, tables.cwx, tables.ftabx
    return tables.fly, tables.fry, tables.gly, tables.gry, tables.efy, tables.cwy, tables.ftaby


def find_faces(tables: GridTables, crest, obj: TerrainObject, snap: float) -> list[tuple[int, int, int]]:
    """(axis, j, i) of the open crest faces within ``snap`` m of the dam's line."""
    grid = tables.grid
    line = shapely.LineString(obj.coordinates)
    out = []
    for axis, zz, wall in ((WEST, crest.xz, crest.xwall), (NORTH, crest.yz, crest.ywall)):
        jj, ii = np.nonzero(np.isfinite(zz) & ~(wall if wall is not None else False))
        if jj.size == 0:
            continue
        x = grid.x0 + (ii + (0.0 if axis == WEST else 0.5)) * grid.dx
        y = grid.y0 - (jj + (0.5 if axis == WEST else 0.0)) * grid.dx
        near = shapely.distance(line, shapely.points(x, y)) <= snap
        fl = _static(tables, axis)[0]
        for j, i in zip(jj[near].tolist(), ii[near].tolist(), strict=True):
            if not grid.mask[j, i]:
                continue
            t, oj, oi = grid.locate(j, i)
            if t <= 0 or fl[t, oj, oi] >= 0.5 * CLOSED:
                continue
            out.append((axis, j, i))
    return out


def _profile(bed, edit, axis: int, j: int, i: int, k: int) -> tuple[np.ndarray, np.ndarray]:
    """(edited, raw) ground along a face: the higher of the two pixels that meet there, as the table builder reads it."""
    if axis == WEST:
        row0, col0, nr, nc = j * k, i * k - 1, k, 2
    else:
        row0, col0, nr, nc = j * k - 1, i * k, 2, k
    raw = bed.read(row0, col0, nr, nc)
    edited = raw.copy()
    if edit is not None:
        edit(edited, row0, col0)
    pick = (lambda z: np.maximum(z[:, 0], z[:, 1])) if axis == WEST else (lambda z: np.maximum(z[0], z[1]))
    return pick(edited), pick(raw)


def build_faces(tables, bed, edits, obj: TerrainObject, manning, snap: float) -> BreachFaces:
    """The dam's faces with everything a rebuild needs; ``edits`` is :func:`wadi2d.terrain.apply_objects`' result."""
    grid = tables.grid
    k = round(grid.dx / bed.pixel)
    found = find_faces(tables, edits.crest, obj, snap)
    if not found:
        raise ValueError(f"breach: no open crest face of '{obj.name}' on the grid")
    axis, jj, ii = (np.array(v, np.int64) for v in zip(*found, strict=True))
    n = axis.size
    crested = np.empty((n, k))
    free = np.empty((n, k))
    s = np.empty((n, k))
    line = shapely.LineString(obj.coordinates)
    q = (np.arange(k) + 0.5) * bed.pixel
    nman = np.broadcast_to(np.asarray(manning, dtype=np.float64), grid.shape)
    fid = np.empty(n, np.int64)
    zl, zr, bl, br, n_inv, length, cw0 = (np.empty(n) for _ in range(7))
    for m in range(n):
        a, j, i = int(axis[m]), int(jj[m]), int(ii[m])
        edited, raw = _profile(bed, edits.edit, a, j, i, k)
        cz = (edits.crest.xz if a == WEST else edits.crest.yz)[j, i]
        crested[m] = np.maximum(edited, cz)
        free[m] = raw if obj.kind == "embankment" else edited
        if a == WEST:
            x, y = np.full(k, grid.x0 + i * grid.dx), grid.y0 - j * grid.dx - q
        else:
            x, y = grid.x0 + i * grid.dx + q, np.full(k, grid.y0 - j * grid.dx)
        s[m] = shapely.line_locate_point(line, shapely.points(x, y))
        (jl, il) = (j, i - 1) if a == WEST else (j - 1, i)
        zl[m], zr[m] = tables.zmin[jl, il], tables.zmin[j, i]
        bl[m], br[m] = tables.zbar[jl, il], tables.zbar[j, i]
        n_inv[m] = 1.0 / nman[j, i]
        length[m] = (edits.crest.xlen if a == WEST else edits.crest.ylen)[j, i]
        t, oj, oi = grid.locate(j, i)
        fid[m] = t * TILE2 + oj * TILE + oi
        cw0[m] = _static(tables, a)[5][t, oj, oi]
    return BreachFaces(axis, jj, ii, fid, s, crested, free, zl, zr, bl, br, n_inv, length, cw0, bed.pixel)


@dataclass
class FaceTables:
    """What the solver reads of each face: inverts over both cells' floors and mean beds, table top, weir, table."""

    fl: np.ndarray
    fr: np.ndarray
    gl: np.ndarray
    gr: np.ndarray
    ef: np.ndarray
    cw: np.ndarray
    ftab: np.ndarray
    """(n, rows, 2)"""


def face_tables(
    faces: BreachFaces, profiles: np.ndarray, cw: np.ndarray, rows: int, e_lo: float, e_hi: float
) -> FaceTables:
    """Tables of the faces on ``profiles`` (n, k), the table builder's own kernel; ``cw`` per face."""
    n, k = profiles.shape
    tab = np.zeros((n, rows, 2))
    zf = np.empty(n)
    top = np.empty(n)
    weight = np.ones(k)
    for m in range(n):
        zf[m], top[m] = _face_table(
            np.ascontiguousarray(profiles[m]), np.nan, faces.pixel, faces.n_inv[m], weight, faces.length[m], e_lo, e_hi,
            tab[m],
        )  # fmt: skip
    return FaceTables(
        zf - faces.zmin_l, zf - faces.zmin_r, zf - faces.zbar_l, zf - faces.zbar_r, top, cw, tab
    )


def read_back(backend, faces: BreachFaces, rows: int) -> FaceTables:
    """The faces as the backend holds them now."""
    cp = getattr(backend, "cp", None)

    def get(a, idx):
        v = a[idx if cp is None else cp.asarray(idx)]
        return np.asarray(v if cp is None else cp.asnumpy(v), dtype=np.float64)

    out = {name: np.empty(faces.size) for name in ("fl", "fr", "gl", "gr", "ef", "cw")}
    tab = np.empty((faces.size, rows, 2))
    for axis, static, ftab in (
        (WEST, backend.static_x, backend.ftabx),
        (NORTH, backend.static_y, backend.ftaby),
    ):
        on = np.nonzero(faces.axis == axis)[0]
        if on.size == 0:
            continue
        idx = faces.fid[on]
        for name, a in zip(("fl", "fr", "gl", "gr", "ef", "cw"), static, strict=True):
            out[name][on] = get(a, idx)
        flat = (2 * rows * idx)[:, None] + np.arange(2 * rows)[None, :]
        tab[on] = get(ftab, flat.ravel()).reshape(on.size, rows, 2)
    return FaceTables(**out, ftab=tab)


def write(backend, faces: BreachFaces, ft: FaceTables, rows: int, only: np.ndarray | None = None) -> None:
    """Put the face tables into the backend's arrays, on the host or the device alike."""
    cp = getattr(backend, "cp", None)

    def put(a, idx, values):
        values = np.ascontiguousarray(values, dtype=np.float32)
        if cp is None:
            a[idx] = values
        else:
            a[cp.asarray(idx)] = cp.asarray(values)

    pick = np.ones(faces.size, bool) if only is None else only
    for axis, static, ftab in (
        (WEST, backend.static_x, backend.ftabx),
        (NORTH, backend.static_y, backend.ftaby),
    ):
        on = np.nonzero((faces.axis == axis) & pick)[0]
        if on.size == 0:
            continue
        idx = faces.fid[on]
        for a, values in zip(static, (ft.fl, ft.fr, ft.gl, ft.gr, ft.ef, ft.cw), strict=True):
            put(a, idx, values[on])
        flat = (2 * rows * idx)[:, None] + np.arange(2 * rows)[None, :]
        put(ftab, flat.ravel(), ft.ftab[on].reshape(-1))


def mismatch(built: FaceTables, rebuilt: FaceTables) -> tuple[float, float]:
    """Largest invert difference (m) and largest table difference over the table's own top value, between two sets."""
    dz = float(np.max(np.abs(built.fr - rebuilt.fr)))
    scale = np.maximum(np.abs(built.ftab[:, -1, :]), 1e-9)[:, None, :]
    dt = float(np.max(np.abs(built.ftab - rebuilt.ftab) / scale))
    return dz, dt
