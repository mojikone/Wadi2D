# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""What the result-line plot says: which kind is which, the stated limit, and which frame a time shows."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from wadi2d_qgis.line_view import (
    FLOW_ESTIMATE,
    FLOW_FACES,
    FRAMES,
    NO_DEM,
    TEMPORARY,
    UPFRONT,
    UPFRONT_LINE,
    UPFRONT_POINT,
    Entry,
    clock,
    entries,
    every,
    frame_at,
    line_view,
    point_view,
    readout,
    record_view,
    step_showing,
    ticks,
    value_at,
)
from wadi2d_qgis.protocol import lines_args

READ = {
    "name": "L",
    "t_s": [0.0, 300.0, 600.0],
    "interval_s": 300.0,
    "length_m": 100.0,
    "flow_m3s": [0.0, 10.0, 5.0],
    "deepest_m": [0.0, 2.0, 1.0],
    "station_m": [10.0, 30.0],
    "ground_m": [100.0, 101.0],
    "ground_source": "dem",
    "level_m": [[None, None], [102.0, 102.0], [101.0, None]],
}
RECORD = {"name": "L", "coordinates": [[0.0, 0.0], [1.0, 1.0]], "t_s": [0.0, 300.0, 600.0], "discharge_m3s": [0.0, -12.0, -6.0]}
POINT = {"name": "P", "x": 1.0, "y": 2.0, "t_s": [0.0, 60.0], "depth_m": [0.0, 1.5], "mean_depth_m": [0.0, 1.0], "level_m": [90.0, 91.5]}


def test_upfront_lines_then_points_keep_their_kind() -> None:
    found = entries({"lines": [RECORD], "points": [POINT]})
    assert [(item.kind, item.name) for item in found] == [(UPFRONT_LINE, "L"), (UPFRONT_POINT, "P")]
    assert [item.label for item in found] == ["Upfront line: L", "Upfront point: P"]
    assert Entry(TEMPORARY, "Line 1").label == "Temporary line: Line 1"


def test_a_temporary_line_says_what_it_is_and_what_limits_it() -> None:
    view = line_view(Entry(TEMPORARY, "Line 1"), READ)
    assert view.heading == "Temporary line: Line 1. Read from saved frames."
    assert "every 5 min" in view.limit
    assert "estimated from depth and speed" in view.limit
    assert "not a number of record" in view.limit
    assert [curve.source for curve in view.charts[0].curves] == [FRAMES]
    assert view.charts[0].curves[0].label == "Saved frames, every 5 min: estimated"
    assert view.charts[0].curves[0].markers


def test_an_upfront_line_shows_the_record_beside_the_frames_and_names_each() -> None:
    entry = entries({"lines": [RECORD]})[0]
    view = line_view(entry, READ)
    assert view.heading.startswith("Upfront line: L. Flow computed during the run")
    record, frames = view.charts[0].curves
    assert (record.source, frames.source) == (UPFRONT, FRAMES)
    assert "number of record" in record.label and "Saved frames" in frames.label
    assert record.values == [0.0, 12.0, 6.0]  # size, as the estimate has no sign
    assert not record.markers


def test_without_frames_an_upfront_line_keeps_its_record() -> None:
    view = record_view(entries({"lines": [RECORD]})[0], [])
    assert view.section is None
    assert [curve.source for curve in view.charts[0].curves] == [UPFRONT]
    assert "number of record" in view.limit


def test_a_point_has_no_flow_and_nothing_along_it() -> None:
    view = point_view(entries({"points": [POINT]})[0], [0.0, 60.0])
    assert view.heading == "Upfront point: P."
    assert view.section is None
    assert [chart.quantity for chart in view.charts] == ["depth", "level"]
    assert not view.charts[1].from_zero


def test_a_run_whose_dem_moved_says_what_ground_is_drawn() -> None:
    view = line_view(Entry(TEMPORARY, "L"), {**READ, "ground_source": "cells"})
    assert NO_DEM in view.section.title


@pytest.mark.parametrize(
    ("t_s", "frame"), [(-5.0, 0), (0.0, 0), (299.0, 0), (299.6, 1), (300.0, 1), (301.0, 1), (599.9, 2), (900.0, 2)]
)
def test_a_time_shows_the_last_frame_at_or_before_it(t_s: float, frame: int) -> None:
    assert frame_at([0.0, 300.0, 600.0], t_s) == frame


@pytest.mark.parametrize(
    ("frame_s", "step"), [(3.0, 0), (304.0, 1), (303.5, 1), (305.0, 2), (5000.0, 9), (0.0, 0)]
)
def test_the_slider_asks_for_the_step_that_shows_a_frame(frame_s: float, step: int) -> None:
    assert step_showing(frame_s, 3.0, 301.0, 10) == step


def test_a_controller_with_no_steps_has_step_zero() -> None:
    assert step_showing(100.0, 0.0, 0.0, 5) == 0
    assert step_showing(100.0, 0.0, 10.0, 0) == 0


def test_times_read_as_a_report_would_put_them() -> None:
    assert clock(0.0) == "0 min"
    assert clock(300.0) == "5 min"
    assert clock(3900.0) == "1 h 05 min"
    assert every(300.0) == "every 5 min"
    assert every(90.0) == "every 1.5 min"
    assert every(301.0) == "every 5 min"


@pytest.mark.parametrize(
    ("low", "high", "expected"),
    [(0.0, 10.0, [0.0, 2.0, 4.0, 6.0, 8.0, 10.0]), (0.0, 1.0, [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]), (101.3, 104.9, [102.0, 103.0, 104.0])],
)
def test_ticks_are_round(low: float, high: float, expected: list[float]) -> None:
    assert ticks(low, high) == expected


def test_ticks_of_nothing_are_one() -> None:
    assert ticks(3.0, 3.0) == [3.0]


def test_a_value_between_points_is_read_straight() -> None:
    curve = line_view(Entry(TEMPORARY, "L"), READ).charts[0].curves[0]
    assert value_at(curve, 300.0 / 3600.0) == pytest.approx(10.0)
    assert value_at(curve, 450.0 / 3600.0) == pytest.approx(7.5)
    assert value_at(curve, 1.0) is None


def test_the_readout_names_each_number_for_what_it_is() -> None:
    view = line_view(entries({"lines": [RECORD]})[0], READ)
    words = readout(view, 1)
    assert words.startswith("5 min from the start of the run")
    assert "flow 12.00 m3/s (upfront)" in words
    assert "flow 10.00 m3/s (frames)" in words
    assert "deepest 2.00 m (frames)" in words


def test_no_frames_no_readout() -> None:
    assert readout(point_view(entries({"points": [POINT]})[0], []), 0) == ""


def test_the_arguments_are_the_engine_command() -> None:
    assert lines_args(Path("run"), "a.json") == ["lines", "run", "--out", "a.json"]
    assert lines_args("run", "a.json", "b.json") == ["lines", "run", "--out", "a.json", "--line", "b.json"]


def test_the_engine_parses_them() -> None:
    cli = pytest.importorskip("wadi2d.engine.cli")
    args = cli.parser().parse_args(lines_args("run", "a.json", "b.json"))
    assert (args.run, args.out, args.line) == ("run", "a.json", "b.json")


def test_a_real_answer_of_the_engine_makes_a_view(tmp_path: Path) -> None:
    """The contract: what the engine writes, through JSON, is what the view reads."""
    lines = pytest.importorskip("wadi2d.products.result_lines")
    from tests.engine.conftest import X0, Y0, job, tilted_box, write_dem
    from wadi2d.run import run_job

    dem = write_dem(tmp_path / "dem.tif", tilted_box(40, 40, 5.0, 0.01), 5.0)
    across = [(X0 + 100.0, Y0 - 2.5), (X0 + 100.0, Y0 - 197.5)]
    cfg = job(
        dem, 40, 40, 5.0,
        run={"duration_s": 180.0},
        storm={"kind": "uniform", "depth_mm": 300.0, "duration_min": 3.0},
        outputs={"map_every_s": 60.0, "pixels": {"enabled": False}, "lines": [{"name": "L", "coordinates": across}],
                 "points": [{"name": "P", "x": X0 + 50.0, "y": Y0 - 50.0}]},
    )  # fmt: skip
    assert run_job(cfg, tmp_path / "run").exit_code == 0
    listing = json.loads(json.dumps(lines.catalogue(tmp_path / "run")))
    line, point = entries(listing)
    read = json.loads(json.dumps(lines.read_line(tmp_path / "run", line.coordinates, line.name)))
    view = line_view(line, read)
    assert [curve.source for curve in view.charts[0].curves] == [UPFRONT, FRAMES]
    assert "every 1 min" in view.limit
    assert len(view.section.level_m) == len(view.frames_s) == len(read["t_s"])
    assert "flow" in readout(view, 1)
    assert point_view(point, listing["frames_s"]).charts[0].curves[0].values


def test_a_line_read_off_the_saved_faces_is_labelled_a_number_of_record_at_the_frame_interval() -> None:
    view = line_view(Entry(TEMPORARY, "Line 1"), {**READ, "flow_source": FLOW_FACES, "flow_m3s": [0.0, -10.0, -5.0]})
    curve = view.charts[0].curves[0]
    assert curve.source == FRAMES
    assert curve.label == "Saved frames, every 5 min: from the faces, of record"
    assert curve.values == [0.0, 10.0, 5.0]  # drawn as a size, the sign stays in the engine's answer
    assert "number of record at the frame interval" in view.limit
    assert "discharge through the faces" in view.limit
    assert "estimated" not in view.limit and "estimated" not in curve.label
    assert "a peak between two frames is not seen" in view.limit


def test_an_answer_that_says_estimate_or_says_nothing_keeps_the_old_words() -> None:
    for read in (READ, {**READ, "flow_source": FLOW_ESTIMATE}):
        view = line_view(Entry(TEMPORARY, "Line 1"), read)
        assert view.charts[0].curves[0].label == "Saved frames, every 5 min: estimated"
        assert "not a number of record" in view.limit


def test_an_upfront_line_read_off_the_faces_shows_the_record_beside_its_own_frames() -> None:
    view = line_view(entries({"lines": [RECORD]})[0], {**READ, "flow_source": FLOW_FACES})
    record, frames = view.charts[0].curves
    assert "number of record" in record.label and "of record" in frames.label
    assert record.source == UPFRONT and frames.source == FRAMES


def test_the_flow_source_words_are_the_engines() -> None:
    engine = pytest.importorskip("wadi2d.products.face_flow")
    assert (FLOW_FACES, FLOW_ESTIMATE) == (engine.FLOW_FACES, engine.FLOW_ESTIMATE)
