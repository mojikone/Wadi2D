"""Each check says one plain sentence, and a clean design says nothing."""

from __future__ import annotations

import numpy as np

from tests.terrain.helpers import GROUND, flat_bed, grid_of, obj
from wadi2d.config.schema import Terrain
from wadi2d.tables import ArrayBed
from wadi2d.terrain import Ground
from wadi2d.terrain.checks import terrain_notes

SOUTH = [(160.0, 300.0), (160.0, 20.0)]
WIDE = {"width": 40.0, "left_slope": 2.0, "right_slope": 2.0}


def said(objects, bed=None, dx=10.0, pixel=1.0, cfg=None):
    grid = grid_of()
    ground = Ground(bed or flat_bed(), grid.x0, grid.y0)
    bounds = (grid.x0, grid.y0 - grid.shape[0] * dx, grid.x0 + grid.shape[1] * dx, grid.y0)
    return " ".join(terrain_notes(objects, ground, dx, pixel, cfg or Terrain(), bounds))


def channel(**fields):
    fields.setdefault("z", [99.0, 98.0])
    fields.setdefault("section", WIDE)
    fields.setdefault("start_end", "taper")
    fields.setdefault("end_end", "taper")
    return obj("channel", SOUTH, name="C", **fields)


def test_a_clean_channel_says_nothing():
    assert said([channel()]) == ""


def test_a_bed_above_the_ground_for_a_long_reach():
    text = said([channel(z=[101.0, 101.0])])
    assert "C: the bed is above the ground for 280 m from station 0 to 280, by up to 1.0 m" in text
    assert "nothing is cut there" in text


def test_a_short_rise_above_the_ground_is_let_pass():
    grid = grid_of()
    z = flat_bed().z.copy()
    row = round(grid.y0 - 160.0)
    z[row - 10 : row + 10, :] = 97.0
    assert "above the ground" not in said([channel()], ArrayBed(z, 1.0))


def test_an_adverse_slope():
    text = said([channel(z=[98.0, 99.0])])
    assert "adverse slope, the bed rises 1.00 m from station 0 to 280" in text
    assert "station 0 is its first vertex" in text


def test_a_level_bed_is_not_adverse():
    assert "adverse" not in said([channel(z=[98.0, 98.0])])


def test_a_table_that_stops_short_or_runs_past_the_line():
    short = {**WIDE, "rows": [{"station": 0.0, "bed_z": 99.0}, {"station": 200.0, "bed_z": 98.0}]}
    long = {**WIDE, "rows": [{"station": 0.0, "bed_z": 99.0}, {"station": 400.0, "bed_z": 98.0}]}
    assert "stops at station 200 of 280 m" in said([channel(z=None, section=short)])
    assert "runs to station 400, but the line is only 280 m" in said([channel(z=None, section=long)])


def test_a_step_between_two_stations():
    section = {
        **WIDE,
        "rows": [
            {"station": 0.0, "bed_z": 99.0}, {"station": 100.0, "bed_z": 98.9}, {"station": 101.0, "bed_z": 97.0},
            {"station": 280.0, "bed_z": 96.5},
        ],
    }  # fmt: skip
    assert "the bed changes 1.90 m in 1.0 m at station 100, which is a step" in said([channel(z=None, section=section)])


def test_a_bottom_finer_than_the_dem():
    assert "bottom width of 2.0 m is finer than the DEM can show at 5 m pixels" in said(
        [channel(section={"width": 2.0})], pixel=5.0
    )


def test_a_channel_too_narrow_for_the_cells():
    text = said([channel(section={"width": 8.0, "left_slope": 2.0, "right_slope": 2.0})])
    assert "between the banks" in text
    assert "under 3 cells of 10 m" in text


def test_a_dyke_with_nothing_to_tie_into():
    bank = obj("embankment", SOUTH, z_constant=103.0, name="D", section={"width": 4.0})
    text = said([bank])
    assert "D: it ends at station 0 standing 3.0 m above the ground, with nothing to tie into" in text
    assert "D: it ends at station 280" in text


def test_a_dyke_tied_to_a_dam_or_high_ground_says_nothing():
    grid = grid_of()
    z = flat_bed().z.copy()
    z[: round(grid.y0 - 250.0), :] = 110.0
    z[round(grid.y0 - 50.0) :, :] = 110.0
    bank = obj("embankment", SOUTH, z_constant=103.0, name="D", section={"width": 4.0})
    assert said([bank], ArrayBed(z, 1.0)) == ""
    dam = obj("crest_line", [(40.0, 21.0), (280.0, 21.0)], z_constant=105.0)
    assert "ends at station 280" not in said([bank, dam])


def test_a_channel_dyke_names_the_bank():
    section = {"width": 40.0, "left_top_z": 102.0, "right_top_z": 99.5}
    dyke = obj("channel_dyke", SOUTH, z_constant=99.0, name="M", section=section, start_end="taper", end_end="taper")
    open_ended = obj("channel_dyke", SOUTH, z_constant=99.0, name="M", section=section)
    assert "the left dyke" not in said([dyke])
    text = said([open_ended])
    assert "M: the left dyke ends at station 0 standing 2.0 m" in text
    assert "the right dyke" not in text


def test_a_channel_cut_in_with_a_square_end():
    text = said([channel(z=[97.0, 96.0], start_end="open", end_end="open")])
    assert "C: its start is cut 3.0 m below the ground with a square face" in text
    assert "C: its end is cut 4.0 m below the ground" in text


def test_a_closed_end_is_not_a_square_face():
    assert "square face" not in said([channel(z=[97.0, 96.0], start_end="closed", end_end="closed")])


def test_an_opening_past_the_end_or_narrower_than_a_cell():
    bank = obj(
        "embankment", SOUTH, z_constant=103.0, name="D", section={"width": 4.0},
        openings=[{"start": 400.0, "end": 420.0}, {"start": 100.0, "end": 105.0}],
    )  # fmt: skip
    text = said([bank])
    assert "the opening at station 400 lies past the end of the line" in text
    assert "the opening at station 100 is narrower than one 10 m cell" in text


def test_a_line_leaving_the_grid():
    wide = [(160.0, 900.0), (160.0, 20.0)]
    assert "part of the line lies outside the grid" in said([obj("channel", wide, z=[99.0, 98.0], name="C", section=WIDE)])


def test_ground_above_the_top_needs_no_dyke_warning():
    grid = grid_of()
    z = flat_bed(GROUND + 5.0).z
    assert "tie" not in said([obj("embankment", SOUTH, z_constant=103.0, section={"width": 4.0})], ArrayBed(z, 1.0))
    assert np.isfinite(grid.dx)
