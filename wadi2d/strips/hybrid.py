# Wadi2D. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The hybrid step on the CPU: square tiles and a polygon strip in one time step (W45, stage 3).

The tile backend steps its faces and positivity as ever; in its ``before_update`` hook the strip mirrors the tile
cells it touches into its ghost entries (mean depth, level, wet share), adds those cells' lattice faces to the Perot
and Green-Gauss sums, steps its own faces, limits its outflows (a real cell gives what it holds; a ghost gives what its
lattice faces left it, so the books close), updates its real cells, and hands each ghost's net outflow to the tile
update as a source term; ``after_update`` restores the sources and writes each interface's discharge and velocity
into the tile's closed face on that edge, own slot and halo copies, so the next tile step's momentum stencil sees
the flow the strip carries across. One global time step: the smaller of the tile rule and the strip's. Tiles that
hold a ghost are always stepped.

What a ghost's lattice faces add [Likely the right form; measured by the stage gate]: the Perot sum of a square from its
four face discharges, the Green-Gauss gradient from its open wet faces' level differences, and the advection rate from its four lattice
faces' outflows times the upwind velocity, a neighbour's taken from that neighbour's own four faces.
"""

from __future__ import annotations

import numpy as np
from numba import njit

from wadi2d.solver.layout import CLOSED, HALO, STRIDE, STRIDE2, TILE
from wadi2d.solver.model import Model
from wadi2d.solver.poly import kernel
from wadi2d.solver.poly.mesh import PolyMesh
from wadi2d.solver.poly.model import PolyState
from wadi2d.solver.state import exchange_map, level_of, plan_of, state_index
from wadi2d.strips.geometry import MeshGeometry
from wadi2d.strips.tables import Ghosts
from wadi2d.tables.builder import GridTables, hbar_at_level

F = np.float32
ZERO, HALF = F(0.0), F(0.5)


@njit(cache=True)
def ghost_sums(ng, nreal, ghost, dx, open_w, open_e, open_n, open_s, zmin, h, d, qx, qy, Ux, Uy, Gx, Gy) -> None:
    """A ghost's lattice part of the Perot sum and of the Green-Gauss sum, before the strip's faces add theirs."""
    for g in range(ng):
        c = nreal + g
        k = ghost[g]
        Ux[c] += HALF * dx * (qx[k] + qx[k + 1])
        Uy[c] -= HALF * dx * (qy[k] + qy[k + STRIDE])
        eta = zmin[k] + d[k]
        if open_w[g] and h[k - 1] > ZERO and h[k] > ZERO:
            Gx[c] += HALF * (eta - (zmin[k - 1] + d[k - 1])) * dx
        if open_e[g] and h[k + 1] > ZERO and h[k] > ZERO:
            Gx[c] += HALF * ((zmin[k + 1] + d[k + 1]) - eta) * dx
        if open_n[g] and h[k - STRIDE] > ZERO and h[k] > ZERO:
            Gy[c] -= HALF * (eta - (zmin[k - STRIDE] + d[k - STRIDE])) * dx
        if open_s[g] and h[k + STRIDE] > ZERO and h[k] > ZERO:
            Gy[c] -= HALF * ((zmin[k + STRIDE] + d[k + STRIDE]) - eta) * dx


@njit(cache=True)
def ghost_rates(ng, nreal, ghost, dx, open_w, open_e, open_n, open_s, h, qx, qy, Ux, Uy, Rx, Ry) -> None:
    """A ghost's lattice part of the advection rate: each lattice face's outflow times the upwind velocity, the
    ghost's own (complete by now) or the neighbour's Perot velocity from that neighbour's four lattice faces."""
    for g in range(ng):
        c = nreal + g
        k = ghost[g]
        # west face: inflow when qx[k] > 0
        for side in range(4):
            if side == 0:
                opened, q_out, n = open_w[g], -qx[k], k - 1
            elif side == 1:
                opened, q_out, n = open_e[g], qx[k + 1], k + 1
            elif side == 2:
                opened, q_out, n = open_n[g], -qy[k], k - STRIDE
            else:
                opened, q_out, n = open_s[g], qy[k + STRIDE], k + STRIDE
            if not opened or q_out == ZERO:
                continue
            if q_out > ZERO:
                ux, uy = Ux[c], Uy[c]
            else:
                vol = h[n] * dx * dx
                if vol > F(1e-9):
                    ux = HALF * dx * (qx[n] + qx[n + 1]) / vol
                    uy = -HALF * dx * (qy[n] + qy[n + STRIDE]) / vol
                else:
                    ux, uy = ZERO, ZERO
            Rx[c] += q_out * ux
            Ry[c] += q_out * uy


@njit(cache=True)
def ghost_ratios(ng, nreal, ghost, dt, dx, h, r_tile, qx1, qy1, out, r) -> None:
    """A ghost gives through the strip's faces at most what its lattice faces, which come first, left it."""
    area = dx * dx
    for g in range(ng):
        c = nreal + g
        k = ghost[g]
        lattice = max(qx1[k + 1], ZERO) + max(-qx1[k], ZERO) + max(qy1[k + STRIDE], ZERO) + max(-qy1[k], ZERO)
        have = max(h[k], ZERO) * area
        avail = max(have - dt * r_tile[k] * lattice, ZERO)
        o = out[c]
        r[c] = avail / (o * dt) if o * dt > avail else F(1.0)


class HybridCpu:
    """A tile model and a strip stepped together; installs itself as the tile backend's hooks."""

    def __init__(self, model: Model, mesh: PolyMesh) -> None:
        if model.backend.name != "cpu":
            raise ValueError("the hybrid step runs on the CPU backend in stage 3")
        if mesh.ghost_state is None:
            raise ValueError("the strip has no ghosts: build its tables with the tile cells it touches")
        self.model = model
        self.mesh = mesh
        self.state = PolyState(mesh, model.num)
        self.ghost = np.asarray(mesh.ghost_state, np.int64)
        self.nreal = mesh.real
        grid, tables = model.grid, model.tables
        self.dx = F(grid.dx)
        self.zmin_state = model.host.to_state(tables.zmin)
        flx, fly = grid.from_tiles(tables.flx), grid.from_tiles(tables.fly)
        j, i = self.cells_of(self.ghost)
        ny, nx = grid.shape
        self.open_w = flx[j, i] < CLOSED
        self.open_e = np.where(i + 1 < nx, flx[j, np.minimum(i + 1, nx - 1)] < CLOSED, False)
        self.open_n = fly[j, i] < CLOSED
        self.open_s = np.where(j + 1 < ny, fly[np.minimum(j + 1, ny - 1), i] < CLOSED, False)
        self.saved = np.zeros(self.ghost.size, F)
        self._edges(mesh, grid)
        b = model.backend
        b.hooks = self
        tiles = np.unique(self.ghost // STRIDE2)
        model.stepper.keep_active[tiles] = True
        model.stepper.rebuild_active(retain=True)

    def _edges(self, mesh: PolyMesh, grid) -> None:
        """Each interface face's closed tile face: its state slot, the sign between the strip's normal and the
        lattice's eastward or southward discharge, and every state copy of that slot (own and halos)."""
        n = self.nreal
        iface = np.nonzero(mesh.right >= n)[0]
        g = self.ghost[mesh.right[iface] - n]
        nx, ny = mesh.nx[iface], mesh.ny[iface]
        east, west, south, north = nx > 0.5, nx < -0.5, ny < -0.5, ny > 0.5
        if not np.all(east | west | south | north):
            raise ValueError("an interface face must lie on a lattice edge")
        slot = np.where(east, g, np.where(west, g + 1, np.where(south, g, g + STRIDE)))
        sign = np.where(east | south, 1.0, -1.0).astype(F)
        dst, src = exchange_map(grid)
        copies: dict[int, list[int]] = {}
        for d_, s_ in zip(dst.tolist(), src.tolist(), strict=True):
            copies.setdefault(s_, []).append(d_)
        self.edge = {}
        for axis, on in (("x", east | west), ("y", south | north)):
            faces, slots, signs = iface[on], slot[on], sign[on]
            unique, group = np.unique(slots, return_inverse=True)
            all_copies = np.array([k for u in unique.tolist() for k in [u, *copies.get(u, [])]], np.int64)
            owner = np.array([m for m, u in enumerate(unique.tolist()) for _ in [u, *copies.get(u, [])]], np.int64)
            ghost_of = np.zeros(unique.size, np.int64)
            ghost_of[group] = self.ghost_slot(mesh, faces, n)
            self.edge[axis] = (faces, group, signs, unique, all_copies, owner, ghost_of)

    def ghost_slot(self, mesh: PolyMesh, faces: np.ndarray, n: int) -> np.ndarray:
        return mesh.right[faces] - n

    def cells_of(self, index: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Grid (j, i) of state indices."""
        grid = self.model.grid
        index = np.asarray(index, np.int64)
        t = index // STRIDE2
        rem = index % STRIDE2
        oj, oi = rem // STRIDE - HALO, rem % STRIDE - HALO
        return grid.tiles[t, 0] * TILE + oj, grid.tiles[t, 1] * TILE + oi

    # ---- the strip's own state
    def set_strip_depth(self, hbar: np.ndarray) -> None:
        m, s = self.mesh, self.state
        n = self.nreal
        s.h[:n] = np.asarray(hbar, F)
        s.d[:n] = level_of(s.h[:n].astype(np.float64), m.hc[:n], m.dtab[:n])
        s.om[:n] = plan_of(s.h[:n].astype(np.float64), m.hc[:n], m.dtab[:n])
        self.model.stepper.refresh_due = True

    def strip_hbar_at_level(self, level: float | np.ndarray) -> np.ndarray:
        m, n = self.mesh, self.nreal
        return hbar_at_level(level, m.zmin[:n], m.hc[:n], m.dtab[:n])

    def set_strip_source(self, rate: np.ndarray) -> None:
        self.state.src[: self.nreal] = np.asarray(rate, F)

    def strip_volume(self) -> float:
        """Water in the strip, the clamp residual of each cell included, as the tiles count theirs."""
        n, s = self.nreal, self.state
        return float(np.sum((s.h[:n].astype(np.float64) + s.res[:n]) * self.mesh.area[:n]))

    def volume(self) -> float:
        return self.model.volume() + self.strip_volume()

    def advance(self, t_end: float, on_step=None) -> float:
        return self.model.advance(t_end, on_step)

    # ---- the run's hooks
    def attach(self, monitor, strip, lines) -> None:
        """The strip's water in the balance, and its faces in every result line that crosses it."""
        from wadi2d.strips.build import line_crossings

        monitor.extra_storage.append(self.strip_volume)
        for n, line in enumerate(lines):
            faces, signs = line_crossings(strip.strip.geometry, strip.kept, strip.mesh, line.coordinates)
            if faces.size:
                monitor.extra_lines.setdefault(n, []).append(self._line_flow(faces, signs))

    def _line_flow(self, faces: np.ndarray, signs: np.ndarray):
        def flow() -> float:
            return float(np.dot(self.state.q[faces].astype(np.float64), signs))

        return flow

    def rain(self, rate: np.ndarray, step: float) -> float:
        """Uniform rain on the strip at the lattice's own rate; returns the volume of the window, m3."""
        r = float(rate.max()) if rate.size else 0.0
        n = self.nreal
        self.state.src[:n] = F(r)
        return r * float(self.mesh.area[:n].sum()) * step

    # ---- the hooks
    def before_update(self, dt: float, want_wave: bool) -> None:
        b, s, n, g = self.model.backend, self.state, self.nreal, self.ghost
        s.h[n:] = b.h[g]
        s.d[n:] = b.d[g]
        s.om[n:] = b.om[g]
        s.zero_vectors()
        ghost_sums(
            g.size, n, g, self.dx, self.open_w, self.open_e, self.open_n, self.open_s, self.zmin_state,
            b.h, b.d, b.qx, b.qy, s.Ux, s.Uy, s.Gx, s.Gy,
        )  # fmt: skip
        def rates() -> None:
            ghost_rates(
                g.size, n, g, self.dx, self.open_w, self.open_e, self.open_n, self.open_s, b.h, b.qx, b.qy,
                s.Ux, s.Uy, s.Rx, s.Ry,
            )  # fmt: skip

        s.step_faces(dt, want_wave, rates)
        L, R = s.static[0], s.static[1]
        kernel.outflows(s.mesh.nfaces, s.ncells, L, R, s.q1, s.out)
        kernel.positivity(n, F(dt), s.h, s.area, s.out, s.r)
        ghost_ratios(g.size, n, g, F(dt), self.dx, b.h, b.r, b.qx1, b.qy1, s.out, s.r)
        kernel.update(
            s.mesh.nfaces, s.ncells, n, F(dt), want_wave, L, R, s.area, s.hc, s.dtab, s.q1, s.r, s.src, s.div,
            s.res, s.h, s.d, s.om, s.q, s.nums[0],
        )  # fmt: skip
        s.u, s.u1 = s.u1, s.u
        s.m, s.m1 = s.m1, s.m
        self.saved[:] = b.src[g]
        b.src[g] = self.saved - s.div[n:] / (self.dx * self.dx)
        if want_wave:
            b.extra_wave = s.wave * float(self.dx)

    def after_update(self, dt: float, want_wave: bool) -> None:
        b, s, n = self.model.backend, self.state, self.nreal
        b.src[self.ghost] = self.saved
        dx = float(self.dx)
        for axis, (faces, group, signs, unique, all_copies, owner, ghost_of) in self.edge.items():
            if faces.size == 0:
                continue
            q_edge = np.zeros(unique.size, np.float64)
            np.add.at(q_edge, group, s.q[faces].astype(np.float64) * signs)
            depth = np.maximum(s.h[n + ghost_of].astype(np.float64), 1e-6)
            speed = q_edge / (depth * dx)
            discharge, velocity = (b.qx, b.u1) if axis == "x" else (b.qy, b.v1)
            discharge[unique] = q_edge.astype(F)
            velocity[all_copies] = speed[owner].astype(F)


def ghosts_for(geo: MeshGeometry, grid_or_model, tables: GridTables) -> Ghosts:
    """The tile cells the geometry's boundary faces open onto: half a cell out along each face's outward normal, an
    active tile cell makes that face an interface; a wall or the void makes it a wall."""
    grid = getattr(grid_or_model, "grid", grid_or_model)
    _area, cx, cy = geo.areas_centroids()
    _length, nfx, nfy, xf, yf = geo.faces(cx, cy)
    boundary = np.nonzero(geo.face_cell[:, 1] < 0)[0]
    px, py = xf[boundary] + 0.5 * grid.dx * nfx[boundary], yf[boundary] + 0.5 * grid.dx * nfy[boundary]
    i = np.floor((px - grid.x0) / grid.dx).astype(np.int64)
    j = np.floor((grid.y0 - py) / grid.dx).astype(np.int64)
    ny, nx = grid.shape
    inside = (i >= 0) & (i < nx) & (j >= 0) & (j < ny)
    active = np.zeros(boundary.size, bool)
    active[inside] = grid.mask[j[inside], i[inside]]
    face_slot = np.full(geo.nfaces, -1, np.int64)
    cells = sorted({(int(a), int(b)) for a, b, on in zip(j, i, active, strict=True) if on})
    slot_of = {c: k for k, c in enumerate(cells)}
    for f, jj, ii, on in zip(boundary, j, i, active, strict=True):
        if on:
            face_slot[f] = slot_of[(int(jj), int(ii))]
    jj = np.array([c[0] for c in cells], np.int64)
    ii = np.array([c[1] for c in cells], np.int64)
    state = np.asarray(state_index(grid, jj, ii), np.int64) if jj.size else np.zeros(0, np.int64)
    gx, gy = grid.xy_of(jj, ii)
    hc, dtab = grid.from_tiles(tables.hc), grid.from_tiles(tables.dtab)
    return Ghosts(
        face_slot, state, gx.astype(np.float64), gy.astype(np.float64), tables.zmin[jj, ii].astype(np.float64),
        tables.zbar[jj, ii].astype(np.float64), hc[jj, ii].astype(np.float64), dtab[jj, ii].astype(np.float64),
        np.full(jj.size, grid.dx * grid.dx),
    )  # fmt: skip
