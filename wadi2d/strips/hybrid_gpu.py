# Wadi2D. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The hybrid step on the GPU (W45, stage 5): the strip stepped by the CUDA twin beside the tile kernels.

The same hooks as :class:`wadi2d.strips.hybrid.HybridCpu`, launch for launch: the ghosts mirrored by a gather, the
sums, rates, faces, limit and update of ``poly.cu``, the ghosts' net outflow into the tile's source array and back,
the interface discharges into the tile's closed faces. Nothing leaves the device inside a step; the wave speed is a
device scalar the stepper reads when it refreshes the time step.
"""

from __future__ import annotations

import numpy as np

from wadi2d.solver.poly.gpu import PolyGpuState
from wadi2d.strips.hybrid import Hybrid

F = np.float32


def _csr(group: np.ndarray, size: int) -> np.ndarray:
    ptr = np.zeros(size + 1, np.int32)
    np.add.at(ptr, group + 1, 1)
    return np.cumsum(ptr, dtype=np.int32)


class HybridGpu(Hybrid):
    """The hybrid step with the strip on the device."""

    def make_state(self) -> PolyGpuState:
        if self.model.backend.name != "gpu":
            raise ValueError("HybridGpu steps a GPU model; make_hybrid picks the class")
        state = PolyGpuState(self.mesh, self.model.num)
        cp = state.cp
        self.ghost_d = cp.asarray(self.ghost.astype(np.int32))
        self.flags = tuple(cp.asarray(np.asarray(f, np.uint8)) for f in (self.open_w, self.open_e, self.open_n, self.open_s))
        self.zmin_d = cp.asarray(self.zmin_state)
        self.saved = cp.zeros(self.ghost.size, F)
        self.max_d, self.max_h = cp.zeros(self.nreal, F), cp.zeros(self.nreal, F)
        self.max_s, self.max_dv = cp.zeros(self.nreal, F), cp.zeros(self.nreal, F)
        self.max_q = cp.zeros(self.mesh.nfaces, F)
        self.speed_depth = F(0.0)
        self.edge_d = {}
        for axis, (faces, group, signs, unique, all_copies, owner, ghost_of) in self.edge.items():
            if faces.size == 0:
                continue
            order = np.argsort(group, kind="stable")
            maps = (
                _csr(group, unique.size), faces[order].astype(np.int32), signs[order].astype(F),
                unique.astype(np.int32), ghost_of.astype(np.int32), _csr(owner, unique.size), all_copies.astype(np.int32),
            )  # fmt: skip
            self.edge_d[axis] = (int(unique.size), tuple(cp.asarray(m) for m in maps))
        return state

    def strip_host(self, name: str) -> np.ndarray:
        return self.state.host(name)

    def strip_maxima(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        cp = self.state.cp
        return cp.asnumpy(self.max_d), cp.asnumpy(self.max_h), cp.asnumpy(self.max_q)

    def strip_speed_maxima(self) -> tuple[np.ndarray, np.ndarray]:
        cp = self.state.cp
        return cp.asnumpy(self.max_s), cp.asnumpy(self.max_dv)

    def watch_boundary(self, faces: np.ndarray) -> None:
        cp = self.state.cp
        self.b_faces_d = cp.asarray(np.asarray(faces, np.int32))
        self.left_dev = cp.zeros(1, cp.float64)

    def boundary_outflow(self) -> float:
        return float(self.left_dev[0]) if self.b_faces.size else 0.0

    def set_strip_depth(self, hbar: np.ndarray) -> None:
        h, d, om = self.strip_start(hbar)
        self.state.set_real("h", h)
        self.state.set_real("d", d)
        self.state.set_real("om", om)

    def set_strip_source(self, rate: np.ndarray) -> None:
        self.state.set_real("src", rate)

    def before_update(self, dt: float, want_wave: bool) -> None:
        b, s, g = self.model.backend, self.state, self.ghost_d
        s.mirror(g, b.h, b.d, b.om)
        s.levels()
        s.sums(g, self.flags, self.zmin_d, b.h, b.d, b.qx, b.qy)
        s.rates(g, self.flags, b.h, b.qx, b.qy)
        s.faces(dt, want_wave)
        s.limit(dt, g, b.h, b.r, b.qx1, b.qy1)
        s.update(dt, want_wave)
        s.ghost_src(g, self.saved, b.src)
        if want_wave:
            b.extra_wave = s.wave[0] * float(self.dx)

    def after_update(self, dt: float, want_wave: bool) -> None:
        b, s = self.model.backend, self.state
        s.restore(self.ghost_d, self.saved, b.src)
        if self.b_faces.size:
            s.tally(self.b_faces_d, dt, self.left_dev)
        s.maxima(float(self.speed_depth), self.max_d, self.max_h, self.max_s, self.max_dv, self.max_q)
        for axis, (nslot, maps) in self.edge_d.items():
            discharge, velocity = (b.qx, b.u1) if axis == "x" else (b.qy, b.v1)
            s.edges(nslot, maps, discharge, velocity)


__all__ = ["HybridGpu"]
