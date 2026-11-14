"""A dam breach on the quadtree (W71): the dam's faces found through the quadtree's own slots, the pool in coarse cells
across an interface, the same trapezoid, the books, the peak against the squares of the finest size; a trigger never
reached changes nothing."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from tests.engine.conftest import X0, Y0, job, write_dem
from tests.engine.test_breach import breach, series
from wadi2d.breach.control import build_breaches
from wadi2d.breach.faces import face_slot, read_back
from wadi2d.breach.shape import opened_area, opening
from wadi2d.run import prepare_grid, run_job
from wadi2d.solver.layout import CLOSED, TILE2
from wadi2d.solver.model import Model
from wadi2d.terrain.crest import WEST

pytest.importorskip("whitebox")

PIXEL, DX = 2.0, 8.0
NX, NY = 192, 64  # 1,536 x 512 m: three squares of 16 m tiles side by side
FALL, SIDE = 0.01, 0.2
CREST_Z, POOL_Z, BED = 103.0, 102.5, 98.0
MID = NY * DX / 2.0


def ground_at(dam_x: float):
    return lambda x, y: BED + FALL * (dam_x - x) + SIDE * np.abs(y - MID)


@pytest.fixture
def dems(tmp_path: Path) -> dict[float, Path]:
    x = (np.arange(NX * DX / PIXEL) + 0.5) * PIXEL
    y = (np.arange(NY * DX / PIXEL) + 0.5) * PIXEL
    return {d: write_dem(tmp_path / f"v{d:g}.tif", ground_at(d)(x[None, :], y[:, None]), PIXEL) for d in (256.0, 504.0)}


MESHES = {
    # the pool in 16 m cells west of the dam, the dam on the west faces of the fine tiles: an interface (refine_lines off,
    # a zone holds everything east of the dam fine)
    "interface": (504.0, {
        "enabled": True, "coarse_dx": 16.0, "min_dx": 4.0, "analysis_pixel": 8.0, "refine_lines": False,
        "stream_area_fine_km2": 100.0, "stream_area_mid_km2": 100.0,
        "zones": [{"coordinates": [(X0 + 512.0, Y0), (X0 + NX * DX, Y0), (X0 + NX * DX, Y0 - NY * DX), (X0 + 512.0, Y0 - NY * DX)], "dx": 8.0}],
    }),
    # the dam and the pool fine, the flood through 16 m cells between 512 and 1,024 m, fine again at the outlet
    "coarse_below": (256.0, {
        "enabled": True, "coarse_dx": 16.0, "min_dx": 4.0, "analysis_pixel": 8.0,
        "stream_area_fine_km2": 100.0, "stream_area_mid_km2": 100.0,
    }),
}  # fmt: skip


def quad_job(dem: Path, dam_x: float, mesh: dict | None, breaches=(), duration=900.0, backend="cpu"):
    across = [(X0 + dam_x, Y0), (X0 + dam_x, Y0 - NY * DX)]
    pool = [(X0, Y0), (X0 + dam_x, Y0), (X0 + dam_x, Y0 - NY * DX), (X0, Y0 - NY * DX)]
    below = [(X0 + dam_x + 100.0, Y0), (X0 + dam_x + 100.0, Y0 - NY * DX)]
    extra = {} if mesh is None else {"mesh": mesh}
    return job(
        dem, NX, NY, DX,
        terrain={"objects": [{"kind": "crest_line", "name": "Dam", "coordinates": across, "z_constant": CREST_Z}]},
        boundaries=[{"kind": "free", "coordinates": [(X0 + NX * DX - 4.0, Y0), (X0 + NX * DX - 4.0, Y0 - NY * DX)]}],
        initial_levels=[{"coordinates": pool, "level": POOL_Z}],
        breaches=list(breaches),
        outputs={"lines": [{"name": "Below", "coordinates": below}]},
        run={"duration_s": duration, "backend": backend},
        **extra,
    )  # fmt: skip


def the_breach(**over) -> dict:
    return breach(station_m=MID, bottom_z=BED, bottom_width_m=16.0, **over)


def test_the_quadtree_faces_hold_the_trapezoid_across_an_interface(dems, tmp_path) -> None:
    dam_x, mesh = MESHES["interface"]
    cfg = quad_job(dems[dam_x], dam_x, mesh, [the_breach()])
    tables, crs = prepare_grid(cfg, tmp_path / "cache")
    grid = tables.grid
    assert grid.quad and set(grid.level[1:].tolist()) == {0, 1}
    model = Model(tables, cfg.numerics, "cpu")
    run = build_breaches(cfg, tables, model, None, crs).runs[0]  # the self-check passed
    f = run.faces
    (jl, il), _ = f.cells(int(np.argmin(np.abs(f.s.mean(axis=1) - MID))))
    assert grid.level[grid.tile_of[jl // 32, il // 32]] == 1, "the pool side of the dam is a 16 m cell"
    assert run.areas == (256.0, 64.0)
    rows = cfg.tables.rows
    before = read_back(model.backend, f, rows)
    run.started = 0.0
    run.update(run.geo.time)
    after = read_back(model.backend, f, rows)
    cut = np.nonzero(after.cw != before.cw)[0]
    assert cut.size > 0 and np.all(after.cw[cut] == pytest.approx(1.44))
    zf = after.fr + f.zmin_r
    area = 0.0
    for m in cut:
        r = np.sqrt(np.clip((CREST_Z - zf[m]) / after.ef[m], 0.0, 1.0)) * (rows - 1)
        area += float(np.interp(r, np.arange(rows), after.ftab[m][:, 0]))
    s = np.linspace(0.0, NY * DX, 20001)
    exact = opened_area(run.geo, opening(run.geo, 1.0, "overtopping", None, False), CREST_Z, ground_at(dam_x)(dam_x, s), s)
    assert area == pytest.approx(exact, rel=0.03)
    assert zf[cut].min() == pytest.approx(BED, abs=PIXEL * SIDE + 1e-6)
    np.testing.assert_array_equal(after.ftab[after.cw == before.cw], before.ftab[after.cw == before.cw])


def test_an_east_interface_face_has_its_slot_in_the_extra_tiles(dems, tmp_path) -> None:
    dam_x, mesh = MESHES["coarse_below"]
    tables, _crs = prepare_grid(quad_job(dems[dam_x], dam_x, mesh), tmp_path / "cache")
    grid = tables.grid
    i = 64  # the first column of the 16 m square: the grid is padded one cell at its north-west corner
    assert grid.level[grid.tile_of[0, i // 32]] == 1 and grid.level[grid.tile_of[0, i // 32 - 1]] == 0
    flx = tables.flx.reshape(-1)
    for j in (3, 33, 40):
        fid, east = face_slot(grid, WEST, j, i)
        assert east and fid >= grid.ntiles * TILE2, "east interface faces live after the real tiles"
        assert flx[fid] < 0.5 * CLOSED, "and are open between two wet cells"
    assert face_slot(grid, WEST, 3, i - 5) == (int(grid.tile_of[0, 1]) * TILE2 + 3 * 32 + (i - 5 - 32), False)


@pytest.mark.parametrize("case", sorted(MESHES))
def test_a_breach_on_the_quadtree_closes_the_books_and_peaks_as_on_the_squares(dems, tmp_path, case) -> None:
    dam_x, mesh = MESHES[case]
    b = [the_breach()]
    square = run_job(quad_job(dems[dam_x], dam_x, None, b), tmp_path / "square")
    quad = run_job(quad_job(dems[dam_x], dam_x, mesh, b), tmp_path / "quad")
    peaks = {}
    for name, s in (("square", square), ("quad", quad)):
        assert s.exit_code == 0, s.message
        assert abs(s.balance.relative) < 1e-6, (name, s.balance)
        rows = series(tmp_path / name, "breach_Dam.csv")
        assert rows[0, 0] == pytest.approx(60.0, abs=1e-9)
        assert rows[rows[:, 1] >= 1.0 - 1e-12][0, 0] == pytest.approx(360.0, abs=1e-9)
        peaks[name] = float(np.abs(series(tmp_path / name, "line_Below.csv")[:, 1]).max())
    print("W71 quad peaks", case, peaks, "storage0", square.balance.storage0, quad.balance.storage0)
    assert quad.balance.storage0 == pytest.approx(square.balance.storage0, rel=0.01)
    assert peaks["quad"] == pytest.approx(peaks["square"], rel=0.05)


def test_a_breach_never_triggered_on_the_quadtree_changes_nothing(dems, tmp_path) -> None:
    dam_x, mesh = MESHES["interface"]
    a = run_job(quad_job(dems[dam_x], dam_x, mesh, duration=300.0), tmp_path / "a")
    b = run_job(quad_job(dems[dam_x], dam_x, mesh, [the_breach(trigger="level", trigger_level=CREST_Z + 5.0)], 300.0), tmp_path / "b")
    assert a.exit_code == b.exit_code == 0, (a.message, b.message)
    assert a.balance.storage == b.balance.storage
    np.testing.assert_array_equal(series(tmp_path / "a", "line_Below.csv"), series(tmp_path / "b", "line_Below.csv"))


@pytest.mark.gpu
def test_the_breach_on_the_quadtree_on_the_gpu_reads_the_cpu_peak(dems, tmp_path) -> None:
    dam_x, mesh = MESHES["interface"]
    b = [the_breach()]
    cpu = run_job(quad_job(dems[dam_x], dam_x, mesh, b), tmp_path / "cpu")
    gpu = run_job(quad_job(dems[dam_x], dam_x, mesh, b, backend="gpu"), tmp_path / "gpu")
    assert cpu.exit_code == 0 and gpu.exit_code == 0 and gpu.backend == "gpu", gpu.message
    assert abs(gpu.balance.relative) < 1e-6
    peak = {k: float(np.abs(series(tmp_path / k, "line_Below.csv")[:, 1]).max()) for k in ("cpu", "gpu")}
    print("W71 quad gpu", peak)
    assert peak["gpu"] == pytest.approx(peak["cpu"], rel=1e-3)
