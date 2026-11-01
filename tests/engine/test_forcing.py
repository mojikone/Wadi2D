"""Forcing pieces in isolation: injection shares, rain volumes, boundary faces, line faces."""

from __future__ import annotations

import numpy as np
import pytest

from tests.engine.conftest import X0, Y0, job, tilted_box, write_dem
from wadi2d.config.schema import Boundary
from wadi2d.forcing import Forcing, Injection, boundary_set, build_storm, cells_along, line_faces
from wadi2d.grid import TileGrid
from wadi2d.run import prepare_grid
from wadi2d.solver.model import Model


def test_injection_goes_to_the_lowest_cell_while_dry_then_with_depth():
    inj = Injection("q", np.arange(3), None, 2, np.array([0.0, 10.0]), np.array([0.0, 10.0]), 0.1)
    np.testing.assert_array_equal(inj.share(np.array([0.0, 0.05, 0.02])), [0.0, 0.0, 1.0])
    np.testing.assert_allclose(inj.share(np.array([0.2, 0.05, 0.6])), [0.25, 0.0, 0.75])


def test_injection_mean_flow_keeps_the_volume():
    inj = Injection("q", np.arange(1), None, 0, np.array([0.0, 100.0, 200.0]), np.array([0.0, 1.0, 2.0]), 0.1)
    assert inj.mean_flow(0.0, 100.0) == pytest.approx(0.5)
    assert inj.mean_flow(100.0, 200.0) == pytest.approx(1.5)
    assert inj.mean_flow(200.0, 300.0) == 0.0
    assert inj.mean_flow(-50.0, 0.0) == 0.0


def test_storm_builders():
    cfg = job("x.tif", 8, 8, 4.0)
    assert build_storm(cfg) is None
    uniform = job(
        "x.tif", 8, 8, 4.0, storm={"kind": "uniform", "depth_mm": 100.0, "duration_min": 60.0,
                                   "storm_area_km2": 50.0,
                                   "arf": {"areas_km2": [10.0, 100.0], "factors": [1.0, 0.8]}},
    )  # fmt: skip
    storm = build_storm(uniform)
    assert storm.total_depth == pytest.approx(100.0 * (1.0 - 0.2 * 40.0 / 90.0))
    hypo = job(
        "x.tif", 8, 8, 4.0, storm={"kind": "hypothetical", "depth_mm": 100.0, "duration_min": 120.0,
                                   "time_percent": [0.0, 50.0, 100.0], "depth_percent": [0.0, 80.0, 100.0]},
    )  # fmt: skip
    assert build_storm(hypo).cumulative_depth(np.array([60.0]))[0] == pytest.approx(80.0)


def small_model(tmp_path, **parts):
    dem = write_dem(tmp_path / "t.tif", tilted_box(64, 64, 2.0, 0.01), 2.0)
    cfg = job(dem, 32, 32, 4.0, **parts)
    tables, _ = prepare_grid(cfg, tmp_path / "cache")
    model = Model(tables, cfg.numerics, "cpu")
    model.set_depth(np.zeros(tables.grid.shape))
    return cfg, tables, model


def test_refresh_steps_add_up_to_the_whole_window(tmp_path):
    cfg, tables, model = small_model(
        tmp_path,
        storm={"kind": "uniform", "depth_mm": 60.0, "duration_min": 60.0},
        hydrology={"curve_number": 75.0},
    )
    bset = boundary_set([], tables)
    forcing = Forcing(cfg, tables, model, bset, build_storm(cfg), {}, [])
    whole = forcing.rate(0.0, 3600.0)[1]
    parts = sum(forcing.rate(t, t + 90.0)[1] for t in np.arange(0.0, 3600.0, 90.0))
    assert parts == pytest.approx(whole, rel=1e-5)
    first = forcing.rate(0.0, 60.0)[1]
    assert first == 0.0, "the initial abstraction takes the first mm"


def test_boundary_cells_take_no_source_and_the_outflow_faces_are_found(tmp_path):
    line = [(X0 + 126.0, Y0), (X0 + 126.0, Y0 - 128.0)]
    b = Boundary(kind="free", coordinates=line)
    cfg, tables, model = small_model(
        tmp_path, storm={"kind": "uniform", "depth_mm": 60.0, "duration_min": 60.0}
    )
    bset = boundary_set([b], tables)
    assert bset.size == 32
    assert bset.mask[:, 32].sum() == 32
    assert bset.xfaces.size == 32
    assert bset.yfaces.size == 0
    assert (bset.xsign == 1.0).all()
    forcing = Forcing(cfg, tables, model, bset, build_storm(cfg), {}, [])
    assert forcing.state.size == 32 * 31


def test_normal_boundary_never_stands_deeper_than_its_inner_cell(tmp_path):
    # the outer column sits in a trench 5 m below the plane: its level must follow, not fill the trench
    z = tilted_box(64, 64, 2.0, 0.01)
    z[:, 60:] -= 5.0
    dem = write_dem(tmp_path / "t.tif", z, 2.0)
    cfg = job(dem, 32, 32, 4.0)
    tables, _ = prepare_grid(cfg, tmp_path / "cache")
    line = [(X0 + 122.0, Y0), (X0 + 122.0, Y0 - 128.0)]
    bset = boundary_set([Boundary(kind="normal", coordinates=line, slope=0.01)], tables)
    assert (bset.cells.kind == 2).all()
    assert (bset.cells.d0 <= 0.0).all()


def test_boundary_on_the_domain_edge_finds_its_cells(tmp_path):
    grid = TileGrid.from_mask(np.ones((16, 16), bool), X0, Y0, 4.0)
    j, i = cells_along(grid, [(X0, Y0 - 64.0), (X0 + 64.0, Y0 - 64.0)])
    assert j.size == 16
    assert (j == 16).all()
    assert grid.mask[j, i].all()
    with pytest.raises(ValueError, match="does not touch"):
        cells_along(grid, [(X0 + 900.0, Y0), (X0 + 950.0, Y0)])


def test_line_faces_sign_follows_the_right_hand_of_the_line():
    grid = TileGrid.from_mask(np.ones((16, 16), bool), X0, Y0, 4.0)
    south_going = line_faces(grid, [(X0 + 20.0, Y0 - 4.0), (X0 + 20.0, Y0 - 44.0)])
    assert south_going.xfaces.size == 10
    assert (south_going.xsign == -1.0).all(), "flow east crosses a south-going line from right to left"
    north_going = line_faces(grid, [(X0 + 20.0, Y0 - 44.0), (X0 + 20.0, Y0 - 4.0)])
    assert (north_going.xsign == 1.0).all()
    east_going = line_faces(grid, [(X0 + 4.0, Y0 - 20.0), (X0 + 44.0, Y0 - 20.0)])
    assert east_going.yfaces.size == 10
    assert (east_going.ysign == 1.0).all(), "south is the right of an east-going line"
