# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""What a job alone tells the dock (W99): a run from before the model was saved, read back as section states."""

from __future__ import annotations

import json
from pathlib import Path

from wadi2d_qgis import job_states
from wadi2d_qgis.job_builder import Feature, build_job


def values(**more) -> dict:
    base = {
        "dem": "dem.tif", "crs": "EPSG:32640", "pixel": 5.0, "dx": 30.0, "manning": 0.045, "duration_h": 2.0,
        "rain_mm_h": 40.0, "rain_hours": 0.5, "curve_number": 85.0, "map_every_s": 900.0, "pixels": False,
        "domain": [Feature("Polygon", [[[0.0, 0.0], [90.0, 0.0], [90.0, 90.0], [0.0, 0.0]]])],
        "boundaries": [Feature("LineString", [[0.0, 0.0], [90.0, 0.0]], {"kind": "normal", "value": 0.012})],
        "design": [Feature("LineString", [[10.1234567, 0.0], [10.0, 90.0]], {"name": "dam"})],
    }  # fmt: skip
    return {**base, **more}


def test_a_plain_job_comes_back_as_section_states(tmp_path: Path) -> None:
    job = build_job(values(), tmp_path)
    states = job_states.job_states(job, tmp_path)
    terrain = states["terrain"]["widgets"]
    assert terrain["dx"] == 30.0 and terrain["manning.box"] == 0.045 and terrain["fill_pits"] is False
    assert terrain["dem"]["provider"] == "gdal" and terrain["dem"]["source"].endswith("dem.tif")
    assert Path(terrain["domain"]["source"]) == tmp_path.resolve() / "inputs" / "domain.geojson"
    storm = states["storm"]["widgets"]
    # W101: the Steady rain is a fixed depth, the same job (40 mm/h for 0.5 h is 20 mm over 0.5 h)
    assert (storm["kind"]["data"], storm["fixed_depth"], storm["hours"]) == ("fixed", 20.0, 0.5)
    assert states["hydrology"]["widgets"]["cn.box"] == 85.0
    assert states["points"]["widgets"]["name"] == "name"
    run, simulation = states["run"]["widgets"], states["simulation"]["widgets"]
    assert (run["pixels"], run["folder"]) == (False, str(tmp_path))
    assert (simulation["duration"], simulation["maps"]["data"], simulation["step_mode"]["data"]) == (
        2.0,
        900.0,
        "auto",
    )
    for unsaid in ("start", "cfl", "dt_max", "dt_min", "lumped_step", "series", "backend"):
        assert unsaid not in simulation  # what the job leaves to the engine stays at the dock's defaults


def test_the_simulation_section_is_read_back_from_a_job(tmp_path: Path) -> None:
    job = build_job(values(), tmp_path)
    job["numerics"] = {"dt_max": 0.5, "dt_min": 0.5}
    job["hydrology"]["time_step_min"] = 2.0
    job["outputs"]["series_every_s"] = 30.0
    job["storm"] = {
        "kind": "gridded",
        "rain_file": "rain.nc",
        "rain_units": "mm",
        "rain_stamp": "end",
        "rain_start": "2021-10-03 06:00",
    }
    states = job_states.job_states(job, tmp_path)
    simulation, storm = states["simulation"]["widgets"], states["storm"]["widgets"]
    assert (simulation["step_mode"]["data"], simulation["fixed_step"]) == ("fixed", 0.5)
    assert (simulation["lumped_step"], simulation["series"], simulation["start"]) == (
        2.0,
        30.0,
        "2021-10-03 06:00",
    )
    assert "start" not in storm and "gauge_start" not in storm  # the run has one start, and it is not Storm's
    job["numerics"] = {"cfl": 0.3, "local_time_stepping": True}
    job["storm"] = {"kind": "uniform", "depth_mm": 20.0, "duration_min": 30.0}
    job["outputs"]["observed"] = [{"name": "g", "start": "2021-10-04 00:00"}]
    simulation = job_states.job_states(job, tmp_path)["simulation"]["widgets"]
    assert (simulation["step_mode"]["data"], simulation["cfl"], simulation["start"]) == (
        "auto",
        0.3,
        "2021-10-04 00:00",
    )
    assert "fixed_step" not in simulation and "dt_max" not in simulation


def test_storms_the_dock_writes_are_read_back(tmp_path: Path) -> None:
    design = {
        "kind": "hypothetical", "depth_mm": 120.0, "hours": 6.0, "pattern": [(0.0, 0.0), (100.0, 100.0)],
        "arf_mode": "area", "area_km2": 74.3, "arf": [(10.0, 0.99), (100.0, 0.913)],
    }  # fmt: skip
    states = job_states.job_states(build_job(values(storm=design), tmp_path), tmp_path)
    storm = states["storm"]["widgets"]  # W101: a design storm comes back as a depth with its pattern in Data tables
    assert (storm["kind"]["data"], storm["depth_mm"], storm["depth_hours"]) == ("depth", 120.0, 6.0)
    assert storm["depth_pattern"]["data"] == "table:Design pattern"
    store = states["tables"]["extra"]["store"]
    assert store["patterns"]["Design pattern"]["time"] == [0.0, 100.0]
    assert store["arf_curves"]["Area reduction"]["factors"] == [0.99, 0.913]
    reduction = states["reduction"]["widgets"]
    for part in ("lumped", "grid"):
        assert (reduction[f"{part}.form"]["data"], reduction[f"{part}.curve"]["data"], reduction[f"{part}.area"]) == (
            "area", "Area reduction", 74.3,
        )  # fmt: skip
    table = {"kind": "hyetograph", "rows": [(15.0, 4.0), (30.0, 11.5)]}
    storm = job_states.job_states(build_job(values(storm=table), tmp_path), tmp_path)["storm"]["widgets"]
    assert (storm["kind"]["data"], storm["hyetograph"]) == ("hyetograph", [[15.0, 4.0], [30.0, 11.5]])


def test_dam_start_levels_come_back_as_rows(tmp_path: Path) -> None:
    job = {
        **build_job(values(), tmp_path),
        "dam_levels": [{"name": "A", "start": "spillway"}, {"name": "B", "start": 97.25}],
    }
    rows = job_states.job_states(job, tmp_path)["structures"]["rows"]["start_water"]
    assert rows == [
        {"name": "A", "start": "spillway", "level": None},
        {"name": "B", "start": "level", "level": 97.25},
    ]


def test_what_a_refilled_dock_would_lose_is_found_by_comparison(tmp_path: Path) -> None:
    first, second = tmp_path / "run", tmp_path / "again"
    job = json.loads(json.dumps(build_job(values(), first)))
    same = json.loads(json.dumps(build_job(values(), second)))
    assert job != same  # the folders differ
    assert job_states.lost(job, first, same, second) == []
    rounded = json.loads(json.dumps(same))
    rounded["outputs"]["lines"][0]["coordinates"][0][0] = 10.123  # as the input file holds it
    assert job_states.lost(job, first, rounded, second) == []
    other = json.loads(json.dumps(build_job(values(curve_number=70.0, manning=0.03), second)))
    assert job_states.lost(job, first, other, second) == [
        "these parts of the job, which stay as the dock has them: hydrology.curve_number, terrain.manning"
    ]
