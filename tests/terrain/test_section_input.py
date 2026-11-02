"""The three ways of giving a section, and tables that are refused in plain words."""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from tests.engine.conftest import X0, Y0, job, write_dem
from wadi2d.config.schema import RunConfig, Section, TerrainObject
from wadi2d.run import load_job, prepare_grid
from wadi2d.terrain.sections import build_profile, read_table, with_tables

LINE = [(0.0, 0.0), (1000.0, 0.0)]


def profile(kind="channel_dyke", **fields):
    return build_profile(TerrainObject(kind=kind, coordinates=LINE, **fields), 1000.0)


def write(path, text, encoding="utf-8"):
    path.write_text(text, encoding=encoding)
    return path


def test_constants_on_the_object():
    p = profile(z_constant=95.0, section={"width": 8.0, "left_top_z": 99.0, "right_top_z": 100.0, "left_slope": 1.5})
    assert p.bed.tolist() == [95.0, 95.0]
    assert p.half.tolist() == [4.0, 4.0]
    assert p.top[0].tolist() == [99.0, 99.0]
    assert p.top[1].tolist() == [100.0, 100.0]
    assert p.inner[0, 0] == 1.5
    assert p.inner[1, 0] == Section().right_slope


def test_a_profile_on_the_vertices():
    obj = TerrainObject(
        kind="channel", coordinates=[(0.0, 0.0), (100.0, 0.0), (300.0, 0.0)], z=[99.0, 98.0, 94.0]
    )
    p = build_profile(obj, 300.0)
    assert np.interp(200.0, p.station, p.bed) == pytest.approx(96.0)


def test_bed_from_a_level_and_a_slope_with_the_top_as_freeboard_above_a_depth():
    p = profile(section={"bed_start_z": 100.0, "bed_slope": 0.01, "water_depth": 2.0, "freeboard": 0.5})
    assert p.bed.tolist() == [100.0, 90.0]
    assert p.top[0].tolist() == [102.5, 92.5]


def test_top_as_freeboard_above_a_given_water_profile(tmp_path):
    table = write(tmp_path / "w.csv", "station,water_z\n0,103\n500,99\n1000,95\n")
    obj = TerrainObject(
        kind="channel_dyke", coordinates=LINE,
        section={"table": str(table), "bed_start_z": 100.0, "bed_slope": 0.01, "freeboard": 1.0},
    )  # fmt: skip
    cfg = RunConfig(terrain={"objects": [obj]})
    p = build_profile(with_tables(cfg).terrain.objects[0], 1000.0)
    assert p.top[0].tolist() == [104.0, 100.0, 96.0]
    assert p.bed.tolist() == [100.0, 95.0, 90.0]


def test_a_csv_table_with_the_full_section(tmp_path):
    text = (
        "station,bed_z,width,left_top_z,right_top_z,left_slope,right_slope,left_crest_width,right_crest_width,"
        "left_outer_slope,right_outer_slope\n"
        "0,100,10,104,103,2,3,4,5,2,2.5\n"
        "1000,90,20,94,93,2,3,4,5,2,2.5\n"
    )
    rows = read_table(write(tmp_path / "s.csv", text))
    p = build_profile(TerrainObject(kind="channel_dyke", coordinates=LINE, section={"rows": rows}), 1000.0)
    assert p.bed.tolist() == [100.0, 90.0]
    assert p.half.tolist() == [5.0, 10.0]
    assert p.top[:, 1].tolist() == [94.0, 93.0]
    assert p.crest[:, 0].tolist() == [4.0, 5.0]
    assert p.outer[:, 0].tolist() == [2.0, 2.5]


def test_empty_cells_read_between_their_neighbours_and_missing_columns_use_the_constants(tmp_path):
    table = write(tmp_path / "s.csv", "station,bed_z,width\n0,100,10\n500,,\n1000,90,30\n")
    rows = read_table(table)
    p = build_profile(
        TerrainObject(kind="channel", coordinates=LINE, section={"rows": rows, "left_slope": 4.0}), 1000.0
    )
    assert np.interp(500.0, p.station, p.bed) == pytest.approx(95.0)
    assert np.interp(500.0, p.station, p.half) == pytest.approx(10.0)
    assert p.inner[0, 0] == 4.0


def test_a_spreadsheet_csv_with_a_byte_order_mark_and_semicolons(tmp_path):
    table = write(tmp_path / "s.csv", "Station;BED_Z;width\n0;100;10\n100;99;10\n", "utf-8-sig")
    assert read_table(table)[1].bed_z == 99.0


@pytest.mark.parametrize(
    "text, words",
    [
        ("bed_z,width\n1,2\n", "must name a 'station' column"),
        ("station,bed\n0,1\n", "unknown column bed"),
        ("station,bed_z\n0,x\n", "line 2"),
        ("station,bed_z\n", "has no rows"),
    ],
)
def test_a_wrong_table_is_refused_in_plain_words(tmp_path, text, words):
    with pytest.raises(ValueError, match=words):
        read_table(write(tmp_path / "s.csv", text))


def test_stations_out_of_order_are_refused(tmp_path):
    table = write(tmp_path / "s.csv", "station,bed_z\n0,100\n300,99\n200,98\n")
    cfg = RunConfig(terrain={"objects": [{"kind": "channel", "coordinates": LINE, "section": {"table": str(table)}}]})
    with pytest.raises(ValueError, match="stations must increase: station 200 comes after 300"):
        with_tables(cfg)


def test_a_top_below_the_bed_is_refused():
    with pytest.raises(ValueError, match="top is below the bed at station 0"):
        profile(z_constant=100.0, section={"crest_z": 99.0})


@pytest.mark.parametrize(
    "kind, fields, words",
    [
        ("channel", {}, "needs a bed"),
        ("embankment", {}, "needs a crest"),
        ("channel_dyke", {"z_constant": 1.0}, "needs a top"),
        ("channel_dyke", {"section": {"crest_z": 1.0}}, "needs a bed"),
        ("channel", {"z_constant": 1.0, "openings": [{"start": 0.0, "end": 5.0}]}, "no raised part"),
        ("embankment", {"z_constant": 1.0, "lining_n": 0.02}, "no channel section"),
    ],
)
def test_an_object_short_of_a_value_is_refused(kind, fields, words):
    with pytest.raises(ValidationError, match=words):
        TerrainObject(kind=kind, coordinates=LINE, **fields)


def test_an_opening_that_ends_before_it_starts_is_refused():
    with pytest.raises(ValidationError, match="before it starts"):
        TerrainObject(kind="embankment", coordinates=LINE, z_constant=1.0, openings=[{"start": 50.0, "end": 10.0}])


def test_a_relative_table_is_found_beside_the_job_and_its_numbers_key_the_cache(tmp_path):
    z = np.full((48, 48), 100.0)
    dem = write_dem(tmp_path / "d.tif", z, 2.0)
    write(tmp_path / "s.csv", "station,bed_z\n0,99\n60,98\n")
    obj = {
        "kind": "channel", "coordinates": [(X0 + 10.0, Y0 - 40.0), (X0 + 70.0, Y0 - 40.0)],
        "section": {"table": "s.csv", "width": 8.0},
    }  # fmt: skip
    cfg = job(dem, 12, 12, 8.0, terrain={"objects": [obj]})
    path = tmp_path / "job.json"
    path.write_text(cfg.model_dump_json(), encoding="utf-8")
    loaded = load_job(path)
    assert loaded.terrain.objects[0].section.table == str(tmp_path / "s.csv")
    first, _ = prepare_grid(loaded, tmp_path / "cache")
    write(tmp_path / "s.csv", "station,bed_z\n0,97\n60,96\n")
    second, _ = prepare_grid(loaded, tmp_path / "cache")
    assert len(list((tmp_path / "cache").glob("grid_*.h5"))) == 2
    assert second.zmin.min() == pytest.approx(first.zmin.min() - 2.0, abs=0.5)
