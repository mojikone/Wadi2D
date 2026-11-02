# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Boundaries table: a row follows the section until someone has set it, and then it stays."""

from __future__ import annotations

import pytest
from wadi2d_qgis.boundary_rows import (
    as_number,
    follow,
    job_properties,
    line_label,
    merge_rows,
    new_row,
    set_kind,
    set_value,
)

DEFAULTS = {"stage": 0.0, "normal": 0.005}


def line(fid: int = 1, **own) -> dict:
    return {"fid": fid, "label": f"Line {fid}", **own}


def test_a_line_with_no_fields_takes_the_section() -> None:
    row = new_row(line(), "normal", 0.008, DEFAULTS)
    assert (row.kind, row.value, row.kind_pinned, row.value_pinned) == ("normal", 0.008, False, False)


def test_a_line_with_both_fields_is_pinned_by_them() -> None:
    row = new_row(line(kind="Stage", value=3.5), "normal", 0.008, DEFAULTS)
    assert (row.kind, row.value, row.kind_pinned, row.value_pinned) == ("stage", 3.5, True, True)


def test_a_kind_field_alone_starts_from_the_default_of_its_kind_not_a_value_of_another() -> None:
    row = new_row(line(kind="stage"), "normal", 0.008, DEFAULTS)
    assert (row.kind, row.value) == ("stage", 0.0)


def test_a_value_field_alone_keeps_the_kind_following_the_section() -> None:
    rows = [new_row(line(value=0.02), "normal", 0.008, DEFAULTS)]
    assert rows[0].value == 0.02
    follow(rows, "stage", 1.0)
    assert (rows[0].kind, rows[0].value) == ("stage", 0.02)


@pytest.mark.parametrize("blank", [None, "", "  ", "x"])
def test_a_blank_field_is_not_a_value(blank) -> None:
    assert as_number(blank) is None
    assert new_row(line(kind="normal", value=blank), "normal", 0.008, DEFAULTS).value == 0.008


def test_rows_follow_the_section_until_pinned() -> None:
    rows = [new_row(line(n), "normal", 0.008, DEFAULTS) for n in (1, 2)]
    set_value(rows[0], 0.03)
    follow(rows, "normal", 0.02)
    assert [row.value for row in rows] == [0.03, 0.02]


def test_changing_a_rows_kind_starts_its_value_from_that_kind() -> None:
    row = new_row(line(), "normal", 0.008, DEFAULTS)
    set_kind(row, "stage", DEFAULTS)
    assert (row.kind, row.value) == ("stage", 0.0)
    set_kind(row, "free", DEFAULTS)
    assert (row.kind, row.value) == ("free", None)


def test_choosing_the_same_kind_keeps_the_value_and_pins_it() -> None:
    row = new_row(line(), "normal", 0.008, DEFAULTS)
    set_kind(row, "normal", DEFAULTS)
    assert row.value == 0.008 and row.kind_pinned and row.value_pinned


def test_the_layer_changing_keeps_what_was_set() -> None:
    rows = merge_rows([line(1), line(2)], [], "normal", 0.008, DEFAULTS)
    set_value(rows[1], 0.04)
    rows = merge_rows([line(2), line(3)], rows, "normal", 0.008, DEFAULTS)
    assert [(row.fid, row.value) for row in rows] == [(2, 0.04), (3, 0.008)]


def test_a_renamed_line_keeps_its_row() -> None:
    rows = merge_rows([line(1)], [], "normal", 0.008, DEFAULTS)
    rows = merge_rows([{"fid": 1, "label": "Sea"}], rows, "normal", 0.008, DEFAULTS)
    assert rows[0].label == "Sea"


def test_free_sends_no_value_to_the_job_whatever_the_row_holds() -> None:
    row = new_row(line(value=3.0), "free", None, DEFAULTS)
    assert job_properties(row) == {"kind": "free", "value": None}


@pytest.mark.parametrize(("name", "label"), [(None, "Line 4"), ("  ", "Line 4"), ("Sea", "Sea"), (7, "7")])
def test_a_row_is_named_by_the_layer_or_by_its_number(name, label: str) -> None:
    assert line_label(4, name) == label
