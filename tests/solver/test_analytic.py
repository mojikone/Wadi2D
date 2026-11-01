"""The solver against exact solutions, on both backends. Limits are measured values plus a margin (W1 validation)."""

from __future__ import annotations

import numpy as np
import pytest

from tests.solver import harness
from wadi2d.config.schema import Numerics
from wadi2d.validation import UniformGrid, compare
from wadi2d.validation.cases import dam_break, lake_at_rest, thacker

PLAIN = Numerics(sheet_flow=False, e_wet=1e-5, h_cfl=1e-4, dt_every=1, dt_max=60.0)
BACKENDS = ["cpu", pytest.param("gpu", marks=pytest.mark.gpu)]


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("axis, grid", [("x", (400, 8)), ("y", (8, 400))])
def test_stoker(backend, axis, grid):
    case = dam_break.build_stoker(UniformGrid(0.0, 0.0, 0.5, *grid), axis=axis)
    r = harness.run(case, num=PLAIN, backend=backend)
    rep = compare(r.state, case, case.t_end)
    assert rep.depth_rmse < 0.02
    assert rep.discharge_rmse < 0.07
    assert abs(rep.volume_error) < 1e-6


@pytest.mark.parametrize("backend", BACKENDS)
def test_ritter(backend):
    case = dam_break.build_ritter(UniformGrid(0.0, 0.0, 0.5, 400, 8))
    r = harness.run(case, num=PLAIN, backend=backend)
    rep = compare(r.state, case, case.t_end)
    assert rep.depth_rmse < 0.01
    assert rep.f_statistic > 0.93
    assert abs(rep.volume_error) < 1e-6


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize(
    "build, k, limit",
    [(thacker.build_planar, 4, 0.0055), (thacker.build_curved, 4, 0.002)],
    ids=["planar", "curved"],
)
def test_thacker_moving_shoreline(backend, build, k, limit):
    case = build(UniformGrid.square(4.0, 200))
    r = harness.run(case, k=k, num=PLAIN, backend=backend)
    rep = compare(r.state, case, case.t_end)
    assert rep.depth_rmse < limit
    assert abs(rep.volume_error) < 5e-5


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("sheet", [False, True])
def test_still_water_stays_still_on_rough_ground_at_altitude(backend, sheet):
    """Partly wet cells over a random bed 1,500 m above the datum: nothing may move."""
    case = lake_at_rest.build_rough(UniformGrid.square(10.0, 100))
    num = Numerics(sheet_flow=sheet, dt_every=1)
    m = harness.build(_raised(case, 1500.0), k=4, num=num, backend=backend)
    harness.set_initial(_raised(case, 1500.0), m, 4)
    # the cell-averaged start differs from the table's level by the interpolation error: let it settle, then watch
    m.advance(2.0)
    v0 = m.volume()
    m.advance(10.0)
    h = m.field("h")
    deep = (h > 0.01) & (np.roll(h, 1, axis=1) > 0.01) & (np.roll(h, 1, axis=0) > 0.01)
    assert np.abs(m.field("u"))[deep].max() < 1e-2
    assert np.abs(m.field("v"))[deep].max() < 1e-2
    assert abs(m.volume() / v0 - 1.0) < 1e-6


def _raised(case, dz):
    """The same case with the bed and the water surface raised by ``dz``."""
    from dataclasses import replace

    sol = case.solution

    class Raised:
        def bed(self, x, y):
            return sol.bed(x, y) + dz

        def state(self, x, y, t):
            return sol.state(x, y, t)

    return replace(case, solution=Raised())
