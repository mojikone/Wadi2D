"""The step limiter (W85): the face the step rule read is named, on either backend, and its numbers are the kernel's."""

from __future__ import annotations

import numpy as np
import pytest

from wadi2d.config.constants import G
from wadi2d.config.schema import Numerics, Tables
from wadi2d.grid import TileGrid
from wadi2d.solver.limiter import step_limiter, tile_waves
from wadi2d.solver.model import Model
from wadi2d.tables import ArrayBed, build_tables

BACKENDS = ["cpu", pytest.param("gpu", marks=pytest.mark.gpu)]
DX, K = 10.0, 10
GROUND, PIT, LEVEL = 100.0, 70.0, 90.0
PJ, PI = 6, 7
"""The pit lies in row PJ of cells, a pixel either side of the west face of column PI."""


def pit_model(backend: str, level: float | None = LEVEL) -> tuple[Model, np.ndarray]:
    """Flat ground with a pit 2 m by 6 m and 30 m deep across one face, water standing in it to ``level``."""
    tg = TileGrid.from_mask(np.ones((12, 12), bool), 0.0, 0.0, DX)
    ny, nx = tg.shape
    z = np.full((ny * K, nx * K), GROUND)
    z[PJ * K + 2 : PJ * K + 8, PI * K - 1 : PI * K + 1] = PIT
    tables = build_tables(tg, ArrayBed(z, DX / K), Tables(), 0.03)
    m = Model(tables, Numerics(), backend)
    if level is not None:
        depth = np.maximum(level - z, 0.0).reshape(ny, K, nx, K).mean(axis=(1, 3))
        m.set_depth(depth)
    return m, z


@pytest.mark.parametrize("backend", BACKENDS)
def test_water_standing_in_a_pit_across_a_face_is_named(backend):
    m, _z = pit_model(backend)
    m.advance(30.0)
    info = step_limiter(m, m.tables)
    assert info is not None and info["source"] == "tiles"
    assert info["axis"] == "x" and info["j"] == PJ and info["i"] in (PI - 1, PI)
    x, y = m.grid.xy_of(np.array(info["j"]), np.array(info["i"]))
    assert (info["x"], info["y"]) == (pytest.approx(float(x)), pytest.approx(float(y)))
    assert info["face_x"] == pytest.approx(m.grid.x0 + PI * DX)
    assert info["bed"] == pytest.approx(PIT) and info["level"] == pytest.approx(LEVEL, abs=1.0)
    # 20 m of water on 6 % of the plan behind a face 6 m wide: the rule reads far more than any depth on the ground
    assert info["plan"] < 0.2 and info["hydraulic_depth"] > 3.0 * info["depth"]
    assert info["celerity"] == pytest.approx(np.sqrt(G * info["hydraulic_depth"]), rel=1e-3)
    assert info["wave"] == pytest.approx(info["speed"] + info["jump"] + info["celerity"], abs=2e-3)


@pytest.mark.parametrize("backend", BACKENDS)
def test_the_reading_is_the_kernels_own_wave_and_step(backend):
    """Still water gives every step the same wave: the reading after the step is the one the step rule took."""
    m, _z = pit_model(backend)
    m.advance(30.0)
    num = m.num
    info = step_limiter(m, m.tables)
    assert info["wave"] == pytest.approx(m.backend.max_wave(), rel=1e-4)
    assert info["tile_wave"] == pytest.approx(m.backend.max_wave(), rel=1e-4)
    assert info["dt"] == pytest.approx(num.cfl * DX / info["wave"], rel=1e-3)
    assert info["dt_tile"] == pytest.approx(info["dt"], rel=1e-3)
    # one tile: nothing else leads
    assert info["dt_without_tile"] == pytest.approx(num.cfl * DX / num.wave_floor)
    wx, wy, _u, _v = tile_waves(m.backend, info["tile"], m.stepper.dt)
    assert max(float(wx.max()), float(wy.max())) == pytest.approx(m.backend.max_wave(), rel=1e-4)


@pytest.mark.parametrize("backend", BACKENDS)
def test_reading_the_limiter_leaves_the_water_alone(backend):
    a, _z = pit_model(backend)
    b, _z = pit_model(backend)
    for t in (5.0, 10.0, 15.0):
        a.advance(t)
        b.advance(t)
        step_limiter(b, b.tables)
    for name in ("h", "d", "u", "v", "qx", "qy"):
        assert np.array_equal(a.field(name), b.field(name)), name
    assert a.stepper.nsteps == b.stepper.nsteps


def test_dry_ground_names_nothing():
    m, _z = pit_model("cpu", level=None)
    m.advance(5.0)
    assert step_limiter(m, m.tables) is None
