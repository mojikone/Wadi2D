"""The gain on a made-up case: a lumped inflow at the head of a long dry valley, a strip of aligned cells on its
axis, hills either side that never get wet. Three runs of the same flood:

  all   every tile stepped at every step (the reference)
  old   the rule before W90: every tile that holds a square the strip touches is kept awake, and its neighbours
  new   the rule of W90: a tile is awake while water can reach it before the next check

    python valley_gain.py <backend> <tiles_y> <tiles_x> <hours> <out .json> [<row of a dry strip from the axis> ...]

Prints awake tiles and time per step, the strip's share of the step, and whether old and new equal the reference.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

from tests.strips.valley import Valley, valley

DRY: tuple[int, ...] = ()
"""Rows, from the axis, of bands of aligned cells that stay dry: the streams of the hills in a hybrid run."""


def timed(hybrid) -> dict:
    """Wrap the strip's two hooks with a clock; on the GPU the device is drained at each, so the split is honest."""
    spent = {"strip": 0.0}
    sync = getattr(hybrid.model.backend, "synchronize", lambda: None)
    for name in ("before_update", "after_update"):
        inner = getattr(hybrid, name)

        def outer(dt, want_wave, _inner=inner):
            sync()
            t0 = time.perf_counter()
            _inner(dt, want_wave)
            sync()
            spent["strip"] += time.perf_counter() - t0

        setattr(hybrid, name, outer)
    return spent


def run(mode: str, backend: str, ty: int, tx: int, hours: float, discharge: float) -> tuple[dict, Valley]:
    v = valley(tiles_y=ty, tiles_x=tx, backend=backend, sleeping=mode != "all", dry_strips=DRY)
    if mode == "old":
        h = v.hybrid
        h.always = np.unique(h.ghost // (36 * 36))
        v.model.stepper.wake_rules = [h._ghost_tiles]
    v.open_end()
    v.model.set_source(v.head(discharge))
    v.advance(30.0)  # compile and warm up outside the clock
    spent = timed(v.hybrid)
    awake_sum, samples = 0, []
    st = v.model.stepper
    n0 = st.nsteps
    v.model.backend.synchronize()
    t0 = time.perf_counter()
    end = hours * 3600.0
    marks = np.linspace(30.0, end, 25)[1:]
    for t in marks:
        before = st.nsteps
        v.advance(float(t))
        awake_sum += (st.nsteps - before) * v.awake()
        samples.append((float(t), v.awake()))
    v.model.backend.synchronize()
    wall = time.perf_counter() - t0
    steps = st.nsteps - n0
    row = {
        "mode": mode, "tiles": v.grid.ntiles - 1, "steps": steps, "wall_s": round(wall, 2),
        "ms_per_step": round(1000.0 * wall / steps, 3), "mean_awake_tiles": round(awake_sum / steps, 1),
        "strip_ms_per_step": round(1000.0 * spent["strip"] / steps, 3),
        "strip_share": round(spent["strip"] / wall, 3), "awake_at": samples[:: max(len(samples) // 8, 1)],
        "volume_m3": v.hybrid.volume(),
    }  # fmt: skip
    return row, v


def main() -> None:
    global DRY
    backend, ty, tx, hours, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]), Path(sys.argv[5])
    DRY = tuple(int(a) for a in sys.argv[6:])
    rows, fields = [], {}
    for mode in ("all", "old", "new"):
        row, v = run(mode, backend, ty, tx, hours, 40.0)
        fields[mode] = v.fields()
        row["strip_cells"] = int(v.hybrid.nreal)
        row["ghost_tiles"] = int(np.unique(v.hybrid.ghost // (36 * 36)).size)
        if mode != "all":
            row["differs_from_all_in"] = {
                k: int(np.sum(fields[mode][k] != fields["all"][k])) for k in fields[mode] if np.any(fields[mode][k] != fields["all"][k])
            }
        rows.append(row)
        print(json.dumps(row))
    out.write_text(json.dumps(rows, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
