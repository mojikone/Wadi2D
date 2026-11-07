"""A design line on a generated basin reads the lumped water that passes it inside a reach (W41).

End to end on the synthetic valley of ``tests/basin/conftest.py``: a design line across the main valley below the fork
becomes a junction whose water runs down a reach to the outlet, so the grid line sees almost nothing. The record adds
the junction's network outflow.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from tests.basin.conftest import NX, NY, PIXEL, X0, Y0, row_y, valley_dem, write_job, write_raster
from wadi2d.basin.build import build_basin
from wadi2d.basin.contract import read_model
from wadi2d.config.schema import BasinSettings, RunConfig
from wadi2d.engine.design_lines import GRID, NETWORK, TOTAL, _side, plans, records
from wadi2d.io.results import write_series_csv
from wadi2d.run import load_job, run_job

SOUTH = Y0 - NY * PIXEL
DAM_Y = row_y(220) + 0.5 * PIXEL
DAM = [(X0 + 300.0, DAM_Y), (X0 + NX * PIXEL - 300.0, DAM_Y)]
"""Across the main valley, 0.7 km below the fork and 0.8 km above the outlet; drawn west to east, so south is its
right, the side it counts positive."""
SETTINGS = BasinSettings(stream_threshold_km2=0.5, snap_m=30.0, section_half_width_m=300.0, section_search_m=20.0)


def test_the_side_is_the_one_a_line_counts_positive() -> None:
    assert _side(DAM, (X0 + 1000.0, DAM_Y - 50.0)) == 1.0  # south of a line drawn east: its right
    assert _side(DAM, (X0 + 1000.0, DAM_Y + 50.0)) == -1.0


def _generated(handback_y: float | None) -> SimpleNamespace:
    dam = {"name": "Dam", "kind": "junction", "outlet": [X0 + 1000.0, DAM_Y], "pour_point": {"line": "Dam"}}
    outlet = {"name": "J1", "kind": "junction", "outlet": [X0 + 1000.0, SOUTH + 5.0]}
    junction = SimpleNamespace(junction="Dam", route="reach", next_junction="J1")
    lines = []
    if handback_y is not None:
        lines = [SimpleNamespace(name="Dam", element="Dam", coordinates=[(X0 + 900.0, handback_y), (X0 + 1100.0, handback_y)])]
    return SimpleNamespace(model={"elements": [dam, outlet]}, junctions=[junction], handbacks=lines)


def test_a_reach_routed_junction_on_the_line_is_added_with_the_lines_sign_and_a_handback_below_is_taken_off(
    tmp_path: Path,
) -> None:
    cfg = RunConfig.model_validate({"outputs": {"lines": [{"name": "Dam", "coordinates": DAM}]}})
    (plan,) = plans(cfg, _generated(DAM_Y - 10.0))
    (part,) = plan.parts
    assert plan.line == "Dam" and part.element == "Dam" and part.sign == 1.0 and part.handback == "Dam"
    assert plans(cfg, _generated(DAM_Y + 30.0))[0].parts[0].handback is None  # a hand-back above: already off the grid
    t_net = np.array([0.0, 600.0, 1200.0])
    write_series_csv(tmp_path / "series" / "network_Dam.csv", t_net, {"inflow_m3s": t_net * 0, "outflow_m3s": np.array([0.0, 100.0, 50.0])})
    write_series_csv(tmp_path / "series" / "handback_Dam.csv", t_net, {"inflow_m3s": np.array([0.0, 4.0, 2.0])})
    t = np.array([0.0, 300.0, 600.0, 900.0, 1200.0])
    grid = np.array([0.0, 2.0, 4.0, 3.0, 2.0])
    made, notes = records([plan], tmp_path, t, {"Dam": grid})
    assert notes == []
    np.testing.assert_allclose(made["Dam"][NETWORK], [0.0, 48.0, 96.0, 72.0, 48.0])
    np.testing.assert_allclose(made["Dam"][TOTAL], made["Dam"][GRID] + made["Dam"][NETWORK])


def test_a_job_with_no_generated_basin_plans_nothing() -> None:
    assert plans(RunConfig.model_validate({}), None) == []


@pytest.fixture(scope="module")
def dam_run(tmp_path_factory):
    pytest.importorskip("whitebox")
    folder = tmp_path_factory.mktemp("design_line")
    dem = write_raster(folder / "dem.tif", valley_dem())
    cn = write_raster(folder / "cn.tif", np.full((NY, NX), 85.0))
    lines = {"lines": [{"name": "Dam", "coordinates": DAM}]}
    job = write_job(folder, dem, terrain={"cn_raster": str(cn), "manning": 0.05}, outputs=lines)
    basin = Path(build_basin(load_job(job), SETTINGS, None, folder / "basin")["basin"])
    data = {
        "grid": {"dx": PIXEL, "extent": [X0, SOUTH, X0 + NX * PIXEL, Y0]},
        "terrain": {"dem": str(dem), "cn_raster": str(cn), "manning": 0.05},
        "storm": {"kind": "uniform", "depth_mm": 60.0, "duration_min": 60.0},
        "hydrology": {"basin_json": str(basin), "time_step_min": 2.0, "inject_radius": 12.0},
        "boundaries": [{"kind": "free", "coordinates": [(X0 - 5.0, SOUTH + 2.0), (X0 + NX * PIXEL + 5.0, SOUTH + 2.0)]}],
        "outputs": {
            "map_every_s": 0.0, "live_every_s": 0.0, "series_every_s": 30.0, "progress_every_s": 0.5,
            "pixels": {"enabled": False}, **lines,
        },
        "run": {"duration_s": 4.0 * 3600.0, "backend": "cpu", "source_every_s": 30.0, "checkpoint_every_s": 0.0},
    }  # fmt: skip
    out = folder / "run"
    run = run_job(RunConfig.model_validate(data), out)
    return basin, out, run


def test_the_design_line_on_a_lumped_reach_reads_the_networks_flow(dam_run) -> None:
    basin, out, run = dam_run
    assert run.exit_code == 0, run.message
    junction = next(e for e in read_model(basin)["elements"] if (e.get("pour_point") or {}).get("line") == "Dam")
    assert junction["downstream"] is not None  # a reach carries its water past the line
    record = np.genfromtxt(out / "series" / "design_Dam.csv", delimiter=",", names=True)
    network = np.genfromtxt(out / "series" / f"network_{junction['name']}.csv", delimiter=",", names=True)
    grid = np.abs(record[GRID])
    total = np.abs(record[TOTAL])
    assert grid.max() < 0.05 * total.max()  # the grid alone sees almost nothing: the W39 symptom
    assert total.max() == pytest.approx(network["outflow_m3s"].max(), rel=0.02)
    volume = float(np.trapezoid(total, record["t_s"]))
    assert volume == pytest.approx(float(np.trapezoid(network["outflow_m3s"], network["t_s"])), rel=0.02)
    assert run.peaks["Dam"][0] == pytest.approx(total.max(), rel=1e-6)  # the run's peak for the line is the record's
