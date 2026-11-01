"""What the sub-grid scheme exists for: thin sheet flow on slopes, crests, parity between backends."""

from __future__ import annotations

import numpy as np
import pytest

from wadi2d.config.constants import CRITICAL_WEIR_COEFF
from wadi2d.config.schema import Numerics, Tables
from wadi2d.grid import TileGrid
from wadi2d.solver.backend import BoundaryCells
from wadi2d.solver.model import Model
from wadi2d.tables import ArrayBed, build_tables

BACKENDS = ["cpu", pytest.param("gpu", marks=pytest.mark.gpu)]
RAIN_MM_H = 50.0


def _pixels(tg, k):
    ny, nx = tg.shape
    p = tg.dx / k
    return np.meshgrid(tg.x0 + (np.arange(nx * k) + 0.5) * p, tg.y0 - (np.arange(ny * k) + 0.5) * p)


def _plane_model(slope, dx, k, n, length, backend, num):
    """Rain on a long plane; the east end is a free outfall."""
    nx, ny = int(length / dx), 3
    tg = TileGrid.from_mask(np.ones((ny, nx), bool), 0.0, 0.0, dx)
    xs, _ = _pixels(tg, k)
    tables = build_tables(tg, ArrayBed((length - xs) * slope, dx / k), Tables(), n)
    m = Model(tables, num, backend)
    rain = np.zeros(tg.shape)
    i = RAIN_MM_H / 3.6e6
    rain[1 : 1 + ny, 1:nx] = i
    m.set_source(rain)
    cells = [m.cell_state_index(j + 1, nx) for j in range(ny)]
    m.set_boundary(
        BoundaryCells(
            np.array(cells, np.int32),
            np.zeros(ny, np.int32),
            np.ones(ny, np.int32),
            np.zeros(ny, np.float32),
            np.zeros(ny, np.float32),
        )
    )
    return m, i, nx, ny


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("slope", [0.01, 0.05, 0.2])
def test_sheet_flow_on_a_plane_matches_the_kinematic_wave(backend, slope):
    """Storage and outflow at equilibrium: the flat-surface reading of a steep cell would hold a seventh of it."""
    n, length, dx = 0.05, 2000.0, 20.0
    m, i, nx, ny = _plane_model(slope, dx, 20, n, length, backend, Numerics(dt_max=2.0))
    tc = (n * length / (slope**0.5 * i ** (2.0 / 3.0))) ** 0.6
    m.advance(2.5 * tc)
    q_end = i * length
    h_end = (q_end * n / slope**0.5) ** 0.6
    hmean = float(m.field("h")[1 + ny // 2, 1:nx].mean())
    assert hmean == pytest.approx(0.625 * h_end, rel=0.03)
    outflow = float(m.field("qx")[1 + ny // 2, nx]) / dx
    assert outflow == pytest.approx(q_end, rel=0.03)


@pytest.mark.parametrize("backend", BACKENDS)
def test_thin_crest_passes_critical_flow(backend):
    nx, ny, k, dx, crest, head = 120, 4, 4, 5.0, 3.0, 1.0
    tg = TileGrid.from_mask(np.ones((ny, nx), bool), 0.0, 0.0, dx)
    xs, _ = _pixels(tg, k)
    i_crest = 61
    z = np.zeros(xs.shape)
    z[(xs >= (i_crest) * dx) & (xs < (i_crest) * dx + dx / k)] = crest
    tables = build_tables(tg, ArrayBed(z, dx / k), Tables(), 0.012)
    m = Model(tables, Numerics(cfl=0.4, dt_every=1), backend)
    h0 = np.zeros(tg.shape)
    h0[:, :i_crest] = crest + head
    m.set_depth(h0)
    n_b = ny * 3
    cells = [m.cell_state_index(j + 1, c) for j in range(ny) for c in (1, 2, 3)]
    m.set_boundary(
        BoundaryCells(
            np.array(cells, np.int32),
            np.zeros(n_b, np.int32),
            np.zeros(n_b, np.int32),
            np.full(n_b, crest + head, np.float32),
            np.full(n_b, crest + head, np.float32),
        )
    )
    m.advance(300.0)
    q = float(m.field("qx")[2, i_crest]) / dx
    hup = float(m.field("h")[2, i_crest - 3]) - crest
    assert q == pytest.approx(CRITICAL_WEIR_COEFF * hup**1.5, rel=0.01)


@pytest.mark.gpu
def test_cpu_gpu_parity_on_a_rough_dam_break():
    from scipy.ndimage import gaussian_filter

    rng = np.random.default_rng(3)
    nx, ny, k, dx = 90, 60, 6, 10.0
    tg = TileGrid.from_mask(np.ones((ny, nx), bool), 0.0, 0.0, dx)
    z = gaussian_filter(rng.normal(0, 1.0, (tg.shape[0] * k + 2, tg.shape[1] * k + 2)), 5) * 30 + 200.0
    tables = build_tables(tg, ArrayBed(z, dx / k), Tables(), 0.03)
    h0 = np.zeros(tg.shape)
    h0[:, :30] = 2.0
    out = {}
    for name in ("cpu", "gpu"):
        m = Model(
            tables, Numerics(dt_every=1, dt_max=0.2), name
        )  # a fixed step, so the kernels alone are compared
        m.set_depth(h0)
        m.advance(60.0)
        out[name] = (m.field("h"), m.field("qx"), m.stepper.nsteps)
    assert out["cpu"][2] == out["gpu"][2]
    assert np.abs(out["cpu"][0] - out["gpu"][0]).max() < 1e-3
    assert np.abs(out["cpu"][1] - out["gpu"][1]).max() < 0.05
