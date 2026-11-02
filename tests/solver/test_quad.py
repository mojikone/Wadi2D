"""The quadtree: grid rules, tables at an interface, and water across 2:1 interfaces against the uniform fine run."""

from __future__ import annotations

import numpy as np
import pytest
from scipy.ndimage import gaussian_filter

from wadi2d.config.schema import Numerics, Tables
from wadi2d.grid import TileGrid
from wadi2d.grid.quad import QuadGrid, balance, halo_maps
from wadi2d.solver.backend import BoundaryCells
from wadi2d.solver.layout import HALO, STRIDE, STRIDE2, TILE
from wadi2d.solver.levels import LevelRule, assign_levels
from wadi2d.solver.model import Model
from wadi2d.solver.state import level_of, plan_of, state_index, tiles_to_state
from wadi2d.tables import ArrayBed, build_tables, hbar_at_level
from wadi2d.tables.builder import CrestFaces
from wadi2d.tables.quad import build_quad_tables

BACKENDS = ["cpu", pytest.param("gpu", marks=pytest.mark.gpu)]
DX = 10.0
PLAIN = {"sheet_flow": False, "dt_every": 1}
LEVELS = {"local_time_stepping": True}


def grids(level, ny: int, nx: int) -> tuple[QuadGrid, TileGrid]:
    """The quadtree and the uniform fine grid on the same cells."""
    mask = np.zeros((ny, nx), bool)
    mask[2:-2, 2:-2] = True
    q = QuadGrid.from_levels(mask, 0.0, 0.0, DX, np.array(level, np.int32))
    return q, TileGrid(0.0, 0.0, DX, q.mask.copy())


def total(m: Model) -> float:
    return float((m.field("h").astype(np.float64) + m.field("res")).sum()) * DX**2


def column_levels(first: int, last: int, nty: int = 2, ntx: int = 10) -> np.ndarray:
    lv = np.zeros((nty, ntx), np.int32)
    lv[:, first:last] = 1
    return lv


def test_balance_is_aligned_and_two_to_one():
    level = np.full((16, 16), 3, np.int32)
    level[5, 5] = 0
    out = balance(level, 3)
    for s in range(1, 4):
        size = 1 << s
        for j in range(0, 16, size):
            for i in range(0, 16, size):
                block = out[j : j + size, i : i + size]
                assert block.max() < s or block.min() == block.max()
    assert out[5, 5] == 0
    pad = np.pad(out, 1, mode="edge")
    for a, b in ((0, 1), (1, 0), (1, 1), (1, -1)):
        assert np.abs(np.roll(pad, (a, b), axis=(0, 1)) - pad)[2:-2, 2:-2].max() <= 1


def test_interfaces_name_the_fine_side_and_where_it_starts():
    q, _u = grids(column_levels(4, 6), 64, 320)
    rows = q.interfaces
    assert rows.shape[0] == 4
    assert set(map(int, rows[:, 4])) == {0, 16}
    assert set(map(int, rows[:, 1])) == {0, 2}
    assert q.cell_count < int(q.mask.sum())


def test_a_level_one_tile_beside_level_two_starts_at_sixteen():
    level = np.ones((4, 8), np.int32)
    level[:, 4:] = 2
    mask = np.zeros((128, 256), bool)
    mask[4:-4, 4:-4] = True
    q = QuadGrid.from_levels(mask, 0.0, 0.0, DX, level)
    rows = q.interfaces
    assert rows.shape[0] > 0
    assert set(map(int, rows[:, 4])) <= {0, 16}


def test_halo_slot_reads_the_cell_that_covers_it():
    q, _u = grids(column_levels(4, 6), 64, 320)
    maps = halo_maps(q)
    fine = int(q.interfaces[q.interfaces[:, 1] == 2][0, 0])
    coarse = int(q.interfaces[q.interfaces[:, 1] == 2][0, 2])
    slots = maps["slot"]
    row = HALO + 5
    ghost = np.nonzero(slots == row * STRIDE + HALO + TILE)[0][0]
    src = int(maps["cell"][fine - 1, ghost])
    assert src // STRIDE2 == coarse
    assert maps["u"][fine - 1, ghost] == fine * STRIDE2 + row * STRIDE + HALO + TILE
    assert maps["qu"][fine - 1, ghost] == 1.0


def test_interface_faces_take_their_inverts_from_the_ground_along_them():
    level = column_levels(4, 6)
    q, u = grids(level, 64, 320)
    rng = np.random.default_rng(1)
    k = 2
    z = gaussian_filter(rng.normal(0, 1.0, (64 * k + 8, 320 * k + 8)), 4) * 20 + 300.0
    bed = ArrayBed(z, DX / k, 4, 4)
    tq = build_quad_tables(q, bed, Tables(), 0.03)
    tu = build_tables(u, bed, Tables(), 0.03)
    row = q.interfaces[(q.interfaces[:, 1] == 0)][0]
    t, base = int(row[0]), int(row[5])
    j0, i0 = q.tiles[t, 0] * TILE, q.tiles[t, 1] * TILE
    zf_u = tu.grid.from_tiles(tu.frx)[j0 + 5, i0] + tu.zmin[j0 + 5, i0]
    zf_q = tq.frx.ravel()[base + 5 * TILE] + tq.zmin[j0 + 5, i0]
    assert zf_q == pytest.approx(zf_u, abs=1e-3)


def _rough(level, backend, num, ny=128, nx=320):
    q, _u = grids(level, ny, nx)
    k = 2
    z = gaussian_filter(np.random.default_rng(5).normal(0, 1.0, (ny * k + 8, nx * k + 8)), 5) * 30 + 1500.0
    tq = build_quad_tables(q, ArrayBed(z, DX / k, 4, 4), Tables(), 0.03)
    return Model(tq, num, backend), q, tq


def _fill(m: Model, q: QuadGrid, t, level: float) -> None:
    n = q.ntiles
    hc, dtab = t.hc[:n].astype(np.float64), t.dtab[:n].astype(np.float64)
    h = hbar_at_level(level, q.to_tiles(t.zmin, np.float64), hc, dtab)
    m.backend.set_field("h", tiles_to_state(q, h))
    m.backend.set_field("d", tiles_to_state(q, level_of(h, hc, dtab)))
    m.backend.set_field("om", tiles_to_state(q, plan_of(h, hc, dtab)))
    m.stepper.backend.wet[:] = 1
    m.stepper.rebuild_active()


@pytest.mark.parametrize("backend", BACKENDS)
def test_still_water_stays_still_across_interfaces(backend):
    m, q, t = _rough(column_levels(3, 6, 4, 10), backend, Numerics(**LEVELS, dt_every=1))
    _fill(m, q, t, 1510.0)
    v0 = total(m)
    m.advance(5.0)
    assert np.abs(m.backend.get_field("u")).max() < 1e-4
    assert np.abs(m.backend.get_field("v")).max() < 1e-4
    assert abs(total(m) / v0 - 1.0) < 1e-6


def _dam(level, backend, x0=1000.0, left=2.0, right=0.5, t_end=60.0):
    q, u = grids(level, 64, 320)
    bed = ArrayBed(np.zeros((72, 328)), DX, 4, 4)
    out = []
    for g, tab, num in (
        (u, build_tables(u, bed, Tables(), 0.03), Numerics(**PLAIN)),
        (q, build_quad_tables(q, bed, Tables(), 0.03), Numerics(**PLAIN, **LEVELS)),
    ):
        m = Model(tab, num, backend)
        x = (np.arange(g.shape[1]) + 0.5) * DX
        m.set_depth(np.tile(np.where(x < x0, left, right), (g.shape[0], 1)) * g.mask)
        v0 = total(m)
        m.advance(t_end)
        out.append((m.field("h").astype(np.float64)[24:40].mean(axis=0), total(m) / v0 - 1.0))
    (a, da), (b, db) = out
    wet = a > 0.0
    rel = np.abs(b - a)[wet] / a[wet]
    return float(rel.max()), float(np.sqrt((rel**2).mean())), abs(da), abs(db)


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize(
    "level, top",
    [(column_levels(4, 10), 0.02), (column_levels(4, 6), 0.02)],
    ids=["into coarse", "through a coarse block"],
)
def test_a_dam_break_crosses_an_interface_as_in_the_uniform_run(backend, level, top):
    worst, rms, _da, db = _dam(level, backend)
    assert worst < top
    assert rms < 0.03
    assert db < 1e-6


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_front_on_dry_ground_crosses_into_coarse_cells(backend):
    _worst, rms, _da, db = _dam(column_levels(4, 10), backend, right=0.0, left=3.0, t_end=40.0)
    assert rms < 0.03
    assert db < 1e-6


def _planar(g, tab, num, backend, step, unit_q=1.0, slope=0.01, n=0.03):
    ny, nx = g.shape
    hn = (unit_q * n / slope**0.5) ** 0.6
    m = Model(tab, num, backend)
    m.set_depth(np.where(g.mask, hn, 0.0))
    rows = np.nonzero(g.mask[:, nx // 2])[0]
    last = int(np.max(np.nonzero(g.mask[ny // 2])[0]))
    cells = np.unique(state_index(g, rows, np.full(rows.size, last)))
    ref = np.unique(state_index(g, rows, np.full(rows.size, last - step)))
    m.set_boundary(
        BoundaryCells(
            cells.astype(np.int32), ref.astype(np.int32), np.full(cells.size, 2, np.int32),
            np.zeros(cells.size, np.float32), np.zeros(cells.size, np.float32),
        )
    )  # fmt: skip
    rate = np.zeros(g.shape)
    first = int(np.min(np.nonzero(g.mask[ny // 2])[0])) + 2
    rate[:, first] = g.mask[:, first] * unit_q / DX
    m.set_source(rate)
    m.advance(2400.0)
    return m.field("h").astype(np.float64)


@pytest.mark.parametrize("backend", BACKENDS)
def test_planar_flow_crosses_interfaces_as_in_the_uniform_run(backend):
    ny, nx, k = 128, 512, 4
    p = DX / k
    x = (np.arange((nx + 8) * k) - 4 * k + 0.5) * p
    z = np.tile(100.0 - 0.01 * x, ((ny + 8) * k, 1))
    bed = ArrayBed(z, p, 4 * k, 4 * k)
    q, u = grids(column_levels(5, 11, 4, 16), ny, nx)
    a = _planar(u, build_tables(u, bed, Tables(), 0.03), Numerics(), backend, 1)[48:80].mean(axis=0)
    b = _planar(q, build_quad_tables(q, bed, Tables(), 0.03), Numerics(**LEVELS), backend, 2)[48:80].mean(
        axis=0
    )
    span = np.arange(30, nx - 30)
    rel = np.abs(b - a)[span] / a[span]
    assert rel.max() < 0.03


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_radial_wave_crosses_every_side_and_corner(backend):
    level = np.zeros((8, 8), np.int32)
    level[2:6, 2:6] = 1
    q, u = grids(level, 256, 256)
    bed = ArrayBed(np.zeros((264, 264)), DX, 4, 4)
    yy, xx = np.mgrid[0:256, 0:256]
    hump = 1.5 + np.exp(-((np.hypot(yy - 127.5, xx - 127.5) * DX / 150.0) ** 2))
    fields = []
    for g, tab, num in (
        (u, build_tables(u, bed, Tables(), 0.03), Numerics(**PLAIN)),
        (q, build_quad_tables(q, bed, Tables(), 0.03), Numerics(**PLAIN, **LEVELS)),
    ):
        m = Model(tab, num, backend)
        m.set_depth(np.where(g.mask, hump, 0.0))
        v0 = total(m)
        m.advance(100.0)
        assert abs(total(m) / v0 - 1.0) < 1e-6
        fields.append(m.field("h").astype(np.float64))
    a, b = fields
    on = u.mask & q.mask
    assert (np.abs(b - a)[on] / a[on]).max() < 0.02
    assert max(np.abs(b - b[:, ::-1]).max(), np.abs(b - b[::-1, :]).max(), np.abs(b - b.T).max()) < 2e-3


@pytest.mark.parametrize("backend", BACKENDS)
def test_rain_on_rough_ground_is_kept_across_interfaces(backend):
    level = np.zeros((6, 8), np.int32)
    level[:2, 2:6] = 1
    level[4:6, :2] = 1
    q, _u = grids(level, 192, 256)
    k = 2
    z = gaussian_filter(np.random.default_rng(7).normal(0, 1.0, (200 * k, 264 * k)), 8) * 60 + 1500.0
    z = z + 0.02 * np.arange(264 * k)[None, :] * DX / k
    tab = build_quad_tables(q, ArrayBed(z, DX / k, 4 * k, 4 * k), Tables(), 0.05)
    m = Model(tab, Numerics(**LEVELS), backend)
    m.set_depth(np.zeros(q.shape))
    rate = np.where(q.mask, 40.0 / 3.6e6, 0.0)
    m.set_source(rate)
    m.advance(900.0)
    assert total(m) == pytest.approx(float(rate.sum()) * DX**2 * 900.0, rel=1e-6)


@pytest.mark.parametrize("backend", BACKENDS)
def test_the_coarse_face_carries_the_sum_of_its_fine_faces(backend):
    level = column_levels(4, 10)
    q, _u = grids(level, 64, 320)
    tab = build_quad_tables(q, ArrayBed(np.zeros((72, 328)), DX, 4, 4), Tables(), 0.03)
    m = Model(tab, Numerics(**PLAIN, **LEVELS), backend)
    x = (np.arange(q.shape[1]) + 0.5) * DX
    m.set_depth(np.tile(np.where(x < 1000.0, 2.0, 0.5), (q.shape[0], 1)) * q.mask)
    m.advance(90.0)
    qx = m.backend.get_field("qx")
    row = q.interfaces[q.interfaces[:, 1] == 2][0]
    fine, coarse, offset = int(row[0]), int(row[2]), int(row[4])
    face = fine * STRIDE2 + (6 + HALO) * STRIDE + HALO + TILE
    next_face = face + STRIDE
    coarse_face = coarse * STRIDE2 + (offset + 3 + HALO) * STRIDE + HALO
    assert qx[face] != 0.0
    assert qx[coarse_face] == pytest.approx(qx[face] + qx[next_face], rel=1e-5)


@pytest.mark.parametrize("backend", BACKENDS)
def test_the_coarse_face_carries_the_sum_along_y_too(backend):
    level = column_levels(4, 10).T
    q, _u = grids(level, 320, 64)
    tab = build_quad_tables(q, ArrayBed(np.zeros((328, 72)), DX, 4, 4), Tables(), 0.03)
    m = Model(tab, Numerics(**PLAIN, **LEVELS), backend)
    y = (np.arange(q.shape[0]) + 0.5) * DX
    m.set_depth(np.tile(np.where(y < 1000.0, 2.0, 0.5)[:, None], (1, q.shape[1])) * q.mask)
    m.advance(90.0)
    qy = m.backend.get_field("qy")
    row = q.interfaces[q.interfaces[:, 1] == 3][0]
    fine, coarse, offset = int(row[0]), int(row[2]), int(row[4])
    face = fine * STRIDE2 + (HALO + TILE) * STRIDE + 6 + HALO
    coarse_face = coarse * STRIDE2 + HALO * STRIDE + offset + 3 + HALO
    assert qy[face] != 0.0
    assert qy[coarse_face] == pytest.approx(qy[face] + qy[face + 1], rel=1e-5)


def test_small_cells_never_step_slower_than_the_large_ones_beside_them():
    """Waves alone cannot do it with the buffer at 0.5 or more; only sticky levels can, so this starts from such levels."""
    q, _u = grids(column_levels(4, 10), 64, 320)
    active = np.arange(1, q.ntiles, dtype=np.int32)
    fine, coarse = q.interfaces[:, 0], q.interfaces[:, 2]
    wave = np.full(q.ntiles, 1.0)
    wave[coarse] = 16.0
    far = q.tiles[:, 1] == 0
    wave[far] = 30.0
    previous = np.zeros(q.ntiles, np.int32)
    previous[fine] = 2
    previous[coarse] = 1
    rule = LevelRule(0.45, 1.0, 0.5, 5.0, 3)
    level, _dt = assign_levels(
        wave, active, q.nbr, q.tile_dx, rule, np.zeros(q.ntiles, bool), previous, q.interfaces
    )
    assert np.all(level[fine] <= level[coarse])


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_crest_across_fine_tiles_holds_until_overtopped(backend):
    q, _u = grids(np.array([[0, 0, 1, 1], [0, 0, 1, 1]]), 64, 128)
    crest = CrestFaces.empty(q.shape)
    i = 20
    crest.xz[:, i] = 3.0
    crest.xlen[:, i] = 1.0
    tab = build_quad_tables(q, ArrayBed(np.zeros((72, 136)), DX, 4, 4), Tables(), 0.03, crest)
    m = Model(tab, Numerics(**LEVELS), backend)
    h = np.zeros(q.shape)
    h[:, :i] = 2.0
    m.set_depth(h * q.mask)
    m.advance(120.0)
    assert m.field("h")[:, i + 1 :].max() == 0.0
    h[:, :i] = 3.5
    m.set_depth(h * q.mask)
    m.advance(240.0)
    assert m.field("h")[:, i + 1 :].max() > 0.05


def test_a_crest_in_a_coarse_tile_is_refused():
    q, _u = grids(column_levels(4, 10), 64, 320)
    crest = CrestFaces.empty(q.shape)
    crest.xz[:, 200] = 3.0
    with pytest.raises(ValueError, match="coarse tiles"):
        build_quad_tables(q, ArrayBed(np.zeros((72, 328)), DX, 4, 4), Tables(), 0.03, crest)


@pytest.mark.gpu
def test_cpu_gpu_parity_across_interfaces():
    out = {}
    for name in ("cpu", "gpu"):
        m, q, t = _rough(
            column_levels(3, 6, 4, 10), name, Numerics(**LEVELS, dt_every=1, dt_max=0.2, lts_levels=0)
        )
        _fill(m, q, t, 1505.0)
        m.advance(20.0)
        out[name] = (m.field("h"), m.field("qx"), m.stepper.nsteps)
    assert out["cpu"][2] == out["gpu"][2]
    assert np.abs(out["cpu"][0] - out["gpu"][0]).max() < 1e-3
    assert np.abs(out["cpu"][1] - out["gpu"][1]).max() < 0.05
