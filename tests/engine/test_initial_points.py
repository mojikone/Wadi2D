"""A level set from a point: the cells under it joined to the point's cell start full (W96)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from tests.engine.conftest import X0, Y0
from tests.engine.test_dam_levels import CREST_X, DX, NY, POOL_M3, SPILLWAY_Z, dam_job, pool_of, valley
from wadi2d.dam_levels import point_pool_depth
from wadi2d.run import job_hash, prepare_grid, run_job

BEHIND = (X0 + CREST_X - 60.0, Y0 - NY * DX / 2.0)
"""On the valley's floor, 60 m behind the dam."""


@pytest.fixture
def dem(tmp_path: Path) -> Path:
    return valley(tmp_path / "valley.tif")


def _point(level: float, at=BEHIND, name: str | None = "Pool") -> dict:
    return {"name": name, "x": at[0], "y": at[1], "level": level}


def test_a_point_behind_the_dam_fills_the_same_pool_as_the_dams_own_start(dem, tmp_path) -> None:
    by_dam, _notes, _tables = pool_of(dam_job(dem, dam_levels=[{"name": "Dam", "start": "spillway"}]), tmp_path / "a")
    cfg = dam_job(dem, initial_points=[_point(SPILLWAY_Z)])
    tables, _crs = prepare_grid(cfg, tmp_path / "b")
    by_point, notes = point_pool_depth(cfg, tables)
    np.testing.assert_array_equal(by_point, by_dam)
    assert float(by_point.sum()) * DX * DX == pytest.approx(POOL_M3, rel=0.08)
    assert notes and notes[0].startswith("Pool: the water starts at 100 m")


def test_a_run_starts_with_the_points_water_and_keeps_its_books(dem, tmp_path) -> None:
    run = run_job(dam_job(dem, initial_points=[_point(SPILLWAY_Z)]), tmp_path / "run")
    assert run.exit_code == 0, run.message
    assert run.balance.storage0 == pytest.approx(POOL_M3, rel=0.08)
    assert abs(run.balance.relative) < 1e-6


def test_a_point_on_dry_ground_or_off_the_domain_is_refused_in_words(dem, tmp_path) -> None:
    high = run_job(dam_job(dem, initial_points=[_point(90.0)]), tmp_path / "high")
    assert high.exit_code == 2 and "stands above the level 90 m" in high.message
    away = run_job(dam_job(dem, initial_points=[_point(100.0, at=(X0 - 500.0, Y0), name=None)]), tmp_path / "away")
    assert away.exit_code == 2 and "Initial point 1" in away.message and "no square cell" in away.message


def test_a_job_without_points_keeps_its_hash(dem) -> None:
    plain = dam_job(dem)
    assert job_hash(dam_job(dem, initial_points=[])) == job_hash(plain) != job_hash(dam_job(dem, initial_points=[_point(100.0)]))
