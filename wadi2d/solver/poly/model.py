# Wadi2D. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A model on a polygon mesh alone, on the CPU: the stage-1 harness of the strip path (W45).

It owns the state arrays (depth and level per cell, velocity, momentum and discharge per face), steps them with the
kernels of :mod:`wadi2d.solver.poly.kernel` under the lattice's own time-step rule, and reads back fields. The hybrid
stepper of stage 3 drives the same kernels beside the tiles; this class is for tests and the race.
"""

from __future__ import annotations

import numpy as np

from wadi2d.config.schema import Numerics
from wadi2d.solver.backend import NumericsRecord
from wadi2d.solver.poly import kernel
from wadi2d.solver.poly.mesh import PolyMesh
from wadi2d.solver.state import level_of, plan_of
from wadi2d.solver.stepper import NumericalFailure
from wadi2d.tables.builder import hbar_at_level

F = np.float32


class PolyState:
    """The arrays of a polygon mesh's state and work, the mesh's ghost cells (a hybrid's tile cells) at the end;
    the static arrays as the kernels take them."""

    def __init__(self, mesh: PolyMesh, num: Numerics) -> None:
        if mesh.dn is None:
            raise ValueError("finish the mesh before stepping it")
        self.mesh = mesh
        self.num = num
        self.rec = NumericsRecord.from_config(num, mesh.dx)
        self.nreal = mesh.real
        nc, nf = mesh.ncells, mesh.nfaces
        self.ncells = nc
        self.h = np.zeros(nc, F)
        self.d = np.zeros(nc, F)
        self.om = np.ones(nc, F)
        self.src = np.zeros(nc, F)
        self.r = np.ones(nc, F)
        self.Ux, self.Uy, self.Rx, self.Ry, self.Gx, self.Gy = (np.zeros(nc, F) for _ in range(6))
        self.out, self.div = np.zeros(nc, F), np.zeros(nc, F)
        self.u, self.m, self.q, self.u1, self.m1, self.q1, self.Dl = (np.zeros(nf, F) for _ in range(7))
        self.area = mesh.area.astype(F)
        self.cx, self.cy = mesh.cx.astype(F), mesh.cy.astype(F)
        m = mesh
        self.static = (
            m.left.astype(np.int64), m.right.astype(np.int64), m.length.astype(F), m.nx.astype(F), m.ny.astype(F),
            m.xf.astype(F), m.yf.astype(F), m.dn.astype(F), m.sx.astype(F), m.sy.astype(F),
            m.fl.astype(F), m.fr.astype(F), m.gl.astype(F), m.gr.astype(F), m.ef.astype(F), m.cw.astype(F),
            m.ftab.astype(F).reshape(-1),
        )  # fmt: skip
        self.hc, self.dtab = m.hc.astype(F), m.dtab.astype(F).reshape(-1)
        r = self.rec
        self.nums = (m.rows, F(r.g), F(r.dx), F(r.e_wet), F(r.h_cfl), F(r.u_max), F(r.lead), F(r.a_min), r.sheet, True)
        self.wave = 0.0

    def zero_vectors(self) -> None:
        for a in (self.Ux, self.Uy, self.Rx, self.Ry, self.Gx, self.Gy):
            a[:] = ZERO

    def step_faces(self, dt: float, refresh: bool, ghost_rates=None) -> None:
        """[3a] to [6]: the cell vectors and gradients (added to what the arrays hold), then every face.
        ``ghost_rates`` runs once the velocities are complete, to add the ghosts' lattice advection."""
        nc, nf = self.ncells, self.mesh.nfaces
        L, R, ln, nfx, nfy, xf, yf, dn, sx, sy, fl, fr, gl, gr, ef, cw, ftab = self.static
        rows, g, dx, e_wet, h_cfl, u_max, lead, a_min, sheet, skew = self.nums
        kernel.perot_velocity(nf, nc, L, R, xf, yf, self.cx, self.cy, self.q, self.h, self.area, self.Ux, self.Uy)
        if ghost_rates is not None:
            ghost_rates()
        kernel.advection_rate(nf, L, R, self.q, self.Ux, self.Uy, self.Rx, self.Ry)
        kernel.level_gradients(nf, nc, L, R, ln, nfx, nfy, fl, fr, self.h, self.d, self.area, e_wet, self.Gx, self.Gy, self.Dl)
        wave = kernel.faces(
            nf, F(dt), refresh, L, R, ln, nfx, nfy, xf, yf, dn, sx, sy, fl, fr, gl, gr, ef, cw, ftab, self.area, self.cx, self.cy,
            self.h, self.d, self.om, self.u, self.m, self.q, self.Ux, self.Uy, self.Rx, self.Ry, self.Gx, self.Gy, self.Dl,
            self.u1, self.m1, self.q1, rows, g, dx, e_wet, h_cfl, u_max, lead, a_min, sheet, skew,
        )  # fmt: skip
        if refresh:
            self.wave = float(wave)

    def step_cells(self, dt: float, refresh: bool) -> None:
        """Positivity of the real cells, the scaled discharges, and the new state of the real cells."""
        nc, nf = self.ncells, self.mesh.nfaces
        L, R = self.static[0], self.static[1]
        rows = self.nums[0]
        kernel.outflows(nf, nc, L, R, self.q1, self.out)
        kernel.positivity(self.nreal, F(dt), self.h, self.area, self.out, self.r)
        kernel.update(nf, nc, self.nreal, F(dt), refresh, L, R, self.area, self.hc, self.dtab, self.q1, self.r, self.src, self.div, self.h, self.d, self.om, self.q, rows)
        self.u, self.u1 = self.u1, self.u
        self.m, self.m1 = self.m1, self.m


ZERO = F(0.0)


class PolyModel:
    """State and stepping on one polygon mesh with no tiles: the stage-1 harness."""

    def __init__(self, mesh: PolyMesh, num: Numerics | None = None) -> None:
        self.mesh = mesh
        self.num = num or Numerics()
        self.state = PolyState(mesh, self.num)
        self.bcell = np.zeros(0, np.int64)
        self.bd0 = np.zeros(0, F)
        self.bh0 = np.zeros(0, F)
        self.t = 0.0
        self.nsteps = 0
        self.dt = self.num.cfl * mesh.dx / self.num.wave_floor
        self.refresh_due = True

    # ---- state in and out
    @property
    def h(self) -> np.ndarray:
        return self.state.h

    @property
    def d(self) -> np.ndarray:
        return self.state.d

    @property
    def u(self) -> np.ndarray:
        return self.state.u

    @property
    def q(self) -> np.ndarray:
        return self.state.q

    def hbar_at_level(self, level: float | np.ndarray) -> np.ndarray:
        m = self.mesh
        return hbar_at_level(level, m.zmin, m.hc, m.dtab)

    def set_depth(self, hbar: np.ndarray) -> None:
        m, s = self.mesh, self.state
        s.h[:] = np.asarray(hbar, F)
        s.d[:] = level_of(s.h.astype(np.float64), m.hc, m.dtab)
        s.om[:] = plan_of(s.h.astype(np.float64), m.hc, m.dtab)
        self.refresh_due = True

    def set_source(self, rate: np.ndarray) -> None:
        """Net source per cell, m/s."""
        self.state.src[:] = np.asarray(rate, F)

    def hold_cells(self, cells: np.ndarray, level: np.ndarray) -> None:
        """Cells whose level is prescribed after every step (the stage-1 boundary)."""
        m = self.mesh
        self.bcell = np.asarray(cells, np.int64)
        hb = hbar_at_level(np.asarray(level, np.float64), m.zmin[self.bcell], m.hc[self.bcell], m.dtab[self.bcell])
        self.bh0 = hb.astype(F)
        self.bd0 = level_of(hb, m.hc[self.bcell], m.dtab[self.bcell]).astype(F)

    def level(self) -> np.ndarray:
        """Water level per cell, m (datum of the DEM)."""
        return self.mesh.zmin + self.state.d.astype(np.float64)

    def volume(self) -> float:
        return float(np.sum(self.state.h.astype(np.float64) * self.mesh.area))

    # ---- stepping
    def step(self, dt: float, refresh: bool) -> None:
        s = self.state
        s.zero_vectors()
        s.step_faces(dt, refresh)
        s.step_cells(dt, refresh)
        if self.bcell.size:
            kernel.boundary(self.bcell, self.bd0, self.bh0, s.h, s.d)

    def advance(self, t_end: float) -> float:
        num = self.num
        dx = self.mesh.dx
        while self.t < t_end - 1e-9:
            refresh = self.refresh_due or self.nsteps % num.dt_every == 0
            self.refresh_due = False
            dt = min(self.dt, t_end - self.t, num.dt_max)
            self.step(dt, refresh)
            self.t += dt
            self.nsteps += 1
            if refresh:
                wave = self.state.wave
                if not np.isfinite(wave) or wave > 1e29:
                    raise NumericalFailure(f"non-finite wave speed at t = {self.t:.3f} s")
                # the lattice rule: cfl dx / wave speed; here the frequency already carries 1 / dn
                self.dt = min(num.cfl / max(wave, num.wave_floor / dx), num.dt_max)
                if self.dt < num.dt_min:
                    raise NumericalFailure(f"time step {self.dt:.2e} s below the minimum at t = {self.t:.3f} s")
        return self.t


__all__ = ["PolyModel", "PolyState"]
