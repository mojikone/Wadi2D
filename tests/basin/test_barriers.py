"""Walls and burn lines in the delineation (W73), by hand counts on a plane falling due south.

On that plane every pixel drains to the pixel below it, so a column carries its own pixels and nothing else: the count
at a row is the row number plus one, and any change is the object's.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from tests.basin.conftest import BED_NORTH, BED_SLOPE, NX, NY, PIXEL, col_x, row_y, write_job, write_raster
from wadi2d.basin.barriers import ground_edits
from wadi2d.basin.build import assemble
from wadi2d.basin.delineate import flow_surface, read_surface
from wadi2d.config.schema import BasinSettings, TerrainObject
from wadi2d.run import job_hash, load_job

SETTINGS = BasinSettings(stream_threshold_km2=0.5, snap_m=30.0, min_reach_m=0.0, min_subbasin_km2=0.0)
WALL_ROW, WALL_WEST, WALL_EAST = 100, 50, 150


def plane() -> np.ndarray:
    rows, _cols = np.mgrid[0:NY, 0:NX]
    return BED_NORTH + (NY - rows) * PIXEL * BED_SLOPE


def counts(tmp_path: Path, objects: list[dict]) -> tuple[np.ndarray, list[str]]:
    dem = write_raster(tmp_path / "plane.tif", plane())
    cfg = load_job(write_job(tmp_path, dem, terrain={"objects": objects}))
    z, pixel, x0, y0, crs = read_surface(cfg, SETTINGS)
    notes: list[str] = []
    surface = flow_surface(z, pixel, x0, y0, crs, ground_edits(cfg, z, pixel, x0, y0, SETTINGS, notes))
    return surface.count.reshape(surface.shape), notes


def wall(**extra) -> dict:
    line = [[col_x(WALL_WEST), row_y(WALL_ROW)], [col_x(WALL_EAST), row_y(WALL_ROW)]]
    return {"kind": "wall", "name": "W1", "coordinates": line, **extra}


def test_the_plane_carries_each_column_alone(tmp_path: Path) -> None:
    count, notes = counts(tmp_path, [])
    assert np.array_equal(count[:, 100], np.arange(1, NY + 1))
    assert notes == []


def test_a_wall_sends_the_water_above_it_round_its_ends(tmp_path: Path) -> None:
    count, notes = counts(tmp_path, [wall()])
    below = WALL_ROW + 1
    span = slice(WALL_WEST, WALL_EAST + 1)
    # under the wall a pixel holds itself and the wall pixel above it: 2, against 102 on the plain plane
    assert np.all(count[below, span] == 2)
    # every path still crosses the row once: what the wall holds back passes round its two ends
    assert count[below].sum() == (below + 1) * NX
    outside = count[below, :WALL_WEST].sum() + count[below, WALL_EAST + 1 :].sum()
    assert outside == (below + 1) * NX - 2 * (WALL_EAST - WALL_WEST + 1)
    assert any("W1" in note for note in notes)


def test_a_wall_ticked_off_changes_nothing(tmp_path: Path) -> None:
    count, notes = counts(tmp_path, [wall(delineate=False)])
    assert np.array_equal(count[:, 100], np.arange(1, NY + 1))
    assert notes == []


def test_a_burn_line_captures_the_columns_it_crosses(tmp_path: Path) -> None:
    # from (row 50, col 100) down to (row 150, col 50): column c meets it at row 50 + 2 (100 - c)
    line = [[col_x(100), row_y(50)], [col_x(50), row_y(150)]]
    count, _notes = counts(tmp_path, [{"kind": "burn_line", "name": "B1", "coordinates": line, "depth": 5.0}])
    above = sum(50 + 2 * (100 - c) for c in range(50, 101))
    end = count[145:156, 45:56].max()
    assert end >= above  # everything north of the line in its 51 columns runs down it
    # the column under the middle of the line keeps only what lies below the line: rows 101 to 299, a 2-pixel cut aside
    assert count[NY - 1, 75] <= NY - 100 + 3
    assert count[NY - 1, 75] < NY


def test_a_burn_wins_where_it_crosses_a_wall(tmp_path: Path) -> None:
    line = [[col_x(100), row_y(60)], [col_x(100), row_y(140)]]
    burn = {"kind": "burn_line", "name": "B1", "coordinates": line, "depth": 5.0}
    count, _notes = counts(tmp_path, [wall(), burn])
    # the water of the burn's own column passes the wall through the cut
    assert count[WALL_ROW + 1 : WALL_ROW + 40, 99:102].max() > WALL_ROW


def test_a_ring_wall_lets_nothing_in(tmp_path: Path) -> None:
    ring = [[col_x(c), row_y(r)] for r, c in ((80, 80), (80, 120), (120, 120), (120, 80), (80, 80))]
    count, _notes = counts(tmp_path, [{"kind": "wall", "name": "Ring", "coordinates": ring}])
    inside = count[82:119, 82:119]
    assert inside.max() <= 41 * 41  # the ring's interior and its own wall pixels at most
    # what lies north of the ring goes round it: the row below it carries all of its columns
    assert count[123].sum() == 124 * NX


def test_delineate_leaves_the_job_hash_alone(tmp_path: Path) -> None:
    dem = write_raster(tmp_path / "plane.tif", plane())
    plain = load_job(write_job(tmp_path, dem, terrain={"objects": [wall()]}))
    ticked = load_job(write_job(tmp_path, dem, terrain={"objects": [wall(delineate=False)]}))
    assert job_hash(plain) == job_hash(ticked)


def test_the_default_tick_by_kind() -> None:
    line = [(0.0, 0.0), (10.0, 0.0)]
    assert TerrainObject(kind="wall", coordinates=line).delineates
    assert TerrainObject(kind="burn_line", coordinates=line, depth=1.0).delineates
    assert not TerrainObject(kind="crest_line", coordinates=line, z_constant=5.0).delineates
    assert TerrainObject(kind="crest_line", coordinates=line, z_constant=5.0, delineate=True).delineates
    assert not TerrainObject(kind="spillway", coordinates=line, z_constant=5.0, delineate=True).delineates


def test_the_generator_reports_what_it_applied(tmp_path: Path) -> None:
    dem = write_raster(tmp_path / "plane.tif", plane())
    model = assemble(load_job(write_job(tmp_path, dem, terrain={"objects": [wall()]})), SETTINGS).model
    assert any(note.startswith("delineated with W1") for note in model["notes"])


@pytest.mark.parametrize("kind", ["crest_line"])
def test_a_ticked_crest_line_stands_as_a_wall_at_its_level(tmp_path: Path, kind: str) -> None:
    # a level 100 m above the plane all along: the same as the plain wall
    count, _notes = counts(tmp_path, [wall(kind=kind, z_constant=BED_NORTH + 200.0, delineate=True)])
    assert np.all(count[WALL_ROW + 1, WALL_WEST : WALL_EAST + 1] == 2)
