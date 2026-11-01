"""GpuBackend: device arrays and the kernel launches. It has the same interface as CpuBackend."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from wadi2d.solver import layout
from wadi2d.solver.backend import BoundaryCells, NumericsRecord
from wadi2d.solver.state import exchange_map
from wadi2d.tables.builder import GridTables

KERNELS = Path(__file__).parent / "kernels"
CELLS_PER_THREAD = 4
BLOCK = (layout.TILE, layout.TILE // CELLS_PER_THREAD)
EXCHANGE_BLOCK = (16, 17)
"""Enough threads for every halo slot of a tile: 272."""


def _source() -> str:
    head = "\n".join(
        f"#define {n} {getattr(layout, n)}" for n in ("TILE", "HALO", "STRIDE", "STRIDE2", "TILE2")
    )
    head += f"\n#define CELLS_PER_THREAD {CELLS_PER_THREAD}\n"
    return head + "".join(
        (KERNELS / f).read_text(encoding="utf-8") + "\n" for f in ("common.cuh", "faces.cu", "cells.cu")
    )


class GpuBackend:
    """Owns the device copies. ``h`` and ``d`` etc. are CuPy arrays, tile-major with halos."""

    name = "gpu"

    def __init__(self, tables: GridTables, num: NumericsRecord) -> None:
        import cupy as cp

        self.cp = cp
        self.grid = tables.grid
        self.num = num
        self.module = cp.RawModule(code=_source(), options=("-std=c++17", "--use_fast_math"))
        self._faces = self.module.get_function("faces")
        self._limit = self.module.get_function("limit")
        self._update = self.module.get_function("update")
        self._exchange = self.module.get_function("exchange")
        self._boundary = self.module.get_function("boundary")
        record = np.array(
            [(num.g, num.dx, num.e_wet, num.h_cfl, num.u_max, tables.rows, int(num.second), int(num.sheet))],
            dtype=np.dtype(
                [("g", "f4"), ("dx", "f4"), ("e_wet", "f4"), ("h_cfl", "f4"), ("u_max", "f4"),
                 ("rows", "i4"), ("second", "i4"), ("sheet", "i4")]
            ),
        )  # fmt: skip
        self.module.get_global("P").copy_from_host(record.ctypes.data, record.nbytes)

        n = self.grid.ntiles * layout.STRIDE2
        for a in layout.STATE_ARRAYS + layout.WORK_ARRAYS:
            setattr(self, a, cp.zeros(n, cp.float32))
        self.Hc = cp.asarray(tables.hc.ravel())
        self.dtab = cp.asarray(tables.dtab.reshape(-1))
        self.static_x = tuple(
            cp.asarray(a.ravel())
            for a in (tables.flx, tables.frx, tables.glx, tables.grx, tables.efx, tables.cwx)
        )
        self.static_y = tuple(
            cp.asarray(a.ravel())
            for a in (tables.fly, tables.fry, tables.gly, tables.gry, tables.efy, tables.cwy)
        )
        self.ftabx = cp.asarray(tables.ftabx.reshape(-1))
        self.ftaby = cp.asarray(tables.ftaby.reshape(-1))
        self.wave = cp.zeros(self.grid.ntiles, cp.float32)
        self.wet = cp.zeros(self.grid.ntiles, cp.int32)

        dst, src = exchange_map(self.grid)
        self.nhalo = dst.size // max(self.grid.ntiles - 1, 1)
        self.slot = cp.asarray((dst[: self.nhalo] - layout.STRIDE2).astype(np.int32))
        self.src_map = cp.asarray(src)
        self.bc: BoundaryCells | None = None
        self.bc_arrays = None
        self.set_active(np.arange(1, self.grid.ntiles, dtype=np.int32))

    def set_active(self, active: np.ndarray) -> None:
        self.active = self.cp.asarray(active.astype(np.int32))
        self.nact = int(active.size)

    def set_field(self, name: str, a: np.ndarray) -> None:
        getattr(self, name)[:] = self.cp.asarray(a)

    def get_field(self, name: str) -> np.ndarray:
        return self.cp.asnumpy(getattr(self, name))

    def set_boundary(self, bc: BoundaryCells) -> None:
        cp = self.cp
        self.bc = bc
        self.bc_arrays = (
            cp.asarray(bc.cell), cp.asarray(bc.ref), cp.asarray(bc.kind), cp.asarray(bc.d0), cp.asarray(bc.h0),
        )  # fmt: skip

    def _exch(self, a, b=None, c=None, e=None) -> None:
        self._exchange(
            (self.nact,), EXCHANGE_BLOCK, (self.active, self.slot, self.src_map, self.nhalo, a, b, c, e)
        )

    def step(self, dt: float, want_wave: bool, want_wet: bool) -> None:
        cp = self.cp
        dtf = cp.float32(dt)
        grid = (self.nact, 1)
        if want_wave:
            self.wave[:] = 0.0
        self._faces(
            grid, BLOCK,
            (self.active, dtf, int(want_wave), self.h, self.d, self.u, self.v, self.mx, self.my, self.qx, self.qy,
             *self.static_x, self.ftabx, *self.static_y, self.ftaby,
             self.u1, self.v1, self.mx1, self.my1, self.qx1, self.qy1, self.wave),
        )  # fmt: skip
        self._exch(self.u1, self.v1, self.qx1, self.qy1)
        self._limit(grid, BLOCK, (self.active, dtf, self.h, self.qx1, self.qy1, self.r))
        self._exch(self.r)
        if want_wet:
            self.wet[:] = 0
        self._update(
            grid, BLOCK,
            (self.active, dtf, int(want_wet), self.qx1, self.qy1, self.r, self.src, self.Hc, self.dtab,
             self.h, self.d, self.qx, self.qy, self.wet),
        )  # fmt: skip
        if self.bc is not None and self.bc.cell.size:
            n = self.bc.cell.size
            self._boundary(((n + 255) // 256,), (256,), (n, *self.bc_arrays, self.h, self.d))
        self._exch(self.h, self.d, self.qx, self.qy)
        self.u, self.u1 = self.u1, self.u
        self.v, self.v1 = self.v1, self.v
        self.mx, self.mx1 = self.mx1, self.mx
        self.my, self.my1 = self.my1, self.my

    def max_wave(self) -> float:
        return float(self.wave.max())

    def wet_flags(self) -> np.ndarray:
        return self.cp.asnumpy(self.wet)

    def synchronize(self) -> None:
        self.cp.cuda.Device().synchronize()
