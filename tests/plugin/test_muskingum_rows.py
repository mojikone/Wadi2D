# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""W89: the reach table of Muskingum routing, without QGIS: typed cells, the engine's proposals as they come
(``wadi2d muskingum`` on a real basin file), and what reaches the job."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from wadi2d_qgis import muskingum_rows as rows_module
from wadi2d_qgis.job_builder import build_job, merge_hms
from wadi2d_qgis.muskingum_rows import (
    COLUMNS,
    COUNT_COLUMN,
    FLOW_COLUMN,
    K_COLUMN,
    MUSKINGUM,
    WORDS_COLUMN,
    X_COLUMN,
    ReachRow,
    apply_proposals,
    cell_text,
    hms_reaches,
    job_rows,
    merge_reaches,
    model_reaches,
    proposal_args,
    set_cell,
    table_note,
)

from tests.hydrology.test_muskingum import MC_BASIN
from tests.plugin.test_job_builder import values

config = pytest.importorskip("wadi2d.config.schema")


@pytest.fixture
def basin(tmp_path: Path) -> Path:
    path = tmp_path / "t.basin"
    path.write_text(MC_BASIN, encoding="utf-8")
    return path


def test_the_reaches_come_from_the_file_or_the_model(basin: Path) -> None:
    assert hms_reaches(basin) == ["R1", "R2", "R3"]
    model = {"elements": [{"kind": "reach", "name": "R1"}, {"kind": "junction", "name": "J1"}]}
    assert model_reaches(model) == ["R1"]
    kept = ReachRow("R2", k_hours=1.0, x=0.2)
    merged = merge_reaches(["R1", "R2"], [kept, ReachRow("R9", k_hours=2.0, x=0.1)])
    assert [row.name for row in merged] == ["R1", "R2"] and merged[1] is kept and merged[0].empty()


def test_typed_cells_become_numbers_and_what_means_nothing_is_named() -> None:
    row = ReachRow("R1")
    set_cell(row, K_COLUMN, "1.25")
    assert row.k_hours == 1.25 and row.problems == ["K and X: both, or neither"] and not row.complete()
    set_cell(row, X_COLUMN, "0.3")
    set_cell(row, COUNT_COLUMN, "15")
    assert (row.x, row.subreaches) == (0.3, 15) and row.complete() and row.words == rows_module.TYPED
    set_cell(row, X_COLUMN, "0.7")
    assert row.problems == ["X: between 0 and 0.5"] and not row.complete()
    set_cell(row, X_COLUMN, "abc")
    assert row.x is None and any("is not a number" in p for p in row.problems)
    set_cell(row, X_COLUMN, "0.2")
    set_cell(row, COUNT_COLUMN, "2.5")
    assert row.subreaches is None and row.problems == ["Subreaches: '2.5' is not a whole number"]
    set_cell(row, COUNT_COLUMN, "")
    assert row.problems == [] and row.complete()
    set_cell(row, FLOW_COLUMN, "1,200")
    assert row.flow == 1200.0
    set_cell(row, K_COLUMN, "0")
    assert "K: above zero" in row.problems
    assert cell_text(row, WORDS_COLUMN) == "K: above zero"
    assert [cell_text(row, c) for c in (0, FLOW_COLUMN, X_COLUMN, COUNT_COLUMN)] == ["R1", "1200", "0.2", ""]


def test_a_reference_flow_that_means_nothing_is_dropped_and_never_holds_the_row_back() -> None:
    """Found through the real dock: a flow of 0 typed for a reach below a dry dam kept its K and X out of the job."""
    row = ReachRow("R1", k_hours=1.0, x=0.2)
    set_cell(row, FLOW_COLUMN, "0")
    assert row.flow is None and row.complete() and "above zero, so none is used" in cell_text(row, WORDS_COLUMN)
    assert proposal_args("b", "o", [row], None, None) == ["muskingum", "b", "--out", "o"]
    assert job_rows([row]) == [{"reach": "R1", "k_hours": 1.0, "x": 0.2, "subreaches": 1}]
    assert table_note([row], True) == "1 of 1 reaches have K and X."
    set_cell(row, FLOW_COLUMN, "abc")
    assert row.flow is None and "is not a number" in row.flow_problem and row.complete()
    row.words = "derived so"
    assert cell_text(row, WORDS_COLUMN).endswith("so none is used. derived so")
    set_cell(row, FLOW_COLUMN, "350")
    assert row.flow == 350.0 and row.flow_problem == "" and cell_text(row, WORDS_COLUMN) == "derived so"
    assert row.words == "derived so"  # a flow is a question to the helper, not an edit of the row's numbers


def test_the_question_carries_the_flows_the_velocity_and_the_control_file() -> None:
    rows = [ReachRow("R1", flow=800.0), ReachRow("R2"), ReachRow("R3", flow=0.0)]
    assert proposal_args("b.basin", "o.json", rows, None, None) == [
        "muskingum", "b.basin", "--out", "o.json", "--flow", "R1=800.0",
    ]  # fmt: skip
    asked = proposal_args("b.basin", "o.json", rows, 2.0, "c.control")
    assert asked[-4:] == ["--velocity", "2.0", "--control", "c.control"]


def test_the_engines_proposals_fill_what_the_user_has_not_typed(basin: Path, tmp_path: Path) -> None:
    """The real command on a real file: R1 has a section, R2 is the file's own Muskingum reach, R3 a lag."""
    from wadi2d.engine.cli import main

    rows = merge_reaches(hms_reaches(basin), [])
    set_cell(rows[0], FLOW_COLUMN, "800")
    out = tmp_path / "found.json"
    assert main(proposal_args(basin, out, rows, None, None)) == 0
    found = json.loads(out.read_text(encoding="utf-8"))
    note = apply_proposals(rows, found)
    first, second, third = rows
    assert first.proposed and first.complete() and "Cunge (1969) at 800 m3/s" in first.words
    assert (second.k_hours, second.x, second.subreaches) == (0.5, 0.25, 6)
    assert second.words.startswith("The file's own Muskingum numbers.")
    assert third.empty() and not third.proposed and third.words.startswith("No proposal")
    assert note.startswith("2 proposed for a 5 min step; 1 with nothing to propose from")
    assert "A proposal is a start" in note
    # a typed row is kept; a row still holding a proposal is proposed again
    set_cell(second, K_COLUMN, "0.9")
    set_cell(first, FLOW_COLUMN, "200")
    assert main(proposal_args(basin, out, rows, None, None)) == 0
    slower = first.k_hours
    note = apply_proposals(rows, json.loads(out.read_text(encoding="utf-8")))
    assert second.k_hours == 0.9 and not second.proposed and "1 kept as typed" in note
    assert first.k_hours > slower and "at 200 m3/s" in first.words  # a smaller flood travels slower
    assert job_rows(rows) == [
        {"reach": "R1", "k_hours": first.k_hours, "x": first.x, "subreaches": first.subreaches},
        {"reach": "R2", "k_hours": 0.9, "x": 0.25, "subreaches": 6},
    ]


def test_an_edit_makes_a_proposal_the_users() -> None:
    row = ReachRow("R1")
    found = {"reaches": [{"name": "R1", "proposal": {"k_hours": 1.5, "x": 0.25, "subreaches": 18, "stable": False},
                          "own": None, "words": "derived so"}], "step_minutes": 5.0}
    note = apply_proposals([row], found)
    assert row.proposed and row.words == "derived so" and "1 not stable at this step" in note
    set_cell(row, X_COLUMN, "0.3")
    assert not row.proposed and row.words == rows_module.TYPED
    assert "1 kept as typed" in apply_proposals([row], found) and row.x == 0.3
    set_cell(row, K_COLUMN, "")
    set_cell(row, X_COLUMN, "")
    set_cell(row, COUNT_COLUMN, "")
    assert row.empty() and row.words == ""
    apply_proposals([row], found)
    assert row.proposed and row.x == 0.25


def test_the_note_says_what_a_run_does_with_the_rows() -> None:
    rows = [ReachRow("R1", k_hours=1.0, x=0.2), ReachRow("R2")]
    assert table_note([], False) == "No reaches: nothing to route."
    hms = table_note(rows, False)
    assert hms.startswith("1 of 2 reaches have K and X.") and "A run stops" in hms and "R2" in hms
    generated = table_note(rows, True)
    assert "left out and its water runs on the 2D grid" in generated and "R2" in generated
    assert table_note(rows[:1], True) == "1 of 1 reaches have K and X."
    set_cell(rows[0], X_COLUMN, "0.9")
    assert "Not usable: R1 (X: between 0 and 0.5)" in table_note(rows, False)
    assert len(COLUMNS) == WORDS_COLUMN + 1


def test_the_rows_reach_the_job_and_are_a_valid_job(tmp_path: Path) -> None:
    rows = [{"reach": "R1", "k_hours": 1.5, "x": 0.25, "subreaches": 18}]
    job = build_job(values(tmp_path, reach_routing=MUSKINGUM, muskingum=rows), tmp_path / "out")
    assert job["hydrology"]["reach_routing"] == "muskingum" and job["hydrology"]["muskingum"] == rows
    checked = config.RunConfig.model_validate(job).hydrology
    assert checked.muskingum[0].subreaches == 18
    assert "muskingum" not in build_job(values(tmp_path, reach_routing=MUSKINGUM, muskingum=[]), tmp_path / "out")["hydrology"]
    other = build_job(values(tmp_path, reach_routing="hms", muskingum=rows), tmp_path / "out")
    assert "muskingum" not in other["hydrology"]  # rows left in a hidden table never ride with another scheme
    imported = {"hydrology": {"hms_basin": "b.basin", "subbasins": [{"name": "S1"}]}, "run": {"duration_s": 60.0}}
    merged = merge_hms(job, imported, {"modes": {"S1": "lumped"}})
    assert merged["hydrology"]["muskingum"] == rows and merged["hydrology"]["reach_routing"] == "muskingum"
