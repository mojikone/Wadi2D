"""The level stepper's operations on the device; ``CpuLevels`` is the same on the host."""

from __future__ import annotations

import numpy as np

from wadi2d.solver import layout

EDGE_BLOCK = (layout.TILE,)
"""One thread per face of an edge."""


class GpuLevels:
    def __init__(self, backend, block, exchange_block) -> None:
        cp = backend.cp
        self.cp = cp
        self.b = backend
        self.block = block
        self.exchange_block = exchange_block
        n = backend.grid.ntiles
        self.h0 = cp.zeros(n * layout.STRIDE2, cp.float32)
        self.d0 = cp.zeros(n * layout.STRIDE2, cp.float32)
        self.est = cp.zeros(4 * n * layout.TILE, cp.float32)
        self.level = cp.zeros(n, cp.int32)
        m = backend.module
        self._strips = m.get_function("strips")
        self._halo = m.get_function("halo_levels")
        self._save = m.get_function("save_old")
        self._commit = m.get_function("commit")
        self._commit_strips = m.get_function("commit_strips")
        self._estimate = m.get_function("edge_estimate")
        self._flux = m.get_function("edge_flux")

    def lists(self, a: np.ndarray):
        return self.cp.asarray(a.astype(np.int32))

    def set_level(self, level: np.ndarray) -> None:
        self.level[:] = self.cp.asarray(level)

    def halo_state(self, tiles, n: int, want_plan: bool) -> None:
        b = self.b
        self._halo(
            (int(tiles.size),), self.exchange_block,
            (tiles, b.slot, b.src_map, b.nhalo, self.level, n, b.h, self.h0, b.d, self.d0, b.u, b.v, b.qx, b.qy),
        )  # fmt: skip
        if want_plan:
            self.exch(tiles, b.om)

    def exch(self, tiles, a, b=None, c=None, e=None) -> None:
        d = self.b
        d._exchange((int(tiles.size),), self.exchange_block, (tiles, d.slot, d.src_map, d.nhalo, a, b, c, e))

    def clear_wave(self) -> None:
        self.b.wave[:] = 0.0

    def clear_wet(self) -> None:
        self.b.wet[:] = 0

    def faces(self, tiles, dt: float, want_wave: bool) -> None:
        b = self.b
        b._faces(
            (int(tiles.size), 1), self.block,
            (tiles, self.cp.float32(dt), int(want_wave), b.om, b.h, b.d, b.u, b.v, b.mx, b.my, b.qx, b.qy,
             *b.static_x, b.ftabx, *b.static_y, b.ftaby,
             b.u1, b.v1, b.mx1, b.my1, b.qx1, b.qy1, b.wave),
        )  # fmt: skip

    def strips(self, edges, dt: float, want_wave: bool) -> None:
        b = self.b
        self._strips(
            (edges.shape[0],), EDGE_BLOCK,
            (edges, self.cp.float32(dt), int(want_wave), b.om, b.h, b.d, b.u, b.v, b.mx, b.my, b.qx, b.qy,
             *b.static_x, b.ftabx, *b.static_y, b.ftaby,
             b.u1, b.v1, b.mx1, b.my1, b.qx1, b.qy1, b.wave),
        )  # fmt: skip

    def faces_done(self, tiles) -> None:
        b = self.b
        self.exch(tiles, b.u1, b.v1, b.qx1, b.qy1)

    def limit(self, tiles, dt: float) -> None:
        b = self.b
        b._limit((int(tiles.size), 1), self.block, (tiles, self.cp.float32(dt), b.h, b.qx1, b.qy1, b.r))

    def limit_done(self, tiles) -> None:
        self.exch(tiles, self.b.r)

    def save(self, tiles) -> None:
        b = self.b
        self._save((int(tiles.size), 1), self.block, (tiles, b.h, b.d, self.h0, self.d0))

    def estimate(self, edges) -> None:
        b = self.b
        self._estimate((edges.shape[0],), EDGE_BLOCK, (edges, b.qx1, b.qy1, b.r, self.est))

    def flux(self, edges, dt: float) -> None:
        b = self.b
        self._flux(
            (edges.shape[0],), EDGE_BLOCK,
            (edges, self.cp.float32(dt), b.qx1, b.qy1, b.r, self.est, b.res, b.qx, b.qy),
        )  # fmt: skip

    def update(self, tiles, dt: float, want_wet: bool, want_plan: bool) -> None:
        b = self.b
        b._update(
            (int(tiles.size), 1), self.block,
            (tiles, self.cp.float32(dt), int(want_wet), int(want_plan), 1, b.res, b.om, b.qx1, b.qy1, b.r, b.src,
             b.Hc, b.dtab, b.h, b.d, b.qx, b.qy, b.wet),
        )  # fmt: skip

    def boundary(self) -> None:
        b = self.b
        if b.bc is not None and b.bc.cell.size:
            n = b.bc.cell.size
            b._boundary(((n + 255) // 256,), (256,), (n, *b.bc_arrays, b.h, b.d))

    def commit(self, tiles) -> None:
        b = self.b
        self._commit(
            (int(tiles.size), 1), self.block, (tiles, b.u1, b.v1, b.mx1, b.my1, b.u, b.v, b.mx, b.my)
        )

    def commit_strips(self, edges) -> None:
        b = self.b
        self._commit_strips(
            (edges.shape[0],), EDGE_BLOCK, (edges, b.u1, b.v1, b.mx1, b.my1, b.u, b.v, b.mx, b.my)
        )

    def wave(self) -> np.ndarray:
        return self.cp.asnumpy(self.b.wave)
