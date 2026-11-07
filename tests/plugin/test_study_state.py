# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A study's progress as the dock folds it: the study's events and the run in progress, without QGIS."""

from __future__ import annotations

import json
from pathlib import Path

from wadi2d_qgis.study_state import StudyState

AREAS = [10.0, 30.0, 90.0]


def write(path: Path, *events: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")


def begin(tmp_path: Path, number: int, of: int = len(AREAS)) -> dict:
    folder = f"runs/A{number}"
    write(
        tmp_path / folder / "progress.jsonl",
        {"ev": "start", "backend": "cpu", "duration_s": 3600.0},
        {"ev": "step", "t": 1800.0, "dt": 1.5, "wet_cells": 1200, "mass_error": 1e-7},
        {"ev": "warn", "message": "line X crosses no active face"},
    )  # fmt: skip
    return {"ev": "run", "index": number, "of": of, "area_km2": AREAS[number - 1], "folder": folder}


def test_before_the_first_run_it_says_the_grid_is_being_built() -> None:
    state = StudyState()
    assert state.percent == 0
    assert "grid" in state.status
    state.apply({"ev": "start", "areas_km2": AREAS, "arf_table_type": "fixed-area"})
    assert state.status == "3 runs to go."


def test_it_says_which_run_of_how_many_and_how_many_are_left(tmp_path: Path) -> None:
    state = StudyState(base=tmp_path)
    state.apply({"ev": "start", "areas_km2": AREAS, "arf_table_type": "fixed-area"})
    state.apply(begin(tmp_path, 1))
    state.poll_run()
    assert state.status.startswith("Run 1 of 3, storm area 10 km2; 2 runs left after it. 0 h 30 min of 1 h 00 min")
    assert state.percent == 16  # half of the first of three
    state.apply({"ev": "output", "kind": "run", "area_km2": 10.0, "code": 0, "peaks": {}})
    assert state.done_runs == 1 and state.percent == 33
    state.apply(begin(tmp_path, 2))
    state.poll_run()
    assert "Run 2 of 3, storm area 30 km2; 1 run left after it." in state.status
    assert state.percent == 50
    state.apply({"ev": "output", "kind": "run", "area_km2": 30.0, "code": 0, "peaks": {}})
    state.apply(begin(tmp_path, 3))
    state.poll_run()
    assert "Run 3 of 3, storm area 90 km2; the last run." in state.status


def test_a_finished_study_says_so_once_per_warning(tmp_path: Path) -> None:
    state = StudyState(base=tmp_path)
    state.apply({"ev": "start", "areas_km2": AREAS[:2]})
    for number in (1, 2):
        state.apply(begin(tmp_path, number, of=2))
        state.apply({"ev": "output", "kind": "run", "area_km2": AREAS[number - 1], "code": 0})
    state.apply({"ev": "done", "status": "finished", "code": 0, "rows": 1})
    assert state.finished and state.succeeded
    assert state.outcome() == (
        "Finished: 2 runs, 1 design flow, for design lines and lumped elements. line X crosses no active face."
    )


def test_a_stopped_study_says_how_far_it_got_and_that_it_has_no_table(tmp_path: Path) -> None:
    state = StudyState(base=tmp_path)
    state.apply({"ev": "start", "areas_km2": AREAS})
    state.apply(begin(tmp_path, 1))
    state.apply({"ev": "output", "kind": "run", "area_km2": 10.0, "code": 0})
    state.apply(begin(tmp_path, 2))
    state.apply({"ev": "output", "kind": "run", "area_km2": 30.0, "code": 6})
    state.apply({"ev": "done", "status": "stopped", "code": 6, "partial": True, "runs": 2})
    assert not state.succeeded
    assert state.outcome().startswith("Stopped after 1 of 3 runs. A stopped study writes no design table")


def test_a_failed_run_names_its_storm_area_and_the_engine_words(tmp_path: Path) -> None:
    state = StudyState(base=tmp_path)
    state.apply({"ev": "start", "areas_km2": AREAS})
    event = begin(tmp_path, 1)
    write(tmp_path / event["folder"] / "progress.jsonl", {"ev": "error", "code": 5, "message": "time step below the floor",
                                                          "cell": {"x": 1.0, "y": 2.0}})  # fmt: skip
    state.apply(event)
    state.apply({"ev": "output", "kind": "run", "area_km2": 10.0, "code": 5})
    state.apply({"ev": "error", "code": 5, "message": "time step below the floor", "area_km2": 10.0})
    said = state.outcome()
    assert "numerically unstable" in said and "time step below the floor" in said
    assert "storm area of 10 km2" in said
    assert state.error_xy == (1.0, 2.0)
