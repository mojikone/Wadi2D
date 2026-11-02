"""The cell grid on the map is the grid the solver stepped, edge for edge, on a uniform grid and on a mesh."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest
import shapely

from tests.engine.conftest import job, tilted_box, write_dem
from wadi2d.grid.quad import QuadGrid
from wadi2d.grid.tiles import TileGrid
from wadi2d.products.cell_grid import (
    CELL_GRID_FILE,
    CELL_GRID_LAYER,
    cell_grid_layer,
    tile_lines,
    write_cell_grid,
)
from wadi2d.run import run_job
from wadi2d.solver.layout import TILE

DX = 5.0


def edge_length(cells: np.ndarray) -> int:
    """Edges that touch an active cell, counted by hand, in cell sides."""
    wide = np.pad(cells, 1)
    return int((wide[:, :-1] | wide[:, 1:]).sum() + (wide[:-1, :] | wide[1:, :]).sum())


def test_a_full_tile_is_its_lines_and_nothing_else() -> None:
    lines = tile_lines(np.ones((TILE, TILE), bool))
    assert lines.shape == (2 * (TILE + 1), 2, 2)
    assert np.abs(lines[:, 1] - lines[:, 0]).sum() == 2 * (TILE + 1) * TILE


@pytest.mark.parametrize("seed", range(4))
def test_any_tile_draws_exactly_the_edges_of_its_cells(seed: int) -> None:
    cells = np.random.default_rng(seed).random((TILE, TILE)) > 0.5
    assert np.abs(tile_lines(cells)[:, 1] - tile_lines(cells)[:, 0]).sum() == edge_length(cells)


def test_a_cell_outside_the_domain_has_no_lines_of_its_own() -> None:
    cells = np.ones((TILE, TILE), bool)
    cells[:, 10:] = False
    lines = tile_lines(cells)
    assert lines[..., 0].max() == 10.0  # the edge of the last cell stays, nothing east of it


def test_a_uniform_grid_comes_out_where_the_solver_has_it() -> None:
    mask = np.zeros((70, 70), bool)
    mask[3:60, 5:64] = True
    grid = TileGrid.from_mask(mask, 1000.0, 2000.0, DX)
    layer = cell_grid_layer(grid)
    assert len(layer.rows) == grid.ntiles - 1
    assert sum(row[2] for row in layer.rows) == int(mask.sum())
    assert {row[0] for row in layer.rows} == {DX}
    box = shapely.total_bounds(layer.geometries)
    jj, ii = np.nonzero(grid.mask)
    assert box[0] == grid.x0 + ii.min() * DX
    assert box[2] == grid.x0 + (ii.max() + 1) * DX
    assert box[3] == grid.y0 - jj.min() * DX
    assert box[1] == grid.y0 - (jj.max() + 1) * DX


def test_a_mesh_shows_each_tile_at_its_own_size() -> None:
    mask = np.ones((TILE * 4, TILE * 4), bool)
    level = np.array([[0, 1], [1, 2]], np.int32)
    grid = QuadGrid.from_levels(mask, 0.0, TILE * 4 * DX, DX, level)
    layer = cell_grid_layer(grid)
    assert sum(row[2] for row in layer.rows) == grid.cell_count
    assert {row[0] for row in layer.rows} == {float(v) for v in grid.tile_dx[1:]}
    assert {row[1] for row in layer.rows} == {int(v) for v in grid.level[1:]}
    for (size, _, _), shape in zip(layer.rows, layer.geometries, strict=True):
        assert shapely.length(shape) == pytest.approx(2 * (TILE + 1) * TILE * size)


def test_the_full_extent_stays_small() -> None:
    """17 M cells: the reason this is lines per tile and not a polygon per cell."""
    grid = TileGrid.from_mask(np.ones((4126, 4126), bool), 0.0, 0.0, 30.0)
    layer = cell_grid_layer(grid)
    assert len(layer.rows) == grid.ntiles - 1 < 18_000


def test_every_run_writes_it(tmp_path: Path) -> None:
    dem = write_dem(tmp_path / "dem.tif", tilted_box(40, 40, 5.0, 0.01), 5.0)
    cfg = job(dem, 40, 40, 5.0, outputs={"pixels": {"enabled": False}})
    assert run_job(cfg, tmp_path / "run").exit_code == 0
    with sqlite3.connect(tmp_path / "run" / CELL_GRID_FILE) as db:
        rows = db.execute(f"SELECT cell_m, cells FROM {CELL_GRID_LAYER}").fetchall()
    assert {row[0] for row in rows} == {5.0}
    assert sum(row[1] for row in rows) > 0


def test_a_failed_drawing_costs_a_warning_and_not_the_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_):
        raise OSError("disk full")

    monkeypatch.setattr("wadi2d.run.write_cell_grid", broken)
    dem = write_dem(tmp_path / "dem.tif", tilted_box(40, 40, 5.0, 0.01), 5.0)
    cfg = job(dem, 40, 40, 5.0)
    assert run_job(cfg, tmp_path / "run").exit_code == 0
    text = (tmp_path / "run" / "progress.jsonl").read_text(encoding="utf-8")
    assert "The cell grid layer could not be written: disk full" in text


def test_it_can_be_written_with_no_crs(tmp_path: Path) -> None:
    grid = TileGrid.from_mask(np.ones((40, 40), bool), 0.0, 0.0, DX)
    assert write_cell_grid(grid, "", tmp_path).is_file()
