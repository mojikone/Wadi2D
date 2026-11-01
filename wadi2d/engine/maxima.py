"""What the run accumulates on the device: maxima and the boundary flow. Small kernels, a Numba twin for the CPU.

Depth is the level above a cell's lowest point; mean depth is ``V / dx^2``; speed is taken at the cell centre from
the four face velocities, only above ``speed_depth``, because a thin film's velocity means nothing. Hazard is
depth x speed. Arrival is the first time the depth reaches ``arrival_depth``. The arrays are tile-major like the
state, so the cost is one launch and no transfer until the end.

The boundary flow is summed every step, in double precision. A sample every few steps aliases a flow that changes
from one step to the next, and the water balance then reports an error the run does not have.
"""

from __future__ import annotations

import numpy as np
from numba import njit, prange

from wadi2d.solver import layout
from wadi2d.solver.gpu.backend import BLOCK, CELLS_PER_THREAD
from wadi2d.solver.layout import HALO, STRIDE, STRIDE2, TILE
from wadi2d.solver.model import Model
from wadi2d.solver.state import from_state

NAMES = ("depth", "mean_depth", "speed", "hazard", "arrival")
NOT_ARRIVED = -1.0
TALLY_BLOCK = 256
"""Threads per block of the boundary tally, the size the solver's boundary kernel uses."""

_KERNELS = """
extern "C" __global__ void maxima(const int* __restrict__ active, const float time, const float arrive,
                                  const float deep, const float* __restrict__ d, const float* __restrict__ h,
                                  const float* __restrict__ u, const float* __restrict__ v,
                                  float* __restrict__ dmax, float* __restrict__ hmax, float* __restrict__ smax,
                                  float* __restrict__ zmax, float* __restrict__ tarr) {
    const int t = active[blockIdx.x];
    const int i = threadIdx.x;
    for (int c = 0; c < CELLS_PER_THREAD; ++c) {
        const int j = threadIdx.y * CELLS_PER_THREAD + c;
        const int k = t * STRIDE2 + (j + HALO) * STRIDE + i + HALO;
        const float dk = d[k];
        if (dk > dmax[k]) dmax[k] = dk;
        if (h[k] > hmax[k]) hmax[k] = h[k];
        if (dk > deep) {
            const float uc = 0.5f * (u[k] + u[k + 1]);
            const float vc = 0.5f * (v[k] + v[k + STRIDE]);
            const float s = sqrtf(uc * uc + vc * vc);
            if (s > smax[k]) smax[k] = s;
            if (s * dk > zmax[k]) zmax[k] = s * dk;
        }
        if (tarr[k] < 0.0f && dk >= arrive) tarr[k] = time;
    }
}

// One thread per face, each adding to its own total: no atomics, and the cost of the boundary kernel.
extern "C" __global__ void tally(const int n, const double dt, const int* __restrict__ face,
                                 const int* __restrict__ axis, const float* __restrict__ sign,
                                 const float* __restrict__ qx, const float* __restrict__ qy,
                                 double* __restrict__ total) {
    const int m = blockIdx.x * blockDim.x + threadIdx.x;
    if (m >= n) return;
    const float q = axis[m] ? qy[face[m]] : qx[face[m]];
    total[m] += dt * (double)(sign[m] * q);
}
"""


def _module(cp):
    """The compiled kernels; CuPy keeps the binary on disk, so this costs a run once."""
    head = "".join(
        f"#define {n} {getattr(layout, n)}\n" for n in ("TILE", "HALO", "STRIDE", "STRIDE2", "TILE2")
    )
    head += f"#define CELLS_PER_THREAD {CELLS_PER_THREAD}\n"
    return cp.RawModule(code=head + _KERNELS, options=("-std=c++17", "--use_fast_math"))


@njit(parallel=True)
def _update_cpu(active, time, arrive, deep, d, h, u, v, dmax, hmax, smax, zmax, tarr):
    for a in prange(active.size):
        t = active[a]
        for j in range(TILE):
            for i in range(TILE):
                k = t * STRIDE2 + (j + HALO) * STRIDE + i + HALO
                dk = d[k]
                dmax[k] = max(dmax[k], dk)
                hmax[k] = max(hmax[k], h[k])
                if dk > deep:
                    uc = 0.5 * (u[k] + u[k + 1])
                    vc = 0.5 * (v[k] + v[k + STRIDE])
                    s = np.sqrt(uc * uc + vc * vc)
                    smax[k] = max(smax[k], s)
                    zmax[k] = max(zmax[k], s * dk)
                if tarr[k] < 0.0 and dk >= arrive:
                    tarr[k] = time


@njit
def _tally_cpu(face, axis, sign, qx, qy):
    total = 0.0
    for m in range(face.size):
        total += float(sign[m]) * float(qy[face[m]] if axis[m] else qx[face[m]])
    return total


class Maxima:
    """Owns the five arrays on the backend's side."""

    def __init__(self, model: Model, arrival_depth: float, speed_depth: float) -> None:
        self.model = model
        self.backend = model.backend
        self.arrive = float(arrival_depth)
        self.deep = float(speed_depth)
        self.cp = getattr(self.backend, "cp", None)
        n = model.grid.ntiles * STRIDE2
        xp = np if self.cp is None else self.cp
        self.arrays = [xp.zeros(n, xp.float32) for _ in NAMES]
        self.arrays[-1][:] = NOT_ARRIVED
        self.kernel = None if self.cp is None else _module(self.cp).get_function("maxima")

    def update(self, t: float) -> None:
        b = self.backend
        if self.cp is None:
            _update_cpu(
                b.active, np.float32(t), np.float32(self.arrive), np.float32(self.deep), b.d, b.h, b.u, b.v,
                *self.arrays,
            )  # fmt: skip
            return
        f = self.cp.float32
        self.kernel(
            (b.nact, 1), BLOCK,
            (b.active, f(t), f(self.arrive), f(self.deep), b.d, b.h, b.u, b.v, *self.arrays),
        )  # fmt: skip

    def raw(self) -> dict[str, np.ndarray]:
        """The arrays in state layout, for a checkpoint."""
        return {n: self._host(a) for n, a in zip(NAMES, self.arrays, strict=True)}

    def restore(self, saved: dict[str, np.ndarray]) -> None:
        for n, a in zip(NAMES, self.arrays, strict=True):
            a[:] = saved[n] if self.cp is None else self.cp.asarray(saved[n])

    def _host(self, a) -> np.ndarray:
        return a.copy() if self.cp is None else self.cp.asnumpy(a)

    def fields(self) -> dict[str, np.ndarray]:
        """(ny, nx) grids by name."""
        self.backend.synchronize()
        return {n: from_state(self.model.grid, a) for n, a in self.raw().items()}


class Tally:
    """Volume through a set of faces, m3, summed every step; positive along the given signs."""

    def __init__(
        self, model: Model, xfaces: np.ndarray, xsign: np.ndarray, yfaces: np.ndarray, ysign: np.ndarray
    ) -> None:
        self.backend = model.backend
        self.cp = getattr(self.backend, "cp", None)
        face = np.concatenate((xfaces, yfaces)).astype(np.int32)
        axis = np.concatenate((np.zeros(xfaces.size), np.ones(yfaces.size))).astype(np.int32)
        sign = np.concatenate((xsign, ysign)).astype(np.float32)
        self.n = int(face.size)
        self.held = 0.0
        self.arrays = (face, axis, sign)
        if self.cp is None or self.n == 0:
            return
        cp = self.cp
        self.arrays = (cp.asarray(face), cp.asarray(axis), cp.asarray(sign))
        self.total = cp.zeros(self.n, cp.float64)
        self.kernel = _module(cp).get_function("tally")
        self.blocks = ((self.n + TALLY_BLOCK - 1) // TALLY_BLOCK,)

    def add(self, dt: float) -> None:
        if self.n == 0:
            return
        b = self.backend
        face, axis, sign = self.arrays
        if self.cp is None:
            self.held += dt * _tally_cpu(face, axis, sign, b.qx, b.qy)
            return
        self.kernel(
            self.blocks, (TALLY_BLOCK,),
            (self.n, self.cp.float64(dt), face, axis, sign, b.qx, b.qy, self.total),
        )  # fmt: skip

    def volume(self) -> float:
        if self.cp is None or self.n == 0:
            return self.held
        return self.held + float(self.total.sum())

    def restore(self, value: float) -> None:
        self.held = value
        if self.cp is not None and self.n:
            self.total[:] = 0.0
