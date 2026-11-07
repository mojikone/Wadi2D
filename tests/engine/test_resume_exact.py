"""A stopped and resumed run ends where an unbroken run ends, to the last digit (W32 item 4, W33)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from tests.engine.test_run import full_job, valley_dem  # noqa: F401
from wadi2d.engine.monitor import Monitor
from wadi2d.run import run_job

SOURCE_EVERY_S = 30.0
STOP_ASKED_AT_S = 1000.0
"""Inside the 34th window: a stop asked here, mid-window, must land at 1,020 s."""


def stop_asked_at(t_s: float):
    """``Monitor.stop_requested`` that reads true once the run passes ``t_s``: a stop file at a set simulated time,
    the same on any backend however fast it runs."""

    def asked(self: Monitor) -> bool:
        return self.last_t >= t_s

    return asked


def series(out: Path) -> dict[str, str]:
    return {path.name: path.read_text(encoding="utf-8") for path in sorted((out / "series").glob("*.csv"))}


@pytest.mark.parametrize("backend", ["cpu", pytest.param("gpu", marks=pytest.mark.gpu)])
def test_a_stop_lands_on_a_source_window_and_the_resumed_run_is_the_unbroken_one(
    valley_dem, tmp_path, backend, monkeypatch  # noqa: F811
):
    cfg = full_job(valley_dem, backend, 2400.0)
    cfg = cfg.model_copy(update={"outputs": cfg.outputs.model_copy(update={"progress_every_s": 0.0})})
    out = tmp_path / "broken"
    with monkeypatch.context() as patch:
        patch.setattr(Monitor, "stop_requested", stop_asked_at(STOP_ASKED_AT_S))
        stopped = run_job(cfg, out)
    assert stopped.exit_code == 6
    assert stopped.t_end == pytest.approx(1020.0, abs=1e-6)

    resumed = run_job(cfg, out, resume=True)
    whole = run_job(cfg, tmp_path / "whole")
    assert resumed.exit_code == whole.exit_code == 0
    assert resumed.steps == whole.steps
    assert series(out) == series(tmp_path / "whole")
    assert resumed.balance.storage == whole.balance.storage
    # The books add in another order across a checkpoint (rain credited at progress ticks, the GPU's outflow tally
    # restarted from the saved sum), so they agree to round-off, not to the digit; the water above is the same.
    for name in ("rain", "inflow", "outflow"):
        assert getattr(resumed.balance, name) == pytest.approx(getattr(whole.balance, name), rel=1e-12), name
    np.testing.assert_array_equal(np.asarray(resumed.dt_min), np.asarray(whole.dt_min))
