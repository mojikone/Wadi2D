"""Rain frames, the hyetograph, and gridded rain over cells and polygons; synthetic data only."""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError
from shapely.geometry import box

from wadi2d.config.schema import ArfTableConfig, Storm
from wadi2d.hydrology.cell_rain import CellRain, rain_pixels
from wadi2d.hydrology.losses import ScsCurveNumber
from wadi2d.storm.gridded import GriddedStorm, move_points, pixel_shares
from wadi2d.storm.hyetograph import HyetographStorm
from wadi2d.storm.rain_frames import PixelSeries, RainFrames, depth_in_mm

UTM = "EPSG:32640"


def frames(depths=None, starts=(0.0, 60.0), ends=(60.0, 120.0), crs=UTM) -> RainFrames:
    """2 x 3 pixels of 1 km, north-west corner at (1000, 5000)."""
    data = np.array([[[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], [[10.0, 20.0, 30.0], [40.0, 50.0, 60.0]]]) if depths is None else depths
    return RainFrames(data, np.array(starts), np.array(ends), 1000.0, 5000.0, 1000.0, 1000.0, crs)


@pytest.mark.parametrize(
    ("units", "value", "period", "expected"),
    [
        ("mm", 5.0, 30.0, 5.0),
        ("kg m-2", 5.0, 30.0, 5.0),
        ("kg m**-2", 5.0, 30.0, 5.0),
        ("m", 0.005, 30.0, 5.0),
        ("mm/h", 10.0, 30.0, 5.0),
        ("mm/hr", 10.0, 30.0, 5.0),
        ("mm h-1", 10.0, 30.0, 5.0),
        ("mm hour-1", 10.0, 30.0, 5.0),
        ("mm/day", 240.0, 60.0, 10.0),
        ("kg m-2 s-1", 0.001, 60.0, 3.6),
        ("kg m^-2 s^-1", 0.001, 60.0, 3.6),
        ("kg/m2/s", 0.001, 60.0, 3.6),
    ],
)
def test_units_become_mm_in_the_period(units, value, period, expected) -> None:
    got = depth_in_mm(np.array([[[value]]]), units, "auto", np.array([period]))
    assert got[0, 0, 0] == pytest.approx(expected)


def test_units_the_job_sets_beat_the_file() -> None:
    got = depth_in_mm(np.array([[[6.0]]]), "furlongs", "mm/h", np.array([30.0]))
    assert got[0, 0, 0] == pytest.approx(3.0)


def test_unknown_units_are_refused_not_guessed() -> None:
    with pytest.raises(ValueError, match="set the units by hand"):
        depth_in_mm(np.array([[[6.0]]]), "furlongs", "auto", np.array([30.0]))


def test_a_flag_for_no_data_is_not_negative_rain() -> None:
    got = depth_in_mm(np.array([[[-9999.9, -1e-6, 2.0]]]), "mm", "auto", np.array([30.0]))
    assert np.isnan(got[0, 0, 0])
    assert got[0, 0, 1] == 0.0
    assert got[0, 0, 2] == 2.0


def test_periods_that_overlap_are_refused() -> None:
    with pytest.raises(ValueError, match="overlap"):
        frames(starts=(0.0, 30.0), ends=(60.0, 120.0))


def test_a_point_finds_its_pixel_and_off_the_grid_is_minus_one() -> None:
    f = frames()
    got = f.pixel_of(np.array([1500.0, 3500.0, 999.0, 4001.0]), np.array([4500.0, 3500.0, 4500.0, 4500.0]))
    assert got.tolist() == [0, 5, -1, -1]


def test_series_is_linear_in_a_period_and_level_across_a_gap() -> None:
    f = frames(starts=(0.0, 120.0), ends=(60.0, 180.0))
    s = PixelSeries(f, np.array([0, 5]))
    assert s.at(-5.0).tolist() == [0.0, 0.0]
    assert s.at(30.0) == pytest.approx([0.5, 3.0])
    assert s.at(60.0) == pytest.approx([1.0, 6.0])
    assert s.at(100.0) == pytest.approx([1.0, 6.0])
    assert s.at(150.0) == pytest.approx([6.0, 36.0])
    assert s.at(500.0) == pytest.approx([11.0, 66.0])


def test_no_data_in_one_frame_counts_as_no_rain_and_is_measured() -> None:
    data = frames().depths.copy()
    data[1, 0, 0] = np.nan
    f = frames(data)
    assert PixelSeries(f, np.array([0])).at(120.0) == pytest.approx([1.0])
    assert f.missing_share() == pytest.approx(1.0 / 12.0)


def test_a_start_date_cuts_a_period_and_keeps_its_share() -> None:
    f = RainFrames(
        frames().depths, np.array([0.0, 60.0]), np.array([60.0, 120.0]), 1000.0, 5000.0, 1000.0, 1000.0, UTM,
        np.datetime64("2021-10-03T00:00:00", "s"),
    )  # fmt: skip
    cut = f.since(np.datetime64("2021-10-03T00:30:00", "s"))
    assert cut.starts_min.tolist() == [0.0, 30.0]
    assert cut.ends_min.tolist() == [30.0, 90.0]
    assert cut.depths[0, 0, 0] == pytest.approx(0.5)
    assert cut.depths[1, 0, 0] == pytest.approx(10.0)


def test_a_start_date_before_the_rain_waits_for_it() -> None:
    f = RainFrames(
        frames().depths, np.array([0.0, 60.0]), np.array([60.0, 120.0]), 1000.0, 5000.0, 1000.0, 1000.0, UTM,
        np.datetime64("2021-10-03T01:00:00", "s"),
    )  # fmt: skip
    assert f.since(np.datetime64("2021-10-03T00:00:00", "s")).starts_min[0] == 60.0


def test_rain_that_only_grows_is_flagged() -> None:
    data = np.arange(1.0, 7.0).reshape(6, 1, 1) * np.ones((6, 2, 3))
    starts = 60.0 * np.arange(6)
    assert RainFrames(data, starts, starts + 60.0, 0.0, 0.0, 1.0, 1.0).looks_cumulative()
    assert not frames().looks_cumulative()


def test_hyetograph_sums_to_its_table_and_is_linear_in_a_period() -> None:
    s = HyetographStorm.from_periods([30.0, 60.0, 90.0], [10.0, 40.0, 5.0])
    assert s.total_depth == 55.0
    assert s.cumulative_depth([0.0, 15.0, 30.0, 45.0, 90.0, 500.0]) == pytest.approx([0, 5, 10, 30, 55, 55])
    assert s.increments(30.0, 4) == pytest.approx([10.0, 40.0, 5.0, 0.0])


def test_hyetograph_ignores_a_storm_area() -> None:
    s = HyetographStorm.from_periods([30.0], [10.0])
    assert s.at_area(500.0) is s


def test_schema_refuses_a_bad_table_and_area_reduction_on_observed_rain() -> None:
    table = ArfTableConfig(areas_km2=[1.0], factors=[0.9])
    with pytest.raises(ValidationError, match="one depth per period"):
        Storm(kind="hyetograph", hyetograph_min=[30.0], hyetograph_mm=[1.0, 2.0])
    with pytest.raises(ValidationError, match="rise from above zero"):
        Storm(kind="hyetograph", hyetograph_min=[30.0, 30.0], hyetograph_mm=[1.0, 2.0])
    with pytest.raises(ValidationError, match="must hold some rain"):
        Storm(kind="hyetograph", hyetograph_min=[30.0], hyetograph_mm=[0.0])
    with pytest.raises(ValidationError, match="no area reduction"):
        Storm(kind="hyetograph", hyetograph_min=[30.0], hyetograph_mm=[1.0], arf=table)
    with pytest.raises(ValidationError, match="no area reduction"):
        Storm(kind="gridded", rain_file="a.nc", arf=table)
    with pytest.raises(ValidationError, match="needs rain_file"):
        Storm(kind="gridded")


def test_a_polygon_inside_one_pixel_takes_that_pixel() -> None:
    f = frames()
    pixels, areas, covered = pixel_shares(f, box(1100.0, 4100.0, 1200.0, 4200.0))
    assert pixels.tolist() == [0]
    assert areas == pytest.approx([10000.0])
    assert covered == pytest.approx(1.0)


def test_subbasin_rain_is_the_area_weighted_mean() -> None:
    polygon = box(1500.0, 4000.0, 2250.0, 5000.0)  # 500 m on the first pixel, 250 m on the second
    storm = GriddedStorm(frames()).bind({"A": polygon}, UTM)
    over = storm.over("A")
    assert over.total_depth == pytest.approx((2.0 / 3.0) * 11.0 + (1.0 / 3.0) * 22.0)
    assert over.cumulative_depth([60.0])[0] == pytest.approx((2.0 / 3.0) * 1.0 + (1.0 / 3.0) * 2.0)


def test_subbasin_off_the_grid_is_refused_and_a_thin_one_is_noted() -> None:
    storm = GriddedStorm(frames()).bind(
        {"far": box(9000.0, 9000.0, 9500.0, 9500.0), "edge": box(500.0, 4000.0, 1500.0, 5000.0)}, UTM
    )
    with pytest.raises(ValueError, match="outside the rain grid"):
        storm.over("far")
    storm.over("edge")
    assert any("edge" in note for note in storm.notes(1000.0))


def test_notes_say_when_the_rain_outlasts_the_run() -> None:
    assert any("stops at 90" in note for note in GriddedStorm(frames()).notes(90.0))
    assert not GriddedStorm(frames()).notes(500.0)


def test_points_move_between_systems() -> None:
    x, y = move_points(np.array([500000.0]), np.array([2600000.0]), UTM, "EPSG:4326")
    assert x[0] == pytest.approx(57.0, abs=1e-6)
    assert 23.0 < y[0] < 24.0


def cells(cn, rained=None):
    x = np.array([1500.0, 1600.0, 3500.0])
    y = np.array([4500.0, 4500.0, 3500.0])
    mask = np.ones(3, bool) if rained is None else rained
    storm = GriddedStorm(frames())
    return CellRain(storm, rain_pixels(storm, x, y, UTM), np.asarray(cn, float), mask)


def test_cells_sharing_a_pixel_and_a_curve_number_share_a_pair() -> None:
    rain = cells([np.nan, np.nan, np.nan])
    assert rain.pair_of[0] == rain.pair_of[1] != rain.pair_of[2]
    assert rain.excess_mm(120.0)[rain.pair_of] == pytest.approx([11.0, 11.0, 66.0])


def test_cell_rain_passes_the_loss_of_each_curve_number() -> None:
    rain = cells([80.0, np.nan, 90.0])
    got = rain.excess_mm(120.0)[rain.pair_of]
    assert got[0] == pytest.approx(ScsCurveNumber(80.0).cumulative_excess(np.array(11.0)))
    assert got[1] == pytest.approx(11.0)
    assert got[2] == pytest.approx(ScsCurveNumber(90.0).cumulative_excess(np.array(66.0)))


def test_a_rained_cell_off_the_rain_grid_stops_the_run() -> None:
    x, y = np.array([1500.0, 99000.0]), np.array([4500.0, 4500.0])
    storm = GriddedStorm(frames())
    with pytest.raises(ValueError, match="does not cover the domain"):
        CellRain(storm, rain_pixels(storm, x, y, UTM), np.array([np.nan, np.nan]), np.ones(2, bool))


def test_a_masked_cell_off_the_rain_grid_does_not_matter() -> None:
    x, y = np.array([1500.0, 99000.0]), np.array([4500.0, 4500.0])
    storm = GriddedStorm(frames())
    rain = CellRain(storm, rain_pixels(storm, x, y, UTM), np.array([np.nan, np.nan]), np.array([True, False]))
    assert rain.excess_mm(120.0)[rain.pair_of[0]] == pytest.approx(11.0)
