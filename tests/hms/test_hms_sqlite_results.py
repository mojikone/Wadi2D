"""The basin ``.sqlite`` reader and the depth-area results XML."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
import shapely

from wadi2d.hms import load_results, sqlite


@pytest.fixture
def database(tmp_path: Path) -> Path:
    """A small file with the columns HMS writes, its statistics as text like the real one."""
    path = tmp_path / "with space.sqlite"
    polygon = shapely.to_wkb(shapely.box(0, 0, 1000, 2000))
    line = shapely.to_wkb(shapely.LineString([(0, 0), (30, 40)]))
    connection = sqlite3.connect(path)
    connection.executescript("""
        create table subbasin2d (GEOMETRY blob, name varchar, centroid_x float, centroid_y float,
            area_sqkm float);
        create table reach2d (GEOMETRY blob, name varchar, length float, slope float);
        create table subbasin_statistics (subbasin_name varchar, longest_length varchar,
            longest_slope varchar, centroidal_length varchar, centroidal_slope varchar,
            "10_85_length" varchar, "10_85_slope" varchar, basin_slope varchar, basin_relief varchar,
            length_units varchar);
        create table reach_statistics (reach_name varchar, reach_length varchar, reach_slope varchar,
            reach_relief varchar, reach_sinuosity varchar, length_units varchar);
        """)
    connection.execute("insert into subbasin2d values (?,?,?,?,?)", (polygon, "S1", 500.0, 1000.0, 2.0))
    connection.execute("insert into reach2d values (?,?,?,?)", (line, "R1", None, None))
    connection.execute("insert into reach2d values (?,?,?,?)", (line, "S1", 50.0, 0.01))
    connection.execute(
        "insert into subbasin_statistics values (?,?,?,?,?,?,?,?,?,?)",
        ("S1", "100.5", "0.1", "50.5", "0.2", "75.5", "0.3", "0.4", "900", "m"),
    )
    connection.execute(
        "insert into reach_statistics values (?,?,?,?,?,?)", ("R1", "50.5", "0.01", "3", "", "m")
    )
    connection.commit()
    connection.close()
    return path


def test_subbasin_polygons(database: Path) -> None:
    polygon = sqlite.subbasin_polygons(database)[0]
    assert (polygon.name, polygon.area_sqkm, polygon.centroid_x) == ("S1", 2.0, 500.0)
    assert polygon.shape().area == pytest.approx(2e6)


def test_reach_lines(database: Path) -> None:
    assert [line.name for line in sqlite.reach_lines(database)] == ["R1", "S1"]
    selected = sqlite.reach_lines(database, ["R1"])
    assert [line.name for line in selected] == ["R1"]
    assert selected[0].length is None
    assert selected[0].shape().length == pytest.approx(50.0)


def test_statistics_become_numbers(database: Path) -> None:
    subbasin = sqlite.subbasin_statistics(database)["S1"]
    assert (subbasin.length_10_85, subbasin.slope_10_85, subbasin.basin_relief) == (75.5, 0.3, 900.0)
    assert subbasin.length_units == "m"
    reach = sqlite.reach_statistics(database)["R1"]
    assert (reach.length, reach.slope, reach.sinuosity) == (50.5, 0.01, None)


def test_connection_cannot_write(database: Path) -> None:
    with sqlite.connect(database) as connection, pytest.raises(sqlite3.OperationalError):
        connection.execute("delete from subbasin2d")


def test_missing_file_is_not_created(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite"
    with pytest.raises(FileNotFoundError):
        sqlite.connect(path)
    assert not path.exists()


def test_results_header(fixtures: Path) -> None:
    results = load_results(fixtures / "DAA_sample.results")
    assert results.name == "DA 100"
    assert results.start == datetime(2000, 1, 1)
    assert results.end == datetime(2000, 1, 3)
    assert results.execution_time == datetime(2026, 10, 26, 9, 53, 30)
    assert list(results.points) == ["S1", "J1"]


def test_results_subbasin(fixtures: Path) -> None:
    statistics = load_results(fixtures / "DAA_sample.results").element("S1")
    assert (statistics.element_type, statistics.analysis_point) == ("Subbasin", "S1")
    assert (statistics.outflow_max, statistics.outflow_volume, statistics.outflow_depth) == (
        39.25,
        273489.5,
        163.5,
    )
    assert statistics.outflow_max_time == datetime(2000, 1, 1, 12, 20)
    assert (statistics.precipitation, statistics.loss, statistics.excess) == (205.0, 41.5, 163.5)
    assert (statistics.drainage_area, statistics.subbasin_area, statistics.area_units) == (10.5, 10.5, "KM2")
    assert statistics.measures["Outflow Maximum"].units == "M3/S"


def test_results_junction_has_no_precipitation(fixtures: Path) -> None:
    statistics = load_results(fixtures / "DAA_sample.results").element("J1")
    assert statistics.precipitation is None
    assert statistics.subbasin_area is None
    assert statistics.drainage_area == 15.75
    assert statistics.outflow_max_time == datetime(2000, 1, 1)


def test_one_element_at_several_points(fixtures: Path) -> None:
    results = load_results(fixtures / "DAA_sample.results")
    assert results.element("S1").outflow_max == 39.25
    assert results.element("J1", "S1").outflow_max == 37.5
    assert results.own_points().keys() == {"S1", "J1"}
    assert results.element("J1", "S1").outflow_volume is None
    assert results.element("J1", "S1").excess is None
