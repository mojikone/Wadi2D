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
