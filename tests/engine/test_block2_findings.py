"""What the whole-catchment validation on Block 2 found missing or silent."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from tests.engine.conftest import X0, Y0, job, write_dem
from wadi2d.forcing import initial_depth
from wadi2d.grid import TileGrid
from wadi2d.io.cache import builder_identity
from wadi2d.run import edge_ponding, prepare_grid, run_job
from wadi2d.solver.state import level_field


def bowl(tmp_path, n: int = 64, res: float = 5.0):
    """A square pit 4 m deep with vertical sides, in flat ground at 10 m."""
    z = np.full((n, n), 10.0)
    z[20:44, 20:44] = 6.0
    return write_dem(tmp_path / "bowl.tif", z, res), n * res


def ring(a: float, b: float) -> list[tuple[float, float]]:
    return [(X0 + a, Y0 - a), (X0 + b, Y0 - a), (X0 + b, Y0 - b), (X0 + a, Y0 - b)]


def events(folder) -> list[dict]:
    return [json.loads(line) for line in (folder / "progress.jsonl").read_text().splitlines()]


def test_an_initial_level_fills_the_pit_and_stays_still(tmp_path):
    dem, side = bowl(tmp_path)
    cfg = job(
        dem, 32, 32, 10.0,
        initial_levels=[{"coordinates": ring(0.0, side), "level": 9.0}],
        run={"duration_s": 300.0},
    )  # fmt: skip
    out = tmp_path / "run"
    summary = run_job(cfg, out, "cpu")
    assert summary.exit_code == 0
    done = events(out)[-1]
    # 24 pixels of 5 m by 3 m of water
    assert done["balance"]["storage_start_m3"] == pytest.approx((24 * 5.0) ** 2 * 3.0, rel=1e-3)
    assert done["balance"]["storage_end_m3"] == pytest.approx(done["balance"]["storage_start_m3"], rel=1e-5)


def test_the_initial_depth_returns_the_level_through_the_table(tmp_path):
    dem, side = bowl(tmp_path)
    cfg = job(dem, 32, 32, 10.0, initial_levels=[{"coordinates": ring(0.0, side), "level": 9.0}])
    tables, _ = prepare_grid(cfg, tmp_path / "cache")
    h = initial_depth(cfg.initial_levels, tables)
    wet = h > 0.0
    assert wet.any()
    level = level_field(tables, h) + tables.zmin
    assert np.abs(level[wet] - 9.0).max() < 1e-3


def test_an_initial_level_below_the_ground_is_refused(tmp_path):
    dem, side = bowl(tmp_path)
    cfg = job(
        dem, 32, 32, 10.0,
        initial_levels=[{"coordinates": ring(0.0, side), "level": 2.0}],
        run={"duration_s": 60.0},
    )  # fmt: skip
    summary = run_job(cfg, tmp_path / "run", "cpu")
    assert summary.exit_code != 0
    assert "datum" in summary.message


def test_a_changed_table_builder_is_a_different_grid(tmp_path):
    root = tmp_path / "pkg"
    (root / "tables").mkdir(parents=True)
    source = root / "tables" / "builder.py"
    source.write_text("a = 1\n")
    before = builder_identity(root)
    assert builder_identity(root) == before
    source.write_text("a = 2\n")
    assert builder_identity(root) != before


def test_the_real_builder_has_sources():
    assert builder_identity() != builder_identity(Path("no such folder"))


def box_grid(n: int = 64, slit: bool = False) -> TileGrid:
    mask = np.zeros((n, n), bool)
    mask[4:60, 4:60] = True
    if slit:
        mask[30, 4:60] = False
    return TileGrid.from_mask(mask, 0.0, 0.0, 20.0)


def test_water_behind_a_slit_in_the_domain_is_found():
    grid = box_grid(slit=True)
    depth = np.zeros(grid.shape)
    j, _ = np.nonzero(grid.mask)
    below_slit = np.nonzero(~grid.mask[:, grid.mask.shape[1] // 2])[0]
    row = int(below_slit[(below_slit > j.min()) & (below_slit < j.max())][0]) + 1
    depth[row, grid.mask.shape[1] // 2] = 53.0
    deep, _x, _y = edge_ponding(grid, depth, np.zeros(grid.shape, bool))
    assert deep == 53.0


def test_water_at_a_boundary_is_not_a_closed_edge():
    grid = box_grid()
    depth = np.zeros(grid.shape)
    j, i = np.nonzero(grid.mask)
    depth[j.min(), i.min() + 20] = 9.0
    open_cells = np.zeros(grid.shape, bool)
    open_cells[j.min(), i.min() + 20] = True
    assert edge_ponding(grid, depth, open_cells)[0] == 0.0
    assert edge_ponding(grid, depth, np.zeros(grid.shape, bool))[0] == 9.0
