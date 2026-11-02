# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A saved profile on disk: what the editor starts from, and that the engine reads back the same ground."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from wadi2d_qgis.job_builder import Feature, LayerError
from wadi2d_qgis.profile_model import ProfileModel
from wadi2d_qgis.profile_table import (
    BED,
    CREST,
    FOLDER_PROPERTY,
    LEFT,
    RIGHT,
    Line,
    ProfileStore,
    apply_levels,
    interp,
    keyed,
    part_label,
    point_at,
    profile_folder,
    profile_path,
    read_rows,
    seed,
    series_keys,
    vertex_stations,
    with_levels,
    write_rows,
)
from wadi2d_qgis.shaped import shaped_object

from wadi2d.config.schema import TerrainObject
from wadi2d.terrain.sections import build_profile, read_table

COORDS = [[0.0, 0.0], [300.0, 400.0], [300.0, 900.0]]
GROUND = [(0.0, 110.0), (500.0, 100.0), (1000.0, 90.0)]


def line(kind="channel", coordinates=COORDS, table=None, **properties) -> Line:
    return Line("1", 1, "Line 1", kind, coordinates, properties, table)


def csv_file(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_stations_and_points_along_a_polyline() -> None:
    stations = vertex_stations(COORDS)
    assert stations == [0.0, 500.0, 1000.0]
    assert point_at(COORDS, stations, 250.0) == (150.0, 200.0)
    assert point_at(COORDS, stations, 750.0) == (300.0, 650.0)
    assert point_at(COORDS, stations, 5000.0) == (300.0, 900.0)


@pytest.mark.parametrize("s, z", [(-1.0, 10.0), (0.0, 10.0), (50.0, 15.0), (100.0, 20.0), (500.0, 20.0)])
def test_a_level_holds_past_the_ends_as_the_engine_reads_it(s, z) -> None:
    assert interp([(0.0, 10.0), (100.0, 20.0)], s) == z


def test_rows_read_as_the_engine_reads_them_a_mark_semicolons_and_blanks(tmp_path) -> None:
    path = tmp_path / "s.csv"
    path.write_text("Station;BED_Z;width\n0;100;10\n100;;\n", encoding="utf-8-sig")
    assert read_rows(path) == [
        {"station": 0.0, "bed_z": 100.0, "width": 10.0},
        {"station": 100.0, "bed_z": None, "width": None},
    ]


@pytest.mark.parametrize(
    "text, words", [("station,bed_z\n,1\n", "needs a station"), ("station,bed_z\n0,x\n", "line 2")]
)
def test_a_wrong_table_is_said_in_words(tmp_path, text, words) -> None:
    with pytest.raises(ValueError, match=words):
        read_rows(csv_file(tmp_path / "s.csv", text))


def test_what_is_written_the_engine_reads(tmp_path) -> None:
    rows = [
        {"station": 0.0, "bed_z": 100.0, "left_top_z": 104.0, "right_top_z": None, "width": 12.0},
        {"station": 1000.5, "bed_z": 99.123456, "left_top_z": 103.0, "right_top_z": 102.0, "width": None},
    ]
    read = read_table(write_rows(tmp_path / "out" / "p.csv", rows))
    assert read[0].width == 12.0
    assert read[0].right_top_z is None
    assert read[1].station == 1000.5
    assert read[1].bed_z == 99.123456


def test_the_columns_come_station_levels_then_the_rest(tmp_path) -> None:
    path = write_rows(tmp_path / "p.csv", [{"width": 1.0, "right_top_z": 2.0, "station": 0.0, "bed_z": 3.0}])
    assert path.read_text(encoding="utf-8").splitlines()[0] == "station,bed_z,right_top_z,width"


@pytest.mark.parametrize(
    "kind, rows, keys",
    [
        ("channel", [], (BED,)),
        ("channel_dyke", [], (BED, LEFT, RIGHT)),
        ("embankment", [], (CREST,)),
        ("embankment", [{"station": 0.0, "left_top_z": 3.0}], (LEFT, RIGHT)),
        ("crest_line", [], (CREST,)),
        ("spillway", [], (CREST,)),
        ("burn_line", [], (CREST,)),
    ],
)
def test_what_is_edited_on_each_kind(kind, rows, keys) -> None:
    assert series_keys(kind, rows) == keys


def test_a_constant_gives_two_points() -> None:
    assert seed(line(crest_z=95.0), GROUND).points == {BED: [(0.0, 95.0), (1000.0, 95.0)]}


def test_z_on_the_vertices_gives_one_point_each() -> None:
    three_d = [[*point, 100.0 - n] for n, point in enumerate(COORDS)]
    assert seed(line(coordinates=three_d), GROUND).points[BED] == [(0.0, 100.0), (500.0, 99.0), (1000.0, 98.0)]


def test_a_repeated_vertex_gives_one_point() -> None:
    three_d = [[0.0, 0.0, 9.0], [0.0, 0.0, 9.0], [10.0, 0.0, 8.0]]
    assert seed(line(coordinates=three_d), []).points[BED] == [(0.0, 9.0), (10.0, 8.0)]


def test_a_start_level_and_slope() -> None:
    assert seed(line(bed_start_z=100.0, bed_slope=0.01), GROUND).points[BED] == [(0.0, 100.0), (1000.0, 90.0)]


def test_a_top_as_freeboard_above_a_depth() -> None:
    done = seed(line("channel_dyke", bed_start_z=100.0, bed_slope=0.01, water_depth=2.0, freeboard=0.5), GROUND)
    assert done.points[LEFT] == [(0.0, 102.5), (1000.0, 92.5)]
    assert done.points[RIGHT] == done.points[LEFT]


def test_one_field_for_both_banks_and_one_for_a_bank() -> None:
    done = seed(line("channel_dyke", crest_z=90.0, top_z=95.0, right_top_z=96.0), GROUND)
    assert done.points[LEFT][0] == (0.0, 95.0)
    assert done.points[RIGHT][0] == (0.0, 96.0)


def test_a_table_outranks_the_line_and_keeps_its_other_columns() -> None:
    rows = [
        {"station": 0.0, "bed_z": 80.0, "width": 10.0},
        {"station": 500.0, "bed_z": None, "width": 20.0},
        {"station": 1000.0, "bed_z": 70.0, "width": None},
    ]
    done = seed(line(crest_z=95.0), GROUND, rows)
    assert done.points[BED] == [(0.0, 80.0), (1000.0, 70.0)]
    assert done.others == {0.0: {"width": 10.0}, 500.0: {"width": 20.0}}


def test_a_line_with_no_level_starts_on_the_ground_and_says_so() -> None:
    done = seed(line("channel_dyke"), GROUND)
    assert done.points[BED] == [(0.0, 110.0), (500.0, 100.0), (1000.0, 90.0)]
    assert done.points[LEFT] == done.points[BED]
    assert "start on the ground" in done.note
    assert seed(line(crest_z=1.0), GROUND).note == ""


def test_a_top_that_starts_on_the_ground_never_starts_under_the_bed() -> None:
    assert seed(line("channel_dyke", crest_z=105.0), GROUND).points[LEFT] == [
        (0.0, 110.0),
        (500.0, 105.0),
        (1000.0, 105.0),
    ]


def test_a_saved_elevation_is_what_a_crest_line_starts_from() -> None:
    rows = [{"station": 0.0, "crest_z": 88.0}, {"station": 400.0, "crest_z": 87.0}]
    assert seed(line("crest_line", crest_z=50.0), GROUND, rows).points[CREST] == [(0.0, 88.0), (400.0, 87.0)]


def test_with_no_ground_and_no_level_a_series_stays_empty() -> None:
    assert seed(line(), []).points[BED] == []


CASES = [
    ("channel", {"crest_z": 95.0}, None),
    ("channel", {"bed_start_z": 100.0, "bed_slope": 0.01}, None),
    ("channel", {"bed_start_z": 100.0, "bed_slope": -0.002, "width": 12.0, "left_slope": 3.0}, None),
    ("channel_dyke", {"crest_z": 90.0, "top_z": 95.0}, None),
    ("channel_dyke", {"crest_z": 90.0, "left_top_z": 95.0, "right_top_z": 96.5}, None),
    ("channel_dyke", {"bed_start_z": 100.0, "bed_slope": 0.01, "water_depth": 2.0, "freeboard": 0.5}, None),
    ("embankment", {"crest_z": 120.0}, None),
    ("channel", {}, "station,bed_z,width\n0,100,10\n400,,\n1000,90,30\n"),
    ("channel_dyke", {"crest_z": 80.0}, "station,bed_z,left_top_z,right_top_z,left_slope\n0,70,75,76,3\n1000,71,77,78,4\n"),
    ("channel_dyke", {}, "station,bed_z,crest_z\n0,70,75\n500,71,76\n1000,69,74\n"),
    ("channel_dyke", {"freeboard": 1.0, "crest_z": 60.0}, "station,water_z\n0,70\n1000,68\n"),
    ("embankment", {}, "station,crest_z,width\n0,120,6\n1000,122,8\n"),
    ("embankment", {}, "station,left_top_z,right_top_z\n0,120,119\n1000,122,121\n"),
    ("embankment", {"crest_z": 130.0}, "station,width\n0,6\n1000,8\n"),
]


@pytest.mark.parametrize("kind, properties, text", CASES)
def test_opening_and_saving_a_line_gives_the_engine_the_same_profile(kind, properties, text, tmp_path) -> None:
    """Every way a level can be given, against the engine's own reader."""
    source = csv_file(tmp_path / "source.csv", text) if text else None
    feature = Feature("LineString", COORDS, properties)
    before = dict(shaped_object(kind, feature))
    if source:
        before["section"] = {**before["section"], "rows": read_table(source)}
    old = build_profile(TerrainObject(**before), 1000.0)

    rows = read_rows(source) if source else []
    model = ProfileModel(seed(Line("1", 1, "L", kind, COORDS, properties), GROUND, rows), 1000.0)
    saved = write_rows(tmp_path / "saved.csv", model.rows())
    after = dict(shaped_object(kind, feature, saved))
    after["section"] = {**after["section"], "rows": read_table(saved), "table": None}
    new = build_profile(TerrainObject(**after), 1000.0)

    s = np.unique(np.concatenate((old.station, new.station, np.linspace(0.0, 1000.0, 41))))
    for right in (False, True):
        was, now = old.at(s, right), new.at(s, right)
        for name in ("bed", "half", "top", "inner", "crest", "outer"):
            np.testing.assert_allclose(getattr(now, name), getattr(was, name), atol=1e-6, err_msg=name)


def test_levels_go_on_the_vertices_and_on_the_line_between_them() -> None:
    done = with_levels(COORDS, [(0.0, 100.0), (250.0, 90.0), (1000.0, 80.0)])
    assert [point[:2] for point in done] == [[0.0, 0.0], [150.0, 200.0], [300.0, 400.0], [300.0, 900.0]]
    assert done[1][2] == 90.0
    assert done[2][2] == pytest.approx(90.0 - 250.0 / 750.0 * 10.0)
    assert done[3][2] == 80.0


def test_a_profile_on_the_vertices_adds_no_vertex_and_one_past_the_end_is_held() -> None:
    done = with_levels(COORDS, [(0.0, 100.0), (500.0, 90.0), (1000.0, 80.0), (1200.0, 70.0)])
    assert [point[:2] for point in done] == COORDS
    assert [point[2] for point in done] == [100.0, 90.0, 80.0]


def test_a_saved_elevation_outranks_the_field_on_the_feature(tmp_path) -> None:
    table = csv_file(tmp_path / "p.csv", "station,crest_z\n0,100\n1000,98\n")
    feature = Feature("LineString", COORDS, {"crest_z": 50.0, "length": 12.0})
    done = apply_levels(feature, str(table))
    assert done.vertex_z() == [100.0, 99.0, 98.0]
    assert done.properties == {"length": 12.0}
    assert apply_levels(feature, None) is feature


@pytest.mark.parametrize("text, words", [("station,bed_z\n0,1\n", "holds no elevations"), ("station,crest_z\n0,x\n", "cannot be read")])
def test_a_saved_elevation_that_cannot_be_used_is_said(tmp_path, text, words) -> None:
    with pytest.raises(LayerError, match=words):
        apply_levels(Feature("LineString", COORDS, {}), str(csv_file(tmp_path / "p.csv", text)))


def test_keys_are_by_feature_with_the_id_taken_back_out() -> None:
    features = [
        Feature("LineString", COORDS, {"fid": 7, "name": "A"}),
        Feature("LineString", COORDS, {"fid": 7, "name": "A"}),
        Feature("LineString", COORDS, {"fid": 9}),
    ]
    done = keyed(features)
    assert [(key, fid) for key, fid, _feature in done] == [("7", 7), ("7_part2", 7), ("9", 9)]
    assert done[0][2].properties == {"name": "A"}
    assert part_label(1, done[1][2], "7_part2") == "A, part 2"
    assert part_label(3, done[2][2], "9") == "Line 3"


class FakeLayer:
    def __init__(self, source: str, chosen=None) -> None:
        self._source = source
        self._chosen = chosen

    def source(self) -> str:
        return self._source

    def id(self) -> str:
        return "drawn_ab:12"

    def customProperty(self, name):
        assert name == FOLDER_PROPERTY
        return self._chosen


def test_profiles_live_beside_the_layer_or_in_the_folder_chosen(tmp_path) -> None:
    shp = tmp_path / "lines.shp"
    shp.write_bytes(b"x")
    assert profile_folder(FakeLayer(str(shp))) == tmp_path / "lines_profiles"
    assert profile_folder(FakeLayer(f"{shp}|layername=dykes|geometrytype=LineString")) == tmp_path / "lines_dykes_profiles"
    assert profile_folder(FakeLayer(str(shp), str(tmp_path / "mine"))) == tmp_path / "mine"


def test_a_layer_with_no_file_keeps_them_with_the_session() -> None:
    folder = profile_folder(FakeLayer("LineString?crs=EPSG:32640"))
    assert folder.name == "drawn_ab_12"
    assert "wadi2d_profiles" in folder.parts


def test_the_store_finds_a_profile_counts_and_drops_it(tmp_path) -> None:
    shp = tmp_path / "lines.shp"
    shp.write_bytes(b"x")
    layer = FakeLayer(str(shp))
    store = ProfileStore()
    assert store.table(layer, "channel", "3") is None
    assert store.count(layer, "channel") == 0
    path = profile_path(tmp_path / "lines_profiles", "channel", "3")
    write_rows(path, [{"station": 0.0, "bed_z": 1.0}])
    write_rows(profile_path(tmp_path / "lines_profiles", "channel_dyke", "3"), [{"station": 0.0, "bed_z": 1.0}])
    assert store.table(layer, "channel", "3") == str(path)
    assert store.count(layer, "channel") == 1
    store.drop(layer, "channel", "3")
    assert store.table(layer, "channel", "3") is None
    assert path.with_name(path.name + ".dropped").is_file()


def test_a_draft_stands_in_for_one_line_only(tmp_path) -> None:
    layer = FakeLayer(str(tmp_path / "none.shp"))
    store = ProfileStore()
    store.draft = ("channel", "3", "draft.csv")
    assert store.table(layer, "channel", "3") == "draft.csv"
    assert store.table(layer, "channel", "4") is None
    assert store.table(layer, "embankment", "3") is None
