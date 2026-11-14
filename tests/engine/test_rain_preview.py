"""``wadi2d rain-preview``: the rain each lumped subbasin and the 2D area take, against the engine's own forcing (W65)."""

from __future__ import annotations

import json

import pytest

from tests.engine.conftest import job
from tests.engine.test_handback import CHAIN, DX, MIDDLE, NX, NY, SINK, SUB, X0, plane, write_basin
from tests.engine.test_network_series import _polygons
from tests.engine.test_rain_run import AREA, AT_505, QUICK, SIDE, TABLE, box, gridded, stack
from tests.engine.test_rain_run import DX as BOX_DX
from wadi2d.engine.cli import main
from wadi2d.engine.rain_preview import AREA_2D, rain_preview
from wadi2d.forcing import build_storm
from wadi2d.run import _lumped_basin, _lumped_rain, run_job


def test_the_2d_depth_of_a_reduced_grid_is_the_rain_the_run_puts_on_its_cells(tmp_path) -> None:
    storm = gridded(stack(tmp_path, 40.0, 10.0), storm_area_km2=505.0, arf=TABLE)
    cfg = job(box(tmp_path), SIDE, SIDE, BOX_DX, storm=storm, run=QUICK)
    found = rain_preview(cfg)
    (area,) = found["areas"]
    assert area["name"] == AREA_2D and area["mode"] == "2d"
    assert found["area_factor"] == pytest.approx(AT_505)
    assert area["depth_mm"] == pytest.approx(25.0 * AT_505, rel=1e-6)
    assert sum(area["mm"]) == pytest.approx(area["depth_mm"], rel=1e-6)
    run = run_job(cfg, tmp_path / "out")
    assert run.exit_code == 0
    assert area["depth_mm"] / 1000.0 * AREA == pytest.approx(run.balance.rain, rel=1e-5)


def test_a_lumped_subbasin_takes_what_the_network_takes_and_the_2d_area_the_rest(tmp_path) -> None:
    wide = SUB.replace("Subbasin: Side", "Subbasin: Wide").format(down="J")
    basin = write_basin(tmp_path, SUB.format(down="J"), wide, CHAIN, SINK)
    table = {"areas_km2": [0.001, 1000.0], "factors": [0.9, 0.5]}
    cfg = job(
        plane(tmp_path), NX, NY, DX,
        storm={"kind": "hypothetical", "depth_mm": 50.0, "duration_min": 60.0, "time_percent": [0, 50, 100],
               "depth_percent": [0, 80, 100], "storm_area_km2": 10.0, "arf": table},
        hydrology={
            "hms_basin": str(basin), "time_step_min": 5.0, "inject_radius": 6.0, "polygons": str(_polygons(tmp_path)),
            "subbasins": [{"name": "Side", "mode": "lumped", "outlet": (X0 + 300.0, MIDDLE)}, {"name": "Wide", "mode": "2d"}],
        },
        run={"duration_s": 7200.0, "backend": "cpu"},
    )  # fmt: skip
    found = rain_preview(cfg)
    names = [(row["name"], row["mode"]) for row in found["areas"]]
    assert names == [("Side", "lumped"), (AREA_2D, "2d")]  # Wide is rain-on-grid: in the 2D area, not a lumped row
    side, two_d = found["areas"]
    basin_model, hms, _cut = _lumped_basin(cfg, "")
    network = _lumped_rain(cfg, build_storm(cfg), basin_model, hms, "").over("Side").increments(5.0, 24)
    assert side["mm"] == pytest.approx(list(network[: len(side["mm"])]), abs=1e-4)
    factor = 0.9 - 0.4 * (10.0 - 0.001) / (1000.0 - 0.001)
    assert side["depth_mm"] == pytest.approx(50.0 * factor, rel=1e-5) == pytest.approx(two_d["depth_mm"], rel=1e-5)
    assert side["peak_mm_h"] == pytest.approx(max(side["mm"]) * 12.0, abs=1e-3)
    assert two_d["area_km2"] == pytest.approx(NX * DX * NY * DX / 1e6 - 40.0 * 40.0 / 1e6, rel=1e-6)


def test_the_command_writes_the_preview_and_refuses_a_job_without_rain(tmp_path, capsys) -> None:
    cfg = job(box(tmp_path), SIDE, SIDE, BOX_DX, storm={"kind": "uniform", "depth_mm": 30.0, "duration_min": 30.0})
    path = tmp_path / "job.json"
    path.write_text(cfg.model_dump_json(), encoding="utf-8")
    out = tmp_path / "preview.json"
    assert main(["rain-preview", str(path), "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["areas"][0]["depth_mm"] == pytest.approx(30.0)
    dry = cfg.model_copy(update={"storm": cfg.storm.model_copy(update={"kind": "none"})})
    path.write_text(dry.model_dump_json(), encoding="utf-8")
    assert main(["rain-preview", str(path), "--out", str(out)]) != 0
    assert "no rain" in capsys.readouterr().err
