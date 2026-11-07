"""Corridors from bank pairs (W45): the rows follow the wadi's width within his bounds of 2026-11-07, the bank lines
are the rows at the banks, and a corridor of one cell across has no row on its centre line."""

from __future__ import annotations

import numpy as np
import pytest
import shapely

from wadi2d.strips.banks import BankPair, CellRule, corridor_specs, pair_width
from wadi2d.strips.mesher import Corridor, corridor_nodes, folds, midline


def _pair(width: float, length: float = 800.0, area: float = 10.0) -> BankPair:
    left = shapely.LineString([(0.0, width / 2), (length, width / 2)])
    right = shapely.LineString([(0.0, -width / 2), (length, -width / 2)])
    return BankPair(area, left, right, midline(left, right))


@pytest.mark.parametrize(
    "width, cells, across",
    [(16.0, 1, 16.0), (60.0, 3, 20.0), (120.0, 4, 30.0), (300.0, 6, 50.0), (1000.0, 20, 50.0)],
)
def test_the_cell_rule_splits_the_width_between_his_bounds(width: float, cells: int, across: float) -> None:
    offsets, n, size = CellRule(20.0, 50.0, 0.25, 1).layout(width)
    assert n == cells and size == pytest.approx(across)
    assert len(offsets) == n + 3 and offsets == sorted(offsets)
    assert offsets[1] == pytest.approx(-width / 2) and offsets[-2] == pytest.approx(width / 2)
    assert offsets[0] == pytest.approx(-width / 2 - size) and offsets[-1] == pytest.approx(width / 2 + size)
    assert np.allclose(np.diff(offsets[1:-1]), size)


def test_more_rows_outside_and_a_coarser_share() -> None:
    offsets, n, size = CellRule(20.0, 50.0, 0.5, 2).layout(100.0)
    assert (n, size) == (2, 50.0)
    assert offsets == pytest.approx([-150.0, -100.0, -50.0, 0.0, 50.0, 100.0, 150.0])


def test_a_corridor_from_a_pair_puts_the_bank_lines_on_the_rows_at_the_banks() -> None:
    pair = _pair(60.0)
    assert pair_width(pair) == pytest.approx(60.0, abs=0.5)
    domain = shapely.box(-200.0, -400.0, 1000.0, 400.0)
    specs, rejected, rules = corridor_specs([pair], domain, CellRule(20.0, 50.0, 0.25, 1), along=20.0, min_length=100.0)
    assert len(specs) == 1 and rejected == []
    (rule,) = rules
    assert rule["cells_across"] == 3 and rule["rows_outside"] == 1
    assert rule["width_m"] == pytest.approx(60.0, abs=0.5) and rule["across_m"] == pytest.approx(20.0, abs=0.2)
    spec = specs[0]
    assert spec["offsets"] == pytest.approx([-50.0, -30.0, -10.0, 10.0, 30.0, 50.0], abs=0.3)
    rows = {s["row"]: shapely.LineString(s["coordinates"]) for s in spec["snap"]}
    assert set(rows) == {1, 4}
    c = Corridor(spec["name"], shapely.LineString(spec["centre"]), np.asarray(spec["offsets"]), 20.0, rows)
    x, y = corridor_nodes(c)
    # travel runs east along the mid-line, so the north bank is left of travel: row 4, at +30 m
    assert np.allclose(y[:, 4], 30.0, atol=1e-6) and np.allclose(y[:, 1], -30.0, atol=1e-6)
    assert np.allclose(np.diff(y, axis=1), 20.0, atol=1e-6)
    assert folds(x, y) == []


def test_a_wadi_of_one_cell_across_has_no_row_on_its_centre_and_its_banks_still_snap() -> None:
    pair = _pair(16.0)
    domain = shapely.box(-200.0, -400.0, 1000.0, 400.0)
    specs, _rejected, rules = corridor_specs([pair], domain, CellRule(20.0, 50.0, 0.25, 1), along=20.0, min_length=100.0)
    assert rules[0]["cells_across"] == 1 and rules[0]["across_m"] == pytest.approx(16.0, abs=0.3)
    spec = specs[0]
    assert spec["offsets"] == pytest.approx([-24.0, -8.0, 8.0, 24.0], abs=0.3)
    assert 0.0 not in spec["offsets"]
    rows = {s["row"]: shapely.LineString(s["coordinates"]) for s in spec["snap"]}
    c = Corridor(spec["name"], shapely.LineString(spec["centre"]), np.asarray(spec["offsets"]), 20.0, rows)
    x, y = corridor_nodes(c)
    assert np.allclose(y[:, 2], 8.0, atol=1e-6) and np.allclose(y[:, 1], -8.0, atol=1e-6)
    assert folds(x, y) == []
