"""A cell never gets two rainfalls: the check, on a grid known by hand."""

from __future__ import annotations

import numpy as np
import pytest
import shapely

from wadi2d.engine.rain_once import check_rain_once
from wadi2d.grid.tiles import TileGrid

X0, Y0, DX = 1000.0, 2000.0, 10.0
NX, NY = 40, 20


def grid() -> TileGrid:
    return TileGrid.from_mask(np.ones((NY, NX), bool), X0, Y0, DX)


def box(x0: float, x1: float, y0: float, y1: float) -> shapely.Polygon:
    return shapely.box(X0 + x0, Y0 - y1, X0 + x1, Y0 - y0)


def test_a_partition_passes() -> None:
    polygons = {"A": box(0.0, 200.0, 0.0, 200.0), "B": box(200.0, 400.0, 0.0, 200.0)}
    check_rain_once(grid(), polygons, ["A", "B"], [])
    check_rain_once(grid(), polygons, ["A"], ["B"])


def test_two_lumped_polygons_on_one_cell_are_refused_with_the_count_and_the_names() -> None:
    polygons = {"A": box(0.0, 200.0, 0.0, 200.0), "B": box(150.0, 400.0, 0.0, 200.0), "C": box(0.0, 10.0, 0.0, 10.0)}
    with pytest.raises(ValueError, match=r"100 cells lie under two lumped subbasins \(A, B\)"):
        check_rain_once(grid(), polygons, ["A", "B"], [])
    with pytest.raises(ValueError, match="A, B, C"):
        check_rain_once(grid(), polygons, ["A", "B", "C"], [])


def test_a_2d_subbasin_under_a_lumped_one_is_refused() -> None:
    polygons = {"A": box(0.0, 200.0, 0.0, 200.0), "B": box(100.0, 400.0, 0.0, 200.0)}
    with pytest.raises(ValueError, match=r"200 cells of 2D subbasin B lie under lumped A"):
        check_rain_once(grid(), polygons, ["A"], ["B"])


def test_a_name_without_a_polygon_is_not_the_checks_business() -> None:
    check_rain_once(grid(), {"A": box(0.0, 200.0, 0.0, 200.0)}, ["A", "Nowhere"], ["Elsewhere"])


def test_cells_outside_the_domain_do_not_count() -> None:
    mask = np.ones((NY, NX), bool)
    mask[:, 20:] = False
    polygons = {"A": box(0.0, 400.0, 0.0, 200.0), "B": box(200.0, 400.0, 0.0, 200.0)}
    check_rain_once(TileGrid.from_mask(mask, X0, Y0, DX), polygons, ["A", "B"], [])
