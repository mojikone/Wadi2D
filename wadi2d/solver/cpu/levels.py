"""Numba twin of solver/gpu/kernels/levels.cu: same statement order, same float32 arithmetic."""

from __future__ import annotations

import numpy as np
from numba import njit

from wadi2d.solver.cpu.kernels import ZERO, F, face_step, scaled
from wadi2d.solver.layout import HALO, STRIDE, STRIDE2, TILE, TILE2


@njit(inline="always")
def edge_face(t, side, q):
    base = t * STRIDE2
    if side == 0:
        return base + (q + HALO) * STRIDE + HALO
    if side == 1:
        return base + HALO * STRIDE + q + HALO
    if side == 2:
        return base + (q + HALO) * STRIDE + HALO + TILE
    return base + (HALO + TILE) * STRIDE + q + HALO


@njit(inline="always")
def edge_cell(c, side, q):
    base = c * STRIDE2
    if side == 0:
        return base + (q + HALO) * STRIDE + HALO + TILE - 1
    if side == 1:
        return base + (HALO + TILE - 1) * STRIDE + q + HALO
    if side == 2:
        return base + (q + HALO) * STRIDE + HALO
    return base + HALO * STRIDE + q + HALO


@njit
def strips(
    edges, dt, want_wave, om, h, d, u, v, mx, my, qx, qy, flx, frx, glx, grx, efx, cwx, ftabx, fly, fry, gly, gry, efy,
    cwy, ftaby, u1, v1, mx1, my1, qx1, qy1, wave, rows, g, dx, e_wet, h_cfl, u_max, lead, a_min, second, sheet, mirror,
):  # fmt: skip
    for n in range(edges.shape[0]):
        fine, side, t = edges[n, 0], edges[n, 1], edges[n, 2]
        for q in range(TILE):
            if side == 2:
                k = t * STRIDE2 + (q + HALO) * STRIDE + HALO
                fid = t * TILE2 + q * TILE
                w = face_step(
                    k, fid, dt, want_wave, om, 1, STRIDE, h, d, u, mx, qx, qy, v, flx, frx, glx, grx, efx, cwx, ftabx,
                    u1, mx1, qx1, rows, g, dx, e_wet, h_cfl, u_max, lead, a_min, second, sheet, mirror,
                )  # fmt: skip
            else:
                k = t * STRIDE2 + HALO * STRIDE + q + HALO
                fid = t * TILE2 + q
                w = face_step(
                    k, fid, dt, want_wave, om, STRIDE, 1, h, d, v, my, qy, qx, u, fly, fry, gly, gry, efy, cwy, ftaby,
                    v1, my1, qy1, rows, g, dx, e_wet, h_cfl, u_max, lead, a_min, second, sheet, mirror,
                )  # fmt: skip
            if want_wave:
                wave[t] = max(wave[t], w)
                wave[fine] = max(wave[fine], w)


@njit
def halo_levels(active, slot, src, nhalo, level, n, h, h0, d, d0, u, v, qx, qy):
    for x in range(active.size):
        t = active[x]
        for m in range(nhalo):
            dst = t * STRIDE2 + slot[m]
            s = src[(t - 1) * nhalo + m]
            span = 1 << level[s // STRIDE2]
            part = n & (span - 1)
            if part == 0:
                h[dst] = h[s]
                d[dst] = d[s]
            else:
                w = F(part) / F(span)
                h[dst] = h0[s] + w * (h[s] - h0[s])
                d[dst] = d0[s] + w * (d[s] - d0[s])
            u[dst] = u[s]
            v[dst] = v[s]
            qx[dst] = qx[s]
            qy[dst] = qy[s]


@njit
def save_old(active, h, d, h0, d0):
    for x in range(active.size):
        t = active[x]
        for j in range(TILE):
            for i in range(TILE):
                k = t * STRIDE2 + (j + HALO) * STRIDE + i + HALO
                h0[k] = h[k]
                d0[k] = d[k]


@njit
def commit(active, u1, v1, mx1, my1, u, v, mx, my):
    for x in range(active.size):
        t = active[x]
        for j in range(TILE):
            for i in range(TILE):
                k = t * STRIDE2 + (j + HALO) * STRIDE + i + HALO
                u[k] = u1[k]
                v[k] = v1[k]
                mx[k] = mx1[k]
                my[k] = my1[k]


@njit
def commit_strips(edges, u1, v1, mx1, my1, u, v, mx, my):
    for n in range(edges.shape[0]):
        t = edges[n, 2]
        for q in range(TILE):
            if edges[n, 1] == 2:
                k = t * STRIDE2 + (q + HALO) * STRIDE + HALO
                u[k] = u1[k]
                mx[k] = mx1[k]
            else:
                k = t * STRIDE2 + HALO * STRIDE + q + HALO
                v[k] = v1[k]
                my[k] = my1[k]


@njit
def edge_estimate(edges, qx1, qy1, r, est):
    for n in range(edges.shape[0]):
        side = edges[n, 1]
        for q in range(TILE):
            k = edge_face(edges[n, 0], side, q)
            s = STRIDE if side & 1 else 1
            f = qy1[k] if side & 1 else qx1[k]
            est[edges[n, 3] * TILE + q] = scaled(f, r[k - s], r[k])


@njit
def edge_flux(edges, dt, qx1, qy1, r, est, res, qx, qy, dx):
    for n in range(edges.shape[0]):
        side, c = edges[n, 1], edges[n, 2]
        for q in range(TILE):
            k = edge_face(edges[n, 0], side, q)
            s = STRIDE if side & 1 else 1
            f = qy1[k] if side & 1 else qx1[k]
            qs = scaled(f, r[k - s], r[k])
            sign = F(-1.0) if side < 2 else F(1.0)
            res[edge_cell(c, side, q)] += sign * dt * (qs - est[edges[n, 3] * TILE + q]) / (dx * dx)
            if side == 2:
                qx[c * STRIDE2 + (q + HALO) * STRIDE + HALO] = qs
            if side == 3:
                qy[c * STRIDE2 + HALO * STRIDE + q + HALO] = qs


class CpuLevels:
    """The level stepper's operations on the CPU; ``GpuLevels`` is the same on the device.

    ``size`` is a tile's cell size as a level: the cell is 2^size finest cells wide, and only the numbers change.
    """

    def __init__(self, backend) -> None:
        self.b = backend
        grid = backend.grid
        n = grid.ntiles
        self.h0 = np.zeros(n * STRIDE2, np.float32)
        self.d0 = np.zeros(n * STRIDE2, np.float32)
        self.est = np.zeros(4 * n * TILE, np.float32)
        self.level = np.zeros(n, np.int32)
        self.quad = getattr(grid, "quad", False)
        if self.quad:
            from wadi2d.grid.quad import halo_maps

            maps = halo_maps(grid)
            self.fu, self.fv = maps["u"].ravel(), maps["v"].ravel()
            self.qu, self.qv = maps["qu"].ravel(), maps["qv"].ravel()
            self.cell = maps["cell"].ravel()
            self.iest = np.zeros(max(grid.interfaces.shape[0], 1) * (TILE // 2), np.float32)

    def dx(self, size: int) -> np.float32:
        return np.float32(self.b.num.dx * (1 << size))

    def args(self, size: int) -> tuple:
        rows, g, _dx, *rest = self.b._args
        return (rows, g, self.dx(size), *rest)

    def lists(self, a: np.ndarray) -> np.ndarray:
        return a

    def set_level(self, level: np.ndarray) -> None:
        self.level[:] = level

    def halo_state(self, tiles, n: int, want_plan: bool) -> None:
        b = self.b
        if self.quad:
            from wadi2d.solver.cpu.quad import quad_halo

            quad_halo(
                tiles, b.slot, self.cell, self.fu, self.fv, self.qu, self.qv, b.nhalo, self.level, n, b.h, self.h0,
                b.d, self.d0, b.u, b.v, b.qx, b.qy,
            )  # fmt: skip
        else:
            halo_levels(
                tiles,
                b.slot,
                b.src_map,
                b.nhalo,
                self.level,
                n,
                b.h,
                self.h0,
                b.d,
                self.d0,
                b.u,
                b.v,
                b.qx,
                b.qy,
            )
        if want_plan:
            self.exch(tiles, b.om)

    def exch(self, tiles, *arrays) -> None:
        from wadi2d.solver.cpu.kernels import exchange

        b = self.b
        for a in arrays:
            exchange(tiles, b.slot, b.src_map, b.nhalo, a)

    def clear_wave(self) -> None:
        self.b.wave[:] = ZERO

    def clear_wet(self) -> None:
        self.b.wet[:] = 0

    def faces(self, tiles, dt: float, want_wave: bool, size: int = 0) -> None:
        from wadi2d.solver.cpu import kernels

        b = self.b
        kernels.faces(
            tiles, np.float32(dt), want_wave, b.om, b.h, b.d, b.u, b.v, b.mx, b.my, b.qx, b.qy,
            *b.static_x, b.ftabx, *b.static_y, b.ftaby,
            b.u1, b.v1, b.mx1, b.my1, b.qx1, b.qy1, b.wave, *self.args(size),
        )  # fmt: skip

    def strips(self, edges, dt: float, want_wave: bool, size: int = 0) -> None:
        b = self.b
        strips(
            edges, np.float32(dt), want_wave, b.om, b.h, b.d, b.u, b.v, b.mx, b.my, b.qx, b.qy,
            *b.static_x, b.ftabx, *b.static_y, b.ftaby,
            b.u1, b.v1, b.mx1, b.my1, b.qx1, b.qy1, b.wave, *self.args(size),
        )  # fmt: skip

    def iface_faces(self, rows, dt: float, want_wave: bool, size: int) -> None:
        from wadi2d.solver.cpu.quad import iface_faces

        b = self.b
        iface_faces(
            rows, np.float32(dt), want_wave, b.om, b.h, b.d, b.u, b.v, b.mx, b.my, b.qx, b.qy,
            *b.static_x, b.ftabx, *b.static_y, b.ftaby,
            b.u1, b.v1, b.mx1, b.my1, b.qx1, b.qy1, b.wave, *self.args(size),
        )  # fmt: skip

    def faces_done(self, tiles) -> None:
        b = self.b
        if self.quad:
            from wadi2d.solver.cpu.quad import quad_faces_done

            quad_faces_done(tiles, b.slot, self.fu, self.fv, b.nhalo, b.u1, b.v1, b.qx1, b.qy1)
        else:
            self.exch(tiles, b.u1, b.v1, b.qx1, b.qy1)

    def iface_load(self, rows) -> None:
        from wadi2d.solver.cpu.quad import iface_load

        b = self.b
        iface_load(rows, b.u1, b.v1, b.qx1, b.qy1)

    def limit(self, tiles, dt: float, size: int = 0) -> None:
        from wadi2d.solver.cpu import kernels

        b = self.b
        kernels.limit(tiles, np.float32(dt), b.h, b.qx1, b.qy1, b.r, self.dx(size))

    def limit_done(self, tiles) -> None:
        self.exch(tiles, self.b.r)

    def save(self, tiles) -> None:
        save_old(tiles, self.b.h, self.b.d, self.h0, self.d0)

    def estimate(self, edges) -> None:
        b = self.b
        edge_estimate(edges, b.qx1, b.qy1, b.r, self.est)

    def flux(self, edges, dt: float, size: int = 0) -> None:
        b = self.b
        edge_flux(edges, np.float32(dt), b.qx1, b.qy1, b.r, self.est, b.res, b.qx, b.qy, self.dx(size))

    def iface_estimate(self, rows, dt: float, size: int) -> None:
        from wadi2d.solver.cpu.quad import iface_estimate

        b = self.b
        iface_estimate(rows, np.float32(dt), b.qx1, b.qy1, b.r, self.iest, b.res, self.dx(size))

    def iface_flux(self, rows, dt: float, size: int) -> None:
        from wadi2d.solver.cpu.quad import iface_flux

        b = self.b
        iface_flux(rows, np.float32(dt), b.qx1, b.qy1, b.r, self.iest, b.res, self.dx(size))

    def iface_store(self, rows) -> None:
        from wadi2d.solver.cpu.quad import iface_store

        b = self.b
        iface_store(rows, b.qx1, b.qy1, b.r, b.u1, b.v1, b.mx1, b.my1, b.u, b.v, b.mx, b.my, b.qx, b.qy)

    def update(self, tiles, dt: float, want_wet: bool, want_plan: bool, size: int = 0) -> None:
        from wadi2d.solver.cpu import kernels

        b = self.b
        kernels.update(
            tiles, np.float32(dt), want_plan, True, b.res, b.om, b.qx1, b.qy1, b.r, b.src, b.Hc, b.dtab, b.h, b.d,
            b.qx, b.qy, b.wet, b.rows, self.dx(size),
        )  # fmt: skip

    def boundary(self) -> None:
        from wadi2d.solver.cpu import kernels

        c = self.b.bc
        if c.cell.size:
            kernels.boundary(c.cell, c.ref, c.kind, c.d0, c.h0, self.b.h, self.b.d)

    def commit(self, tiles) -> None:
        b = self.b
        commit(tiles, b.u1, b.v1, b.mx1, b.my1, b.u, b.v, b.mx, b.my)

    def commit_strips(self, edges) -> None:
        b = self.b
        commit_strips(edges, b.u1, b.v1, b.mx1, b.my1, b.u, b.v, b.mx, b.my)

    def wave(self) -> np.ndarray:
        return self.b.wave.copy()
