"""Corridors from bank pairs (W45): the rows follow the wadi's width within his bounds of 2026-11-07, the bank lines
are the rows at the banks, and a corridor of one cell across has no row on its centre line."""

from __future__ import annotations

import numpy as np
import pytest
import shapely

from wadi2d.strips.banks import BankPair, CellRule, corridor_specs, pair_width
from wadi2d.strips.mesher import Corridor, corridor_nodes, corridor_polygon, folds, midline


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


def test_a_corridor_on_the_thalweg_takes_its_edges_from_the_banks_and_keeps_the_median_in_a_gap() -> None:
    """His direction of 2026-11-07: the centre line drives the cells, the floor's edges say how far they repeat."""
    from wadi2d.config.schema import CorridorSpec
    from wadi2d.strips.banks import corridor_specs_thalweg
    from wadi2d.strips.build import snap_geometry

    thalweg = {"line": shapely.LineString([(0.0, 0.0), (900.0, 0.0)]), "area_km2": 10.0, "incised_m": 3.0}
    banks = [
        {"line": shapely.LineString([(0.0, 20.0), (400.0, 20.0)]), "side": "left", "area_km2": 10.0},
        {"line": shapely.LineString([(500.0, 26.0), (900.0, 26.0)]), "side": "left", "area_km2": 10.0},  # a 100 m gap
        {"line": shapely.LineString([(0.0, -40.0), (900.0, -40.0)]), "side": "right", "area_km2": 10.0},
    ]
    domain = shapely.box(-300.0, -400.0, 1200.0, 400.0)
    specs, rejected, rules = corridor_specs_thalweg([thalweg], banks, domain, cell=30.0, along=30.0, min_length=100.0, fixed=False)
    assert len(specs) == 1 and rejected == [], rejected
    (rule,) = rules
    assert rule["cells_across"] == 2 and rule["right_m"] == pytest.approx(40.0, abs=0.5) and 20.0 <= rule["left_m"] <= 26.0
    spec = CorridorSpec.model_validate(specs[0])  # the job carries it: the banks' pieces as a list of lines
    assert spec.offsets[0] == pytest.approx(-40.0, abs=0.5) and 20.0 <= spec.offsets[-1] <= 26.0
    snap = {row.row: snap_geometry(row.coordinates) for row in spec.snap}
    assert snap[2].geom_type == "MultiLineString" and snap[0].geom_type == "LineString"
    c = Corridor(spec.name, shapely.LineString(spec.centre), np.asarray(spec.offsets), 30.0, snap, snap_nearest=False)
    x, y = corridor_nodes(c)
    assert np.allclose(y[:, 0], -40.0, atol=1e-6)
    west, gap, east = x[:, 2] < 390.0, (x[:, 2] > 410.0) & (x[:, 2] < 490.0), x[:, 2] > 510.0
    assert np.allclose(y[west, 2], 20.0, atol=1e-6) and np.allclose(y[east, 2], 26.0, atol=1e-6)
    assert gap.any() and np.all((y[gap, 2] > 19.0) & (y[gap, 2] < 27.0))  # the median half-width, not a point of either piece
    assert np.allclose(y[:, 1], 0.5 * (y[:, 0] + y[:, 2]), atol=1e-6)  # the inner row shares the width
    assert folds(x, y) == []
    one_sided = corridor_specs_thalweg([thalweg], banks[:2], domain, cell=30.0, along=30.0, min_length=100.0, fixed=False)
    assert one_sided[0] == [] and "one side or none" in one_sided[1][0]["why"]


def test_a_ragged_corridor_repeats_fixed_cells_out_to_the_floor_edge() -> None:
    """His word of 2026-11-07, late: cells of 30 m repeated from the centre line to the 5 % edge, not varying sizes."""
    from wadi2d.config.schema import CorridorSpec
    from wadi2d.strips.banks import corridor_specs_thalweg
    from wadi2d.strips.build import snap_geometry
    from wadi2d.strips.mesher import build_strip_mesh, corridor_cells

    thalweg = {"line": shapely.LineString([(0.0, 0.0), (900.0, 0.0)]), "area_km2": 10.0, "incised_m": 3.0}
    banks = [
        {"line": shapely.LineString([(0.0, 40.0), (450.0, 40.0)]), "side": "left", "area_km2": 10.0},
        {"line": shapely.LineString([(450.0, 95.0), (900.0, 95.0)]), "side": "left", "area_km2": 10.0},
        {"line": shapely.LineString([(0.0, -50.0), (900.0, -50.0)]), "side": "right", "area_km2": 10.0},
    ]
    domain = shapely.box(-300.0, -400.0, 1200.0, 400.0)
    specs, rejected, rules = corridor_specs_thalweg([thalweg], banks, domain, cell=30.0, along=30.0, min_length=100.0, fixed=True)
    assert len(specs) == 1 and rejected == [], rejected
    assert rules[0]["across_m"] == 30.0
    spec = CorridorSpec.model_validate(specs[0])
    assert spec.offsets == [] and spec.cell_m == 30.0 and len(spec.edges_left) == 2
    edges = {"left": snap_geometry(spec.edges_left), "right": snap_geometry(spec.edges_right)}
    c = Corridor(spec.name, shapely.LineString(spec.centre), np.zeros(0), 30.0, {}, edges=edges, cell=30.0)
    x, y, valid = corridor_cells(c, smooth=0)
    assert x.shape[1] == 6  # two cells to the right (50 m rounds to 2), up to three to the left (95 m rounds to 3)
    rows_y = y[0]
    assert np.allclose(rows_y, [-60.0, -30.0, 0.0, 30.0, 60.0, 90.0])  # every row at a whole multiple of 30 m
    per_station = valid.sum(axis=1)
    assert per_station[:8].tolist() == [3] * 8 and per_station[-8:].tolist() == [5] * 8  # 1 then 3 on the left, 2 on the right
    assert set(np.unique(per_station).tolist()) <= {3, 5}  # the change is one step, held, no notch
    polygon = corridor_polygon(x, y, valid)
    assert polygon.area == pytest.approx(valid.sum() * 900.0, rel=1e-6)
    from tests.strips.test_mesher import _grid  # a 20 m lattice far larger than this corridor

    grid = _grid()
    shift = np.array([grid.x0 + 400.0, grid.y0 - 500.0])
    moved = Corridor(spec.name, shapely.LineString(np.asarray(spec.centre) + shift), np.zeros(0), 30.0, {}, edges={k: shapely.transform(g, lambda p: p + shift) for k, g in edges.items()}, cell=30.0)
    strip = build_strip_mesh(grid, [moved])
    assert int((strip.corridor >= 0).sum()) == int(valid.sum()) and int((strip.corridor < 0).sum()) > 0
    assert strip.geometry.areas_centroids()[0][strip.corridor >= 0].min() == pytest.approx(900.0, rel=1e-6)


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
