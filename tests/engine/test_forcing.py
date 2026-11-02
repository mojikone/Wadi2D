"""Forcing pieces in isolation: injection shares, rain volumes, boundary faces, line faces."""

from __future__ import annotations

import json

import numpy as np
import pytest

from tests.engine.conftest import X0, Y0, job, tilted_box, write_dem
from wadi2d.config.schema import Boundary
from wadi2d.forcing import (
    BoundarySet,
    Forcing,
    Injection,
    boundary_notes,
    boundary_set,
    build_storm,
    cells_along,
    line_faces,
)
from wadi2d.grid import TileGrid
from wadi2d.run import prepare_grid, run_job
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


def _triangle() -> TileGrid:
    """Active below the diagonal: an edge no straight line lies on, 4 m cells."""
    return TileGrid.from_mask(np.tril(np.ones((64, 64), bool)), X0, Y0, 4.0)


def test_a_line_within_a_cell_of_the_domain_keeps_its_cells():
    grid = TileGrid.from_mask(np.ones((16, 16), bool), X0, Y0, 4.0)
    line = [(X0, Y0 - 64.0), (X0 + 64.0, Y0 - 64.0)]
    np.testing.assert_array_equal(cells_along(grid, line), cells_along(grid, line, snap_m=150.0))


def test_a_line_off_the_domain_opens_the_cells_nearest_to_it():
    grid = _triangle()
    line = [(X0 + 40.0, Y0 + 8.0), (X0 + 264.0, Y0 - 216.0)]  # along the diagonal, 32 m off it
    with pytest.raises(ValueError, match="does not touch"):
        cells_along(grid, line, snap_m=8.0)
    j, i = cells_along(grid, line, snap_m=150.0)
    assert grid.mask[j, i].all()
    assert j.size > 50


def test_a_line_too_far_off_is_named_and_a_good_one_is_not():
    mask = np.ones((32, 32), bool)
    grid = TileGrid.from_mask(mask, X0, Y0, 4.0)
    near = Boundary(kind="free", coordinates=[(X0 + 2.0, Y0), (X0 + 2.0, Y0 - 128.0)])
    far = Boundary(
        kind="free", coordinates=[(X0 + 126.0, Y0), (X0 + 126.0, Y0 - 128.0), (X0 + 2000.0, Y0 - 128.0)]
    )
    cells = [cells_along(grid, b.coordinates, 4, b.snap_m)[0].size for b in (near, far)]
    bset = BoundarySet(None, None, None, None, None, None, tuple(cells))
    notes = boundary_notes([near, far], bset, grid.dx)
    assert len(notes) == 1
    assert notes[0].startswith("Open boundary 2: the line is 2.0 km long but opens only 0.2 km of the domain")


def _sloped_outlet_outflow(dem, tmp_path, name: str, off: float) -> tuple[float, int]:
    """Rain on a plane falling east, a domain with a slanted east edge, one outlet ``off`` metres east of that edge."""
    path = tmp_path / f"{name}.geojson"
    ring = [[X0, Y0], [X0 + 170.0, Y0], [X0 + 110.0, Y0 - 96.0], [X0, Y0 - 96.0], [X0, Y0]]
    path.write_text(json.dumps({"type": "Polygon", "coordinates": [ring]}), "utf-8")
    outlet = [(X0 + 170.0 + off, Y0), (X0 + 110.0 + off, Y0 - 96.0)]
    cfg = job(
        dem, 50, 24, 4.0,
        grid={"dx": 4.0, "extent": None, "domain": str(path)},
        storm={"kind": "uniform", "depth_mm": 60.0, "duration_min": 10.0},
        boundaries=[{"kind": "free", "coordinates": outlet}],
        run={"duration_s": 1500.0, "source_every_s": 30.0},
    )  # fmt: skip
    run = run_job(cfg, tmp_path / name)
    assert run.exit_code == 0, run.message
    return run.balance.outflow, run.balance.rain


def test_an_outlet_drawn_off_the_domain_drains_like_one_drawn_on_it(tilted_dem, tmp_path):
    inside, rain = _sloped_outlet_outflow(tilted_dem, tmp_path, "on", -4.0)
    outside, _ = _sloped_outlet_outflow(tilted_dem, tmp_path, "off", 40.0)
    assert inside > 0.5 * rain
    assert outside == pytest.approx(inside, rel=0.05)


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
