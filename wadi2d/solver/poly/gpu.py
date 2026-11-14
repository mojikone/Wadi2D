# Wadi2D. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The polygon step on the GPU (W45, stage 5): the strip's state on the device and the launches of ``poly.cu``.

The same arrays as :class:`wadi2d.solver.poly.model.PolyState`, as CuPy arrays, plus the cell-to-face CSR the cell
kernels gather through. The hybrid stepper of :mod:`wadi2d.strips.hybrid_gpu` drives the launches beside the tile
kernels; nothing here reads the lattice except through the pointers that stepper passes.
"""

from __future__ import annotations

import numpy as np

from wadi2d.config.schema import Numerics
from wadi2d.solver.backend import NumericsRecord
from wadi2d.solver.gpu.backend import KERNELS, header, load_module
from wadi2d.solver.poly.mesh import PolyMesh

F = np.float32
THREADS = 256


def cell_faces(left: np.ndarray, right: np.ndarray, ncells: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """CSR of each cell's faces with the sign that makes the face discharge an outflow of the cell: ``+1`` on the
    left cell, ``-1`` on the right. Faces of a cell come in face order, so a sum is the same every launch."""
    nf = left.size
    cell = np.concatenate((left, right))
    face = np.concatenate((np.arange(nf), np.arange(nf)))
    sign = np.concatenate((np.ones(nf, F), -np.ones(nf, F)))
    order = np.lexsort((face, cell))
    ptr = np.zeros(ncells + 1, np.int32)
    np.add.at(ptr, cell + 1, 1)
    return np.cumsum(ptr, dtype=np.int32), face[order].astype(np.int32), sign[order]


def grid_of(n: int) -> tuple[int]:
    return (max((n + THREADS - 1) // THREADS, 1),)


class PolyGpuState:
    """The arrays of a polygon mesh's state and work on the device, the ghosts at the end; the kernels of
    ``poly.cu`` compiled for this mesh's cell size and table rows."""

    def __init__(self, mesh: PolyMesh, num: Numerics) -> None:
        import cupy as cp

        if mesh.dn is None:
            raise ValueError("finish the mesh before stepping it")
        self.cp = cp
        self.mesh = mesh
        self.num = num
        self.rec = NumericsRecord.from_config(num, mesh.dx)
        self.nreal = mesh.real
        nc, nf = mesh.ncells, mesh.nfaces
        self.ncells = nc
        z = cp.zeros
        self.h, self.d, self.src, self.r = z(nc, F), z(nc, F), z(nc, F), cp.ones(nc, F)
        self.om = cp.ones(nc, F)
        self.Ux, self.Uy, self.Rx, self.Ry, self.Gx, self.Gy = (z(nc, F) for _ in range(6))
        self.out, self.div, self.res = z(nc, F), z(nc, F), z(nc, F)
        self.u, self.m, self.q, self.u1, self.m1, self.q1, self.Dl = (z(nf, F) for _ in range(7))
        self.wave = z(1, F)
        m = mesh
        self.area = cp.asarray(m.area.astype(F))
        self.cx, self.cy = cp.asarray(m.cx.astype(F)), cp.asarray(m.cy.astype(F))
        self.L, self.R = cp.asarray(m.left.astype(np.int32)), cp.asarray(m.right.astype(np.int32))
        self.static = tuple(
            cp.asarray(a.astype(F))
            for a in (m.length, m.nx, m.ny, m.xf, m.yf, m.dn, m.sx, m.sy, m.fl, m.fr, m.gl, m.gr, m.ef, m.cw)
        )
        self.ftab = cp.asarray(m.ftab.astype(F).reshape(-1))
        self.dzl, self.dzr = cp.asarray(m.dzl.astype(F)), cp.asarray(m.dzr.astype(F))
        self.hc, self.dtab = cp.asarray(m.hc.astype(F)), cp.asarray(m.dtab.astype(F).reshape(-1))
        ptr, face, sign = cell_faces(m.left, m.right, nc)
        self.ptr, self.cf, self.cs = cp.asarray(ptr), cp.asarray(face), cp.asarray(sign)
        source = header() + (KERNELS / "common.cuh").read_text(encoding="utf-8") + "\n"
        source += (KERNELS / "poly.cu").read_text(encoding="utf-8") + f"\n// strip at {mesh.dx} m, {m.rows} rows\n"
        self.module = load_module(cp, source, self.rec, mesh.dx, m.rows)
        self.k = {n: self.module.get_function(n) for n in (
            "poly_levels", "poly_sums", "poly_rates", "poly_faces", "poly_limit", "poly_scale", "poly_update",
            "poly_ghost_src", "poly_edges", "poly_mirror", "poly_restore", "poly_cell_maxima", "poly_face_maxima",
            "poly_tally", "poly_accumulate",
        )}  # fmt: skip

    # ---- host views
    def host(self, name: str) -> np.ndarray:
        return self.cp.asnumpy(getattr(self, name))

    def set_real(self, name: str, values: np.ndarray) -> None:
        getattr(self, name)[: self.nreal] = self.cp.asarray(np.asarray(values, F))

    def face_arrays(self) -> dict:
        """The per-face arrays a face rebuild writes (W69, a breach on strip faces), by name; the device arrays."""
        fl, fr, gl, gr, ef, cw = self.static[8:14]
        return {"fl": fl, "fr": fr, "gl": gl, "gr": gr, "ef": ef, "cw": cw, "ftab": self.ftab, "dzl": self.dzl, "dzr": self.dzr}

    # ---- launches
    def levels(self) -> None:
        nf = self.mesh.nfaces
        fl, fr = self.static[8], self.static[9]
        self.k["poly_levels"](grid_of(nf), (THREADS,), (nf, self.L, self.R, fl, fr, self.h, self.d, self.Dl))

    def sums(self, ghost, flags, zmin_t, h_t, d_t, qx_t, qy_t) -> None:
        nc = self.ncells
        ln, nfx, nfy, xf, yf = self.static[:5]
        self.k["poly_sums"](
            grid_of(nc), (THREADS,),
            (nc, self.nreal, self.ptr, self.cf, self.cs, xf, yf, self.cx, self.cy, ln, nfx, nfy, self.q, self.h,
             self.area, self.Dl, ghost, *flags, zmin_t, h_t, d_t, qx_t, qy_t, self.Ux, self.Uy, self.Gx, self.Gy),
        )  # fmt: skip

    def rates(self, ghost, flags, h_t, qx_t, qy_t) -> None:
        nc = self.ncells
        self.k["poly_rates"](
            grid_of(nc), (THREADS,),
            (nc, self.nreal, self.ptr, self.cf, self.cs, self.L, self.R, self.q, self.Ux, self.Uy, ghost, *flags,
             h_t, qx_t, qy_t, self.Rx, self.Ry),
        )  # fmt: skip

    def faces(self, dt: float, want_wave: bool) -> None:
        nf = self.mesh.nfaces
        if want_wave:
            self.wave[:] = 0.0
        self.k["poly_faces"](
            grid_of(nf), (THREADS,),
            (nf, F(dt), int(want_wave), self.L, self.R, *self.static, self.ftab, self.dzl, self.dzr, self.area, self.cx, self.cy,
             self.h, self.d, self.om, self.u, self.m, self.q, self.Ux, self.Uy, self.Rx, self.Ry, self.Gx, self.Gy,
             self.Dl, self.u1, self.m1, self.q1, self.wave),
        )  # fmt: skip

    def limit(self, dt_tile: float, dt: float, ghost, h_t, r_t, qx1_t, qy1_t, given) -> None:
        nc = self.ncells
        self.k["poly_limit"](
            grid_of(nc), (THREADS,),
            (nc, self.nreal, F(dt_tile), F(dt), self.ptr, self.cf, self.cs, self.q1, self.h, self.area, ghost, h_t, r_t,
             qx1_t, qy1_t, given, self.out, self.r),
        )  # fmt: skip

    def accumulate(self, ghost, dt: float, dt_tile: float, div_acc, given, q_mean) -> None:
        ng, nf = int(ghost.size), self.mesh.nfaces
        self.k["poly_accumulate"](
            grid_of(max(ng, nf)), (THREADS,),
            (ng, nf, self.nreal, F(dt), F(dt / dt_tile), self.div, self.q, div_acc, given, q_mean),
        )  # fmt: skip

    def update(self, dt: float, want_wave: bool) -> None:
        nf, nc = self.mesh.nfaces, self.ncells
        self.k["poly_scale"](grid_of(nf), (THREADS,), (nf, self.L, self.R, self.q1, self.r, self.q))
        self.k["poly_update"](
            grid_of(nc), (THREADS,),
            (nc, self.nreal, F(dt), int(want_wave), self.ptr, self.cf, self.cs, self.area, self.hc, self.dtab,
             self.q, self.src, self.div, self.res, self.h, self.d, self.om),
        )  # fmt: skip
        self.u, self.u1 = self.u1, self.u
        self.m, self.m1 = self.m1, self.m

    def ghost_src(self, ghost, saved, src_t, div_acc, dt_tile: float) -> None:
        ng = int(ghost.size)
        if ng:
            self.k["poly_ghost_src"](grid_of(ng), (THREADS,), (ng, self.nreal, ghost, div_acc, F(dt_tile), saved, src_t))

    def edges(self, nslot: int, maps: tuple, discharge, velocity, q_mean) -> None:
        if nslot:
            self.k["poly_edges"](grid_of(nslot), (THREADS,), (nslot, self.nreal, *maps, q_mean, self.h, discharge, velocity))

    def mirror(self, ghost, h_t, d_t, om_t) -> None:
        ng = int(ghost.size)
        if ng:
            self.k["poly_mirror"](grid_of(ng), (THREADS,), (ng, self.nreal, ghost, h_t, d_t, om_t, self.h, self.d, self.om))

    def restore(self, ghost, saved, src_t) -> None:
        ng = int(ghost.size)
        if ng:
            self.k["poly_restore"](grid_of(ng), (THREADS,), (ng, ghost, saved, src_t))

    def maxima(self, speed_depth: float, max_d, max_h, max_s, max_dv, max_q) -> None:
        n, nf = self.nreal, self.mesh.nfaces
        self.k["poly_cell_maxima"](grid_of(n), (THREADS,), (n, F(speed_depth), self.d, self.h, self.Ux, self.Uy, max_d, max_h, max_s, max_dv))
        self.k["poly_face_maxima"](grid_of(nf), (THREADS,), (nf, self.q, max_q))

    def tally(self, faces, ghosts, dt: float, left, left_ghost) -> None:
        nb = int(faces.size)
        if nb:
            self.k["poly_tally"](grid_of(nb), (THREADS,), (nb, faces, ghosts, self.q, F(dt), left, left_ghost))


__all__ = ["PolyGpuState", "cell_faces"]
