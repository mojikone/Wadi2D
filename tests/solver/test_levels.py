"""Local time stepping: level logic, the uniform limit, conservation across edges, and the analytic cases."""

from __future__ import annotations

import numpy as np
import pytest
from scipy.ndimage import gaussian_filter

from tests.solver import harness
from wadi2d.config.constants import CRITICAL_WEIR_COEFF
from wadi2d.config.schema import Numerics, Tables
from wadi2d.grid import TileGrid
from wadi2d.solver.backend import BoundaryCells
from wadi2d.solver.level_stepper import trailing_level
from wadi2d.solver.levels import SIDES, LevelRule, assign_levels, plan_cycle
from wadi2d.solver.model import Model
from wadi2d.tables import ArrayBed, build_tables
from wadi2d.validation import UniformGrid, compare
from wadi2d.validation.cases import dam_break

BACKENDS = ["cpu", pytest.param("gpu", marks=pytest.mark.gpu)]
PLAIN = {"sheet_flow": False, "e_wet": 1e-5, "h_cfl": 1e-4, "dt_every": 1, "dt_max": 60.0}
LEVELS = {"local_time_stepping": True}
RULE = LevelRule(0.45, 1.0, 1.0, 5.0, 3)


def _row_grid(n: int) -> np.ndarray:
    """Neighbours of a row of ``n`` tiles numbered from 1; slots follow ``TileGrid.nbr``."""
    nbr = np.zeros((n + 1, 8), np.int32)
    for t in range(1, n + 1):
        nbr[t, 3] = t - 1
        nbr[t, 4] = t + 1 if t < n else 0
    return nbr


def test_trailing_level():
    assert [trailing_level(n, 2) for n in range(8)] == [2, 0, 1, 0, 2, 0, 1, 0]


def test_levels_differ_by_at_most_one_and_take_the_fastest_step():
    nbr = _row_grid(6)
    wave = np.array([0.0, 40.0, 2.0, 2.0, 2.0, 2.0, 2.0])
    active = np.arange(1, 7)
    level, dt0 = assign_levels(wave, active, nbr, 10.0, RULE, np.zeros(7, bool))
    assert dt0 == pytest.approx(0.45 * 10.0 / 40.0)
    assert np.abs(np.diff(level[1:])).max() <= 1
    assert level[1] == 0
    assert level[1:].max() > 0
    assert np.all(dt0 * 2.0 ** level[1:] <= 0.45 * 10.0 / np.maximum(wave[1:], 1.0) + 1e-9)


def test_a_pinned_tile_stays_at_level_zero():
    nbr = _row_grid(4)
    wave = np.array([0.0, 40.0, 40.0, 1.0, 1.0])
    pinned = np.array([False, False, False, False, True])
    level, _dt = assign_levels(wave, np.arange(1, 5), nbr, 10.0, RULE, pinned)
    assert level[4] == 0


def test_levels_hold_while_the_step_barely_moves():
    nbr = _row_grid(4)
    active = np.arange(1, 5)
    first, _dt = assign_levels(
        np.array([0.0, 8.0, 3.0, 3.0, 3.0]), active, nbr, 10.0, RULE, np.zeros(5, bool)
    )
    again, _dt = assign_levels(
        np.array([0.0, 8.5, 3.1, 3.1, 3.1]), active, nbr, 10.0, RULE, np.zeros(5, bool), first
    )
    assert np.array_equal(first, again)


def test_plan_lists_each_edge_once_with_its_owner():
    nbr = _row_grid(3)
    level = np.array([0, 0, 1, 1], np.int32)
    plan = plan_cycle(level, np.arange(1, 4), nbr[:, SIDES])
    assert plan.top == 1
    assert [(s, e.tolist()) for s, e in plan.edges_x[0]] == [(0, [[1, 2, 2, 0]])]
    assert [(s, e.tolist()) for s, e in plan.strips[0]] == [(0, [[1, 2, 2, 0]])]
    assert plan.coarse[1].tolist() == [2]


def _force(m: Model, level, dt: float) -> None:
    """Fix the levels and the smallest step, so the edge code runs whatever the waves do."""
    st = m.stepper
    st.level = np.asarray(level, np.int32)
    st.dt = dt
    st.fresh_wave = True
    st.plan = None
    st._reassign = lambda: None


def _rough_model(backend, num=None, seed=5):
    rng = np.random.default_rng(seed)
    nx, ny, k, dx = 92, 60, 4, 10.0
    tg = TileGrid.from_mask(np.ones((ny, nx), bool), 0.0, 0.0, dx)
    z = gaussian_filter(rng.normal(0, 1.0, (tg.shape[0] * k + 2, tg.shape[1] * k + 2)), 5) * 30 + 1500.0
    return Model(
        build_tables(tg, ArrayBed(z, dx / k), Tables(), 0.03), num or Numerics(**LEVELS), backend
    ), tg


def _columns(tg) -> np.ndarray:
    """Levels 0, 1, 2, 1 across the tile columns."""
    return np.array([0, *(np.array([0, 1, 2, 1])[tg.tiles[1:, 1] % 4])], np.int32)


def _total(m) -> float:
    held = m.field("h").astype(np.float64) + m.field("res")
    return float(held.sum()) * m.grid.dx**2


@pytest.mark.parametrize("backend", BACKENDS)
def test_level_zero_is_the_uniform_step_exactly(backend):
    case = dam_break.build_stoker(UniformGrid(0.0, 0.0, 0.5, 400, 8), axis="x")
    uniform = harness.run(case, num=Numerics(**PLAIN), backend=backend)
    level = harness.run(
        case,
        num=Numerics(**PLAIN, **LEVELS, lts_levels=0, lts_wave_floor=3.0),
        backend=backend,
    )
    assert level.wall_steps == uniform.wall_steps
    assert np.array_equal(level.state.h, uniform.state.h)
    assert np.array_equal(level.state.qx, uniform.state.qx)


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("axis, grid", [("x", (400, 8)), ("y", (8, 400))])
def test_stoker_with_levels(backend, axis, grid):
    case = dam_break.build_stoker(UniformGrid(0.0, 0.0, 0.5, *grid), axis=axis)
    r = harness.run(case, num=Numerics(**PLAIN, **LEVELS), backend=backend)
    rep = compare(r.state, case, case.t_end)
    assert rep.depth_rmse < 0.02
    assert rep.discharge_rmse < 0.07


@pytest.mark.parametrize("backend", BACKENDS)
def test_ritter_with_levels(backend):
    case = dam_break.build_ritter(UniformGrid(0.0, 0.0, 0.5, 400, 8))
    r = harness.run(case, num=Numerics(**PLAIN, **LEVELS), backend=backend)
    rep = compare(r.state, case, case.t_end)
    assert rep.depth_rmse < 0.01
    assert rep.f_statistic > 0.93


@pytest.mark.parametrize("backend", BACKENDS)
def test_stoker_across_forced_levels(backend):
    """The shock crosses edges 0-1, 1-2, 2-1 at a step the slowest tile can carry."""
    case = dam_break.build_stoker(UniformGrid(0.0, 0.0, 0.5, 400, 8), axis="x")
    m = harness.build(case, num=Numerics(**PLAIN, **LEVELS), backend=backend)
    harness.set_initial(case, m, 1)
    bc = harness.boundary_cells(case, m)
    if bc.cell.size:
        m.set_boundary(bc)
    level = np.array([0, *(np.array([0, 1, 2, 1])[m.grid.tiles[1:, 1] % 4])], np.int32)
    wmax = 10.0
    _force(m, level, 0.11 * 0.5 / wmax)
    m.stepper.pinned[:] = False
    m.advance(case.t_end)
    rep = compare(harness.result(case, m), case, case.t_end)
    assert rep.depth_rmse < 0.03
    assert rep.discharge_rmse < 0.1


@pytest.mark.parametrize("backend", BACKENDS)
def test_water_is_conserved_across_forced_levels(backend):
    """A dam break over rough ground through levels 0, 1, 2: the water, residuals included, stays what it was."""
    m, tg = _rough_model(backend)
    h0 = np.where(tg.mask & (np.arange(tg.shape[1])[None, :] < 30), 2.0, 0.0)
    m.set_depth(h0)
    v0 = _total(m)
    _force(m, _columns(tg), 0.1)
    m.advance(40.0)
    assert m.field("h").max() > 0.0
    assert abs(_total(m) / v0 - 1.0) < 1e-6


@pytest.mark.parametrize("backend", BACKENDS)
def test_still_water_stays_still_across_forced_levels(backend):
    m, tg = _rough_model(backend)
    from wadi2d.solver.state import plan_field
    from wadi2d.tables import hbar_at_level

    t = m.tables
    h0 = np.asarray(hbar_at_level(1510.0, t.zmin, tg.from_tiles(t.hc), tg.from_tiles(t.dtab)))
    h0 = np.where(tg.mask, h0, 0.0)
    assert plan_field(t, h0).min() > 0.0
    m.set_depth(h0)
    _force(m, _columns(tg), 0.1)
    m.advance(5.0)
    h = m.field("h")
    deep = (h > 0.01) & (np.roll(h, 1, axis=1) > 0.01) & (np.roll(h, 1, axis=0) > 0.01) & tg.mask
    assert np.abs(m.field("u"))[deep].max() < 1e-2
    assert np.abs(m.field("v"))[deep].max() < 1e-2


@pytest.mark.parametrize("backend", BACKENDS)
def test_thin_crest_passes_critical_flow_with_levels(backend):
    nx, ny, k, dx, crest, head = 120, 4, 4, 5.0, 3.0, 1.0
    tg = TileGrid.from_mask(np.ones((ny, nx), bool), 0.0, 0.0, dx)
    x = (np.arange(tg.shape[1] * k) - k + 0.5) * dx / k
    xs = np.tile(x, (tg.shape[0] * k, 1))
    i_crest = 61
    z = np.zeros(xs.shape)
    z[(xs >= i_crest * dx) & (xs < i_crest * dx + dx / k)] = crest
    tables = build_tables(tg, ArrayBed(z, dx / k), Tables(), 0.012)
    m = Model(tables, Numerics(cfl=0.4, dt_every=1, **LEVELS), backend)
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


def _swell(num, backend, dt=None):
    """A smooth 0.3 m hump on 2 m of water, centred on an edge, over a flat bed: it crosses edges side on."""
    nx, ny, dx = 158, 30, 10.0
    tg = TileGrid.from_mask(np.ones((ny, nx), bool), 0.0, 0.0, dx)
    z = np.zeros((tg.shape[0] + 2, tg.shape[1] + 2))
    m = Model(build_tables(tg, ArrayBed(z, dx), Tables(), 0.012), num, backend)
    x = (np.arange(tg.shape[1]) + 0.5) * dx
    h = 2.0 + 0.3 * np.exp(-(((x - 630.0) / 60.0) ** 2))
    m.set_depth(np.where(tg.mask, np.tile(h, (tg.shape[0], 1)), 0.0))
    return m, tg


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_smooth_wave_crosses_forced_levels_as_in_the_uniform_run(backend):
    """Only time accuracy at the edges can move this: interpolated halos, and edge faces stepped at the fine rate."""
    step = 0.25
    uniform, tg = _swell(Numerics(sheet_flow=False, dt_every=1, dt_max=step), backend)
    uniform.advance(90.0)
    level, tg = _swell(Numerics(sheet_flow=False, dt_every=1, **LEVELS), backend)
    _force(level, _columns(tg), step)
    level.advance(90.0)
    diff = (level.field("h") - uniform.field("h"))[tg.mask]
    assert float(np.sqrt((diff**2).mean())) < 1.6e-3


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_tile_that_wakes_beside_slow_tiles_keeps_the_levels_graded(backend):
    """A front reaches dry tiles while tiles behind it have slowed. Edges hold exactly two fine steps per coarse one."""
    nx, ny, dx = 254, 30, 2.0
    tg = TileGrid.from_mask(np.ones((ny, nx), bool), 0.0, 0.0, dx)
    z = np.zeros((tg.shape[0] + 2, tg.shape[1] + 2))
    num = Numerics(lts_wave_floor=0.5, lts_buffer=0.5, h_cfl=1e-3, **LEVELS)
    m = Model(build_tables(tg, ArrayBed(z, dx), Tables(), 0.03), num, backend)
    h = np.zeros(tg.shape)
    h[:, 8:30] = 2.0
    h[:, 30:60] = 0.03
    m.set_depth(h * tg.mask)
    v0 = _total(m)
    st = m.stepper
    worst = [0]
    woke = [int(st.backend.nact)]

    def watch(s):
        woke[0] = max(woke[0], int(s.backend.nact))
        p = s.plan
        if p is None:
            s._set_plan()
            p = s.plan
        active = np.asarray(s.backend.active_tiles)
        on = np.zeros(s.level.size, bool)
        on[active] = True
        for side in range(4):
            other = s.same[active, side]
            keep = on[other]
            gap = np.abs(s.level[other[keep]] - s.level[active[keep]])
            worst[0] = max(worst[0], int(gap.max()) if gap.size else 0)

    start = int(st.backend.nact)
    m.advance(120.0, watch)
    assert woke[0] > start
    assert worst[0] <= 1
    assert abs(_total(m) / v0 - 1.0) < 1e-6


def test_a_plan_grades_a_tile_that_woke_at_level_zero_among_slow_ones():
    """Edges hold exactly two fine steps per coarse one; a gap of two would overwrite a live estimate and lose water."""
    m, tg = _rough_model("cpu")
    m.set_depth(np.where(tg.mask, 1.0, 0.0))
    st = m.stepper
    st.level = np.full(tg.ntiles, 2, np.int32)
    st.level[0] = 0
    st.level[1] = 0
    st.plan = None
    st._set_plan()
    for side in range(4):
        other = st.same[1:, side]
        keep = other > 0
        assert np.abs(st.level[other[keep]] - st.level[1:][keep]).max() <= 1


def test_the_first_cycle_keeps_to_the_largest_step():
    m, tg = _rough_model("cpu", Numerics(dt_max=0.05, **LEVELS))
    m.set_depth(np.where(tg.mask, 1.0, 0.0))
    m.advance(0.2)
    assert m.stepper.nsteps >= 4


@pytest.mark.gpu
def test_cpu_gpu_parity_across_forced_levels():
    out = {}
    for name in ("cpu", "gpu"):
        m, tg = _rough_model(name)
        m.set_depth(np.where(tg.mask & (np.arange(tg.shape[1])[None, :] < 30), 2.0, 0.0))
        _force(m, _columns(tg), 0.1)
        m.advance(30.0)
        out[name] = (m.field("h"), m.field("qx"), m.stepper.nsteps)
    assert out["cpu"][2] == out["gpu"][2]
    assert np.abs(out["cpu"][0] - out["gpu"][0]).max() < 1e-3
    assert np.abs(out["cpu"][1] - out["gpu"][1]).max() < 0.05
