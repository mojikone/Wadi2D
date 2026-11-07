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


class PolyModel:
    """State and stepping on one polygon mesh."""

    def __init__(self, mesh: PolyMesh, num: Numerics | None = None) -> None:
        if mesh.dn is None:
            raise ValueError("finish the mesh before stepping it")
        self.mesh = mesh
        self.num = num or Numerics()
        self.rec = NumericsRecord.from_config(self.num, mesh.dx)
        nc, nf = mesh.ncells, mesh.nfaces
        self.h = np.zeros(nc, F)
        self.d = np.zeros(nc, F)
        self.om = np.ones(nc, F)
        self.src = np.zeros(nc, F)
        self.r = np.ones(nc, F)
        self.Ux, self.Uy, self.Rx, self.Ry, self.Gx, self.Gy = (np.zeros(nc, F) for _ in range(6))
        self.out, self.div = np.zeros(nc, F), np.zeros(nc, F)
        self.u, self.m, self.q, self.u1, self.m1, self.q1, self.Dl = (np.zeros(nf, F) for _ in range(7))
        self.bcell = np.zeros(0, np.int64)
        self.bd0 = np.zeros(0, F)
        self.bh0 = np.zeros(0, F)
        self.t = 0.0
        self.nsteps = 0
        self.dt = self.num.cfl * mesh.dx / self.num.wave_floor
        self.refresh_due = True
        self.wave = 0.0
        m = mesh
        self._static = (
            m.left.astype(np.int64), m.right.astype(np.int64), m.length.astype(F), m.nx.astype(F), m.ny.astype(F),
            m.xf.astype(F), m.yf.astype(F), m.dn.astype(F), m.sx.astype(F), m.sy.astype(F),
            m.fl.astype(F), m.fr.astype(F), m.gl.astype(F), m.gr.astype(F), m.ef.astype(F), m.cw.astype(F),
            m.ftab.astype(F).reshape(-1), m.area.astype(F), m.cx.astype(F), m.cy.astype(F),
        )  # fmt: skip
        self._cells = (m.hc.astype(F), m.dtab.astype(F).reshape(-1))
        r = self.rec
        self._nums = (
            m.rows, F(r.g), F(r.dx), F(r.e_wet), F(r.h_cfl), F(r.u_max), F(r.lead), F(r.a_min), r.sheet, True,
        )  # fmt: skip

    # ---- state in and out
    def hbar_at_level(self, level: float | np.ndarray) -> np.ndarray:
        m = self.mesh
        return hbar_at_level(level, m.zmin, m.hc, m.dtab)

    def set_depth(self, hbar: np.ndarray) -> None:
        m = self.mesh
        self.h[:] = np.asarray(hbar, F)
        self.d[:] = level_of(self.h.astype(np.float64), m.hc, m.dtab)
        self.om[:] = plan_of(self.h.astype(np.float64), m.hc, m.dtab)
        self.refresh_due = True

    def set_source(self, rate: np.ndarray) -> None:
        """Net source per cell, m/s."""
        self.src[:] = np.asarray(rate, F)

    def hold_cells(self, cells: np.ndarray, level: np.ndarray) -> None:
        """Cells whose level is prescribed after every step (the stage-1 boundary)."""
        m = self.mesh
        self.bcell = np.asarray(cells, np.int64)
        hb = hbar_at_level(np.asarray(level, np.float64), m.zmin[self.bcell], m.hc[self.bcell], m.dtab[self.bcell])
        self.bh0 = hb.astype(F)
        self.bd0 = level_of(hb, m.hc[self.bcell], m.dtab[self.bcell]).astype(F)

    def level(self) -> np.ndarray:
        """Water level per cell, m (datum of the DEM)."""
        return self.mesh.zmin + self.d.astype(np.float64)

    def volume(self) -> float:
        return float(np.sum(self.h.astype(np.float64) * self.mesh.area))

    # ---- stepping
    def step(self, dt: float, refresh: bool) -> None:
        m = self.mesh
        nc, nf = m.ncells, m.nfaces
        L, R, ln, nfx, nfy, xf, yf, dn, sx, sy, fl, fr, gl, gr, ef, cw, ftab, area, cx, cy = self._static
        hc, dtab = self._cells
        rows, g, dx, e_wet, h_cfl, u_max, lead, a_min, sheet, skew = self._nums
        dtf = F(dt)
        kernel.cell_vectors(nf, nc, L, R, xf, yf, cx, cy, self.q, self.h, area, self.Ux, self.Uy, self.Rx, self.Ry)
        kernel.level_gradients(nf, nc, L, R, ln, nfx, nfy, fl, fr, self.h, self.d, area, e_wet, self.Gx, self.Gy, self.Dl)
        wave = kernel.faces(
            nf, dtf, refresh, L, R, ln, nfx, nfy, xf, yf, dn, sx, sy, fl, fr, gl, gr, ef, cw, ftab, area, cx, cy,
            self.h, self.d, self.om, self.u, self.m, self.q, self.Ux, self.Uy, self.Rx, self.Ry, self.Gx, self.Gy, self.Dl,
            self.u1, self.m1, self.q1, rows, g, dx, e_wet, h_cfl, u_max, lead, a_min, sheet, skew,
        )  # fmt: skip
        kernel.update(nf, nc, dtf, refresh, L, R, area, hc, dtab, self.q1, self.r, self.src, self.out, self.div, self.h, self.d, self.om, self.q, rows)
        if self.bcell.size:
            kernel.boundary(self.bcell, self.bd0, self.bh0, self.h, self.d)
        self.u, self.u1 = self.u1, self.u
        self.m, self.m1 = self.m1, self.m
        if refresh:
            self.wave = float(wave)

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
                if not np.isfinite(self.wave) or self.wave > 1e29:
                    raise NumericalFailure(f"non-finite wave speed at t = {self.t:.3f} s")
                # the lattice rule: cfl dx / wave speed; here the frequency already carries 1 / dn
                self.dt = min(num.cfl / max(self.wave, num.wave_floor / dx), num.dt_max)
                if self.dt < num.dt_min:
                    raise NumericalFailure(f"time step {self.dt:.2e} s below the minimum at t = {self.t:.3f} s")
        return self.t


__all__ = ["PolyModel"]
