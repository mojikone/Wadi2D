"""A breach on a strip's own faces (W69): the dam's faces on the aligned or centre mesh, rebuilt from their pixels.

A strip face carries a dam where its two cells lie on different sides of the dam's line (:mod:`wadi2d.strips.objects`,
the side rule); its table was built from the ground sampled along the face's segment at the pixel spacing, lifted to
the crest (:func:`wadi2d.strips.tables.build_poly_tables`). A breach rebuilds exactly that with the crest lowered to the
breach's surface, never below the ground without the dam, through the same ``_face_table`` kernel, then the lattice's
rule that every invert stands at or above both cells' floors (:meth:`wadi2d.solver.poly.mesh.PolyMesh.finish`). The
roughness is read back from the table the run holds, so a raster of n needs nothing more. The bed drops of the faces
of the cells beside the dam (W47's carry) are recomputed from the new inverts, the opposite faces as the mesh chose
them. The rebuilt numbers go into the strip state's own arrays, numpy or CuPy, so the kernels are untouched.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import shapely

from wadi2d.breach.faces import FaceTables
from wadi2d.tables.core import _face_table

NAMES = ("fl", "fr", "gl", "gr", "ef", "cw")


@dataclass
class StripFaces:
    """The dam's faces on the strip, in mesh face order; per-sample arrays are flat, face ``m`` at
    ``start[m]:start[m + 1]``."""

    face: np.ndarray
    """Index of each face in the strip mesh (and its state)."""
    start: np.ndarray
    s: np.ndarray
    """Station of each sample along the dam line, m."""
    crested: np.ndarray
    """The ground along the face raised to the crest: what the tables were built on."""
    free: np.ndarray
    """The ground without the dam, the lowest a breach cuts."""
    spacing: np.ndarray
    n_inv: np.ndarray
    left: np.ndarray
    right: np.ndarray
    """The two cells of each face in the strip mesh; a right cell at or past ``nreal`` is a ghost (a tile cell)."""
    zmin_l: np.ndarray
    zmin_r: np.ndarray
    zbar_l: np.ndarray
    zbar_r: np.ndarray
    cw0: np.ndarray
    zf: np.ndarray
    """The whole mesh's inverts as the run holds them now, for the bed drops."""
    drops: tuple[np.ndarray, np.ndarray, np.ndarray]
    """(face, side 0 left 1 right, opposite face) of every drop a breach can move."""

    @property
    def size(self) -> int:
        return int(self.face.size)

    def per_face(self, values: np.ndarray, reduce) -> np.ndarray:
        return np.array([reduce(values[a:b]) for a, b in zip(self.start[:-1], self.start[1:], strict=True)])

    def any_below(self, prof: np.ndarray) -> np.ndarray:
        """Per face, whether ``prof`` stands anywhere below the crested ground."""
        low = prof < self.crested - 1e-9
        return np.logical_or.reduceat(low, self.start[:-1]) if low.size else np.zeros(self.size, bool)


def _window(bed, grid, xs: np.ndarray, ys: np.ndarray, pad: float):
    from wadi2d.strips.tables import Pixels

    col0 = int(np.floor((xs.min() - pad - grid.x0) / bed.pixel))
    row0 = int(np.floor((grid.y0 - ys.max() - pad) / bed.pixel))
    ncols = int(np.ceil((xs.max() - xs.min() + 2 * pad) / bed.pixel)) + 1
    nrows = int(np.ceil((ys.max() - ys.min() + 2 * pad) / bed.pixel)) + 1
    raw = np.asarray(bed.read(row0, col0, nrows, ncols), np.float64)
    k = round(grid.dx / bed.pixel)

    def pixels(edit) -> Pixels:
        z = raw.copy()
        if edit is not None:
            edit(z, row0, col0)
        return Pixels(z, grid.x0 + col0 * bed.pixel, grid.y0 - row0 * bed.pixel, grid.dx / k)

    return pixels


def _opposites(mesh, faces: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Every (face, side, opposite face) of the real cells beside ``faces``, by the rule of
    :func:`wadi2d.solver.poly.mesh.opposite_drops`, on the inverts the mesh holds."""
    L, R, nx, ny, zf = mesh.left, mesh.right, mesh.nx, mesh.ny, mesh.zf
    nreal = mesh.real
    tie = 1e-9 if mesh.cut_faces else -1.0
    cells = {int(c) for c in np.concatenate((L[faces], R[faces])).tolist() if c < nreal}
    of_cell = {c: np.nonzero((mesh.left == c) | (mesh.right == c))[0] for c in cells}
    out_f, out_side, out_g = [], [], []
    for c in sorted(cells):
        for f in of_cell[c].tolist():
            for side, owner in ((0, int(L[f])), (1, int(R[f]))):
                if owner != c:
                    continue
                s_f = 1.0 if side == 0 else -1.0
                ox, oy = s_f * nx[f], s_f * ny[f]
                best, best_dot = -1, -0.5
                for g in of_cell[c].tolist():
                    if g == f:
                        continue
                    sign = 1.0 if L[g] == c else -1.0
                    dot = sign * (nx[g] * ox + ny[g] * oy)
                    if dot < best_dot - max(tie, 0.0):
                        best, best_dot = g, dot
                    elif best >= 0 and dot < best_dot + tie and zf[g] < zf[best]:
                        best, best_dot = g, min(dot, best_dot)
                if best >= 0:
                    out_f.append(f)
                    out_side.append(side)
                    out_g.append(best)
    return np.array(out_f, np.int64), np.array(out_side, np.int64), np.array(out_g, np.int64)


def build_strip_faces(cfg, tables, bed, edits, free_edit, obj, model) -> StripFaces | None:
    """The dam's faces on the strip, or None where the run has no strip or the dam crosses none of its faces.
    ``edits`` is :func:`wadi2d.terrain.apply_objects`' result for the job; ``free_edit`` the pixel edit of the ground
    without the dam."""
    st = getattr(tables, "strip", None)
    hybrid = getattr(model.backend, "hooks", None)
    if st is None or hybrid is None:
        return None
    from wadi2d.strips.hybrid import ghosts_for
    from wadi2d.strips.objects import crest_polylines, faces_from_objects
    from wadi2d.strips.tables import face_profile
    from wadi2d.terrain import Ground

    grid = tables.grid
    geo, mesh, kept = st.strip.geometry, st.mesh, st.kept
    ghosts = ghosts_for(geo, grid, tables)
    ground = Ground(bed, grid.x0, grid.y0)
    mine = crest_polylines([obj], grid.dx, cfg.terrain, ground, edits.shapes)
    held = crest_polylines(cfg.terrain.objects, grid.dx, cfg.terrain, ground, edits.shapes)
    own, _cw, _wall = faces_from_objects(geo, ghosts, mine)
    crest, _cw, _wall = faces_from_objects(geo, ghosts, held)
    pos = np.full(geo.nfaces, -1, np.int64)
    pos[kept] = np.arange(kept.size)
    gfaces = np.nonzero(np.isfinite(own) & (pos >= 0))[0]
    gfaces = gfaces[np.isfinite(crest[gfaces])]
    if gfaces.size == 0:
        return None
    nodes = geo.face_node[gfaces]
    xs, ys = geo.x[nodes.ravel()], geo.y[nodes.ravel()]
    pixels = _window(bed, grid, xs, ys, 2.0 * grid.dx)
    edited_pix = pixels(edits.edit)
    free_pix = edited_pix if free_edit is edits.edit else pixels(free_edit)
    line = shapely.LineString(obj.coordinates)
    face = pos[gfaces]
    state = hybrid.state.face_arrays()
    held_tab = _get(hybrid, state["ftab"], face, mesh.rows)
    held_cw = _get(hybrid, state["cw"], face)
    starts, s_all, cr_all, fr_all, spacing, n_inv = [0], [], [], [], [], []
    rows = mesh.rows
    tab = np.zeros((rows, 2))
    for m, g in enumerate(gfaces.tolist()):
        a, b = geo.face_node[g]
        prof, step = face_profile(edited_pix, geo.x[a], geo.y[a], geo.x[b], geo.y[b])
        free, _ = face_profile(free_pix, geo.x[a], geo.y[a], geo.x[b], geo.y[b])
        crested = np.maximum(prof, crest[g])
        k = prof.size
        t = (np.arange(k) + 0.5) / k
        px, py = geo.x[a] + (geo.x[b] - geo.x[a]) * t, geo.y[a] + (geo.y[b] - geo.y[a]) * t
        s_all.append(shapely.line_locate_point(line, shapely.points(px, py)))
        cr_all.append(crested)
        fr_all.append(np.minimum(free, crested))
        starts.append(starts[-1] + k)
        spacing.append(step)
        # the face's roughness, read back from the conveyance the run holds at the table's top
        _face_table(crested, np.nan, step, 1.0, np.ones(k), 1.0, cfg.tables.face_depth_min, cfg.tables.face_depth_max, tab)
        unit = tab[-1, 1]
        n_inv.append((held_tab[m, -1, 1] / unit) ** (1.0 / 0.6) if unit > 0.0 else 1.0 / cfg.terrain.manning)
    L, R = mesh.left[face], mesh.right[face]
    return StripFaces(
        face=face, start=np.array(starts, np.int64), s=np.concatenate(s_all), crested=np.concatenate(cr_all),
        free=np.concatenate(fr_all), spacing=np.array(spacing), n_inv=np.array(n_inv), left=L, right=R,
        zmin_l=mesh.zmin[L], zmin_r=mesh.zmin[R], zbar_l=mesh.zbar[L], zbar_r=mesh.zbar[R], cw0=held_cw,
        zf=np.asarray(mesh.zf, np.float64).copy(), drops=_opposites(mesh, face),
    )  # fmt: skip


def face_tables(faces: StripFaces, profiles: np.ndarray, cw: np.ndarray, rows: int, e_lo: float, e_hi: float):
    """Tables of the faces on the flat ``profiles``, as the strip's table builder makes a crest face's; and the
    inverts, raised to both cells' floors as the mesh raises them."""
    n = faces.size
    tab = np.zeros((n, rows, 2))
    zf = np.empty(n)
    top = np.empty(n)
    for m in range(n):
        a, b = faces.start[m], faces.start[m + 1]
        p = np.ascontiguousarray(profiles[a:b])
        zf[m], top[m] = _face_table(p, np.nan, faces.spacing[m], faces.n_inv[m], np.ones(b - a), 1.0, e_lo, e_hi, tab[m])
    zf = np.maximum(np.maximum(zf, faces.zmin_l), faces.zmin_r)
    ft = FaceTables(zf - faces.zmin_l, zf - faces.zmin_r, zf - faces.zbar_l, zf - faces.zbar_r, top, cw, tab)
    return ft, zf


def _cp(hybrid):
    return getattr(hybrid.state, "cp", None)


def _get(hybrid, a, idx: np.ndarray, rows: int | None = None) -> np.ndarray:
    cp = _cp(hybrid)
    if rows is not None:
        idx = ((2 * rows * idx)[:, None] + np.arange(2 * rows)[None, :]).ravel()
    v = a[idx if cp is None else cp.asarray(idx)]
    v = np.asarray(v if cp is None else cp.asnumpy(v), dtype=np.float64)
    return v if rows is None else v.reshape(-1, rows, 2)


def _put(hybrid, a, idx: np.ndarray, values: np.ndarray) -> None:
    cp = _cp(hybrid)
    values = np.ascontiguousarray(values, dtype=np.float32)
    if cp is None:
        a[idx] = values
    else:
        a[cp.asarray(idx)] = cp.asarray(values)


def read_back(hybrid, faces: StripFaces, rows: int) -> FaceTables:
    """The faces as the strip state holds them now."""
    arrays = hybrid.state.face_arrays()
    out = {name: _get(hybrid, arrays[name], faces.face) for name in NAMES}
    return FaceTables(**out, ftab=_get(hybrid, arrays["ftab"], faces.face, rows))


def write(hybrid, faces: StripFaces, ft: FaceTables, zf: np.ndarray, rows: int, only: np.ndarray) -> None:
    """Put the faces' tables into the strip state, then the bed drops of the faces beside them."""
    arrays = hybrid.state.face_arrays()
    on = np.nonzero(only)[0]
    if on.size == 0:
        return
    idx = faces.face[on]
    for name in NAMES:
        _put(hybrid, arrays[name], idx, getattr(ft, name)[on])
    flat = ((2 * rows * idx)[:, None] + np.arange(2 * rows)[None, :]).ravel()
    _put(hybrid, arrays["ftab"], flat, ft.ftab[on].reshape(-1))
    faces.zf[idx] = zf[on]
    f, side, g = faces.drops
    if f.size == 0:
        return
    value = 0.5 * (faces.zf[g] - faces.zf[f])
    ok = np.isfinite(value)
    for k, name in ((0, "dzl"), (1, "dzr")):
        pick = ok & (side == k)
        if pick.any():
            _put(hybrid, arrays[name], f[pick], value[pick])
