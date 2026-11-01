"""Rules the held-out projects taught: rain by subbasin, the ARF floor, rasters in another system, what is left out.

No project data. Everything here failed, crashed or was never reached on Block 2.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform
from shapely.geometry import box

from wadi2d.hydrology import Junction, LumpedEngine, Subbasin, TimeGrid
from wadi2d.hydrology.losses import NoLoss
from wadi2d.hydrology.model import Basin
from wadi2d.hydrology.replication import Comparison, results_file_name
from wadi2d.hydrology.routing import MuskingumCunge
from wadi2d.hydrology.transforms import ScsUnitHydrograph
from wadi2d.storm import ArfTable, HypotheticalStorm, PercentPattern, StormBySubbasin
from wadi2d.storm.grid_depth import DepthGrid

STEP_SECONDS = 300.0
GEOGRAPHIC = "EPSG:4326"
UTM = "EPSG:32640"


@pytest.mark.parametrize(
    ("analysis", "expected"),
    [
        ("DA 100yr B1", "DAA_DA_100yr_B1.results"),
        ("DA 10yr 1D DAM - All", "DAA_DA_10yr_1D_DAM___All.results"),
    ],
)
def test_results_file_name_replaces_every_non_alphanumeric(analysis: str, expected: str) -> None:
    assert results_file_name(analysis) == expected


def comparison(hms_peak: float, peak: float) -> Comparison:
    return Comparison("A", "P", hms_peak, peak, 0.0, 0.0, 5.0)


def test_a_dam_that_spills_nothing_compares_equal_without_dividing_by_zero() -> None:
    assert comparison(0.0, 0.0).error_percent == 0.0


def test_flow_where_hms_has_none_is_an_infinite_error() -> None:
    assert comparison(0.0, 1.0).error_percent == math.inf


@pytest.mark.parametrize(
    ("length", "celerity", "cells", "substeps"),
    [
        (10.61, 1.524, 1, 43),  # logged dt 7.0 s
        (56.57, 1.524, 1, 8),
        (950.77, 10.524, 1, 3),
        (2144.61, 14.524, 1, 2),
        (3007.87, 15.524, 1, 2),  # 0.646: still rounds to two
        (318.70, 1.524, 1, 1),  # 0.697: one
        (441.84, 1.524, 1, 1),
        (465.98, 1.524, 2, 2),  # 1.02: two cells, then the step halves
        (577.99, 1.524, 2, 2),
        (610.12, 1.524, 2, 1),  # 1.3345: past 4/3 the step stays whole
        (913.97, 1.524, 2, 1),
        (1076.52, 1.524, 3, 1),
        (17006.85, 1.524, 38, 1),
    ],
)
def test_cells_and_substeps_are_what_the_hms_logs_print(
    length: float, celerity: float, cells: int, substeps: int
) -> None:
    reach = MuskingumCunge(length, 0.01, 0.05, 20.0, 1.0, celerity)
    found_cells, dx, found_substeps = reach.grid(STEP_SECONDS)
    assert (found_cells, found_substeps) == (cells, substeps)
    assert dx == pytest.approx(length / cells)


ARF = ArfTable(np.array([1.0, 5.0]), np.array([0.999, 0.994]), reduces_below_table=False)
PATTERN = PercentPattern(np.array([0.0, 100.0]), np.array([0.0, 100.0]))


def test_hms_applies_no_reduction_below_the_smallest_area() -> None:
    assert ARF.factor(0.789) == 1.0
    assert ARF.factor(1.0) == pytest.approx(0.999)
    assert ARF.factor(3.0) == pytest.approx(0.9965)


def test_an_arf_table_holds_its_end_factor_unless_told_otherwise() -> None:
    assert ArfTable(np.array([1.0, 5.0]), np.array([0.999, 0.994])).factor(0.5) == pytest.approx(0.999)


def rain_basin() -> Basin:
    def subbasin(name: str) -> Subbasin:
        return Subbasin(name, "J", 2.0, NoLoss(), ScsUnitHydrograph(30.0))

    return Basin("rain", [subbasin("A"), subbasin("B"), Junction("J", None)])


def test_each_subbasin_gets_its_own_depth_under_one_area_reduction() -> None:
    storm = HypotheticalStorm(0.0, PATTERN, 1.0, 1.0, ARF)
    rain = StormBySubbasin(storm, {"A": 100.0, "B": 200.0}).at_area(3.0)
    run = LumpedEngine(rain_basin()).run(rain, TimeGrid(5.0, 40))
    assert run.water["A"].precipitation.sum() == pytest.approx(100.0 * 0.9965)
    assert run.water["B"].precipitation.sum() == pytest.approx(200.0 * 0.9965)


def test_a_subbasin_with_no_depth_raises() -> None:
    rain = StormBySubbasin(HypotheticalStorm(0.0, PATTERN, 1.0), {"A": 100.0})
    with pytest.raises(KeyError, match="no storm depth"):
        LumpedEngine(rain_basin()).run(rain, TimeGrid(5.0, 40))


def geographic_raster(path: Path) -> None:
    """Four 0.1-degree cells over UTM zone 40, depth = 1, 2 by row, 3, 4."""
    data = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
    profile = {"driver": "GTiff", "height": 2, "width": 2, "count": 1, "dtype": "float32", "crs": GEOGRAPHIC}
    with rasterio.open(path, "w", transform=from_origin(57.0, 23.0, 0.1, 0.1), **profile) as raster:
        raster.write(data, 1)


def around_centre(lon: float, lat: float, half_width: float = 5000.0) -> object:
    (x,), (y,) = transform(GEOGRAPHIC, UTM, [lon], [lat])
    return box(x - half_width, y - half_width, x + half_width, y + half_width)


def test_a_geographic_raster_is_read_under_projected_polygons(tmp_path: Path) -> None:
    path = tmp_path / "pmp.tif"
    geographic_raster(path)
    grid = DepthGrid.load(path, UTM)
    assert grid.mean_over([around_centre(57.05, 22.95)]) == pytest.approx(1.0)
    assert grid.mean_over([around_centre(57.15, 22.85)]) == pytest.approx(4.0)


def test_without_moving_the_cells_nothing_is_centred_in_a_projected_polygon(tmp_path: Path) -> None:
    """The failure Majlas showed; it is a coordinate system, not a small catchment."""
    path = tmp_path / "pmp.tif"
    geographic_raster(path)
    with pytest.raises(ValueError, match="no grid cell"):
        DepthGrid.load(path).mean_over([around_centre(57.05, 22.95)])


def test_a_raster_already_in_the_system_of_the_polygons_is_not_moved(tmp_path: Path) -> None:
    path = tmp_path / "pmp.tif"
    geographic_raster(path)
    assert DepthGrid.load(path, GEOGRAPHIC).x == pytest.approx(DepthGrid.load(path).x)


def test_a_cell_named_twice_counts_once(tmp_path: Path) -> None:
    path = tmp_path / "pmp.tif"
    geographic_raster(path)
    grid = DepthGrid.load(path, UTM)
    first = grid.cells_in(around_centre(57.05, 22.95))
    second = grid.cells_in(around_centre(57.15, 22.95))
    assert grid.mean_of([first, first, second]) == pytest.approx(1.5)


def test_a_polygon_holding_no_cell_centre_raises_instead_of_guessing(tmp_path: Path) -> None:
    path = tmp_path / "pmp.tif"
    geographic_raster(path)
    between = around_centre(57.10, 22.90, 100.0)
    with pytest.raises(ValueError, match="no grid cell"):
        DepthGrid.load(path, UTM).mean_over([between])
