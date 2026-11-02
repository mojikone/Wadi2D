# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The mesh lines table: what a size becomes on the ladder, and a row that follows until someone has set it."""

from __future__ import annotations

import pytest
from wadi2d_qgis.mesh_rows import (
    follow,
    job_properties,
    merge_rows,
    new_row,
    reversed_note,
    rounded_note,
    rung_size,
    set_far,
    set_near,
    set_rows,
)


def line(fid: int = 1, **own) -> dict:
    return {"fid": fid, "label": f"Line {fid}", **own}


@pytest.mark.parametrize(
    ("asked", "got"),
    [(10.0, 10.0), (15.0, 10.0), (19.99, 10.0), (20.0, 20.0), (30.0, 20.0), (40.0, 40.0), (70.0, 40.0), (80.0, 80.0),
     (500.0, 80.0), (5.0, 10.0)],
)  # fmt: skip
def test_a_size_goes_down_the_ladder_and_stays_on_it(asked, got) -> None:
    assert rung_size(asked, 10.0, 80.0) == got


def test_a_ladder_of_one_rung_gives_that_rung() -> None:
    assert rung_size(5.0, 10.0, 10.0) == 10.0
    assert rung_size(50.0, 10.0, 10.0) == 10.0


def test_with_no_finest_cell_yet_the_size_stands() -> None:
    assert rung_size(15.0, 0.0, 80.0) == 15.0


def test_a_new_line_starts_at_the_two_ends() -> None:
    row = new_row(line(), 10.0, 80.0, 4)
    assert (row.near, row.rows, row.far) == (10.0, 4, 80.0)
    assert not (row.near_pinned or row.rows_pinned or row.far_pinned)


def test_the_layer_s_fields_pin_a_row() -> None:
    row = new_row(line(near_dx=20.0, rows=6, far_dx=40.0), 10.0, 80.0, 4)
    assert (row.near, row.rows, row.far) == (20.0, 6, 40.0)
    assert row.near_pinned and row.rows_pinned and row.far_pinned


def test_a_blank_field_is_not_a_value() -> None:
    row = new_row(line(near_dx=None, rows="", far_dx="x"), 10.0, 80.0, 4)
    assert (row.near, row.rows, row.far) == (10.0, 4, 80.0)


def test_rows_follow_the_ends_until_set() -> None:
    rows = [new_row(line(n), 10.0, 80.0, 4) for n in (1, 2)]
    set_near(rows[0], 15.0)
    set_far(rows[1], 30.0)
    follow(rows, 20.0, 160.0)
    assert (rows[0].near, rows[0].far) == (15.0, 160.0)
    assert (rows[1].near, rows[1].far) == (20.0, 30.0)


def test_a_row_set_by_hand_survives_the_layer_changing() -> None:
    old = [new_row(line(1), 10.0, 80.0, 4), new_row(line(2), 10.0, 80.0, 4)]
    set_rows(old[1], 7.0)
    rows = merge_rows([line(2), line(3)], old, 10.0, 80.0, 4)
    assert [row.fid for row in rows] == [2, 3]
    assert rows[0].rows == 7
    assert rows[1].rows == 4


def test_the_job_gets_what_was_asked() -> None:
    row = new_row(line(), 10.0, 80.0, 4)
    set_near(row, 15.0)
    assert job_properties(row) == {"name": "Line 1", "near_dx": 15.0, "rows": 4, "far_dx": 80.0}


def test_a_note_names_what_moved() -> None:
    assert rounded_note("Wadi", 15.0, 30.0, 10.0, 80.0) == "Wadi: near 15 m becomes 10 m, far 30 m becomes 20 m."
    assert rounded_note("Wadi", 10.0, 30.0, 10.0, 80.0) == "Wadi: far 30 m becomes 20 m."
    assert rounded_note("Wadi", 10.0, 40.0, 10.0, 80.0) == ""


def test_near_above_far_is_named() -> None:
    assert "Wadi" in reversed_note("Wadi", 40.0, 20.0)
    assert reversed_note("Wadi", 20.0, 20.0) == ""
