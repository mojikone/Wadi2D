"""The level stepper's operations on the device; ``CpuLevels`` is the same on the host."""

from __future__ import annotations

import numpy as np

from wadi2d.solver import layout

EDGE_BLOCK = (layout.TILE,)
"""One thread per face of an edge."""
COARSE_BLOCK = (layout.TILE // 2,)
"""One thread per coarse cell along an interface."""


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
        grid = backend.grid
        self.quad = getattr(grid, "quad", False)
        self.modules = backend.size_modules()
        m = self.modules[0]
        self._halo = m.get_function("halo_levels")
        self._save = m.get_function("save_old")
        self._commit = m.get_function("commit")
        self._commit_strips = m.get_function("commit_strips")
        self._estimate = m.get_function("edge_estimate")
        self.kernels = {
            name: [mod.get_function(name) for mod in self.modules]
            for name in (
                "faces",
                "limit",
                "update",
                "strips",
                "edge_flux",
                "iface_faces",
                "iface_estimate",
                "iface_flux",
            )
        }
        self._iface_load = m.get_function("iface_load")
        self._iface_store = m.get_function("iface_store")
        self._quad_halo = m.get_function("quad_halo")
        self._quad_done = m.get_function("quad_faces_done")
        if self.quad:
            from wadi2d.grid.quad import halo_maps

            maps = halo_maps(grid)
            self.fu, self.fv = cp.asarray(maps["u"].ravel()), cp.asarray(maps["v"].ravel())
            self.qu, self.qv = cp.asarray(maps["qu"].ravel()), cp.asarray(maps["qv"].ravel())
            self.iest = cp.zeros(max(grid.interfaces.shape[0], 1) * (layout.TILE // 2), cp.float32)

    def lists(self, a: np.ndarray):
        return self.cp.asarray(a.astype(np.int32))

    def set_level(self, level: np.ndarray) -> None:
        self.level[:] = self.cp.asarray(level)

    def halo_state(self, tiles, n: int, want_plan: bool) -> None:
        b = self.b
        if self.quad:
            self._quad_halo(
                (int(tiles.size),), self.exchange_block,
                (tiles, b.slot, b.src_map, self.fu, self.fv, self.qu, self.qv, b.nhalo, self.level, n, b.h, self.h0,
                 b.d, self.d0, b.u, b.v, b.qx, b.qy),
            )  # fmt: skip
        else:
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

    def faces(self, tiles, dt: float, want_wave: bool, size: int = 0) -> None:
        b = self.b
        self.kernels["faces"][size](
            (int(tiles.size), 1), self.block,
            (tiles, self.cp.float32(dt), int(want_wave), b.om, b.h, b.d, b.u, b.v, b.mx, b.my, b.qx, b.qy,
             *b.static_x, b.ftabx, *b.static_y, b.ftaby,
             b.u1, b.v1, b.mx1, b.my1, b.qx1, b.qy1, b.wave),
        )  # fmt: skip

    def strips(self, edges, dt: float, want_wave: bool, size: int = 0) -> None:
        self._edge_faces("strips", edges, dt, want_wave, size)

    def iface_faces(self, rows, dt: float, want_wave: bool, size: int) -> None:
        self._edge_faces("iface_faces", rows, dt, want_wave, size)

    def _edge_faces(self, name: str, rows, dt: float, want_wave: bool, size: int) -> None:
        b = self.b
        self.kernels[name][size](
            (rows.shape[0],), EDGE_BLOCK,
            (rows, self.cp.float32(dt), int(want_wave), b.om, b.h, b.d, b.u, b.v, b.mx, b.my, b.qx, b.qy,
             *b.static_x, b.ftabx, *b.static_y, b.ftaby,
             b.u1, b.v1, b.mx1, b.my1, b.qx1, b.qy1, b.wave),
        )  # fmt: skip

    def faces_done(self, tiles) -> None:
        b = self.b
        if self.quad:
            self._quad_done(
                (int(tiles.size),), self.exchange_block,
                (tiles, b.slot, self.fu, self.fv, b.nhalo, b.u1, b.v1, b.qx1, b.qy1),
            )  # fmt: skip
        else:
            self.exch(tiles, b.u1, b.v1, b.qx1, b.qy1)

    def iface_load(self, rows) -> None:
        b = self.b
        self._iface_load((rows.shape[0],), COARSE_BLOCK, (rows, b.u1, b.v1, b.qx1, b.qy1))

    def iface_estimate(self, rows, dt: float, size: int) -> None:
        b = self.b
        self.kernels["iface_estimate"][size](
            (rows.shape[0],), COARSE_BLOCK,
            (rows, self.cp.float32(dt), b.qx1, b.qy1, b.r, self.iest, b.res),
        )  # fmt: skip

    def iface_flux(self, rows, dt: float, size: int) -> None:
        b = self.b
        self.kernels["iface_flux"][size](
            (rows.shape[0],), COARSE_BLOCK,
            (rows, self.cp.float32(dt), b.qx1, b.qy1, b.r, self.iest, b.res),
        )  # fmt: skip

    def iface_store(self, rows) -> None:
        b = self.b
        self._iface_store(
            (rows.shape[0],), EDGE_BLOCK,
            (rows, b.qx1, b.qy1, b.r, b.u1, b.v1, b.mx1, b.my1, b.u, b.v, b.mx, b.my, b.qx, b.qy),
        )  # fmt: skip

    def limit(self, tiles, dt: float, size: int = 0) -> None:
        b = self.b
        self.kernels["limit"][size](
            (int(tiles.size), 1), self.block, (tiles, self.cp.float32(dt), b.h, b.qx1, b.qy1, b.r)
        )

    def limit_done(self, tiles) -> None:
        self.exch(tiles, self.b.r)

    def save(self, tiles) -> None:
        b = self.b
        self._save((int(tiles.size), 1), self.block, (tiles, b.h, b.d, self.h0, self.d0))

    def estimate(self, edges) -> None:
        b = self.b
        self._estimate((edges.shape[0],), EDGE_BLOCK, (edges, b.qx1, b.qy1, b.r, self.est))

    def flux(self, edges, dt: float, size: int = 0) -> None:
        b = self.b
        self.kernels["edge_flux"][size](
            (edges.shape[0],), EDGE_BLOCK,
            (edges, self.cp.float32(dt), b.qx1, b.qy1, b.r, self.est, b.res, b.qx, b.qy),
        )  # fmt: skip

    def update(self, tiles, dt: float, want_wet: bool, want_plan: bool, size: int = 0) -> None:
        b = self.b
        self.kernels["update"][size](
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
