"""Rain gauges: how gauges share a place, how a record becomes periods, and how a job's gauges become one storm.

Every expected number is worked by hand in the test's own lines.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
import shapely

from wadi2d.config.gauges import Gauge, GaugeRain
from wadi2d.config.schema import RunConfig
from wadi2d.hydrology.gauge_rain import GaugeCellRain
from wadi2d.io.series import read_record
from wadi2d.storm.gauge_build import build_gauge_storm
from wadi2d.storm.gauge_series import on_edges, periods_of, since_start
from wadi2d.storm.gauge_weights import inverse_distance, nearest, polygon_points, thiessen_shares
from wadi2d.storm.gauges import GaugeStorm

TWO = np.array([[0.0, 0.0], [10.0, 0.0]])


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def job(tmp_path: Path, gauges: list[dict], **rain) -> RunConfig:
    return RunConfig.model_validate(
        {
            "grid": {"dx": 10.0, "extent": (0.0, 0.0, 100.0, 100.0)},
            "terrain": {"dem": str(tmp_path / "dem.tif")},
            "storm": {"kind": "gauges", "gauges": {"gauges": gauges, **rain}},
        }
    )


# How gauges share a place.


def test_a_place_takes_its_nearest_gauge_and_a_tie_the_first_listed() -> None:
    index = nearest(np.array([1.0, 9.0, 5.0]), np.array([0.0, 0.0, 0.0]), TWO)
    assert index.tolist() == [0, 1, 0]


def test_thiessen_shares_are_the_areas_either_side_of_the_bisector() -> None:
    square = shapely.box(0.0, 0.0, 10.0, 10.0)
    assert thiessen_shares(square, np.array([[2.5, 5.0], [7.5, 5.0]])) == pytest.approx([0.5, 0.5])
    # gauges at x 2 and 6: the bisector stands at x 4, so 40 % of the square is nearer the first
    assert thiessen_shares(square, np.array([[2.0, 5.0], [6.0, 5.0]])) == pytest.approx([0.4, 0.6])
    # a gauge far outside still takes its share: x 2 and 30, bisector at 16, the whole square is the first's
    assert thiessen_shares(square, np.array([[2.0, 5.0], [30.0, 5.0]])) == pytest.approx([1.0, 0.0])


def test_inverse_distance_squared_by_hand() -> None:
    gauges = np.array([[1.0, 0.0], [0.0, 2.0]])
    weights, beyond = inverse_distance(np.array([0.0]), np.array([0.0]), gauges, 2.0, None, quadrants=False)
    # 1 / 1^2 and 1 / 2^2: 1 and 0.25 of 1.25
    assert weights[0] == pytest.approx([0.8, 0.2])
    assert beyond == 0


def test_inverse_distance_takes_the_nearest_gauge_of_each_quadrant() -> None:
    # (1, 0) and (0, 2) both lie north-east of the origin; (-2, 0) north-west
    gauges = np.array([[1.0, 0.0], [0.0, 2.0], [-2.0, 0.0]])
    weights, _ = inverse_distance(np.array([0.0]), np.array([0.0]), gauges, 2.0, None, quadrants=True)
    assert weights[0] == pytest.approx([0.8, 0.0, 0.2])  # 1 and 1 / 4, the (0, 2) gauge left out
    weights, _ = inverse_distance(np.array([0.0]), np.array([0.0]), gauges, 2.0, None, quadrants=False)
    assert weights[0] == pytest.approx(np.array([1.0, 0.25, 0.25]) / 1.5)


def test_a_search_radius_drops_far_gauges_and_a_place_with_none_takes_its_nearest() -> None:
    gauges = np.array([[1.0, 0.0], [0.0, 3.0]])
    weights, beyond = inverse_distance(
        np.array([0.0, 50.0]), np.array([0.0, 0.0]), gauges, 2.0, 2.0, quadrants=False
    )
    assert weights[0] == pytest.approx([1.0, 0.0])
    assert weights[1] == pytest.approx(
        [1.0, 0.0]
    )  # nothing within 2 m of (50, 0): the nearest gauge, and counted
    assert beyond == 1


def test_a_place_on_a_gauge_takes_that_gauge_alone() -> None:
    weights, _ = inverse_distance(np.array([10.0]), np.array([0.0]), TWO, 2.0, None, quadrants=False)
    assert weights[0] == pytest.approx([0.0, 1.0])


def test_polygon_points_lie_inside_and_number_about_what_was_asked() -> None:
    triangle = shapely.Polygon([(0, 0), (100, 0), (0, 100)])
    x, y = polygon_points(triangle, 400)
    assert shapely.contains_xy(triangle, x, y).all()
    assert 300 < x.size < 500


# How a record becomes periods.


def test_an_incremental_csv_with_its_interval_leaves_a_missing_row_as_a_gap(tmp_path) -> None:
    path = write(tmp_path / "g.csv", "minutes,mm\n5,1\n10,2\n20,4\n")
    record = read_record(path, time_unit="min")
    periods = periods_of("g", record, None, "incremental", "mm", 5.0, "end")
    assert periods.starts.tolist() == [0.0, 5.0, 10.0, 15.0]
    assert periods.ends.tolist() == [5.0, 10.0, 15.0, 20.0]
    assert np.isnan(periods.depths[2])  # 10 to 15 min: no row
    assert periods.total == 7.0


def test_an_incremental_csv_with_no_interval_takes_its_spacing() -> None:
    from wadi2d.io.series import StationRecord

    record = StationRecord("g", np.array([1.0, 2.0, 4.0]), minutes=np.array([5.0, 10.0, 20.0]))
    periods = periods_of("g", record, None, "incremental", "mm", None, "end")
    # the first period as long as the second, then each from the stamp before
    assert periods.starts.tolist() == [0.0, 5.0, 10.0]
    assert periods.depths.tolist() == [1.0, 2.0, 4.0]


def test_a_cumulative_record_is_differenced_and_a_fall_is_refused(tmp_path) -> None:
    from wadi2d.io.series import StationRecord

    record = StationRecord("g", np.array([0.0, 3.0, 3.0, 10.0]), minutes=np.array([0.0, 10.0, 20.0, 30.0]))
    periods = periods_of("g", record, None, "cumulative")
    assert periods.depths.tolist() == [3.0, 0.0, 7.0]
    reset = StationRecord("g", np.array([0.0, 3.0, 1.0]), minutes=np.array([0.0, 10.0, 20.0]))
    with pytest.raises(ValueError, match="falls at value 3"):
        periods_of("g", reset, None, "cumulative")


def test_inches_become_millimetres_and_a_negative_depth_is_refused() -> None:
    from wadi2d.io.series import StationRecord

    record = StationRecord("g", np.array([1.0]), minutes=np.array([10.0]))
    assert periods_of("g", record, None, "incremental", "in", 10.0).total == pytest.approx(25.4)
    negative = StationRecord("g", np.array([1.0, -2.0]), minutes=np.array([10.0, 20.0]))
    with pytest.raises(ValueError, match="negative depth"):
        periods_of("g", negative, None, "incremental", "mm", 10.0)


def test_rain_before_the_start_is_cut_by_its_share() -> None:
    from wadi2d.io.series import StationRecord

    record = StationRecord("g", np.array([6.0, 6.0]), minutes=np.array([2.0, 8.0]))
    cut = since_start(periods_of("g", record, None, "incremental", "mm", 6.0, "end"))
    # the first period runs -4 to 2 min: a third of it falls after zero
    assert cut.starts.tolist() == [0.0, 2.0]
    assert cut.depths.tolist() == pytest.approx([2.0, 6.0])


def test_a_period_split_by_other_gauges_edges_keeps_its_rate() -> None:
    from wadi2d.io.series import StationRecord

    periods = periods_of(
        "g", StationRecord("g", np.array([9.0]), minutes=np.array([30.0])), None, "incremental", "mm", 30.0
    )
    assert on_edges(periods, np.array([0.0, 10.0, 30.0])).tolist() == [3.0, 6.0]


# The readers.


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("2021-10-04 00:05", datetime(2021, 10, 4, 0, 5)),
        ("2021-10-04T00:05:00", datetime(2021, 10, 4, 0, 5)),
        ("04Oct2021 00:05", datetime(2021, 10, 4, 0, 5)),
        ("03Oct2021, 2400", datetime(2021, 10, 4, 0, 0)),
    ],
)
def test_dates_year_first_or_as_hec_writes_them(tmp_path, cell, expected) -> None:
    record = read_record(write(tmp_path / "g.csv", f"time,rain\n{cell},1.5\n"))
    assert record.dates[0] == np.datetime64(expected, "s")
    assert record.values.tolist() == [1.5]


def test_a_day_first_date_needs_its_format(tmp_path) -> None:
    path = write(tmp_path / "g.csv", "time,rain\n04/10/2021 00:05,1\n")
    with pytest.raises(ValueError, match="time_format"):
        read_record(path)
    record = read_record(path, time_format="%d/%m/%Y %H:%M")
    assert record.dates[0] == np.datetime64("2021-10-04T00:05", "s")


def test_a_named_column_and_missing_values(tmp_path) -> None:
    path = write(tmp_path / "g.csv", "# station A\nminute;A;B\n5;1;-901\n10;;2\n15;x;3\n")
    record = read_record(path, record="B")
    assert np.isnan(record.values[0]) and record.values[1:].tolist() == [2.0, 3.0]
    assert np.isnan(read_record(path).values[1:]).all()


def test_times_that_do_not_rise_are_refused(tmp_path) -> None:
    with pytest.raises(ValueError, match="times must rise"):
        read_record(write(tmp_path / "g.csv", "5,1\n5,2\n"))


def test_a_dss_rain_record_brings_its_own_type_and_units(tmp_path) -> None:
    from hecdss import HecDss, RegularTimeSeries

    path = tmp_path / "rain.dss"
    native = HecDss(str(path))
    series = RegularTimeSeries.create(
        values=[0.1, 0.2, 0.0], units="IN", data_type="PER-CUM", interval="15Minute",
        start_date=datetime(2021, 10, 4, 0, 15), path="//LIHBAN/PRECIP-INC/01Oct2021/15Minute/OBS/",
    )  # fmt: skip
    native.put(series)
    native.close()
    record = read_record(path, None)
    assert record.kind == "PER-CUM" and record.interval_min == 15.0
    periods = periods_of(
        "g", record, np.datetime64("2021-10-04T00:00", "s"), "cumulative", "mm"
    )  # the file wins
    assert periods.starts.tolist() == [0.0, 15.0, 30.0]
    assert periods.total == pytest.approx(0.3 * 25.4)


# A job's gauges as one storm.


def test_two_gauges_on_different_clocks_become_one_storm(tmp_path) -> None:
    a = write(tmp_path / "a.csv", "2021-10-04 00:10,2\n2021-10-04 00:20,4\n")
    b = write(tmp_path / "b.csv", "2021-10-04 00:15,3\n2021-10-04 00:20,3\n")
    cfg = job(
        tmp_path,
        [
            {"name": "A", "x": 0.0, "y": 0.0, "file": str(a), "interval_min": 10.0},
            {"name": "B", "x": 10.0, "y": 0.0, "file": str(b), "interval_min": 5.0},
        ],
        gaps="zero",
    )
    storm = build_gauge_storm(cfg)
    assert str(storm.origin) == "2021-10-04T00:00:00"  # the earliest period opens at 00:00
    assert storm.edges.tolist() == [0.0, 10.0, 15.0, 20.0]
    assert storm.totals.tolist() == [6.0, 6.0]
    # by 00:15, A has 2 and half of its 4; B has its first period, 00:10 to 00:15, and nothing before it
    assert storm.depths_at(15.0).tolist() == pytest.approx([4.0, 3.0])
    assert any("gauge B had no value for 10 min" in note for note in storm.filled)


def test_a_gap_is_refused_by_gauge_and_time(tmp_path) -> None:
    a = write(tmp_path / "a.csv", "5,1\n10,1\n15,1\n")
    b = write(tmp_path / "b.csv", "5,1\n15,1\n")
    gauges = [
        {"name": "A", "x": 0.0, "y": 0.0, "file": str(a), "interval_min": 5.0},
        {"name": "B", "x": 10.0, "y": 0.0, "file": str(b), "interval_min": 5.0},
    ]
    with pytest.raises(ValueError, match="rain gauge B has no value from minute 5 to minute 10"):
        build_gauge_storm(job(tmp_path, gauges))
    zero = build_gauge_storm(job(tmp_path, gauges, gaps="zero"))
    assert zero.totals.tolist() == [3.0, 2.0]
    filled = build_gauge_storm(job(tmp_path, gauges, gaps="neighbours"))
    assert filled.totals.tolist() == [3.0, 3.0]  # B's gap given A's rain, its nearest gauge with data
    assert any("gauge B had no value for 5 min" in note for note in filled.filled)


def test_a_job_with_no_gauges_and_an_empty_hms_gage_file_says_so(tmp_path) -> None:
    gage = write(tmp_path / "p.gage", "Gage Manager: p\n     Version: 4.12\nEnd:\n\n")
    basin = write(tmp_path / "p.basin", "")
    data = {
        "grid": {"dx": 10.0, "extent": (0.0, 0.0, 100.0, 100.0)},
        "terrain": {"dem": str(tmp_path / "dem.tif")},
        "hydrology": {"hms_basin": str(basin)},
        "storm": {"kind": "gauges", "gauges": {}},
    }
    assert gage.exists()
    with pytest.raises(ValueError, match="holds no precipitation gage with a position"):
        build_gauge_storm(RunConfig.model_validate(data))


def test_schema_refuses_a_gauge_without_position_or_record() -> None:
    with pytest.raises(ValueError, match="needs either file or hms_gage"):
        Gauge(name="A", x=0.0, y=0.0)
    with pytest.raises(ValueError, match="needs its position"):
        Gauge(name="A", file="a.csv")
    with pytest.raises(ValueError, match="unknown gauges"):
        GaugeRain(gauges=[Gauge(name="A", x=0, y=0, file="a.csv")], weights={"S1": {"Z": 1.0}})


# The same rain on cells and on a lumped subbasin.


def storm_of(method: str, **extra) -> GaugeStorm:
    edges = np.array([0.0, 30.0, 60.0])
    cumulative = np.array([[0.0, 0.0], [10.0, 40.0], [20.0, 60.0]])
    return GaugeStorm(("W", "E"), TWO * 100.0, edges, cumulative, method=method, **extra)


@pytest.mark.parametrize("method", ["thiessen", "inverse_distance"])
def test_a_lumped_subbasin_takes_the_mean_of_its_cells(method) -> None:
    """The areal mean over a polygon equals the mean of fine cells inside it, under both methods."""
    polygon = shapely.Polygon([(-200, -300), (900, -100), (700, 400), (-100, 250)])
    storm = storm_of(method, samples=20000).bind({"S": polygon}, "", "")
    step = 5.0
    gx, gy = np.meshgrid(np.arange(-300, 1000, step) + step / 2, np.arange(-400, 500, step) + step / 2)
    inside = shapely.contains_xy(polygon, gx.ravel(), gy.ravel())
    x, y = gx.ravel()[inside], gy.ravel()[inside]
    cells = GaugeCellRain(storm, x, y, np.full(x.size, np.nan), np.ones(x.size, bool))
    for minutes in (15.0, 30.0, 60.0):
        cell_mean = float(cells.rain_mm(minutes)[cells.pair_of].mean())
        lumped = float(storm.over("S").cumulative_depth([minutes])[0])
        assert lumped == pytest.approx(cell_mean, rel=2e-3)


def test_gauge_weights_replace_the_spatial_method_for_their_subbasin() -> None:
    storm = storm_of("thiessen", gauge_weights={"S": {"W": 3.0, "E": 1.0}}).bind({}, "", "")
    # weights scaled to 0.75 and 0.25: 0.75 * 20 + 0.25 * 60
    assert storm.over("S").total_depth == pytest.approx(30.0)
    with pytest.raises(KeyError, match="no polygon for subbasin T"):
        storm.over("T")


def test_cells_with_one_gauge_and_one_curve_number_share_one_excess() -> None:
    storm = storm_of("thiessen")
    x = np.array([10.0, 20.0, 990.0, 980.0, 30.0])
    cn = np.array([80.0, 80.0, 80.0, np.nan, 70.0])
    cells = GaugeCellRain(storm, x, np.zeros(5), cn, np.ones(5, bool))
    assert cells.pair_of.max() + 1 == 4  # (W, 80), (E, 80), (E, none), (W, 70)
    excess = cells.excess_mm(60.0)[cells.pair_of]
    assert excess[3] == pytest.approx(60.0)  # no curve number: the rain whole
    assert excess[0] == excess[1] and excess[0] < 20.0
