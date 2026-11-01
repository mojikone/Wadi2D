"""Storms, area reduction and the registry; no data folder needed."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from wadi2d.storm import (
    STORM_METHODS,
    ArfTable,
    HypotheticalStorm,
    PercentPattern,
    Registry,
    Storm,
    UniformStorm,
)
from wadi2d.storm.grid_depth import DepthGrid

ARF = ArfTable(np.array([1.0, 10.0, 100.0]), np.array([0.99, 0.9, 0.8]))
PATTERN = PercentPattern(np.array([0.0, 50.0, 100.0]), np.array([0.0, 80.0, 100.0]))


def test_arf_hits_its_nodes_and_interpolates_linearly_in_area() -> None:
    assert ARF.factor(10.0) == pytest.approx(0.9)
    assert ARF.factor(55.0) == pytest.approx(0.85)


def test_arf_holds_the_end_factors_beyond_the_table() -> None:
    assert ARF.factor(0.5) == pytest.approx(0.99)
    assert ARF.factor(1000.0) == pytest.approx(0.8)


def test_arf_rejects_a_table_that_does_not_rise_in_area() -> None:
    with pytest.raises(ValueError, match="increase"):
        ArfTable(np.array([2.0, 1.0]), np.array([0.9, 0.95]))


def test_hypothetical_increments_are_period_ending_and_sum_to_the_depth() -> None:
    storm = HypotheticalStorm(depth_mm=100.0, pattern=PATTERN, duration_hours=2.0)
    steps = storm.increments(30.0, 6)
    assert steps == pytest.approx([40.0, 40.0, 10.0, 10.0, 0.0, 0.0])
    assert storm.cumulative_depth(np.array([0.0, 60.0, 120.0, 500.0])) == pytest.approx(
        [0.0, 80.0, 100.0, 100.0]
    )


def test_hypothetical_pattern_is_interpolated_linearly_inside_a_segment() -> None:
    storm = HypotheticalStorm(depth_mm=100.0, pattern=PATTERN, duration_hours=2.0)
    assert storm.cumulative_depth(15.0) == pytest.approx(20.0)


def test_at_area_reduces_a_copy_and_leaves_the_storm_alone() -> None:
    storm = HypotheticalStorm(
        depth_mm=100.0, pattern=PATTERN, duration_hours=2.0, arf=ARF, storm_area_km2=1.0
    )
    reduced = storm.at_area(100.0)
    assert reduced.total_depth == pytest.approx(80.0)
    assert storm.total_depth == pytest.approx(99.0)
    assert reduced.increments(120.0, 1).sum() == pytest.approx(80.0)


def test_uniform_storm_rains_at_a_constant_rate_then_stops() -> None:
    steps = UniformStorm(depth_mm=30.0, duration_minutes=30.0).increments(10.0, 4)
    assert steps == pytest.approx([10.0, 10.0, 10.0, 0.0])


def test_uniform_storm_reduces_by_area() -> None:
    storm = UniformStorm(depth_mm=30.0, duration_minutes=30.0, arf=ARF)
    assert storm.at_area(10.0).total_depth == pytest.approx(27.0)


@pytest.mark.parametrize("storm", [UniformStorm(1.0, 1.0), HypotheticalStorm(1.0, PATTERN, 1.0)])
def test_every_storm_meets_the_protocol(storm: Storm) -> None:
    assert isinstance(storm, Storm)


def test_registry_builds_a_storm_by_name() -> None:
    assert STORM_METHODS.build("Uniform", depth_mm=5.0, duration_minutes=5.0).total_depth == 5.0
    assert "Hypothetical Storm" in STORM_METHODS


def test_registry_refuses_an_unknown_name_and_a_second_entry() -> None:
    registry: Registry[int] = Registry("test")
    registry.register("one")(int)
    with pytest.raises(KeyError, match="unknown test method"):
        registry.build("two")
    with pytest.raises(ValueError, match="already registered"):
        registry.register("one")(int)


def test_depth_grid_mean_takes_cells_centred_in_the_polygons(tmp_path: Path) -> None:
    path = tmp_path / "depths.tif"
    values = np.array([[1.0, 2.0, 3.0], [4.0, -9.0, 6.0]], dtype=np.float32)
    transform = from_origin(0.0, 20.0, 10.0, 10.0)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=2,
        width=3,
        count=1,
        dtype="float32",
        nodata=-9.0,
        transform=transform,
    ) as raster:
        raster.write(values, 1)
    grid = DepthGrid.load(path)
    assert grid.mean_over([box(0.0, 10.0, 10.0, 20.0)]) == pytest.approx(1.0)
    assert grid.mean_over([box(0.0, 0.0, 12.0, 8.0), box(20.0, 10.0, 30.0, 20.0)]) == pytest.approx(3.5)
    assert grid.mean_over([box(10.0, 0.0, 20.0, 10.0), box(10.0, 10.0, 20.0, 20.0)]) == pytest.approx(2.0)
    with pytest.raises(ValueError, match="no grid cell"):
        grid.mean_over([box(100.0, 100.0, 110.0, 110.0)])
