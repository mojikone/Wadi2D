# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The points of a profile, without Qt: drag, type, undo, and what cannot be built."""

from __future__ import annotations

import pytest
from wadi2d_qgis.profile_model import ProfileModel
from wadi2d_qgis.profile_table import BED, CREST, LEFT, RIGHT, Seed


def channel() -> ProfileModel:
    return ProfileModel(Seed({BED: [(0.0, 100.0), (500.0, 95.0), (1000.0, 90.0)]}), 1000.0)


def dyke() -> ProfileModel:
    tops = [(0.0, 104.0), (500.0, 100.0), (1000.0, 96.0)]
    return ProfileModel(Seed({BED: [(0.0, 100.0), (1000.0, 90.0)], LEFT: list(tops), RIGHT: list(tops)}), 1000.0)


def drag(model: ProfileModel, key: str, index: int, station: float, level: float) -> None:
    model.begin()
    model.drag(key, index, station, level)
    model.end()


def test_a_drag_moves_one_point() -> None:
    model = channel()
    drag(model, BED, 1, 400.0, 93.0)
    assert model.points[BED] == [[0.0, 100.0], [400.0, 93.0], [1000.0, 90.0]]


def test_a_point_stops_short_of_its_neighbours() -> None:
    model = channel()
    drag(model, BED, 1, 5000.0, 93.0)
    assert model.points[BED][1][0] == 999.99
    drag(model, BED, 1, -50.0, 93.0)
    assert model.points[BED][1][0] == 0.01


def test_the_ends_of_the_line_keep_their_stations() -> None:
    model = channel()
    drag(model, BED, 0, 200.0, 101.0)
    drag(model, BED, 2, 800.0, 89.0)
    assert model.points[BED][0] == [0.0, 101.0]
    assert model.points[BED][2] == [1000.0, 89.0]


def test_one_drag_is_one_undo_however_many_moves_it_made() -> None:
    model = channel()
    model.begin()
    for level in (94.0, 93.0, 92.0):
        model.drag(BED, 1, 500.0, level)
    model.end()
    assert model.undo()
    assert model.points[BED][1] == [500.0, 95.0]
    assert not model.can_undo


def test_a_press_and_release_with_no_move_leaves_no_undo() -> None:
    model = channel()
    model.begin()
    model.end()
    assert not model.can_undo


def test_redo_comes_back_and_a_new_edit_clears_it() -> None:
    model = channel()
    drag(model, BED, 1, 500.0, 93.0)
    model.undo()
    assert model.can_redo
    assert model.redo()
    assert model.points[BED][1] == [500.0, 93.0]
    model.undo()
    drag(model, BED, 1, 500.0, 92.0)
    assert not model.can_redo
    assert not model.redo()


def test_dirty_follows_undo_and_save() -> None:
    model = channel()
    assert not model.dirty
    drag(model, BED, 1, 500.0, 93.0)
    assert model.dirty
    model.undo()
    assert not model.dirty
    model.redo()
    model.mark_saved()
    assert not model.dirty


def test_a_new_point_goes_in_order_and_on_a_station_it_sets_the_level() -> None:
    model = channel()
    assert model.add(BED, 250.0, 97.0) == 1
    assert [point[0] for point in model.points[BED]] == [0.0, 250.0, 500.0, 1000.0]
    assert model.add(BED, 500.0, 94.0) == 2
    assert len(model.points[BED]) == 4
    assert model.points[BED][2] == [500.0, 94.0]


def test_a_series_keeps_one_point() -> None:
    model = ProfileModel(Seed({BED: [(0.0, 1.0)]}), 10.0)
    assert "at least one point" in model.remove(BED, 0)
    assert model.points[BED] == [[0.0, 1.0]]


def test_the_table_is_the_union_of_the_stations_with_blanks() -> None:
    assert dyke().rows()[1] == {"station": 500.0, BED: None, LEFT: 100.0, RIGHT: 100.0}


def test_other_columns_stay_with_their_stations() -> None:
    model = ProfileModel(Seed({BED: [(0.0, 1.0)]}, {0.0: {"width": 3.0}, 70.0: {"width": 9.0}}), 100.0)
    assert model.rows() == [
        {"station": 0.0, BED: 1.0, "width": 3.0},
        {"station": 70.0, BED: None, "width": 9.0},
    ]


def test_a_new_row_takes_the_levels_already_there() -> None:
    model = dyke()
    assert model.add_station(250.0) == ""
    assert model.rows()[1] == {"station": 250.0, BED: 97.5, LEFT: 102.0, RIGHT: 102.0}


@pytest.mark.parametrize("station, words", [(-1.0, "cannot be negative"), (500.0, "already in the table")])
def test_a_bad_new_row_is_refused(station, words) -> None:
    assert words in dyke().add_station(station)


def test_a_typed_station_moves_the_row() -> None:
    model = dyke()
    assert model.move_station(500.0, 600.0) == ""
    assert model.rows()[1]["station"] == 600.0
    assert model.points[LEFT][1] == [600.0, 100.0]


@pytest.mark.parametrize("station, words", [(-1.0, "cannot be negative"), (1000.0, "already in the table")])
def test_a_bad_typed_station_is_refused_and_nothing_moves(station, words) -> None:
    model = dyke()
    assert words in model.move_station(500.0, station)
    assert model.points[LEFT][1] == [500.0, 100.0]


def test_a_typed_station_can_pass_its_neighbour() -> None:
    model = channel()
    model.add_station(700.0)
    model.move_station(700.0, 300.0)
    assert [point[0] for point in model.points[BED]] == [0.0, 300.0, 500.0, 1000.0]


def test_a_blank_cell_takes_the_point_away_and_a_number_sets_it() -> None:
    model = dyke()
    assert model.set_level(LEFT, 500.0, None) == ""
    assert model.at(LEFT, 500.0) is None
    assert model.level(LEFT, 500.0) == 100.0
    assert model.set_level(LEFT, 500.0, 101.0) == ""
    assert model.points[LEFT][1] == [500.0, 101.0]


def test_a_row_goes_only_if_every_series_keeps_a_point() -> None:
    model = dyke()
    assert model.remove_station(500.0) == ""
    assert model.stations() == [0.0, 1000.0]
    lone = ProfileModel(Seed({BED: [(0.0, 1.0)], LEFT: [(0.0, 2.0), (9.0, 2.0)]}), 10.0)
    assert "at least one point" in lone.remove_station(0.0)
    assert lone.points[LEFT][0] == [0.0, 2.0]


def test_tops_together_move_add_and_go_as_one() -> None:
    model = dyke()
    model.tied = True
    drag(model, LEFT, 1, 450.0, 99.0)
    assert model.points[RIGHT][1] == [450.0, 99.0]
    model.add(RIGHT, 700.0, 98.0)
    assert model.at(LEFT, 700.0) == 2
    model.remove(LEFT, 2)
    assert model.at(RIGHT, 700.0) is None


def test_apart_the_tops_move_alone() -> None:
    model = dyke()
    drag(model, LEFT, 1, 500.0, 99.0)
    assert model.points[RIGHT][1] == [500.0, 100.0]


def test_a_tied_point_with_no_mate_moves_alone() -> None:
    model = dyke()
    model.add(LEFT, 700.0, 98.0)
    model.tied = True
    drag(model, LEFT, 2, 700.0, 97.0)
    assert model.points[LEFT][2] == [700.0, 97.0]
    assert model.at(RIGHT, 700.0) is None


def test_both_tops_alike_is_seen() -> None:
    model = dyke()
    assert model.tops_alike()
    drag(model, LEFT, 1, 500.0, 99.0)
    assert not model.tops_alike()
    assert not channel().tops_alike()


def test_a_top_under_the_bed_is_said_with_its_station() -> None:
    model = dyke()
    assert model.problems() == []
    drag(model, RIGHT, 1, 500.0, 90.0)
    assert model.problems() == ["The right top is below the bed at station 500."]


def test_a_top_under_the_bed_between_points_is_found_too() -> None:
    model = ProfileModel(
        Seed({BED: [(0.0, 10.0), (50.0, 20.0), (100.0, 10.0)], LEFT: [(0.0, 15.0), (100.0, 15.0)]}), 100.0
    )
    assert model.problems() == ["The left top is below the bed at station 50."]


def test_a_series_with_no_points_is_said() -> None:
    assert ProfileModel(Seed({BED: []}), 10.0).problems() == ["The bed has no points."]


def test_a_kind_with_no_bed_has_nothing_to_be_under() -> None:
    assert ProfileModel(Seed({CREST: [(0.0, 1.0)]}), 10.0).problems() == []


def test_the_limit_is_the_line_or_a_table_that_runs_past_it() -> None:
    assert channel().limit == 1000.0
    assert ProfileModel(Seed({BED: [(0.0, 1.0), (1500.0, 2.0)]}), 1000.0).limit == 1500.0


def test_a_named_label_is_used_in_the_words() -> None:
    model = ProfileModel(Seed({CREST: []}), 10.0, {CREST: "invert"})
    assert model.problems() == ["The invert has no points."]
