"""A cell never gets two rainfalls: the check, on a grid known by hand."""

from __future__ import annotations

import numpy as np
import pytest
import shapely

from wadi2d.engine.rain_once import check_rain_once
from wadi2d.grid.tiles import TileGrid

X0, Y0, DX = 1000.0, 2000.0, 10.0
NX, NY = 40, 20
SHARE = 0.01


def grid() -> TileGrid:
    return TileGrid.from_mask(np.ones((NY, NX), bool), X0, Y0, DX)


def box(x0: float, x1: float, y0: float, y1: float) -> shapely.Polygon:
    return shapely.box(X0 + x0, Y0 - y1, X0 + x1, Y0 - y0)


def test_a_partition_passes_without_a_word() -> None:
    polygons = {"A": box(0.0, 200.0, 0.0, 200.0), "B": box(200.0, 400.0, 0.0, 200.0)}
    assert check_rain_once(grid(), polygons, ["A", "B"], [], SHARE) == []
    assert check_rain_once(grid(), polygons, ["A"], ["B"], SHARE) == []


def test_two_lumped_polygons_on_the_same_ground_are_refused_with_the_count_and_the_names() -> None:
    polygons = {"A": box(0.0, 200.0, 0.0, 200.0), "B": box(150.0, 400.0, 0.0, 200.0)}
    with pytest.raises(ValueError, match=r"100 cells lie under both lumped subbasins A and B \(25.00 % of the smaller"):
        check_rain_once(grid(), polygons, ["A", "B"], [], SHARE)


def test_a_2d_subbasin_under_a_lumped_one_is_refused() -> None:
    polygons = {"A": box(0.0, 200.0, 0.0, 200.0), "B": box(100.0, 400.0, 0.0, 200.0)}
    with pytest.raises(ValueError, match=r"200 cells of 2D subbasin B lie under lumped A"):
        check_rain_once(grid(), polygons, ["A"], ["B"], SHARE)


def test_a_sliver_under_the_share_is_a_warning_with_the_count() -> None:
    polygons = {"A": box(0.0, 200.0, 0.0, 200.0), "B": box(194.0, 400.0, 0.0, 200.0)}  # 6 m wide, 3 % of the smaller
    with pytest.raises(ValueError, match="20 cells"):
        check_rain_once(grid(), polygons, ["A", "B"], [], SHARE)
    (note,) = check_rain_once(grid(), polygons, ["A", "B"], [], 0.05)
    assert note.startswith("20 cells lie under both lumped subbasins A and B (3.00 % of the smaller")
    assert "sliver" in note


def test_a_shared_edge_is_a_tie_not_an_overlap() -> None:
    """Cell centres on the edge between two pixel-exact polygons: the rasteriser may burn both, the check says nothing."""
    polygons = {"A": box(0.0, 205.0, 0.0, 200.0), "B": box(205.0, 400.0, 0.0, 200.0)}  # the edge on the cell centres
    assert check_rain_once(grid(), polygons, ["A", "B"], [], SHARE) == []
    assert check_rain_once(grid(), polygons, ["A"], ["B"], SHARE) == []


def test_a_name_without_a_polygon_is_not_the_checks_business() -> None:
    assert check_rain_once(grid(), {"A": box(0.0, 200.0, 0.0, 200.0)}, ["A", "Nowhere"], ["Elsewhere"], SHARE) == []


def test_a_self_touching_polygon_as_digitised_ones_are_is_made_valid_first() -> None:
    """A bow tie: GEOS refuses to intersect it as it is; Block 2's own HMS polygons have such a spot."""
    bow = shapely.Polygon([(X0, Y0), (X0 + 200.0, Y0 - 200.0), (X0 + 200.0, Y0), (X0, Y0 - 200.0), (X0, Y0)])
    assert not bow.is_valid
    polygons = {"A": bow, "B": box(200.0, 400.0, 0.0, 200.0)}
    assert check_rain_once(grid(), polygons, ["A", "B"], [], SHARE) == []
    polygons["B"] = box(100.0, 400.0, 0.0, 200.0)
    with pytest.raises(ValueError, match="lie under both lumped subbasins A and B"):
        check_rain_once(grid(), polygons, ["A", "B"], [], SHARE)


def test_cells_outside_the_domain_do_not_count() -> None:
    mask = np.ones((NY, NX), bool)
    mask[:, 20:] = False
    polygons = {"A": box(0.0, 400.0, 0.0, 200.0), "B": box(200.0, 400.0, 0.0, 200.0)}
    assert check_rain_once(TileGrid.from_mask(mask, X0, Y0, DX), polygons, ["A", "B"], [], SHARE) == []
