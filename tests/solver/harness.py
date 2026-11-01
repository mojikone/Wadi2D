"""Run an analytic case through the production solver: tables from the case bed, boundaries, exact comparison."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from wadi2d.config.schema import Numerics, Tables
from wadi2d.grid import TileGrid
from wadi2d.solver.backend import BoundaryCells
from wadi2d.solver.model import Model
from wadi2d.tables import ArrayBed, build_tables
from wadi2d.validation.case import BoundaryKind, Case, State

PAD = 1
"""Cells of padding TileGrid.from_mask adds on the low side of each axis."""


@dataclass
class Run:
    model: Model
    state: State
    wall_steps: int


def _pixels(case: Case, tg: TileGrid, k: int) -> tuple[np.ndarray, np.ndarray]:
    g = case.grid
    p = g.dx / k
    ny, nx = tg.shape
    x = g.x0 + (np.arange(nx * k) - PAD * k + 0.5) * p
    y = g.y0 + (np.arange(ny * k) - PAD * k + 0.5) * p
    return np.meshgrid(x, y)


def build(
    case: Case, k: int = 1, tables: Tables | None = None, num: Numerics | None = None, backend: str = "cpu"
) -> Model:
    g = case.grid
    tg = TileGrid.from_mask(np.ones((g.ny, g.nx), bool), g.x0, g.y0, g.dx)
    xs, ys = _pixels(case, tg, k)
    bed = np.asarray(case.solution.bed(xs, ys), dtype=np.float64)
    n = case.manning_n if case.manning_n > 0.0 else 1e-6
    tab = build_tables(tg, ArrayBed(bed, g.dx / k), tables or Tables(), n)
    return Model(tab, num or Numerics(), backend)


def _average(case: Case, m: Model, k: int, t: float) -> State:
    """Exact state averaged over each cell's pixels, so the volume is exact on any bed."""
    xs, ys = _pixels(case, m.grid, k)
    s = case.solution.state(xs, ys, t)
    ny, nx = m.grid.shape

    def mean(a):
        return np.broadcast_to(a, xs.shape).reshape(ny, k, nx, k).mean(axis=(1, 3))

    return State(mean(s.h), mean(s.qx), mean(s.qy))


def set_initial(case: Case, m: Model, k: int, t: float = 0.0) -> None:
    s = _average(case, m, k, t)
    m.set_depth(s.h)
    wet = s.h > 1e-9
    m.set_velocity(
        np.where(wet, s.qx / np.maximum(s.h, 1e-9), 0.0), np.where(wet, s.qy / np.maximum(s.h, 1e-9), 0.0)
    )


def boundary_cells(case: Case, m: Model) -> BoundaryCells:
    """Depth and transmissive sides as boundary cells; inflow sides are set by ``inflow_rate``."""
    g = case.grid
    cell, ref, kind, d0, h0 = [], [], [], [], []
    for name, b in (("west", case.boundaries.west), ("east", case.boundaries.east)):
        if b.kind is BoundaryKind.CLOSED or (b.kind is BoundaryKind.INFLOW and b.depth is None):
            continue
        i = 0 if name == "west" else g.nx - 1
        inner = 1 if name == "west" else g.nx - 2
        for j in range(g.ny):
            c = m.cell_state_index(j + PAD, i + PAD)
            cell.append(c)
            ref.append(m.cell_state_index(j + PAD, inner + PAD))
            if b.depth is not None:
                kind.append(0)
                d0.append(b.depth)
                h0.append(b.depth)
            else:
                kind.append(2)
                d0.append(0.0)
                h0.append(0.0)
    return BoundaryCells(
        np.array(cell, np.int32), np.array(ref, np.int32), np.array(kind, np.int32),
        np.array(d0, np.float32), np.array(h0, np.float32),
    )  # fmt: skip


def inflow_rate(case: Case, m: Model) -> np.ndarray:
    """Source rate (m/s) that feeds the inflow side."""
    g = case.grid
    rate = np.zeros(m.grid.shape)
    b = case.boundaries.west
    if b.kind is BoundaryKind.INFLOW and b.discharge is not None:
        rate[PAD : PAD + g.ny, PAD + 1] = b.discharge / g.dx
    return rate


def result(case: Case, m: Model) -> State:
    """The solver state on the case grid; unit discharges at cell centres from the face values."""
    g = case.grid
    sl = (slice(PAD, PAD + g.ny), slice(PAD, PAD + g.nx))
    h = m.field("h")[sl]
    qxf = m.field("qx")
    qyf = m.field("qy")
    qx = 0.5 * (qxf + np.roll(qxf, -1, axis=1))[sl] / g.dx
    qy = 0.5 * (qyf + np.roll(qyf, -1, axis=0))[sl] / g.dx
    return State(h.astype(np.float64), qx.astype(np.float64), qy.astype(np.float64))


def run(
    case: Case,
    k: int = 1,
    tables: Tables | None = None,
    num: Numerics | None = None,
    backend: str = "cpu",
    t_end: float | None = None,
) -> Run:
    m = build(case, k, tables, num, backend)
    set_initial(case, m, k)
    bc = boundary_cells(case, m)
    if bc.cell.size:
        m.set_boundary(bc)
    rate = inflow_rate(case, m)
    if rate.any():
        m.set_source(rate)
    m.advance(t_end if t_end is not None else case.t_end)
    return Run(m, result(case, m), m.stepper.nsteps)
