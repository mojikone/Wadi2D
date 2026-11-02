"""Mesh lines: near size for the given rows, each doubling for as many rows out to far, sizes rounded to the ladder."""

from __future__ import annotations

import json

import numpy as np
import pytest
import shapely

from tests.engine.conftest import X0, Y0, job
from tests.engine.test_mesh import _on_mesh, big_valley  # noqa: F401
from tests.engine.test_run import full_job
from wadi2d.config.schema import Mesh, RefineLine, RunConfig
from wadi2d.engine.cli import main
from wadi2d.grid.quad import QuadGrid, balance
from wadi2d.mesh.build import line_sizes, report
from wadi2d.mesh.refine import Lattice, band_levels, line_levels, rung, zone_levels
from wadi2d.run import run_job
from wadi2d.solver.layout import TILE

DX = 10.0
SIDE = 32
"""Lattice squares a side: 32 tiles of 320 m, 10.24 km."""
TOP = 3
ACROSS = [(X0 + 100.0, Y0 - 300.0), (X0 + 900.0, Y0 - 300.0)]
"""Along the test valley, inside its domain."""
EAST_WEST = [(100.0, 5120.0), (10140.0, 5120.0)]
"""Along the lattice's middle, on a square edge."""


def lattice() -> Lattice:
    return Lattice(0.0, DX * TILE * SIDE, DX, SIDE, SIDE)


def request(near: float = 10.0, rows: int = 4, far: float = 80.0, coordinates=None) -> RefineLine:
    return RefineLine(coordinates=coordinates or EAST_WEST, near_dx=near, rows=rows, far_dx=far)


def built(*lines: RefineLine) -> QuadGrid:
    wanted = band_levels(list(lines), lattice(), TOP)
    mask = np.ones((SIDE * TILE, SIDE * TILE), bool)
    return QuadGrid.from_levels(mask, 0.0, DX * TILE * SIDE, DX, wanted)


def size_at(grid: QuadGrid, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """The cell size over each point."""
    j, i = ((grid.y0 - y) // grid.dx).astype(int), ((x - grid.x0) // grid.dx).astype(int)
    keep = (j >= 0) & (j < grid.shape[0]) & (i >= 0) & (i < grid.shape[1])
    tiles = grid.tile_of[j[keep] // TILE, i[keep] // TILE]
    return grid.tile_dx[tiles]


def biggest_within(grid: QuadGrid, line: list[tuple[float, float]], reach: float) -> float:
    """The largest cell found within ``reach`` of the line, on a 5 m lattice of points."""
    ax = np.arange(2.5, grid.shape[1] * grid.dx, 5.0)
    x, y = np.meshgrid(ax, ax)
    points = shapely.points(x.ravel(), grid.y0 - y.ravel())
    near = shapely.distance(points, shapely.LineString(line)) <= reach
    return float(size_at(grid, shapely.get_x(points)[near], shapely.get_y(points)[near]).max())


@pytest.mark.parametrize(
    ("asked", "level"),
    [(10.0, 0), (15.0, 0), (19.99, 0), (20.0, 1), (30.0, 1), (40.0, 2), (79.0, 2), (80.0, 3), (500.0, 3), (5.0, 0), (0.5, 0)],
)
def test_a_size_goes_down_the_ladder_and_stays_on_it(asked, level):
    assert rung(asked, DX, TOP) == level


def test_a_size_on_a_rung_stays_there_through_float_noise():
    assert rung(40.000000001, DX, TOP) == 2
    assert rung(39.999999999, DX, TOP) == 2


def test_near_and_far_must_be_the_right_way_round():
    with pytest.raises(ValueError, match="near_dx"):
        request(near=40.0, far=20.0)


def test_rows_must_be_at_least_one():
    with pytest.raises(ValueError):
        request(rows=0)


def test_a_line_needs_two_points():
    with pytest.raises(ValueError):
        RefineLine(coordinates=[(0.0, 0.0)], near_dx=10.0, far_dx=20.0)


def test_no_lines_change_nothing():
    assert (band_levels([], lattice(), TOP) == TOP).all()
    assert Mesh().lines == []


def test_near_cells_hold_for_the_rows_asked_on_each_side():
    grid = built(request(rows=4))
    assert biggest_within(grid, EAST_WEST, 40.0) == 10.0


def test_near_cells_hold_for_a_slanted_line_too():
    line = [(1000.0, 1000.0), (9000.0, 8300.0)]
    grid = built(request(rows=9, coordinates=line))
    assert biggest_within(grid, line, 90.0) == 10.0


@pytest.mark.parametrize("rows", [40, 90])
def test_every_doubling_holds_for_as_many_rows(rows):
    grid = built(request(rows=rows, far=40.0))
    assert biggest_within(grid, EAST_WEST, rows * 10.0) == 10.0
    assert biggest_within(grid, EAST_WEST, rows * 30.0) <= 20.0
    assert biggest_within(grid, EAST_WEST, rows * 70.0) <= 40.0


def test_past_the_band_the_cells_reach_the_coarsest():
    grid = built(request(rows=4, far=20.0))
    assert grid.tile_dx[1:].max() == 80.0
    assert set(np.unique(grid.tile_dx[1:])) == {10.0, 20.0, 40.0, 80.0}


def cells_on_a_wide_lattice(rows: int, far: float) -> int:
    """Far from the edges, so that the balance is not what fills the lattice."""
    side = 96
    size = side * TILE * DX
    line = [(200.0, size / 2.0 + 37.0), (size - 200.0, size / 2.0 + 37.0)]
    wanted = band_levels([request(rows=rows, far=far, coordinates=line)], Lattice(0.0, size, DX, side, side), TOP)
    return QuadGrid.from_levels(np.ones((side * TILE, side * TILE), bool), 0.0, size, DX, wanted).cell_count


def test_far_changes_the_mesh_once_the_band_outgrows_a_tile():
    assert cells_on_a_wide_lattice(64, 40.0) > cells_on_a_wide_lattice(64, 10.0)


@pytest.mark.parametrize("rows", [2, 32])
def test_up_to_a_tile_of_rows_far_changes_nothing(rows):
    """The 2:1 balance grades through every size anyway, one ring of tiles each. Far_sweep.py measures it; the dock says so."""
    assert cells_on_a_wide_lattice(rows, 10.0) == cells_on_a_wide_lattice(rows, 80.0)


def test_a_near_size_above_the_finest_gives_that_size():
    grid = built(request(near=20.0, rows=6))
    assert biggest_within(grid, EAST_WEST, 120.0) == 20.0
    assert grid.tile_dx[1:].min() == 20.0


def test_a_near_size_off_the_ladder_goes_down():
    grid = built(request(near=30.0, rows=6))
    assert grid.tile_dx[1:].min() == 20.0


def test_a_line_at_the_coarsest_refines_nothing():
    assert built(request(near=80.0, far=80.0)).level[1:].min() == TOP


def test_two_lines_take_the_finer_of_the_two():
    other = [(5120.0, 100.0), (5120.0, 10140.0)]
    grid = built(request(near=10.0, far=10.0), request(near=40.0, far=40.0, coordinates=other))
    assert biggest_within(grid, EAST_WEST, 40.0) == 10.0
    assert biggest_within(grid, other, 160.0) == 40.0


def test_the_band_stays_2_to_1():
    wanted = band_levels([request(rows=3)], lattice(), TOP)
    settled = balance(wanted, TOP)
    assert (settled == balance(settled, TOP)).all()
    assert np.abs(np.diff(settled, axis=0)).max() <= 1
    assert np.abs(np.diff(settled, axis=1)).max() <= 1


def test_zones_read_the_ladder_as_before():
    ring = [(10.0, 10.0), (300.0, 10.0), (300.0, 300.0), (10.0, 300.0)]
    for dx, level in ((10.0, 0), (15.0, 0), (20.0, 1), (35.0, 1), (40.0, 2), (900.0, TOP)):
        mesh = Mesh(zones=[{"coordinates": ring, "dx": dx}])
        assert zone_levels(mesh, lattice(), TOP).min() == level
        assert int(np.clip(np.floor(np.log2(dx / DX) + 1e-9), 0, TOP)) == level


def test_lines_on_the_finest_lattice_are_as_they_were():
    """The must-be-fine rule is not a band: level 0 on what it touches, and nothing around it."""
    out = line_levels([EAST_WEST], lattice(), 20.0, TOP)
    assert set(np.unique(out)) == {0, TOP}


def config(dx: float = 10.0, coarse: float = 80.0, **line) -> RunConfig:
    return RunConfig.model_validate(
        {
            "grid": {"dx": dx},
            "mesh": {
                "enabled": True,
                "coarse_dx": coarse,
                "lines": [{"name": "Wadi", "coordinates": EAST_WEST, "near_dx": 15.0, "far_dx": 30.0, "rows": 5, **line}],
            },
        }
    )


def test_each_line_says_what_was_asked_and_what_it_gets():
    assert line_sizes(config()) == [
        {
            "name": "Wadi", "near_asked": 15.0, "near": 10.0, "rows": 5, "far_asked": 30.0, "far": 20.0,
            "reach": 150.0, "rounded": True,
        }
    ]  # fmt: skip


def test_a_line_on_the_ladder_says_it_was_not_rounded():
    assert line_sizes(config(near_dx=20.0, far_dx=40.0))[0]["rounded"] is False


def test_a_far_size_alone_off_the_ladder_is_said_too():
    """A mutation check found nothing held this: the run would keep quiet about a far size it moved."""
    sizes = line_sizes(config(near_dx=10.0, far_dx=30.0))[0]
    assert (sizes["near"], sizes["far"], sizes["rounded"]) == (10.0, 20.0, True)


def test_sizes_past_the_ends_of_the_ladder_are_held_there():
    sizes = line_sizes(config(near_dx=5.0, far_dx=500.0))[0]
    assert (sizes["near"], sizes["far"], sizes["rounded"]) == (10.0, 80.0, True)


def test_an_unnamed_line_takes_its_number():
    data = config().model_dump(mode="json")
    data["mesh"]["lines"][0]["name"] = ""
    assert line_sizes(RunConfig.model_validate(data))[0]["name"] == "Line 1"


def test_the_report_carries_the_lines():
    grid = built(request())
    assert report(grid, 100, DX).lines == []
    assert report(grid, 100, DX, line_sizes(config())).lines[0]["near"] == 10.0


def on_valley(dem, **line) -> RunConfig:
    """Rain on the valley; streams off, so the band is the line's own doing."""
    base = _on_mesh(full_job(dem, "cpu", 300.0), stream_area_fine_km2=900.0, stream_area_mid_km2=900.0)
    data = base.model_dump(mode="json")
    data["mesh"]["lines"] = [{"name": "Band", "near_dx": 4.0, "far_dx": 8.0, "rows": 3, **line}]
    return RunConfig.model_validate(data)


def test_a_band_runs_through_the_engine_and_keeps_the_water(big_valley, tmp_path):  # noqa: F811
    pytest.importorskip("whitebox")
    cfg = on_valley(big_valley, coordinates=ACROSS)
    summary = run_job(cfg, tmp_path / "run")
    assert summary.exit_code == 0, summary.message
    assert abs(summary.balance.relative) < 1e-5


def test_a_band_adds_cells_to_a_mesh(big_valley, tmp_path):  # noqa: F811
    pytest.importorskip("whitebox")
    cfg = on_valley(big_valley, coordinates=ACROSS)
    data = cfg.model_dump(mode="json")
    data["mesh"]["lines"] = []
    plain = run_job(RunConfig.model_validate(data), tmp_path / "plain")
    band = run_job(cfg, tmp_path / "band")
    assert band.cells > plain.cells


def test_a_run_says_when_a_line_was_rounded(big_valley, tmp_path):  # noqa: F811
    pytest.importorskip("whitebox")
    cfg = on_valley(big_valley, near_dx=5.0, far_dx=8.0, coordinates=ACROSS)
    assert run_job(cfg, tmp_path / "run").exit_code == 0
    said = (tmp_path / "run" / "progress.jsonl").read_text(encoding="utf-8")
    warnings = [json.loads(s)["message"] for s in said.splitlines() if '"warn"' in s[:30]]
    assert any("Band" in text and "5 m" in text and "4 m" in text for text in warnings)


def test_a_line_on_the_ladder_says_nothing(big_valley, tmp_path):  # noqa: F811
    pytest.importorskip("whitebox")
    cfg = on_valley(big_valley, coordinates=ACROSS)
    assert run_job(cfg, tmp_path / "run").exit_code == 0
    assert "rounded" not in (tmp_path / "run" / "progress.jsonl").read_text(encoding="utf-8")


def test_a_line_that_misses_the_domain_is_refused(big_valley, tmp_path):  # noqa: F811
    """It would refine nothing and say nothing, as a boundary line off the domain once did."""
    pytest.importorskip("whitebox")
    cfg = on_valley(big_valley, coordinates=[(X0 - 5000.0, Y0 + 5000.0), (X0 - 4000.0, Y0 + 5000.0)])
    summary = run_job(cfg, tmp_path / "run")
    assert summary.exit_code == 2
    assert "Band" in summary.message
    assert "domain" in summary.message


def test_the_preview_reports_each_line(big_valley, tmp_path, capsys):  # noqa: F811
    pytest.importorskip("whitebox")
    path = tmp_path / "job.json"
    cfg = on_valley(big_valley, coordinates=ACROSS)
    path.write_text(cfg.model_dump_json(), encoding="utf-8")
    assert main(["mesh", str(path), "--out", str(tmp_path / "preview")]) == 0
    capsys.readouterr()
    lines = json.loads((tmp_path / "preview" / "mesh.json").read_text(encoding="utf-8"))["lines"]
    assert lines[0]["name"] == "Band"
    assert lines[0]["near"] == 4.0


def test_lines_are_ignored_on_the_uniform_grid(big_valley, tmp_path):  # noqa: F811
    base = job(big_valley, 64, 64, 4.0, run={"duration_s": 30.0})
    data = base.model_dump(mode="json")
    plain = run_job(base, tmp_path / "plain")
    data["mesh"]["lines"] = [{"coordinates": [(0.0, 0.0), (1.0, 1.0)], "near_dx": 4.0, "far_dx": 8.0}]
    other = run_job(RunConfig.model_validate(data), tmp_path / "other")
    assert other.cells == plain.cells
    assert other.steps == plain.steps
