"""The link's lag and what holding does to a peak, at three lumped steps, on the closed box of the tests (CPU).

The reach is a plain 10-minute lag, whose answer is exact, so whatever else moves is the link's.

    python lag_table.py <work folder>     # writes lag_table.json here
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from tests.engine.test_handback import (  # noqa: E402
    LAG_MIN,
    LINE_X,
    SINK,
    X0,
    across,
    box,
    centroid,
    lag_reach,
    series,
    write_basin,
)
from wadi2d.run import run_job  # noqa: E402


def one(work: Path, step: float) -> dict:
    folder = work / f"step_{step:g}"
    folder.mkdir(parents=True, exist_ok=True)
    sections = [
        {"name": "Before", "coordinates": across(LINE_X - 8.0)},
        {"name": "After", "coordinates": across(X0 + 352.0)},
    ]
    cfg = box(
        folder,
        write_basin(folder, lag_reach(), SINK),
        step=step,
        outputs={"lines": sections, "series_every_s": 10.0},
    )
    out = folder / "run"
    run = run_job(cfg, out)
    t = series(out, "lines", "Before", "t_s")
    before = np.abs(series(out, "lines", "Before", "discharge_m3s"))
    after = np.abs(series(out, "lines", "After", "discharge_m3s"))
    dt = step * 60.0
    line = series(out, "handbacks", "Line", "inflow_m3s")
    held = series(out, "network", "R1", "outflow_m3s")
    m = line.size - int(LAG_MIN / step)
    k = np.arange(line.size) * dt
    link = centroid((k + dt / 2.0)[-m:], held[-m:]) - centroid((k - dt / 2.0)[:m], line[:m]) - LAG_MIN * 60.0
    total = centroid(t, after) - centroid(t, before) - LAG_MIN * 60.0
    return {
        "step_min": step,
        "link_lag_s": float(link),
        "grid_total_lag_s": float(total),
        "peak_before_m3s": float(before.max()),
        "peak_after_m3s": float(after.max()),
        "peak_ratio": float(after.max() / before.max()),
        "whole_relative_error": run.balance.whole_relative,
    }


if __name__ == "__main__":
    work = Path(sys.argv[1])
    rows = [one(work, step) for step in (1.0, 2.0, 5.0)]
    (HERE / "lag_table.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    for row in rows:
        print(row)
