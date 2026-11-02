# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A saved profile from the file to the ground the engine builds, through the job builder as it stands."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from wadi2d_qgis.job_builder import Feature, build_job, write_job
from wadi2d_qgis.profile_table import BED, CREST, LEFT, RIGHT, apply_levels, with_levels, write_rows
from wadi2d_qgis.shaped import TABLE

from tests.engine.conftest import X0, Y0, write_dem
from wadi2d.config.schema import TerrainObject
from wadi2d.grid.tiles import TileGrid
from wadi2d.run import load_job, prepare_grid
from wadi2d.terrain.crest import line_lengths, staircase
from wadi2d.terrain.objects import apply_objects
from wadi2d.terrain.sections import build_profile, with_tables

LINE = [[X0 + 10.0, Y0 - 40.0], [X0 + 70.0, Y0 - 40.0]]


def values(tmp_path: Path, dem: Path, structures: dict) -> dict:
    return {
        "dem": str(dem), "crs": "EPSG:32640", "geographic": False, "pixel": 2.0, "dx": 8.0,
        "extent": (X0, Y0 - 96.0, X0 + 96.0, Y0), "manning": 0.035, "rain_mm_h": 25.0, "rain_hours": 1.0,
        "structures": structures, "boundaries": [], "design": [], "output": str(tmp_path / "out"), "duration_h": 2.0,
    }  # fmt: skip


def ground_with(tmp_path: Path, name: str, table: Path | None, tmp_dem: Path) -> np.ndarray:
    """The job the dock would write for one channel, read back by the engine: the lowest ground in each cell."""
    feature = Feature("LineString", LINE, {"crest_z": 99.0, "width": 8.0, TABLE: str(table) if table else None})
    out = tmp_path / name
    job = build_job(values(tmp_path, tmp_dem, {"channel": [feature]}), out)
    grid, _ = prepare_grid(load_job(write_job(job, out)), tmp_path / "cache")
    return grid.zmin


@pytest.fixture
def dem(tmp_path: Path) -> Path:
    return write_dem(tmp_path / "d.tif", np.full((48, 48), 100.0), 2.0)


def test_a_saved_profile_reaches_the_job_by_the_table_route_and_moves_the_ground(tmp_path, dem) -> None:
    saved = write_rows(tmp_path / "lines_profiles" / "channel_line_0.csv", [
        {"station": 0.0, BED: 97.0}, {"station": 60.0, BED: 96.0},
    ])  # fmt: skip
    before = ground_with(tmp_path, "fields", None, dem)
    after = ground_with(tmp_path, "edited", saved, dem)
    assert before[before > -1e6].min() == pytest.approx(99.0)
    assert after[after > -1e6].min() == pytest.approx(96.0, abs=0.2)

    job = json.loads((tmp_path / "edited" / "job.json").read_text(encoding="utf-8"))
    section = job["terrain"]["objects"][0]["section"]
    copied = Path(section["table"])
    assert copied.parent == (tmp_path / "edited" / "inputs").resolve()
    assert copied.read_text(encoding="utf-8") == saved.read_text(encoding="utf-8")
    assert "rows" not in section


def test_the_job_of_a_line_with_no_profile_names_no_table(tmp_path, dem) -> None:
    feature = Feature("LineString", LINE, {"crest_z": 99.0, TABLE: None})
    job = build_job(values(tmp_path, dem, {"channel": [feature]}), tmp_path / "out")
    assert "table" not in job["terrain"]["objects"][0]["section"]


def test_a_saved_top_outranks_the_field_of_a_channel_with_dykes(tmp_path, dem) -> None:
    saved = write_rows(tmp_path / "p.csv", [
        {"station": 0.0, BED: 97.0, LEFT: 103.0, RIGHT: 104.0}, {"station": 60.0, BED: 96.0, LEFT: 102.0, RIGHT: 101.0},
    ])  # fmt: skip
    feature = Feature("LineString", LINE, {"crest_z": 90.0, "top_z": 110.0, TABLE: str(saved)})
    job = build_job(values(tmp_path, dem, {"channel_dyke": [feature]}), tmp_path / "out")
    written = write_job(job, tmp_path / "out")
    cfg = with_tables(load_job(written))
    profile = build_profile(cfg.terrain.objects[0], 60.0)
    assert profile.bed.tolist() == [97.0, 96.0]
    assert profile.top[0].tolist() == [103.0, 102.0]
    assert profile.top[1].tolist() == [104.0, 101.0]


def test_a_crest_line_takes_a_profile_as_z_on_its_vertices_in_the_job(tmp_path, dem) -> None:
    table = write_rows(tmp_path / "p.csv", [{"station": 0.0, CREST: 102.0}, {"station": 30.0, CREST: 101.0}, {"station": 60.0, CREST: 103.0}])
    feature = apply_levels(Feature("LineString", LINE, {"crest_z": 50.0}), str(table))
    job = build_job(values(tmp_path, dem, {"crest_line": [feature]}), tmp_path / "out")
    entry = job["terrain"]["objects"][0]
    assert entry["z"] == [102.0, 101.0, 103.0]
    assert "z_constant" not in entry
    assert entry["coordinates"][1] == [X0 + 40.0, Y0 - 40.0]
    assert TerrainObject(**entry).z == [102.0, 101.0, 103.0]
    assert json.loads((tmp_path / "out" / "inputs" / "crest_line.geojson").read_text(encoding="utf-8"))


GRID_DX = 20.0


def grid() -> TileGrid:
    mask = np.ones((64, 64), bool)
    return TileGrid.from_mask(mask, 0.0, 1280.0, GRID_DX)


DIAGONAL = [[105.0, 130.0], [1105.0, 910.0]]


def test_on_its_vertices_a_profile_moves_no_face() -> None:
    plain = staircase(grid(), DIAGONAL)
    table = with_levels(DIAGONAL, [(0.0, 10.0), (float(line_lengths(DIAGONAL)[-1]), 12.0)])
    same = staircase(grid(), [point[:2] for point in table])
    assert np.array_equal(plain.corners, same.corners)


def furthest_corner(st, line) -> float:
    """How far the staircase strays from the true line, m."""
    a, b = np.array(line[0]), np.array(line[1])
    along = (b - a) / np.linalg.norm(b - a)
    x = grid().x0 + st.corners[:, 1] * GRID_DX - a[0]
    y = grid().y0 - st.corners[:, 0] * GRID_DX - a[1]
    return float(np.abs(x * along[1] - y * along[0]).max())


@pytest.mark.parametrize("share", [0.05, 0.25, 0.37, 0.5, 0.75, 0.95])
def test_a_point_between_vertices_keeps_the_length_and_shifts_the_faces_under_half_a_cell(share) -> None:
    length = float(line_lengths(DIAGONAL)[-1])
    table = with_levels(DIAGONAL, [(0.0, 10.0), (share * length, 11.0), (length, 12.0)])
    coordinates = [point[:2] for point in table]
    assert len(coordinates) == 3
    plain, forced = staircase(grid(), DIAGONAL), staircase(grid(), coordinates)
    assert forced.factor.sum() == pytest.approx(plain.factor.sum())
    assert float(line_lengths(coordinates)[-1]) == pytest.approx(length)
    assert furthest_corner(forced, DIAGONAL) <= furthest_corner(plain, DIAGONAL) + 0.5 * GRID_DX


def test_a_spillway_length_is_the_same_with_a_point_between_its_vertices() -> None:
    length = float(line_lengths(LINE)[-1])
    coordinates = [p[:2] for p in with_levels(LINE, [(0.0, 10.0), (20.0, 9.0), (length, 10.0)])]
    assert float(line_lengths(coordinates)[-1]) == pytest.approx(length)


def test_the_grid_cache_keeps_edits_apart(tmp_path, dem) -> None:
    first = write_rows(tmp_path / "a.csv", [{"station": 0.0, BED: 97.0}, {"station": 60.0, BED: 96.0}])
    second = write_rows(tmp_path / "b.csv", [{"station": 0.0, BED: 97.0}, {"station": 60.0, BED: 95.0}])
    ground_with(tmp_path, "one", first, dem)
    ground_with(tmp_path, "two", second, dem)
    assert len(list((tmp_path / "cache").glob("grid_*.h5"))) == 2


def test_apply_objects_builds_a_crest_line_with_a_profile() -> None:
    entry = {"kind": "crest_line", "coordinates": [[100.0, 640.0], [500.0, 640.0], [900.0, 640.0]], "z": [10.0, 12.0, 11.0]}
    edits = apply_objects(grid(), [TerrainObject(**entry)], 2.0)
    faces = edits.crest.yz[~np.isnan(edits.crest.yz)]
    assert faces.min() >= 10.0
    assert faces.max() <= 12.0
    assert faces.max() - faces.min() > 1.0
