"""Sleeping tiles through ``run_job`` (W90): a job with a real corridor (the mesher's aligned rows and the polygons
round them, not squares) and an inflow at its head on dry ground gives, with tiles asleep, the series, the strip's
depths and the maps of the same job with every tile stepped at every step, and most of its tiles sleep."""

from __future__ import annotations

import json

import numpy as np
import pytest
import rasterio

from tests.engine.conftest import X0, Y0, job, tilted_box, write_dem
from tests.engine.test_resume_exact import series
from tests.engine.test_strips_run import _strip_depths
from wadi2d.config.schema import Inflow
from wadi2d.run import run_job
from wadi2d.solver import model as model_module

NX, NY, DX = 256, 96, 4.0
MID_Y = Y0 - 0.5 * NY * DX


def long_job(dem):
    """1,024 x 384 m at 4 m, 36 tiles with the padding: a corridor down the middle, 2 m3/s into its head for ten
    minutes, no rain, a free edge at the low end."""
    cfg = job(
        dem, NX, NY, DX,
        boundaries=[{"kind": "free", "coordinates": [(X0 + NX * DX - 3.0, Y0 + 2.0), (X0 + NX * DX - 3.0, Y0 - NY * DX - 2.0)]}],
        outputs={"lines": [{"name": "across", "coordinates": [(X0 + 400.0, Y0 - 100.0), (X0 + 400.0, Y0 - 284.0)]}], "series_every_s": 10.0},
        run={"duration_s": 1500.0, "backend": "cpu", "source_every_s": 10.0},
        strips={
            "enabled": True,
            "corridors": [{"name": "mid", "centre": [(X0 + 40.0, MID_Y), (X0 + 800.0, MID_Y)], "offsets": [-12.0, -8.0, -4.0, 0.0, 4.0, 8.0, 12.0]}],
        },
    )  # fmt: skip
    point = Inflow(name="in", x=X0 + 60.0, y=MID_Y, times_s=[0.0, 600.0, 601.0, 1500.0], flows=[2.0, 2.0, 0.0, 0.0])
    return cfg.model_copy(update={"hydrology": cfg.hydrology.model_copy(update={"inflows": [point], "inject_radius": 6.0})})


def awake(out) -> list[int]:
    rows = (json.loads(s) for s in (out / "progress.jsonl").read_text(encoding="utf-8").splitlines())
    return [int(r["active_tiles"]) for r in rows if r.get("ev") == "step"]


def test_a_job_with_a_corridor_on_dry_ground_sleeps_and_is_the_all_tiles_run(tmp_path, monkeypatch) -> None:
    dem = write_dem(tmp_path / "long.tif", tilted_box(2 * NX, 2 * NY, 2.0, 0.01), 2.0)
    cfg = long_job(dem)
    asleep = run_job(cfg, tmp_path / "asleep")
    make = model_module.make_stepper

    def every_tile(backend, grid, num):
        stepper = make(backend, grid, num)
        stepper.adaptive_active = False
        return stepper

    with monkeypatch.context() as patch:
        patch.setattr(model_module, "make_stepper", every_tile)
        whole = run_job(cfg, tmp_path / "whole")
    assert asleep.exit_code == 0 and whole.exit_code == 0, (asleep.message, whole.message)
    (tiles,) = set(awake(tmp_path / "whole"))  # every tile at every step
    slept = awake(tmp_path / "asleep")
    assert tiles == 36 and min(slept) < max(slept) < tiles, (min(slept), max(slept))
    assert asleep.steps == whole.steps
    assert asleep.balance.inflow == pytest.approx(1200.0, rel=0.01)
    assert series(tmp_path / "asleep") == series(tmp_path / "whole")
    assert _strip_depths(tmp_path / "asleep") == _strip_depths(tmp_path / "whole")
    for name in ("inflow", "outflow", "storage"):
        assert getattr(asleep.balance, name) == getattr(whole.balance, name), name
    for name in ("max_depth.tif", "max_speed.tif"):
        with rasterio.open(tmp_path / "asleep" / "maps" / name) as a, rasterio.open(tmp_path / "whole" / "maps" / name) as b:
            assert np.array_equal(a.read(1), b.read(1)), name
