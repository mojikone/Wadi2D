# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""W101 item 3: a flow line's hydrograph typed at a step (HEC-RAS's way) and levels from points, the job each writes
and the engine's schema takes."""

from __future__ import annotations

from wadi2d_qgis import job_states
from wadi2d_qgis.boundary_rows import Row, has_hydrograph, job_properties
from wadi2d_qgis.job_builder import Feature, build_job, problems

from wadi2d.config.schema import RunConfig

LINE = [[0.0, 0.0], [0.0, 100.0]]


def values(tmp_path, **extra) -> dict:
    dem = tmp_path / "dem.tif"
    dem.write_bytes(b"x")
    return {
        "dem": str(dem), "crs": "EPSG:32640", "dx": 10.0, "manning": 0.04, "duration_h": 1.0, "output": str(tmp_path),
        "extent": (0.0, 0.0, 100.0, 100.0), "rain_mm_h": 10.0, "rain_hours": 1.0, **extra,
    }  # fmt: skip


def typed_row(**more) -> Row:
    return Row(1, "Inflow", "flow", None, True, True, None, **{"typed": True, "step_min": 30.0, "flows": [0.0, 25.0, 10.0], **more})


def test_a_typed_hydrograph_writes_the_engines_table(tmp_path) -> None:
    row = typed_row(slope=0.01)
    assert has_hydrograph(row)
    props = job_properties(row)
    assert props["step_s"] == 1800.0 and props["flows"] == [0.0, 25.0, 10.0] and props["file"] is None
    job = build_job(values(tmp_path, boundaries=[Feature("LineString", LINE, props)]), tmp_path / "a")
    assert job["boundaries"][0]["flow"] == {"step_s": 1800.0, "flows": [0.0, 25.0, 10.0], "slope": 0.01}
    flow = RunConfig.model_validate(job).boundaries[0].flow
    assert flow.table()[0][-1] == 3600.0  # the engine writes the times out: a flow every 30 min


def test_a_file_stays_the_job_of_before(tmp_path) -> None:
    row = Row(1, "Inflow", "flow", None, True, True, "q.csv")
    assert job_properties(row) == {"kind": "flow", "value": None, "file": "q.csv"}


def test_a_short_table_is_refused_in_words(tmp_path) -> None:
    short = job_properties(typed_row(flows=[5.0]))
    found = problems(values(tmp_path, boundaries=[Feature("LineString", LINE, short)]))
    assert any("two flows at least" in text for text in found)
    assert not has_hydrograph(typed_row(flows=[5.0]))


def test_levels_from_points(tmp_path) -> None:
    point = {"name": "Sea", "x": 50.0, "y": 50.0, "level": 1.2}
    job = build_job(values(tmp_path, initial_points=[point]), tmp_path / "b")
    assert job["initial_points"] == [point]
    assert RunConfig.model_validate(job).initial_points[0].level == 1.2
    found = problems(values(tmp_path, initial_points=[{**point, "level": None}]))
    assert any("need a level" in text for text in found)


def test_a_job_gives_its_typed_hydrograph_back(tmp_path) -> None:
    job = build_job(values(tmp_path, boundaries=[Feature("LineString", LINE, job_properties(typed_row()))]), tmp_path / "c")
    states = job_states.job_states(job, tmp_path / "elsewhere", tmp_path / "x_imported_inputs.gpkg")
    row = states["boundaries"]["rows"][""][0]
    assert (row["typed"], row["step_min"], row["flows"]) == (True, 30.0, [0.0, 25.0, 10.0])
