"""A lumped hydrograph enters on the wadi, clear above every result line (W41).

The valley is one V down the middle of the test lattice, falling south (``tests/basin/conftest.py``). A dam line runs
across it at row 150; the subbasin is everything north of the line, and its outlet is given two cells below the line,
where HMS's icon of the dam junction lay on Block 2.
"""

from __future__ import annotations

import numpy as np
import pytest
import shapely

from tests.basin.conftest import NX, NY, PIXEL, X0, Y0, col_x, row_y, straight_valley, write_raster
from wadi2d.config.schema import RunConfig
from wadi2d.engine.entries import place_entries
from wadi2d.run import _drop_point_entries, prepare_grid, run_job

pytest.importorskip("whitebox")

LINE_Y = Y0 - 150 * PIXEL
"""The dam line, on the lattice edge between rows 149 and 150."""
DAM = [(X0 + 5.0, LINE_Y), (X0 + NX * PIXEL - 5.0, LINE_Y)]
BELOW = (col_x(NX // 2), row_y(152))
"""The outlet as an HMS icon gives it: two cells below the line, on the thalweg."""
RADIUS = 12.0
NORTH = shapely.box(X0, LINE_Y, X0 + NX * PIXEL, Y0)


def job_on(dem, entry: str, **hydrology) -> RunConfig:
    south = Y0 - NY * PIXEL
    data = {
        "grid": {"dx": PIXEL, "extent": [X0, south, X0 + NX * PIXEL, Y0]},
        "terrain": {"dem": str(dem), "manning": 0.05},
        "hydrology": {"inject_radius": RADIUS, "entry_erode_m": 20.0, **hydrology},
        "boundaries": [{"kind": "free", "coordinates": [(X0 - 5.0, south + 2.0), (X0 + NX * PIXEL + 5.0, south + 2.0)]}],
        "outputs": {
            "map_every_s": 0.0, "live_every_s": 0.0, "series_every_s": 10.0, "progress_every_s": 0.5,
            "pixels": {"enabled": False}, "lines": [{"name": "Dam", "coordinates": DAM}],
        },
        "run": {"duration_s": 900.0, "backend": "cpu", "source_every_s": 10.0, "checkpoint_every_s": 0.0},
    }  # fmt: skip
    if entry:
        data["hydrology"].setdefault("subbasins", [{"name": "S1", "mode": "lumped", "outlet": BELOW, "entry": entry}])
    return RunConfig.model_validate(data)


@pytest.fixture(scope="module")
def valley(tmp_path_factory):
    folder = tmp_path_factory.mktemp("entries")
    return folder, write_raster(folder / "dem.tif", straight_valley())


def test_a_subbasin_enters_at_its_wadi_outlet_clear_above_the_dam_line(valley) -> None:
    folder, dem = valley
    cfg = job_on(dem, "wadi")
    tables, crs = prepare_grid(cfg, folder / "cache")
    (placed,) = place_entries(cfg, tables, {"S1": NORTH}, crs)
    x, y = placed.point
    assert placed.clear and placed.name == "S1" and placed.kind == "subbasin"
    assert abs(x - col_x(NX // 2)) <= 0.5 * PIXEL  # on the thalweg
    assert y - LINE_Y > RADIUS + PIXEL  # the injection's cells and one more stay clear of the line's cells
    assert y - LINE_Y < 6 * PIXEL  # and no farther up the wadi than it must
    assert placed.moved_m > 2 * PIXEL


def test_a_point_entry_and_a_job_without_wadi_entries_are_left_alone(valley) -> None:
    folder, dem = valley
    cfg = job_on(dem, "point")
    tables, crs = prepare_grid(cfg, folder / "cache")
    assert place_entries(cfg, tables, {"S1": NORTH}, crs) == []


def test_a_subbasin_without_a_polygon_walks_up_from_its_outlet(valley) -> None:
    folder, dem = valley
    cfg = job_on(dem, "wadi")
    tables, crs = prepare_grid(cfg, folder / "cache")
    (placed,) = place_entries(cfg, tables, {}, crs)
    assert placed.clear and "outlet" in placed.note
    assert placed.point[1] - LINE_Y > RADIUS + PIXEL  # the walk crossed the line to get clear above it
    assert "started on a line's cells" in placed.note  # and says the line now counts all of it


def test_an_inflow_placed_below_the_line_crosses_it_on_the_grid_only_with_a_wadi_entry(valley) -> None:
    folder, dem = valley
    reads = {}
    for entry in ("point", "wadi"):
        inflow = {"name": "S1", "x": BELOW[0], "y": BELOW[1], "times_s": [0.0, 900.0], "flows": [2.0, 2.0], "entry": entry}
        cfg = job_on(dem, "", inflows=[inflow])
        out = folder / f"run_{entry}"
        run = run_job(cfg, out)
        assert run.exit_code == 0, run.message
        series = np.genfromtxt(out / "series" / "line_Dam.csv", delimiter=",", names=True)
        reads[entry] = float(np.abs(np.trapezoid(series["discharge_m3s"], series["t_s"])))
        assert (out / "entries.json").is_file() == (entry == "wadi")
    assert reads["point"] < 1.0  # m3: entered below the line, the line never sees it
    assert reads["wadi"] > 0.5 * 2.0 * 900.0  # entered above, it crosses the line on the grid


def test_the_job_hash_of_a_job_without_wadi_entries_is_the_hash_it_had_before_entries() -> None:
    hydrology = {
        "subbasins": [{"name": "S1", "entry": "point"}], "inflows": [{"name": "I", "entry": "point"}],
        "entry_erode_m": 80.0,
    }  # fmt: skip
    _drop_point_entries(hydrology)
    assert hydrology == {"subbasins": [{"name": "S1"}], "inflows": [{"name": "I"}]}
    kept = {"subbasins": [{"name": "S1", "entry": "wadi"}], "inflows": [], "entry_erode_m": 80.0}
    _drop_point_entries(kept)
    assert kept["subbasins"][0]["entry"] == "wadi" and kept["entry_erode_m"] == 80.0
