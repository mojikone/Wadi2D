"""Exact pixels against hand numbers. Lines run south, so the right bank is west and the left bank east."""

from __future__ import annotations

import math

import numpy as np
import pytest

from tests.terrain.helpers import GROUND, at, edited, flat_bed, grid_of, obj
from wadi2d.config.schema import TerrainObject
from wadi2d.tables import ArrayBed
from wadi2d.terrain.alignment import Alignment
from wadi2d.terrain.earthworks import Shape

SOUTH = [(160.0, 300.0), (160.0, 20.0)]
Y = 160.5


def across(z, grid, xs):
    return [at(z, grid, x, Y) for x in xs]


def test_a_cut_section_pixel_by_pixel():
    # bed 98, 4 m bottom, right slope 3 (west), left slope 2 (east), ground 100
    channel = obj(
        "channel", SOUTH, z_constant=98.0, section={"width": 4.0, "left_slope": 2.0, "right_slope": 3.0}
    )
    z, grid = edited([channel])
    xs = [150.5, 152.5, 153.5, 155.5, 157.5, 159.5, 160.5, 162.5, 164.5, 166.5]
    # west: 98 + (a - 2) / 3, daylight at a = 8; east: 98 + (a - 2) / 2, daylight at a = 6
    expected = [100.0, 99.8333, 99.5, 98.8333, 98.1667, 98.0, 98.0, 98.25, 99.25, 100.0]
    assert across(z, grid, xs) == pytest.approx(expected, abs=1e-3)


def test_a_fill_section_pixel_by_pixel():
    # crest 103, 6 m wide, right slope 3 (west), left slope 2 (east), ground 100
    bank = obj(
        "embankment", SOUTH, z_constant=103.0, section={"width": 6.0, "left_slope": 2.0, "right_slope": 3.0}
    )
    z, grid = edited([bank])
    xs = [147.5, 148.5, 151.5, 156.5, 157.5, 162.5, 163.5, 165.5, 168.5, 169.5]
    # west: 103 - (a - 3) / 3, toe at a = 12; east: 103 - (a - 3) / 2, toe at a = 9
    expected = [100.0, 100.1667, 101.1667, 102.8333, 103.0, 103.0, 102.75, 101.75, 100.25, 100.0]
    assert across(z, grid, xs) == pytest.approx(expected, abs=1e-3)


def test_a_mixed_section_is_dyke_on_one_bank_and_cut_on_the_other():
    # bed 97, 4 m bottom. West bank: top 102, above ground 100, so a dyke. East bank: top 99, below ground, so a cut.
    section = {
        "width": 4.0, "left_slope": 1.0, "right_slope": 2.0, "left_top_z": 99.0, "right_top_z": 102.0,
        "right_crest_width": 3.0, "right_outer_slope": 2.0, "left_crest_width": 2.0, "left_outer_slope": 2.0,
    }  # fmt: skip
    z, grid = edited([obj("channel_dyke", SOUTH, z_constant=97.0, section=section)])
    xs = [
        140.5,
        141.5,
        144.5,
        145.5,
        147.5,
        148.5,
        150.5,
        155.5,
        157.5,
        159.5,
        160.5,
        162.5,
        163.5,
        164.5,
        165.5,
        170.5,
    ]
    # west: inner 97 + (a - 2) / 2 to 102 at a = 12, crest to a = 15, outer 102 - (a - 15) / 2, toe at a = 19
    # east: 97 + (a - 2) up to the ground at a = 5; its top of 99 at a = 4 is below ground, so nothing is built
    expected = [
        100.0,
        100.25,
        101.75,
        102.0,
        102.0,
        101.75,
        100.75,
        98.25,
        97.25,
        97.0,
        97.0,
        97.5,
        98.5,
        99.5,
        100.0,
        100.0,
    ]
    assert across(z, grid, xs) == pytest.approx(expected, abs=1e-3)


def test_a_bank_turns_from_dyke_to_cut_where_the_ground_passes_its_top():
    # the ground rises eastward... along the line: below the top in the north, above it in the south
    grid = grid_of()
    ny, nx = grid.shape[0] * 10, grid.shape[1] * 10
    y = grid.y0 - (np.arange(ny) + 0.5)
    ground = np.tile((GROUND + (160.0 - y) * 0.02)[:, None], (1, nx))
    bed = ArrayBed(ground, 1.0)
    section = {"width": 4.0, "crest_z": 100.0, "left_crest_width": 3.0, "right_crest_width": 3.0}
    z, grid = edited([obj("channel_dyke", SOUTH, z_constant=97.0, section=section)], bed)
    # crest edge at a = 2 + 2 * 3 = 8, so x = 170: north of y = 160 the ground is under 100
    assert at(z, grid, 170.5, 240.5) == pytest.approx(100.0, abs=1e-6)
    south_ground = at(ground, grid, 170.5, 80.5)
    assert south_ground > 101.0
    assert at(z, grid, 180.5, 80.5) == pytest.approx(
        south_ground, abs=1e-6
    )  # cut bank: untouched ground beyond it
    assert at(z, grid, 170.5, 80.5) == pytest.approx(
        97.0 + (10.5 - 2.0) / 2.0, abs=1e-6
    )  # the inner slope, carried up


@pytest.mark.parametrize("angle", [30.0, 45.0, 72.0])
def test_a_section_is_the_same_at_any_angle(angle):
    ux, uy = math.cos(math.radians(angle)), -math.sin(math.radians(angle))
    a = (160.0 - 120.0 * ux, 160.0 - 120.0 * uy)
    b = (160.0 + 120.0 * ux, 160.0 + 120.0 * uy)
    channel = obj(
        "channel", [a, b], z_constant=98.0, section={"width": 4.0, "left_slope": 2.0, "right_slope": 2.0}
    )
    z, grid = edited([channel])
    for offset, expected in ((0.0, 98.0), (1.5, 98.0), (3.0, 98.5), (4.0, 99.0), (5.5, 99.75), (7.0, 100.0)):
        x, y = 160.0 - uy * offset, 160.0 + ux * offset
        row, col = int((grid.y0 - y) // 1.0), int((x - grid.x0) // 1.0)
        px, py = grid.x0 + col + 0.5, grid.y0 - row - 0.5
        along = (px - 160.0) * ux + (py - 160.0) * uy
        true = math.hypot(px - 160.0 - along * ux, py - 160.0 - along * uy)
        hand = min(98.0 + max(true - 2.0, 0.0) / 2.0, 100.0)
        assert z[row, col] == pytest.approx(hand, abs=1e-6), (offset, expected)


def test_values_read_linearly_between_stations_with_no_step():
    rows = [
        {"station": 0.0, "bed_z": 98.0, "width": 4.0, "left_slope": 2.0, "right_slope": 2.0},
        {"station": 280.0, "bed_z": 96.0, "width": 12.0, "left_slope": 4.0, "right_slope": 2.0},
    ]
    shape = Shape.of(obj("channel", SOUTH, section={"rows": rows}))
    mid = shape.profile.at(np.array([70.0]), False)
    assert mid.bed[0] == pytest.approx(97.5)
    assert mid.half[0] == pytest.approx(3.0)
    assert mid.inner[0] == pytest.approx(2.5)
    z, grid = edited([obj("channel", SOUTH, section={"rows": rows})])
    along = np.array([at(z, grid, 160.5, y + 0.5) for y in range(40, 280)])
    assert np.abs(np.diff(along)).max() < 2.0 / 280.0 + 1e-9


def test_openings_take_the_raised_part_out_and_end_in_a_slope():
    bank = obj(
        "embankment", SOUTH, z_constant=103.0, section={"width": 2.0, "left_slope": 2.0, "right_slope": 2.0},
        openings=[{"start": 100.0, "end": 160.0}],
    )  # fmt: skip
    z, grid = edited([bank])
    assert at(z, grid, 160.5, 300.0 - 130.5) == pytest.approx(GROUND)
    # 4 m into the gap the crest has fallen 2 m: a slope, not a cliff
    assert at(z, grid, 160.5, 300.0 - 104.5) == pytest.approx(103.0 - 4.5 / 2.0, abs=1e-6)
    assert at(z, grid, 160.5, 300.0 - 90.5) == pytest.approx(103.0)
    profile = np.array([at(z, grid, 160.5, 300.0 - s - 0.5) for s in range(40, 240)])
    assert np.abs(np.diff(profile)).max() <= 0.5 + 1e-9


def test_an_opening_on_one_bank_leaves_the_other_alone():
    section = {"width": 4.0, "crest_z": 102.0, "left_crest_width": 2.0, "right_crest_width": 2.0}
    dyke = obj(
        "channel_dyke",
        SOUTH,
        z_constant=99.0,
        section=section,
        openings=[{"start": 100.0, "end": 180.0, "side": "left"}],
    )
    z, grid = edited([dyke])
    y = 300.0 - 140.5
    # crest edge at a = 2 + 2 * 3 = 8: the right bank stands at x = 152, the left is gone at x = 168
    assert at(z, grid, 151.5, y) == pytest.approx(102.0)
    assert at(z, grid, 169.5, y) == pytest.approx(GROUND)
    # the left inner slope still cuts down to the bed, and daylights at the ground, a = 4
    assert at(z, grid, 162.5, y) == pytest.approx(99.0 + 0.5 / 2.0, abs=1e-6)
    assert at(z, grid, 164.5, y) == pytest.approx(GROUND)


def test_an_open_channel_end_is_square_and_a_closed_end_wraps_round():
    section = {"width": 4.0, "left_slope": 2.0, "right_slope": 2.0}
    square, grid = edited([obj("channel", SOUTH, z_constant=98.0, section=section)])
    closed, _ = edited([obj("channel", SOUTH, z_constant=98.0, section=section, end_end="closed")])
    past = 20.0 - 2.5  # 2.5 m past the last station
    assert at(square, grid, 160.5, past) == pytest.approx(GROUND)
    assert at(closed, grid, 160.5, past) == pytest.approx(98.0 + 2.5 / 2.0, abs=1e-6)
    assert at(closed, grid, 160.5, 20.0 - 5.5) == pytest.approx(GROUND)


def test_an_embankment_ends_in_a_cone_without_being_asked():
    bank = obj(
        "embankment", SOUTH, z_constant=103.0, section={"width": 4.0, "left_slope": 2.0, "right_slope": 2.0}
    )
    z, grid = edited([bank])
    assert at(z, grid, 160.5, 20.0 - 2.5) == pytest.approx(103.0 - 2.5 / 2.0, abs=1e-6)
    assert at(z, grid, 160.5, 20.0 - 6.5) == pytest.approx(GROUND)


def test_a_tapered_end_fades_to_the_ground():
    channel = obj(
        "channel", SOUTH, z_constant=96.0, section={"width": 4.0}, start_end="taper", taper_length=40.0
    )
    z, grid = edited([channel])
    assert at(z, grid, 160.5, 300.0 - 10.5) == pytest.approx(GROUND - 4.0 * 10.5 / 40.0, abs=1e-6)
    assert at(z, grid, 160.5, 300.0 - 60.5) == pytest.approx(96.0)
    assert at(z, grid, 160.5, 300.0 + 2.5) == pytest.approx(GROUND)


def test_vertical_sides_are_a_wall_of_ground_not_a_division_by_zero():
    channel = obj(
        "channel", SOUTH, z_constant=98.0, section={"width": 4.0, "left_slope": 0.0, "right_slope": 0.0}
    )
    z, grid = edited([channel])
    assert across(z, grid, [156.5, 158.5, 161.5, 163.5]) == [100.0, 98.0, 98.0, 100.0]


def test_a_bend_keeps_its_offset_round_the_outside():
    line = [(60.0, 160.0), (160.0, 160.0), (160.0, 60.0)]
    channel = obj(
        "channel", line, z_constant=98.0, section={"width": 4.0, "left_slope": 2.0, "right_slope": 2.0}
    )
    z, grid = edited([channel])
    # outside of the bend: 4 m out along the diagonal from the vertex
    offset = 4.0 / math.sqrt(2.0)
    assert at(z, grid, 160.0 + offset, 160.0 + offset) == pytest.approx(99.0, abs=0.4)
    assert at(z, grid, 110.5, 160.5) == pytest.approx(98.0)
    assert at(z, grid, 160.5, 110.5) == pytest.approx(98.0)


def test_objects_stack_in_order_so_a_channel_can_pass_through_a_dam():
    across_valley = [(40.0, 160.0), (280.0, 160.0)]
    dam = obj("embankment", across_valley, z_constant=105.0, section={"width": 6.0})
    drain = obj(
        "channel", SOUTH, z_constant=98.0, section={"width": 4.0, "left_slope": 1.0, "right_slope": 1.0}
    )
    z, grid = edited([dam, drain])
    assert at(z, grid, 160.5, 160.5) == pytest.approx(98.0)
    assert at(z, grid, 100.5, 160.5) == pytest.approx(105.0)


def test_station_and_offset_of_a_point():
    line = Alignment([(0.0, 0.0), (100.0, 0.0)])
    at_point = line.locate(np.array([30.0, 30.0, 120.0, -7.0]), np.array([4.0, -3.0, 2.0, -5.0]))
    assert at_point.s.tolist() == [30.0, 30.0, 100.0, 0.0]
    assert at_point.offset.tolist() == [-4.0, 3.0, -2.0, 5.0]  # negative left, looking along the line
    assert at_point.beyond.tolist() == [0.0, 0.0, 20.0, 7.0]


def test_ground_samples_read_the_pixel_under_the_point():
    from wadi2d.terrain import Ground

    grid = grid_of()
    z = np.arange(grid.shape[0] * 10.0)[:, None] + np.arange(grid.shape[1] * 10.0)[None, :] * 1000.0
    ground = Ground(ArrayBed(z, 1.0), grid.x0, grid.y0)
    x = np.array([grid.x0 + 0.5, grid.x0 + 600.5, grid.x0 + 3.2])
    y = np.array([grid.y0 - 0.5, grid.y0 - 2.5, grid.y0 - 600.5])
    assert ground(x, y).tolist() == [0.0, 600002.0, 3600.0]


def test_existing_objects_have_no_section(tmp_path):
    with pytest.raises(ValueError, match="takes no section"):
        TerrainObject(kind="wall", coordinates=SOUTH, section={"width": 4.0})
    assert TerrainObject(kind="wall", coordinates=SOUTH).section is None


def test_a_flat_bed_outside_the_reach_is_untouched():
    bank = obj(
        "embankment", SOUTH, z_constant=103.0, section={"width": 4.0, "left_slope": 2.0, "right_slope": 2.0}
    )
    z, _grid = edited([bank])
    assert (z != flat_bed().z).sum() == pytest.approx(280 * 16 + 60, rel=0.15)
