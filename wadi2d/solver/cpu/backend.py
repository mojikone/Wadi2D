"""CpuBackend: the same interface as GpuBackend, on numpy arrays."""

from __future__ import annotations

import numpy as np

from wadi2d.solver import layout
from wadi2d.solver.backend import BoundaryCells, NumericsRecord
from wadi2d.solver.cpu import kernels
from wadi2d.solver.state import exchange_map
from wadi2d.tables.builder import GridTables


class CpuBackend:
    """Owns the arrays on the host."""

    name = "cpu"

    def __init__(self, tables: GridTables, num: NumericsRecord) -> None:
        self.grid = tables.grid
        self.num = num
        self.rows = tables.rows
        n = self.grid.ntiles * layout.STRIDE2
        for a in layout.STATE_ARRAYS + layout.WORK_ARRAYS:
            setattr(self, a, np.zeros(n, np.float32))
        self.Hc = tables.hc.ravel()
        self.dtab = tables.dtab.reshape(-1)
        self.static_x = tuple(
            a.ravel() for a in (tables.flx, tables.frx, tables.glx, tables.grx, tables.efx, tables.cwx)
        )
        self.static_y = tuple(
            a.ravel() for a in (tables.fly, tables.fry, tables.gly, tables.gry, tables.efy, tables.cwy)
        )
        self.ftabx = tables.ftabx.reshape(-1)
        self.ftaby = tables.ftaby.reshape(-1)
        self.wave = np.zeros(self.grid.ntiles, np.float32)
        self.wet = np.zeros(self.grid.ntiles, np.int32)
        dst, src = exchange_map(self.grid)
        self.nhalo = dst.size // max(self.grid.ntiles - 1, 1)
        self.slot = (dst[: self.nhalo] - layout.STRIDE2).astype(np.int32)
        self.src_map = src
        self.bc = BoundaryCells.empty()
        self.set_active(np.arange(1, self.grid.ntiles, dtype=np.int32))
        f = np.float32
        self._args = (
            self.rows,
            f(num.g),
            f(num.dx),
            f(num.e_wet),
            f(num.h_cfl),
            f(num.u_max),
            f(num.lead),
            f(num.a_min),
            num.second,
            num.sheet,
        )

    def set_active(self, active: np.ndarray) -> None:
        self.active = active.astype(np.int32)
        self.active_tiles = self.active
        self.nact = int(active.size)

    def set_field(self, name: str, a: np.ndarray) -> None:
        getattr(self, name)[:] = a

    def get_field(self, name: str) -> np.ndarray:
        return getattr(self, name).copy()

    def set_boundary(self, bc: BoundaryCells) -> None:
        self.bc = bc

    def _exch(self, *arrays) -> None:
        for a in arrays:
            kernels.exchange(self.active, self.slot, self.src_map, self.nhalo, a)

    def step(self, dt: float, want_wave: bool, want_wet: bool) -> None:
        if self.nact == 0:
            return
        dtf = np.float32(dt)
        kernels.faces(
            self.active, dtf, want_wave, self.om, self.h, self.d, self.u, self.v, self.mx, self.my, self.qx, self.qy,
            *self.static_x, self.ftabx, *self.static_y, self.ftaby,
            self.u1, self.v1, self.mx1, self.my1, self.qx1, self.qy1, self.wave, *self._args,
        )  # fmt: skip
        self._exch(self.u1, self.v1, self.qx1, self.qy1)
        kernels.limit(self.active, dtf, self.h, self.qx1, self.qy1, self.r, np.float32(self.num.dx))
        self._exch(self.r)
        kernels.update(
            self.active, dtf, want_wave, self.res, self.om, self.qx1, self.qy1, self.r, self.src, self.Hc, self.dtab, self.h, self.d, self.qx,
            self.qy, self.wet, self.rows, np.float32(self.num.dx),
        )  # fmt: skip
        if self.bc.cell.size:
            b = self.bc
            kernels.boundary(b.cell, b.ref, b.kind, b.d0, b.h0, self.h, self.d)
        self._exch(self.h, self.d, self.qx, self.qy)
        if want_wave:
            self._exch(self.om)
        self.u, self.u1 = self.u1, self.u
        self.v, self.v1 = self.v1, self.v
        self.mx, self.mx1 = self.mx1, self.mx
        self.my, self.my1 = self.my1, self.my

    def max_wave(self) -> float:
        return float(self.wave.max())

    def wet_flags(self) -> np.ndarray:
        return self.wet.copy()

    def synchronize(self) -> None:
        return None
