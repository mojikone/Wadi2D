"""``terrain.pit_check`` and ``terrain.fill_pits`` through whole runs (W85): the warning and the layer, the fill as
terrain objects of the resolved job, the step with and without the pit, the balance, and old jobs left as they were.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest
import rasterio

from tests.engine.conftest import X0, Y0, write_dem
from tests.engine.test_run import full_job, valley
from wadi2d.config.schema import PIT_FILL_NAME, RunConfig
from wadi2d.run import job_hash, prepare_grid, run_job
from wadi2d.terrain.pits import FILE, LAYER

DEEP = 12.0
"""A hole 4 m by 8 m and this deep beside the thalweg, a pixel column either side of a cell face."""
PIT_X, PIT_Y = X0 + 256.0, Y0 - 188.0
DURATION = 1800.0


@pytest.fixture
def pit_dem(tmp_path: Path) -> Path:
    z = valley(256, 192, 2.0)
    z[92:96, 127:129] -= DEEP
    return write_dem(tmp_path / "pit.tif", z, 2.0)


@pytest.fixture
def plain_dem(tmp_path: Path) -> Path:
    return write_dem(tmp_path / "plain.tif", valley(256, 192, 2.0), 2.0)


def job(dem: Path, **terrain) -> RunConfig:
    cfg = full_job(dem, "cpu", duration=DURATION)
    return cfg.model_copy(update={"terrain": cfg.terrain.model_copy(update=terrain)})


def events(out: Path, kind: str) -> list[dict]:
    lines = (out / "progress.jsonl").read_text(encoding="utf-8").splitlines()
    return [e for e in map(json.loads, lines) if e["ev"] == kind]


def warned(out: Path, words: str) -> list[str]:
    return [e["message"] for e in events(out, "warn") if words in e["message"]]


def test_the_check_names_the_pit_and_filling_it_lengthens_the_step(pit_dem, tmp_path):
    off, on = tmp_path / "off", tmp_path / "on"
    left, filled = run_job(job(pit_dem), off), run_job(job(pit_dem, fill_pits=True), on)
    assert left.exit_code == 0 and filled.exit_code == 0, (left.message, filled.message)

    # the check: one pit, named with where it is, how deep and how large, in the warnings and in the layer
    (note,) = warned(off, "a pit in the ground")
    assert f"({PIT_X - 4.0:.0f}, {PIT_Y:.0f})" in note or f"({PIT_X + 4.0:.0f}, {PIT_Y:.0f})" in note
    assert "can leave over no face" in note and "in 2 cells" in note
    assert warned(off, "tick Fill pits")
    with sqlite3.connect(off / FILE) as db:
        ((depth, area, cells, was_filled),) = db.execute(
            f'SELECT depth_m, area_m2, cells, filled FROM "{LAYER}"'
        ).fetchall()
    assert depth == pytest.approx(DEEP, abs=0.5) and area < 2 * 64.0 and cells == 2 and was_filled == 0
    (made,) = [e for e in events(off, "output") if e.get("kind") == "terrain_pits"]
    assert made["pits"] == 1 and made["filled"] is False

    # the fill: the same pit, now two fill objects of the job as it ran, and none of it left in the tables
    assert warned(on, "filled to its spill level") and warned(on, "1 pits filled")
    assert not warned(on, "are left after the fill")
    ran = RunConfig.model_validate_json((on / "config.resolved.json").read_text(encoding="utf-8"))
    fills = [o for o in ran.terrain.objects if o.name.startswith(PIT_FILL_NAME)]
    assert len(fills) == 2 and ran.terrain.fill_pits
    plain = RunConfig.model_validate_json((off / "config.resolved.json").read_text(encoding="utf-8"))
    assert plain.terrain.objects == []

    # the step: the pit under water asks for a shorter one; without it the run takes fewer steps
    assert filled.steps < 0.8 * left.steps
    assert filled.dt_min > left.dt_min
    for summary in (left, filled):
        assert abs(summary.balance.relative) < 1e-6
    # the pit held water back; filled, that water leaves, and nothing else is gained or lost
    assert filled.balance.rain == pytest.approx(left.balance.rain, rel=1e-9)
    assert filled.balance.outflow > left.balance.outflow
    assert filled.balance.outflow - left.balance.outflow < 4.0 * 8.0 * DEEP * 1.2

    # the pixel maps take the filled ground: no pixel of the run with the fill reads the hole's depth
    for folder, deepest in ((off, DEEP - 1.0), (on, 3.0)):
        with rasterio.open(next((folder / "pixels").glob("*depth*.tif"))) as src:
            a = src.read(1, masked=True)
        assert (float(a.max()) > deepest) == (folder is off)


def test_the_ground_away_from_the_pit_is_the_same_to_the_digit(pit_dem, tmp_path):
    cache = tmp_path / "cache"
    left, _crs = prepare_grid(job(pit_dem), cache)
    ran = run_job(
        job(pit_dem, fill_pits=True).model_copy(
            update={"run": job(pit_dem).run.model_copy(update={"duration_s": 60.0})}
        ),
        tmp_path / "on",
    )
    assert ran.exit_code == 0, ran.message
    cfg = RunConfig.model_validate_json(
        (tmp_path / "on" / "config.resolved.json").read_text(encoding="utf-8")
    )
    filled, _crs = prepare_grid(cfg, cache)
    grid = left.grid
    j, i = grid.cell_of(PIT_X, PIT_Y)
    away = np.ones(grid.shape, bool)
    away[j, i - 1 : i + 1] = False
    assert np.array_equal(left.zmin[away], filled.zmin[away]) and np.array_equal(
        left.zbar[away], filled.zbar[away]
    )
    for name in ("hc", "dtab"):
        assert np.array_equal(
            grid.from_tiles(getattr(left, name))[away], grid.from_tiles(getattr(filled, name))[away]
        )
    assert np.all(filled.zmin[j, i - 1 : i + 1] > left.zmin[j, i - 1 : i + 1] + DEEP - 1.0)


def test_a_job_without_the_fill_keeps_its_hash_and_one_with_it_is_one_job_before_and_after(pit_dem, tmp_path):
    plain = job(pit_dem)
    assert job_hash(plain) == job_hash(job(pit_dem, pit_check=False))
    assert job_hash(plain) == job_hash(
        job(pit_dem, pit_max_cells=7.0, pit_min_depth=1.0)
    )  # read only when filling
    asked = job(pit_dem, fill_pits=True)
    assert job_hash(asked) != job_hash(plain)
    assert job_hash(asked) != job_hash(job(pit_dem, fill_pits=True, pit_min_depth=1.0))
    out = tmp_path / "on"
    short = asked.model_copy(update={"run": asked.run.model_copy(update={"duration_s": 60.0})})
    assert run_job(short, out).exit_code == 0
    ran = RunConfig.model_validate_json((out / "config.resolved.json").read_text(encoding="utf-8"))
    assert len(ran.terrain.objects) == 2 and job_hash(ran) == job_hash(short)
    # the resolved job run again is the same job: its fills are found again, not doubled
    again = tmp_path / "again"
    assert run_job(ran, again).exit_code == 0
    twice = RunConfig.model_validate_json((again / "config.resolved.json").read_text(encoding="utf-8"))
    assert twice.terrain.objects == ran.terrain.objects


def test_ground_with_no_pit_says_nothing_and_runs_as_before(plain_dem, tmp_path):
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    for out, terrain in ((a, {}), (b, {"pit_check": False}), (c, {"fill_pits": True})):
        assert run_job(job(plain_dem, **terrain), out).exit_code == 0
        assert not warned(out, "pit") and not (out / FILE).exists()
        assert not [e for e in events(out, "output") if e.get("kind") == "terrain_pits"]
    for name in ("max_depth", "max_speed"):
        with rasterio.open(a / "maps" / f"{name}.tif") as first:
            want = first.read(1)
        for out in (b, c):
            with rasterio.open(out / "maps" / f"{name}.tif") as other:
                assert np.array_equal(want, other.read(1)), (name, out.name)
