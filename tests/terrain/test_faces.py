"""Where a shaped object stands as a line of crest faces, and where it must not."""

from __future__ import annotations

import numpy as np
import pytest

from tests.terrain.helpers import GROUND, flat_bed, grid_of, obj
from wadi2d.config.schema import Terrain
from wadi2d.tables import ArrayBed
from wadi2d.terrain import Ground, apply_objects
from wadi2d.terrain.earthworks import Shape

NORTH_SOUTH = [(160.0, 300.0), (160.0, 20.0)]
CFG = Terrain()


def ground_of(bed):
    grid = grid_of()
    return Ground(bed, grid.x0, grid.y0)


def faces(objects, bed=None):
    grid = grid_of()
    bed = bed or flat_bed()
    return apply_objects(grid, objects, 1.0, CFG, ground_of(bed)).crest, grid


def test_an_embankment_gets_a_crest_line_along_its_axis():
    bank = obj("embankment", NORTH_SOUTH, z_constant=103.0, section={"width": 4.0})
    crest, grid = faces([bank])
    column = round((160.0 - grid.x0) / grid.dx)
    assert np.nanmax(crest.xz) == 103.0
    assert (crest.xz[:, column] == 103.0).sum() == 28
    assert np.isnan(np.delete(crest.xz, column, axis=1)).all()


def test_an_embankment_buried_by_the_ground_has_no_faces():
    bank = obj("embankment", NORTH_SOUTH, z_constant=99.0, section={"width": 4.0})
    crest, _ = faces([bank])
    assert np.isnan(crest.xz).all()


def test_a_crest_line_stops_at_an_opening():
    bank = obj(
        "embankment",
        NORTH_SOUTH,
        z_constant=103.0,
        section={"width": 4.0},
        openings=[{"start": 100.0, "end": 160.0}],
    )
    crest, grid = faces([bank])
    column = round((160.0 - grid.x0) / grid.dx)
    raised = np.flatnonzero(crest.xz[:, column] == 103.0)
    gap_top = round((grid.y0 - 200.0) / grid.dx)
    gap_bottom = round((grid.y0 - 140.0) / grid.dx)
    assert not ((raised >= gap_top) & (raised < gap_bottom)).any()
    assert (raised < gap_top).any()
    assert (raised >= gap_bottom).any()


def test_each_bank_of_a_channel_gets_its_own_line_where_it_stands_as_a_dyke():
    section = {"width": 20.0, "crest_z": 102.0, "left_slope": 2.0, "right_slope": 2.0}
    crest, grid = faces([obj("channel_dyke", NORTH_SOUTH, z_constant=99.0, section=section)])
    # crest edge at 10 + 2 * 3 = 16, middle of a 3 m crest at 17.5, which snaps to 20 m off the line
    columns = sorted({int(i) for i in np.nonzero(crest.xz == 102.0)[1]})
    assert [grid.x0 + c * grid.dx for c in columns] == [140.0, 180.0]


def test_a_bank_in_cut_has_no_line():
    section = {"width": 20.0, "left_top_z": 99.5, "right_top_z": 102.0, "left_crest_width": 2.0}
    crest, grid = faces([obj("channel_dyke", NORTH_SOUTH, z_constant=99.0, section=section)])
    columns = {grid.x0 + int(c) * grid.dx for c in np.nonzero(crest.xz == 102.0)[1]}
    assert columns == {140.0}
    assert not np.any(crest.xz == 99.5)


def test_a_dyke_line_stops_where_the_ground_rises_past_its_top_and_runs_on_a_cell_into_it():
    grid = grid_of()
    ny, nx = grid.shape[0] * 10, grid.shape[1] * 10
    y = grid.y0 - (np.arange(ny) + 0.5)
    bed = ArrayBed(np.tile((GROUND + (160.0 - y) * 0.02)[:, None], (1, nx)), 1.0)
    section = {"width": 20.0, "crest_z": 100.0, "left_top_z": 100.0, "right_top_z": 100.0}
    shape = Shape.of(obj("channel_dyke", NORTH_SOUTH, z_constant=97.0, section=section))
    runs = shape.crest_runs(grid.dx, CFG, ground_of(bed))
    assert len(runs) == 2
    # ground passes 100 - 0.05 at y = 162.5; one 10 m cell of overlap beyond that
    assert runs[0].coordinates[-1, 1] == pytest.approx(152.5, abs=5.0)


def test_the_two_banks_never_join_across_the_channel():
    section = {"width": 10.0, "crest_z": 102.0}
    crest, _grid = faces([obj("channel_dyke", NORTH_SOUTH, z_constant=99.0, section=section)])
    # no face runs east-west across the channel at its ends
    assert np.isnan(crest.yz).all()


def test_a_short_gap_between_two_stretches_stays_open():
    section = {"width": 20.0, "crest_z": 102.0}
    dyke = obj(
        "channel_dyke",
        NORTH_SOUTH,
        z_constant=99.0,
        section=section,
        openings=[{"start": 100.0, "end": 120.0}],
    )
    crest, grid = faces([dyke])
    row = round((grid.y0 - 190.0) // grid.dx)
    assert np.isnan(crest.xz[row]).all()


def test_a_dyke_end_ties_to_a_dam_it_meets():
    dam = obj("crest_line", [(40.0, 21.0), (280.0, 21.0)], z_constant=105.0)
    bank = obj("embankment", [(160.0, 300.0), (160.0, 34.0)], z_constant=103.0, section={"width": 4.0})
    crest, grid = faces([dam, bank])
    column = round((160.0 - grid.x0) / grid.dx)
    dam_row = round((grid.y0 - 21.0) / grid.dx)
    assert crest.xz[dam_row - 1, column] == 103.0


def test_a_spillway_on_an_embankment_takes_the_fill_out_of_its_pixels_and_keeps_its_faces():
    bank = obj("embankment", NORTH_SOUTH, z_constant=103.0, section={"width": 6.0})
    spill = obj("spillway", [(160.0, 200.0), (160.0, 120.0)], z_constant=101.0, coefficient=2.1)
    grid = grid_of()
    bed = flat_bed()
    edits = apply_objects(grid, [bank, spill], 1.0, CFG, ground_of(bed))
    z = bed.z.copy()
    edits.edit(z, 0, 0)
    row = round(grid.y0 - 160.5)
    col = round(160.5 - grid.x0)
    assert z[row, col] == GROUND
    assert z[round(grid.y0 - 260.5), col] == 103.0
    column = round((160.0 - grid.x0) / grid.dx)
    assert 101.0 in crest_values(edits.crest.xz[:, column])
    assert 103.0 in crest_values(edits.crest.xz[:, column])


def crest_values(values):
    return set(values[~np.isnan(values)].tolist())


def test_a_closed_channel_end_is_closed_by_a_line_across_it():
    section = {"width": 20.0, "crest_z": 102.0}
    crest, _ = faces([obj("channel_dyke", NORTH_SOUTH, z_constant=99.0, section=section, end_end="closed")])
    assert np.any(crest.yz == 102.0)


def test_a_tapered_dyke_end_comes_down_to_the_ground():
    bank = obj(
        "embankment",
        NORTH_SOUTH,
        z_constant=103.0,
        section={"width": 4.0},
        end_end="taper",
        taper_length=100.0,
    )
    crest, grid = faces([bank])
    column = round((160.0 - grid.x0) / grid.dx)
    values = crest.xz[:, column]
    known = values[~np.isnan(values)]
    assert known.max() == 103.0
    assert known.min() < 101.0


def test_a_crest_line_keeps_off_the_channel_round_a_tight_bend():
    # the inside bank's offset line would loop back past the corner: none of its faces may cross the channel
    line = [(60.0, 200.0), (200.0, 200.0), (200.0, 60.0)]
    section = {"width": 30.0, "crest_z": 102.0, "left_slope": 2.0, "right_slope": 2.0}
    shape = Shape.of(obj("channel_dyke", line, z_constant=99.0, section=section))
    inside = next(run for run in shape.crest_runs(10.0, CFG, None) if run.side == "right")
    x, y = inside.coordinates.T
    assert shape.line.distance(x, y).min() >= 21.0 - 5.0
    assert np.hypot(*np.diff(inside.coordinates, axis=0).T).max() < 40.0


def test_without_a_ground_every_stretch_counts_as_standing():
    bank = obj("embankment", NORTH_SOUTH, z_constant=99.0, section={"width": 4.0})
    crest = apply_objects(grid_of(), [bank], 1.0, CFG).crest
    assert np.nanmax(crest.xz) == 99.0
