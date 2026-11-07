"""The lumped elements of a depth-area study: an exact lumped rerun where no 2D water is above, the 2D runs where a
hand-back feeds the element, nothing where the grid keeps the water. His decision of 2026-11-07."""

from __future__ import annotations

import csv
import json

import numpy as np
import pytest

from tests.engine.test_handback import SINK, SUB, X0, box, flood, lag_reach, side_polygon, write_basin
from wadi2d.arf import arf_study, bracket_areas, storm_areas
from wadi2d.arf_network import EXACT, FROM_RUNS, ON_GRID, exact_peaks, plan_elements
from wadi2d.forcing import build_storm
from wadi2d.hms import load_basin
from wadi2d.hydrology.depth_area import analyse_point, point_storm
from wadi2d.hydrology.from_hms import basin_from_hms
from wadi2d.hydrology.model import TimeGrid
from wadi2d.hydrology.network import LumpedEngine
from wadi2d.run import InvalidJob

MIDDLE = 2_700_000.0 - 32 * 4.0 / 2.0
STORM = {
    "kind": "uniform", "depth_mm": 30.0, "duration_min": 20.0, "storm_area_km2": 1.0,
    "arf": {"areas_km2": [0.01, 10.0], "factors": [1.0, 0.5], "table_type": "test table"},
}  # fmt: skip
CHAIN = "Junction: J\n     Downstream: R2\nEnd:\n\nReach: R2\n     Downstream: Out\n\n     Route: Lag\n     Lag: 10\nEnd:\n\n"
TOP = SUB.replace("Subbasin: Side", "Subbasin: Top").replace("Area: 0.1", "Area: 0.3")


def plain_network(tmp_path, *extra: str, subbasins=None):
    basin = write_basin(tmp_path, SUB.format(down="J"), *extra, CHAIN, SINK)
    subbasins = subbasins or [{"name": "Side", "mode": "lumped", "outlet": (X0 + 300.0, MIDDLE)}]
    return basin, box(
        tmp_path, basin, storm=STORM, inflows=[], duration=3600.0,
        hydrology={"polygons": str(side_polygon(tmp_path)), "subbasins": subbasins, "handbacks": []},
    )  # fmt: skip


def test_bracketing_areas_span_the_wanted_ones_about_a_factor_two_apart_and_six_at_most():
    assert bracket_areas([20.971], 2.0, 6) == [20.971]
    np.testing.assert_allclose(bracket_areas([20.971, 211.085, 74.3], 2.0, 6), np.geomspace(20.971, 211.085, 5))
    assert len(bracket_areas([1.0, 1000.0], 2.0, 6)) == 6
    assert bracket_areas([10.0, 15.0], 2.0, 6) == pytest.approx([10.0, 15.0])


def test_a_bracketing_study_takes_the_design_lines_and_the_fed_elements(tmp_path):
    data = plain_network(tmp_path)[1].model_dump(mode="json")
    data["arf"]["bracket"] = True
    data["outputs"]["lines"] = [{"name": "A", "coordinates": [(0.0, 0.0), (1.0, 0.0)], "drainage_area_km2": 40.0}]
    cfg = type(plain_network(tmp_path)[1]).model_validate(data)
    assert storm_areas(cfg, [5.0]) == pytest.approx([5.0, 10.0, 20.0, 40.0])
    data["outputs"]["lines"] = []
    with pytest.raises(InvalidJob, match=r"arf.bracket needs"):
        storm_areas(type(cfg).model_validate(data))


def test_with_no_2d_water_above_every_element_is_rerun_alone_at_its_own_area_as_hms_does(tmp_path):
    basin_file, cfg = plain_network(tmp_path)
    view, plans = plan_elements(cfg, "")
    assert {p.name: p.how for p in plans} == {"Side": EXACT, "J": EXACT, "R2": EXACT, "Out": EXACT}
    assert {p.area_km2 for p in plans} == {0.1}
    found = exact_peaks(view, plans, "")
    basin = basin_from_hms(load_basin(basin_file), None)
    grid = TimeGrid(1.0, 60)
    for name in ("Side", "J", "R2", "Out"):
        hms = analyse_point(LumpedEngine(basin), point_storm(build_storm(cfg)), grid, name)
        assert hms.storm_area_km2 == pytest.approx(0.1)
        assert found[name][0] == pytest.approx(hms.peak, rel=1e-9)
        assert found[name][1] == pytest.approx(hms.peak_minutes * 60.0)
    assert found["Side"][0] > found["Out"][0] * 0.99, "a lag reach moves the peak, it does not cut it"


def test_below_a_2d_subbasin_the_grid_holds_the_water_so_the_element_has_no_flow_of_its_own(tmp_path):
    subbasins = [
        {"name": "Side", "mode": "lumped", "outlet": (X0 + 300.0, MIDDLE)},
        {"name": "Top", "mode": "2d"},
    ]
    _basin, cfg = plain_network(tmp_path, TOP.format(down="J"), subbasins=subbasins)
    _view, plans = plan_elements(cfg, "")
    hows = {p.name: p.how for p in plans}
    assert hows == {"Side": EXACT, "Top": ON_GRID, "J": ON_GRID, "R2": ON_GRID, "Out": ON_GRID}
    assert {p.name: p.area_km2 for p in plans}["J"] == pytest.approx(0.4), "its area counts the 2D subbasin"


def test_a_study_reads_a_hand_back_element_from_its_2d_runs_and_its_lumped_subbasin_at_its_own_area(tmp_path):
    basin = write_basin(tmp_path, SUB.format(down="R1"), lag_reach(), SINK)
    back = {"name": "Back", "x": X0 + 340.0, "y": MIDDLE, "element": "R1"}
    cfg = box(
        tmp_path, basin, storm=STORM, inflows=[flood(), back], duration=3600.0,
        hydrology={"polygons": str(side_polygon(tmp_path)),
                   "subbasins": [{"name": "Side", "mode": "lumped", "outlet": (X0 + 300.0, MIDDLE)}]},
        arf={"areas_km2": [0.05, 0.2]},
    )  # fmt: skip
    _view, plans = plan_elements(cfg, "")
    assert {p.name: p.how for p in plans} == {"Side": EXACT, "R1": FROM_RUNS, "Out": ON_GRID}

    out = tmp_path / "study"
    study = arf_study(cfg, out)
    assert study.exit_code == 0, study.message
    assert len(list((out / "runs").iterdir())) == 2, "one 2D run per storm area, never one per element"
    rows = {r["design_point"]: r for r in csv.DictReader((out / "design_points.csv").open(encoding="utf-8"))}
    assert set(rows) == {"Side", "R1"}
    side, fed = rows["Side"], rows["R1"]
    assert side["read_as"].startswith("lumped element, rerun")
    assert float(side["storm_area_low_km2"]) == float(side["storm_area_high_km2"]) == pytest.approx(0.1)
    assert fed["read_as"].startswith("lumped element with 2D water")
    assert (float(fed["storm_area_low_km2"]), float(fed["storm_area_high_km2"])) == (0.05, 0.2)
    low, high, design = (float(fed[k]) for k in ("peak_low_m3s", "peak_high_m3s", "design_peak_m3s"))
    assert low > 0.0 and high > 0.0
    assert min(low, high) <= design <= max(low, high)
    expected = np.exp(np.interp(np.log(0.1), np.log([0.05, 0.2]), np.log([low, high])))
    assert design == pytest.approx(expected, rel=1e-9)
    saved = json.loads((out / "study.json").read_text(encoding="utf-8"))
    assert saved["on_grid"] == ["Out"]
