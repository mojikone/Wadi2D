# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The gauges table without Qt: its rows, what stops a run, and the job it writes, checked against the real engine."""

from __future__ import annotations

from pathlib import Path

import pytest
from wadi2d_qgis.gauge_rows import (
    FLOW,
    LEVEL,
    RAIN,
    GaugeRow,
    gauge_problems,
    joined_gauges,
    merge_rows,
    observed_records,
    position_text,
    rain_storm,
    read_position,
)
from wadi2d_qgis.job_builder import Feature, build_job, problems

from tests.plugin.test_job_builder import values

config = pytest.importorskip("wadi2d.config.schema")
LINES, POINTS = {"Outlet"}, {"Well"}


def record(tmp_path: Path, name: str = "g.csv") -> str:
    path = tmp_path / name
    path.write_text("minute,mm\n10,1\n", encoding="utf-8")
    return str(path)


def test_layer_points_become_rain_rows_and_keep_what_was_set_on_them() -> None:
    first = merge_rows([("A", 1.0, 2.0), ("B", 3.0, 4.0)], [GaugeRow("Q", FLOW, at="Outlet")])
    assert [(r.name, r.kind, r.from_layer) for r in first] == [
        ("A", RAIN, True),
        ("B", RAIN, True),
        ("Q", FLOW, False),
    ]
    first[0].file = "a.csv"
    again = merge_rows([("A", 5.0, 6.0)], first)
    assert [(r.name, r.file, r.x, r.y) for r in again[:1]] == [("A", "a.csv", 5.0, 6.0)]
    assert [r.name for r in again] == ["A", "Q"]  # B left the layer; the typed row stays


def test_a_position_reads_as_two_numbers() -> None:
    assert read_position("488963, 2632307") == (488963.0, 2632307.0)
    assert read_position("488963 2632307.5") == (488963.0, 2632307.5)
    assert read_position("Outlet") is None
    assert position_text(GaugeRow("A", RAIN, x=1.0, y=2.25)) == "1.0, 2.2"
    assert position_text(GaugeRow("Q", FLOW, at="Outlet")) == "Outlet"


def test_what_stops_a_run_is_said_in_plain_words(tmp_path: Path) -> None:
    rows = [
        GaugeRow("A", RAIN, file=record(tmp_path)),
        GaugeRow("Q", FLOW, file=record(tmp_path), at="Well"),
        GaugeRow("H", LEVEL, file=str(tmp_path / "none.csv"), at="Outlet"),
        GaugeRow("A", FLOW),
    ]
    found = gauge_problems(rows, True, LINES, POINTS)
    assert "Two gauges have the same name: their results are kept by name." in found
    assert "Rain gauge A needs its position, x and y." in found
    assert "Gauge Q must name a result line or a lumped element to be compared with." in found
    assert "Gauge H must name a result point to be compared with." in found
    assert any(text.startswith("Gauge H: the record is not there") for text in found)
    assert "Gauge A: choose its record, a CSV table or a DSS file." in found
    assert gauge_problems([GaugeRow("Q", FLOW, file=record(tmp_path), at="Outlet")], True, LINES, POINTS) == [
        "The storm is set to the rain gauges: add one in the Gauges section."
    ]


def test_a_flow_gauge_names_a_line_or_else_a_lumped_element(tmp_path: Path) -> None:
    rows = [
        GaugeRow("Q1", FLOW, file=record(tmp_path), at="Outlet"),
        GaugeRow("Q2", FLOW, file=record(tmp_path), at="S13", series="//S13/FLOW//5MIN/OBS/"),
        GaugeRow("H", LEVEL, file=record(tmp_path), at="Well"),
        GaugeRow("R", RAIN, file=record(tmp_path), x=1.0, y=2.0),
    ]
    found = observed_records(rows, LINES, POINTS, "2021-10-04 00:00")
    assert [(r["name"], r["compare"], r["target"], r["quantity"]) for r in found] == [
        ("Q1", "line", "Outlet", "flow"), ("Q2", "element", "S13", "flow"), ("H", "point", "Well", "level"),
    ]  # fmt: skip
    assert found[1]["record"] == "//S13/FLOW//5MIN/OBS/" and found[0]["start"] == "2021-10-04 00:00"
    for item in found:
        config.Observed.model_validate(item)


def test_the_storm_block_is_a_valid_engine_storm(tmp_path: Path) -> None:
    rows = [GaugeRow("A", RAIN, file=record(tmp_path), x=1.0, y=2.0), GaugeRow("Q", FLOW, at="Outlet")]
    storm = rain_storm(
        rows, {"method": "inverse_distance", "radius_m": 5000.0, "gaps": "zero", "start": "2021-10-04 00:00"}
    )
    assert [g["name"] for g in storm["gauges"]["gauges"]] == ["A"]
    parsed = config.Storm.model_validate(storm)
    assert parsed.gauges.search_radius_m == 5000.0 and parsed.rain_start == "2021-10-04 00:00"
    plain = rain_storm(rows, {"method": "thiessen", "radius_m": 5000.0})
    assert "search_radius_m" not in plain["gauges"] and "rain_start" not in plain


def test_the_dock_builds_a_job_the_engine_accepts(tmp_path: Path) -> None:
    rows = [
        GaugeRow("A", RAIN, file=record(tmp_path), x=400100.0, y=2699500.0),
        GaugeRow("Q", FLOW, file=record(tmp_path, "q.csv"), at="Outlet"),
    ]
    design = [Feature("LineString", [[400000.0, 2699500.0], [400500.0, 2699500.0]], {"name": "Outlet"})]
    chosen = values(
        tmp_path,
        storm={"kind": "gauges"},
        design=design,
        gauges={"rows": rows, "settings": {"method": "thiessen"}},
    )
    assert problems(chosen) == []
    job = build_job(chosen, tmp_path / "out")
    cfg = config.RunConfig.model_validate(job)
    assert cfg.storm.kind == "gauges" and cfg.storm.gauges.gauges[0].name == "A"
    assert cfg.outputs.observed[0].target == "Outlet" and cfg.outputs.observed[0].compare == "line"


def test_an_empty_gauges_table_leaves_the_job_as_it_was(tmp_path: Path) -> None:
    plain = build_job(values(tmp_path), tmp_path / "out")
    empty = build_job(values(tmp_path, gauges={"rows": [], "settings": {}}), tmp_path / "out")
    assert plain == empty and "observed" not in empty["outputs"]
    assert problems(values(tmp_path, gauges={"rows": [], "settings": {}})) == []
    joined = joined_gauges(values(tmp_path, observed_gauges={"rows": [], "start": ""}))
    assert build_job(joined, tmp_path / "out") == plain and problems(joined) == []


START = "2021-10-04 00:00"
OUTLET = [Feature("LineString", [[400000.0, 2699500.0], [400500.0, 2699500.0]], {"name": "Outlet"})]
WELL = [Feature("Point", [400200.0, 2699500.0], {"name": "Well"})]


def _rows(tmp_path: Path):
    rain = [
        GaugeRow("West", RAIN, file=record(tmp_path, "w.csv"), x=400100.0, y=2699500.0, from_layer=True),
        GaugeRow("East", RAIN, file=record(tmp_path, "e.csv"), x=400400.0, y=2699500.0, values="cumulative"),
    ]
    observed = [
        GaugeRow("Q", FLOW, file=record(tmp_path, "q.csv"), at="Outlet"),
        GaugeRow("H", LEVEL, file=record(tmp_path, "h.csv"), at="Well", series="stage"),
    ]
    return rain, observed


CASES = {
    "rain gauges only, nearest gauge, a start": (
        "gauges", True, False, {"method": "thiessen", "radius_m": None, "gaps": "error", "start": START}, START, ""
    ),
    "rain, flow and level, inverse distance in a radius": (
        "gauges", True, True, {"method": "inverse_distance", "radius_m": 5000.0, "gaps": "zero", "start": START},
        START, "",
    ),
    "rain and flow, no start": ("gauges", True, True, {"method": "thiessen", "gaps": "neighbours", "start": ""}, "", ""),
    "flow and level under a design storm, a start": ("hypothetical", False, True, {}, START, START),
}


@pytest.mark.parametrize("case", list(CASES))
def test_the_two_tables_write_the_job_the_one_table_wrote(tmp_path: Path, case: str) -> None:
    """W77: rain gauges in the Storm section, flow and level gauges in 7b; for the same rows the job is W54's."""
    kind, with_rain, with_observed, settings, old_start, typed_start = CASES[case]
    rain, observed = _rows(tmp_path)
    rain, observed = (rain if with_rain else []), (observed if with_observed else [])
    storm = {"kind": "gauges"} if kind == "gauges" else {
        "kind": "hypothetical", "depth_mm": 80.0, "hours": 2.0, "pattern": [(0.0, 0.0), (100.0, 100.0)],
        "area_km2": 0.0, "arf": [],
    }  # fmt: skip
    old_settings = {**settings, "start": old_start}
    old = values(tmp_path, storm=storm, design=OUTLET + WELL, gauges={"rows": rain + observed, "settings": old_settings})
    new = values(tmp_path, storm=storm, design=OUTLET + WELL, observed_gauges={"rows": observed, "start": typed_start})
    if kind == "gauges":
        new["rain_gauges"] = {"rows": rain, "settings": settings}
    new = joined_gauges(new)
    assert problems(old) == problems(new) == []
    first, second = build_job(old, tmp_path / "out"), build_job(new, tmp_path / "out")
    assert first == second
    config.RunConfig.model_validate(second)


def test_the_records_own_start_wins_over_the_rain_gauges(tmp_path: Path) -> None:
    rain, observed = _rows(tmp_path)
    new = joined_gauges(values(
        tmp_path, storm={"kind": "gauges"}, design=OUTLET + WELL,
        rain_gauges={"rows": rain, "settings": {"method": "thiessen", "start": START}},
        observed_gauges={"rows": observed, "start": "2021-10-03 23:00"},
    ))  # fmt: skip
    job = build_job(new, tmp_path / "out")
    assert job["storm"]["rain_start"] == START
    assert {r["start"] for r in job["outputs"]["observed"]} == {"2021-10-03 23:00"}
