"""The compute interface both backends implement, and the choice between them."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from wadi2d.config.constants import G
from wadi2d.config.schema import Numerics
from wadi2d.tables.builder import GridTables


@dataclass(frozen=True)
class NumericsRecord:
    """The run-time numbers kernels read; built once from the configuration."""

    g: float
    dx: float
    e_wet: float
    h_cfl: float
    u_max: float
    lead: float
    a_min: float
    second: bool
    sheet: bool
    mirror: bool

    @classmethod
    def from_config(cls, num: Numerics, dx: float) -> NumericsRecord:
        return cls(
            G, dx, num.e_wet, num.h_cfl, num.u_max, float(num.dt_every), num.plan_min, num.limiter != "none",
            num.sheet_flow,
            num.mirror_dry_faces,
        )  # fmt: skip


@dataclass
class BoundaryCells:
    """Cells whose level is prescribed after every update. kind: 0 fixed, 1 free, 2 follows ``ref`` plus d0."""

    cell: np.ndarray
    ref: np.ndarray
    kind: np.ndarray
    d0: np.ndarray
    h0: np.ndarray

    @classmethod
    def empty(cls) -> BoundaryCells:
        i = np.zeros(0, np.int32)
        f = np.zeros(0, np.float32)
        return cls(i, i.copy(), i.copy(), f, f.copy())


def select_backend(name: str, tables: GridTables, num: NumericsRecord):
    """``auto`` takes the GPU when CuPy sees a device, the CPU otherwise."""
    if name in ("auto", "gpu"):
        try:
            import cupy as cp

            if cp.cuda.runtime.getDeviceCount() > 0:
                from wadi2d.solver.gpu.backend import GpuBackend

                return GpuBackend(tables, num)
        except Exception:
            if name == "gpu":
                raise
        if name == "gpu":
            raise RuntimeError("no CUDA device available")
    from wadi2d.solver.cpu.backend import CpuBackend

    return CpuBackend(tables, num)
