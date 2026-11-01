"""Each test here is a failure an independent review found by running the code. They must stay fixed."""

from __future__ import annotations

import numpy as np
import pytest

from wadi2d.config.schema import Numerics, Tables
from wadi2d.grid import TileGrid
from wadi2d.solver.model import Model
from wadi2d.solver.stepper import NumericalFailure
from wadi2d.tables import ArrayBed, build_tables

BACKENDS = ["cpu", pytest.param("gpu", marks=pytest.mark.gpu)]


def _model(z, dx, backend, nside, num=None, k=1, n=0.03):
    tg = TileGrid.from_mask(np.ones((nside, nside), bool), 0.0, 0.0, dx)
    return Model(build_tables(tg, ArrayBed(z(tg, k), dx / k), Tables(), n), num or Numerics(), backend), tg


def _flat(tg, k):
    return np.zeros((tg.shape[0] * k + 2, tg.shape[1] * k + 2))


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("depth, mm_h", [(20.0, 10.0), (20.0, 30.0), (2.0, 3.0)])
def test_rain_on_deep_water_is_stored_in_full(backend, depth, mm_h):
    """Float32 alone rounds this rain away: 0 % stored at 20 m and 10 mm/h, 113 % at 2 m and 3 mm/h."""
    m, tg = _model(_flat, 10.0, backend, 30)
    h0 = np.where(tg.mask, depth, 0.0)
    m.set_depth(h0)
    rate = np.where(tg.mask, mm_h / 3.6e6, 0.0)
    m.set_source(rate)
    m.advance(3600.0)
    stored = float((m.field("h").astype(np.float64) - h0).sum())
    expected = float(rate.sum()) * 3600.0
    assert stored == pytest.approx(expected, rel=0.01)


@pytest.mark.parametrize("backend", BACKENDS)
def test_step_follows_a_sudden_drop(backend):
    """A pool over a cliff: the Courant number stays bounded with the step refreshed every 8 steps."""

    def cliff(tg, k):
        z = np.zeros((tg.shape[0] * k + 2, tg.shape[1] * k + 2))
        z[:, tg.shape[1] // 2 :] = -30.0
        return z

    dx = 10.0
    m, tg = _model(cliff, dx, backend, 62, Numerics(dt_every=8))
    h = np.zeros(tg.shape)
    h[:, : tg.shape[1] // 2] = 3.0
    m.set_depth(np.where(tg.mask, h, 0.0))
    worst = 0.0

    def watch(s):
        nonlocal worst
        if s.nsteps % 8 == 0:
            worst = max(worst, float(np.abs(s.backend.get_field("u")).max()) * s.dt / dx)

    m.advance(40.0, watch)
    assert worst < 1.0


@pytest.mark.parametrize("backend", BACKENDS)
def test_first_step_on_dry_ground_is_not_the_longest(backend):
    m, _ = _model(_flat, 20.0, backend, 30)
    assert m.stepper.dt <= m.num.cfl * 20.0 / m.num.wave_floor + 1e-9


@pytest.mark.parametrize("backend", BACKENDS)
def test_water_is_not_stranded_when_a_source_stops(backend):
    """Rain starts and ends between two wet-flag steps on a dry grid; the water must still drain."""

    def slope(tg, k):
        return np.tile(0.01 * 20.0 * (tg.shape[1] - np.arange(tg.shape[1] + 2)), (tg.shape[0] + 2, 1))

    m, tg = _model(slope, 20.0, backend, 120)
    rate = np.where(tg.mask, 0.1, 0.0)  # 0.1 m in one second
    m.set_source(rate)
    m.advance(1.0)
    m.set_source(np.zeros(tg.shape))
    before = m.field("h").copy()
    m.advance(600.0)
    assert np.abs(m.field("h") - before).max() > 0.0


@pytest.mark.parametrize("backend", BACKENDS)
def test_an_empty_grid_does_not_crash(backend):
    m, _ = _model(_flat, 20.0, backend, 30)
    m.advance(10.0)
    assert m.stepper.t == pytest.approx(10.0)


@pytest.mark.parametrize("backend", BACKENDS)
def test_nan_stops_the_run(backend):
    m, tg = _model(_flat, 10.0, backend, 30)
    m.set_depth(np.where(tg.mask, 1.0, 0.0))
    u = m.backend.get_field("u")
    u[m.cell_state_index(10, 10)] = float("nan")
    m.backend.set_field("u", u)
    m.stepper.refresh_due = True
    with pytest.raises(NumericalFailure):
        m.advance(5.0)


@pytest.mark.parametrize("backend", BACKENDS)
def test_narrow_pond_on_a_face_line_stays_calm(backend):
    """A one-pixel trench along a face with a small level difference across it must not grow."""
    k, dx, nside = 10, 20.0, 30

    def trench(tg, kk):
        z = np.zeros((tg.shape[0] * kk + 2, tg.shape[1] * kk + 2))
        c = 15 * kk
        z[:, c - 1 : c + 1] = -2.0
        return z

    m, tg = _model(trench, dx, backend, nside, Numerics(dt_every=1), k=k)
    h0 = np.zeros(tg.shape)
    h0[:, 14] = 0.05
    h0[:, 15] = 0.03
    m.set_depth(np.where(tg.mask, h0, 0.0))
    peak = 0.0

    def watch(_):
        nonlocal peak
        d = m.field("d") + m.tables.zmin
        peak = max(peak, float(np.abs(d[10, 14] - d[10, 15])))

    for t in range(1, 21):
        m.advance(float(t * 3), watch if t % 5 == 0 else None)
    assert peak < 0.5
