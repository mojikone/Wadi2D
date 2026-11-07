"""Where a dam's pool starts (W34): empty by default, at the spillway crest or at a level by name, one pool only."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from tests.engine.conftest import X0, Y0, job, write_dem
from wadi2d.basin.job import dry_start
from wadi2d.config.schema import DamLevel
from wadi2d.dam_levels import grid_pool_depth, with_dam_starts
from wadi2d.forcing import boundary_set
from wadi2d.hydrology.model import Basin, Reservoir
from wadi2d.hydrology.reservoir import ReservoirOutflowStructures, Spillway
from wadi2d.run import job_hash, prepare_grid, run_job

PIXEL, DX = 2.0, 8.0
NX, NY = 50, 25
"""Cells: 400 m along the valley, 200 m across."""
FALL, SIDE = 0.01, 0.2
"""The valley falls 1 % east; its sides rise 0.2 m per m."""
CREST_X = 200.0
SPILLWAY_Z, CREST_Z = 100.0, 103.0
POOL_M3 = 5.0 * (SPILLWAY_Z - (100.0 - FALL * CREST_X)) ** 3 / (3.0 * FALL)
"""The V behind the dam at the spillway: depth 0.01 x at x m from the west edge, area 5 d2, so 5e-4 x3 / 3."""


def valley(path: Path) -> Path:
    x = (np.arange(NX * DX / PIXEL) + 0.5) * PIXEL
    y = (np.arange(NY * DX / PIXEL) + 0.5) * PIXEL
    z = 100.0 - FALL * x[None, :] + SIDE * np.abs(y[:, None] - NY * DX / 2.0)
    return write_dem(path, z, PIXEL)


def dam_job(dem: Path, **parts):
    across = [(X0 + CREST_X, Y0), (X0 + CREST_X, Y0 - NY * DX)]
    middle = [(X0 + CREST_X, Y0 - NY * DX / 2.0 + 12.0), (X0 + CREST_X, Y0 - NY * DX / 2.0 - 12.0)]
    return job(
        dem, NX, NY, DX,
        terrain={"objects": [
            {"kind": "crest_line", "name": "Dam", "coordinates": across, "z_constant": CREST_Z},
            {"kind": "spillway", "name": "Spill", "coordinates": middle, "z_constant": SPILLWAY_Z},
        ]},
        boundaries=[{"kind": "free", "coordinates": [(X0 + NX * DX - 4.0, Y0), (X0 + NX * DX - 4.0, Y0 - NY * DX)]}],
        run={"duration_s": 30.0},
        **parts,
    )  # fmt: skip


@pytest.fixture
def dem(tmp_path: Path) -> Path:
    return valley(tmp_path / "valley.tif")


def pool_of(cfg, tmp_path: Path) -> tuple[np.ndarray, list[str], object]:
    tables, _crs = prepare_grid(cfg, tmp_path / "cache")
    bset = boundary_set(cfg.boundaries, tables, cfg.grid.line_samples)
    depth, notes = grid_pool_depth(cfg, tables, bset.mask, {})
    return depth, notes, tables


def test_a_dam_starts_empty_unless_named_and_takes_a_word_or_a_level() -> None:
    assert DamLevel(name="Dam").start == "empty"
    assert DamLevel(name="Dam", start="spillway").start == "spillway"
    assert DamLevel(name="Dam", start=101.5).start == 101.5
    with pytest.raises(ValidationError):
        DamLevel(name="Dam", start="full")


def test_an_old_job_keeps_its_hash_and_a_start_level_changes_it(dem) -> None:
    plain = dam_job(dem)
    assert "dam_levels" not in plain.model_fields_set
    named = dam_job(dem, dam_levels=[{"name": "Dam", "start": "spillway"}])
    assert job_hash(dam_job(dem, dam_levels=[])) == job_hash(plain) != job_hash(named)


def test_the_grid_pool_fills_behind_the_dam_to_the_spillway_and_not_below_it(dem, tmp_path) -> None:
    cfg = dam_job(dem, dam_levels=[{"name": "Dam", "start": "spillway"}])
    depth, notes, tables = pool_of(cfg, tmp_path)
    jj, ii = np.nonzero(depth > 0.0)
    x, _y = tables.grid.xy_of(jj, ii)
    assert np.asarray(x).max() < X0 + CREST_X, "nothing below the dam"
    volume = float(depth.sum()) * DX * DX
    assert volume == pytest.approx(POOL_M3, rel=0.08)
    assert any("starts at 100 m" in note for note in notes)


def test_a_run_starts_with_that_water_and_an_empty_dam_with_none(dem, tmp_path) -> None:
    point = {"points": [{"name": "Pool", "x": X0 + CREST_X - 30.0, "y": Y0 - NY * DX / 2.0}]}
    full = run_job(dam_job(dem, dam_levels=[{"name": "Dam", "start": "spillway"}], outputs=point), tmp_path / "full")
    empty = run_job(dam_job(dem, dam_levels=[{"name": "Dam", "start": "empty"}]), tmp_path / "empty")
    unnamed = run_job(dam_job(dem), tmp_path / "unnamed")
    assert full.exit_code == empty.exit_code == unnamed.exit_code == 0, (full.message, empty.message)
    assert full.balance.storage0 == pytest.approx(POOL_M3, rel=0.08)
    assert empty.balance.storage0 == unnamed.balance.storage0 == 0.0
    assert abs(full.balance.relative) < 1e-6
    rows = np.loadtxt(tmp_path / "full" / "series" / "point_Pool.csv", delimiter=",", skiprows=1, ndmin=2)
    assert rows[0, 3] == pytest.approx(SPILLWAY_Z, abs=0.02), "the level stands at the spillway crest"


def test_a_level_over_the_crest_or_an_unknown_name_is_refused_in_words(dem, tmp_path) -> None:
    over = run_job(dam_job(dem, dam_levels=[{"name": "Dam", "start": CREST_Z + 20.0}]), tmp_path / "over")
    assert over.exit_code != 0 and "open boundary" in over.message
    unknown = run_job(dam_job(dem, dam_levels=[{"name": "Nowhere", "start": "spillway"}]), tmp_path / "unknown")
    assert unknown.exit_code != 0 and "Nowhere" in unknown.message


def basin_with(initial: float) -> Basin:
    routing = ReservoirOutflowStructures(
        elevations_m=np.array([90.0, 95.0, 100.0, 105.0]),
        areas_m2=np.array([0.0, 1e4, 4e4, 9e4]),
        spillways=(Spillway(101.0, 20.0, 1.7), Spillway(99.5, 5.0, 1.7)),
        initial_elevation_m=initial,
    )
    return Basin("b", [Reservoir(name="Dam", downstream=None, routing=routing)])


@pytest.mark.parametrize(("start", "level"), [("empty", 90.0), ("spillway", 99.5), (97.25, 97.25)])
def test_a_lumped_reservoir_takes_the_start_by_name(start, level) -> None:
    basin = basin_with(100.0)
    taken = with_dam_starts(basin, [DamLevel(name="Dam", start=start), DamLevel(name="Other", start="spillway")])
    assert taken == {"Dam": level}
    assert basin.elements["Dam"].routing.initial_elevation_m == level


def test_a_lumped_start_off_the_table_is_refused() -> None:
    with pytest.raises(ValueError, match="off its table"):
        with_dam_starts(basin_with(100.0), [DamLevel(name="Dam", start=120.0)])


def test_a_derived_start_is_the_empty_pool_and_a_given_one_stays() -> None:
    def reservoir(value: float, source: str) -> dict:
        return {
            "kind": "reservoir",
            "name": "Dam",
            "parameters": {
                "elevation_m": {"value": [86.96, 90.0, 100.0], "source": "terrain"},
                "initial_elevation_m": {"value": value, "source": source},
            },
        }

    model = dry_start({"elements": [reservoir(100.0, "derived"), reservoir(95.0, "user")]})
    assert [e["parameters"]["initial_elevation_m"]["value"] for e in model["elements"]] == [86.96, 95.0]
