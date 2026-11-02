"""Local time stepping through the whole engine: the balance with a boundary, the maxima, a stop and a resume."""

from __future__ import annotations

import threading
import time

import h5py
import numpy as np
import pytest

from tests.engine.test_run import full_job, valley_dem  # noqa: F401  (a fixture)
from wadi2d.config.schema import RunConfig
from wadi2d.run import run_job


def with_levels(cfg: RunConfig, **numerics) -> RunConfig:
    data = cfg.model_dump(mode="json")
    data["numerics"].update({"local_time_stepping": True, **numerics})
    return RunConfig.model_validate(data)


@pytest.mark.parametrize("backend", ["cpu", pytest.param("gpu", marks=pytest.mark.gpu)])
def test_levels_match_the_uniform_run_through_the_engine(valley_dem, tmp_path, backend):  # noqa: F811
    plain = run_job(full_job(valley_dem, backend, 900.0), tmp_path / "plain")
    level = run_job(with_levels(full_job(valley_dem, backend, 900.0)), tmp_path / "level")
    assert level.exit_code == 0
    assert abs(level.balance.relative) < 1e-5
    # the uniform engine itself moves 14 % on this sheet between a step of 1.2 s and 0.05 s: a longer step is the cause here
    assert level.balance.outflow == pytest.approx(plain.balance.outflow, rel=0.02)
    assert level.peaks["Cross"][0] == pytest.approx(plain.peaks["Cross"][0], rel=0.02)
    with (
        h5py.File(tmp_path / "plain" / "results.h5", "r") as f,
        h5py.File(tmp_path / "level" / "results.h5", "r") as g,
    ):
        a, b = f["maxima/depth"][()], g["maxima/depth"][()]
    assert np.abs(a - b).max() < 0.1


def test_a_stopped_run_with_levels_resumes(valley_dem, tmp_path):  # noqa: F811
    out = tmp_path / "run"
    cfg = with_levels(full_job(valley_dem, "cpu", 2400.0))

    def stop_soon() -> None:
        while not (out / "results.h5").exists():
            time.sleep(0.02)
        time.sleep(0.3)
        (out / "stop").touch()

    thread = threading.Thread(target=stop_soon, daemon=True)
    thread.start()
    summary = run_job(cfg, out)
    thread.join()
    assert summary.exit_code == 6
    done = run_job(cfg, out, resume=True)
    assert done.exit_code == 0
    assert done.t_end == pytest.approx(2400.0)
    assert abs(done.balance.relative) < 2e-3
