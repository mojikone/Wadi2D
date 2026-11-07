"""A stopped and resumed run ends where an unbroken run ends, to the last digit (W32 item 4, W33)."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np
import pytest

from tests.engine.test_run import full_job, valley_dem  # noqa: F401
from wadi2d.run import run_job

SOURCE_EVERY_S = 30.0


def stop_once_started(out: Path) -> threading.Thread:
    def stop_soon() -> None:
        while not (out / "results.h5").exists():
            time.sleep(0.02)
        time.sleep(0.3)
        (out / "stop").touch()

    thread = threading.Thread(target=stop_soon, daemon=True)
    thread.start()
    return thread


def series(out: Path) -> dict[str, str]:
    return {path.name: path.read_text(encoding="utf-8") for path in sorted((out / "series").glob("*.csv"))}


@pytest.mark.parametrize("backend", ["cpu", pytest.param("gpu", marks=pytest.mark.gpu)])
def test_a_stop_lands_on_a_source_window_and_the_resumed_run_is_the_unbroken_one(valley_dem, tmp_path, backend):  # noqa: F811
    cfg = full_job(valley_dem, backend, 2400.0)
    cfg = cfg.model_copy(update={"outputs": cfg.outputs.model_copy(update={"progress_every_s": 0.01})})
    out = tmp_path / "broken"
    thread = stop_once_started(out)
    stopped = run_job(cfg, out)
    thread.join()
    assert stopped.exit_code == 6
    assert 0.0 < stopped.t_end < 2400.0
    assert stopped.t_end / SOURCE_EVERY_S == pytest.approx(round(stopped.t_end / SOURCE_EVERY_S), abs=1e-9)

    resumed = run_job(cfg, out, resume=True)
    whole = run_job(cfg, tmp_path / "whole")
    assert resumed.exit_code == whole.exit_code == 0
    assert resumed.steps == whole.steps
    assert series(out) == series(tmp_path / "whole")
    for name in ("outflow", "storage"):
        assert getattr(resumed.balance, name) == getattr(whole.balance, name), name
    # The books credit a window's rain in pieces at wall-clock progress ticks, so even two unbroken runs part in the 16th digit.
    for name in ("rain", "inflow"):
        assert getattr(resumed.balance, name) == pytest.approx(getattr(whole.balance, name), rel=1e-12), name
    np.testing.assert_array_equal(np.asarray(resumed.dt_min), np.asarray(whole.dt_min))
