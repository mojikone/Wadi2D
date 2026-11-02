# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The progress tail, the run state, the live source, without QGIS."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from wadi2d_qgis.progress import ProgressTail, RunState, event_xy, live_source, read_state, run_is_live
from wadi2d_qgis.protocol import read_run_info, write_run_info


def line(**event) -> bytes:
    return (json.dumps(event) + "\n").encode("utf-8")


def test_tail_reads_only_what_is_new(tmp_path: Path) -> None:
    path = tmp_path / "progress.jsonl"
    tail = ProgressTail(path)
    assert tail.poll() == []
    path.write_bytes(line(ev="start") + line(ev="step", t=1.0))
    assert [event["ev"] for event in tail.poll()] == ["start", "step"]
    assert tail.poll() == []
    with path.open("ab") as stream:
        stream.write(line(ev="step", t=2.0))
    assert tail.poll()[0]["t"] == 2.0


def test_a_half_written_line_waits_for_the_rest(tmp_path: Path) -> None:
    path = tmp_path / "progress.jsonl"
    whole = line(ev="step", t=5.0)
    path.write_bytes(whole[:7])
    tail = ProgressTail(path)
    assert tail.poll() == []
    with path.open("ab") as stream:
        stream.write(whole[7:])
    assert tail.poll() == [{"ev": "step", "t": 5.0}]


def test_junk_lines_are_skipped_and_the_rest_is_read(tmp_path: Path) -> None:
    path = tmp_path / "progress.jsonl"
    path.write_bytes(b"not json\n[1, 2]\n" + b'{"no_ev": 1}\n' + line(ev="done", code=0))
    assert [event["ev"] for event in ProgressTail(path).poll()] == ["done"]


def test_a_replaced_file_is_read_from_the_top(tmp_path: Path) -> None:
    path = tmp_path / "progress.jsonl"
    path.write_bytes(line(ev="start", n=1) + line(ev="step", t=1.0))
    tail = ProgressTail(path)
    tail.poll()
    path.write_bytes(line(ev="start", n=2))
    assert tail.poll() == [{"ev": "start", "n": 2}]


def test_state_folds_the_engine_events() -> None:
    state = RunState()
    state.apply({"ev": "start", "duration_s": 3600.0, "backend": "gpu"})
    state.apply({"ev": "step", "t": 900.0, "dt": 1.82, "mass_error": 2e-6, "wet_cells": 12345})
    assert state.percent == 25
    assert state.status == "0 h 15 min of 1 h 00 min | step 1.82 s | 12,345 wet cells | mass error 2.0e-06"
    assert not state.finished


def test_the_status_leaves_out_what_the_engine_does_not_report() -> None:
    state = RunState(t_end=3600.0)
    state.apply({"ev": "step", "t": 60.0, "dt": 2.0})
    assert state.status == "0 h 01 min of 1 h 00 min | step 2 s"


def test_percent_stays_within_bounds() -> None:
    assert RunState().percent == 0
    assert RunState(t=5000.0, t_end=3600.0).percent == 100


def test_done_ends_a_run_with_its_code_and_wet_area() -> None:
    state = RunState(t_end=10.0)
    state.apply({"ev": "done", "status": "finished", "code": 0, "t": 10.0, "wet_area_km2": 1.5})
    assert state.finished
    assert state.succeeded
    assert "wet area 1.50 km2" in state.status
    assert state.outcome() == "Finished."


def test_a_run_too_short_for_a_step_event_still_reports_its_mass_error() -> None:
    state = RunState(t_end=900.0)
    state.apply({"ev": "done", "code": 0, "t": 900.0, "balance": {"relative_error": 3e-7}})
    assert "mass error 3.0e-07" in state.status


def test_an_error_does_not_end_a_run_because_the_maps_come_after_it() -> None:
    state = RunState()
    cell = {"j": 1, "i": 2, "x": 412345.5, "y": 2701234.5, "wave": 30.0}
    state.apply({"ev": "error", "code": 5, "message": "time step below the floor", "cell": cell})
    assert not state.finished
    state.apply({"ev": "done", "status": "numerical failure", "code": 5})
    assert state.finished
    assert not state.succeeded
    assert state.error_xy == (412345.5, 2701234.5)
    said = state.outcome()
    assert said.startswith("The run went numerically unstable.")
    assert "time step below the floor. At x" in said
    assert "412,345.5" in said


def test_an_event_without_a_cell_has_no_position() -> None:
    assert event_xy({"ev": "error", "code": 2, "message": "x"}) is None
    assert event_xy({"ev": "error", "cell": {"j": 1, "i": 2}}) is None


def test_warnings_are_kept() -> None:
    state = RunState()
    state.apply({"ev": "warn", "message": "point P1 is outside the domain"})
    assert state.warnings == ["point P1 is outside the domain"]


def test_a_warning_stays_in_the_last_message() -> None:
    state = RunState(exit_code=0)
    for _ in range(2):
        state.apply({"ev": "warn", "message": "water stood 9 m deep against the domain edge"})
    assert state.outcome() == "Finished. water stood 9 m deep against the domain edge."


def test_read_state_takes_t_end_from_the_plugin_record(tmp_path: Path) -> None:
    (tmp_path / "progress.jsonl").write_bytes(line(ev="step", t=10.0))
    write_run_info(tmp_path, 4242, "EPSG:32640", 100.0)
    assert read_run_info(tmp_path)["crs"] == "EPSG:32640"
    assert read_state(tmp_path).percent == 10


def test_a_folder_without_a_run_is_not_live(tmp_path: Path) -> None:
    assert not run_is_live(tmp_path)


def test_a_finished_run_is_not_live(tmp_path: Path) -> None:
    (tmp_path / "progress.jsonl").write_bytes(line(ev="start") + line(ev="done", code=0))
    assert not run_is_live(tmp_path)


def test_a_run_whose_process_exists_is_live(tmp_path: Path) -> None:
    (tmp_path / "progress.jsonl").write_bytes(line(ev="start"))
    write_run_info(tmp_path, os.getpid(), "", None)
    assert run_is_live(tmp_path)


def test_a_run_whose_process_is_gone_is_not_live(tmp_path: Path) -> None:
    child = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True)
    (tmp_path / "progress.jsonl").write_bytes(line(ev="start"))
    write_run_info(tmp_path, int(child.stdout), "", None)
    assert not run_is_live(tmp_path)


def test_with_no_process_known_only_a_fresh_file_counts(tmp_path: Path) -> None:
    path = tmp_path / "progress.jsonl"
    path.write_bytes(line(ev="start"))
    assert run_is_live(tmp_path)
    old = time.time() - 3600
    os.utime(path, (old, old))
    assert not run_is_live(tmp_path)


def test_live_source_stamps_change_with_the_file(tmp_path: Path) -> None:
    assert live_source(tmp_path) is None
    tif = tmp_path / "live" / "depth.tif"
    tif.parent.mkdir()
    tif.write_bytes(b"one")
    path, first = live_source(tmp_path)
    assert path == tif
    os.utime(tif, ns=(1, 1))
    assert live_source(tmp_path)[1] != first


def test_live_source_follows_the_numbered_fallback(tmp_path: Path) -> None:
    live = tmp_path / "live"
    live.mkdir()
    (live / "depth.tif").write_bytes(b"old")
    (live / "depth_17.tif").write_bytes(b"new")
    (live / "latest.json").write_text('{"path": "live/depth_17.tif", "t": 3600.0}', "utf-8")
    assert live_source(tmp_path)[0] == live / "depth_17.tif"


def test_a_broken_latest_file_falls_back_to_the_plain_raster(tmp_path: Path) -> None:
    live = tmp_path / "live"
    live.mkdir()
    (live / "depth.tif").write_bytes(b"x")
    (live / "latest.json").write_text("{half", "utf-8")
    assert live_source(tmp_path)[0] == live / "depth.tif"


def test_the_bar_and_the_status_follow_the_pixel_maps() -> None:
    state = RunState(t_end=100.0)
    state.apply({"ev": "step", "t": 100.0, "dt": 1.0})
    assert state.percent == 100
    state.apply({"ev": "products", "stage": "maps", "done": 12, "of": 193, "percent": 40.0})
    assert state.percent == 40
    assert state.status == "Pixel maps: saved map: 12 of 193"
    state.apply({"ev": "products", "stage": "smooth", "done": 0, "of": 2, "percent": 85.0})
    assert "polygons" in state.status
    state.apply({"ev": "done", "code": 0, "t": 100.0, "products": "finished"})
    assert state.percent == 100
    assert state.products == "finished"
    assert "Pixel maps" not in state.status


def test_a_stop_during_the_pixel_maps_is_said_on_a_finished_run() -> None:
    state = RunState(t_end=100.0)
    state.apply({"ev": "products", "stage": "maps", "done": 1, "of": 9, "percent": 10.0})
    state.apply({"ev": "warn", "message": "Pixel maps stopped on request. The run itself finished."})
    state.apply({"ev": "done", "code": 0, "t": 100.0, "products": "stopped"})
    assert state.succeeded
    assert "Pixel maps stopped" in state.outcome()
