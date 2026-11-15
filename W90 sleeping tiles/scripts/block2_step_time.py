"""Time per step on Block 2 itself (W79's run, read only), with the water of one of its saved frames put back into
the model: every tile stepped, the rule before W90 (the strip's ghost tiles and their neighbours kept awake), the
rule of W90, and the squares with no strip stepped at all, which gives the strip's share.

    python block2_step_time.py <run folder> <grid cache .h5> <strip cache .pkl> <backend> <out .json> <frame time s> [...]

The frame's depths go in with no velocities, so the flow is not the run's; the kernels' cost is set by which faces
are wet, which the depths decide. Nothing is written to the run folder.
"""

from __future__ import annotations

import json
import pickle
import sys
import time
from pathlib import Path

import h5py
import numpy as np

from wadi2d.config.schema import RunConfig
from wadi2d.engine.handback import sink_lines
from wadi2d.engine.inflow_lines import open_lines
from wadi2d.forcing import boundary_set
from wadi2d.io.cache import load_tables
from wadi2d.solver.layout import STRIDE2
from wadi2d.solver.model import Model
from wadi2d.strips.hybrid import make_hybrid

STEPS = 320
"""Steps timed in each mode: twenty checks of the active list."""


def frame_at(results: Path, t: float, n: int) -> tuple[float, np.ndarray, np.ndarray]:
    with h5py.File(results, "r") as f:
        name = min(f["maps"], key=lambda k: abs(float(f["maps"][k].attrs["t_s"]) - t))
        g = f["maps"][name]
        return float(g.attrs["t_s"]), g["mean_depth"][()], g["strip_mean_depth"][0, :n]


def timed_steps(model, steps: int) -> tuple[float, float]:
    """Wall time per step over at least ``steps`` steps, s, and the mean awake tiles over them."""
    st, b = model.stepper, model.backend
    b.synchronize()
    awake, rounds, n0 = 0, 0, st.nsteps
    t0 = time.perf_counter()
    while st.nsteps - n0 < steps:
        st.advance(st.t + 16.0 * st.dt)
        awake += int(b.nact)
        rounds += 1
    b.synchronize()
    return (time.perf_counter() - t0) / (st.nsteps - n0), awake / rounds


def main() -> None:
    run, grid_file, strip_file, backend, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], Path(sys.argv[5])
    times = [float(a) for a in sys.argv[6:]]
    cfg = RunConfig.model_validate_json((run / "config.resolved.json").read_text(encoding="utf-8"))
    t0 = time.perf_counter()
    tables = load_tables(grid_file, grid_file.stem.removeprefix("grid_"))
    with open(strip_file, "rb") as f:
        made = pickle.load(f)["strip"]
    print(f"tables and strip read in {time.perf_counter() - t0:.1f} s", flush=True)
    n = made.mesh.real
    rows = []
    for t_frame in times:
        t_s, depth, strip_depth = frame_at(run / "results.h5", t_frame, n)
        for mode in ("all", "old", "new", "squares only"):
            model = Model(tables, cfg.numerics, backend)
            model.stepper.adaptive_active = mode != "all"
            hybrid = None
            watch_s = 0.0
            if mode != "squares only":
                t1 = time.perf_counter()
                hybrid = make_hybrid(model, made.mesh, cfg.strips.substeps)
                watch_s = time.perf_counter() - t1
                if mode == "old":
                    hybrid.always = np.unique(hybrid.ghost // STRIDE2)
                    model.stepper.wake_rules = [hybrid._ghost_tiles]
            lines = [*open_lines(cfg.boundaries), *sink_lines(cfg.hydrology.handbacks)]
            model.set_boundary(boundary_set(lines, tables, cfg.grid.line_samples).cells)
            model.set_depth(np.where(tables.grid.mask, depth, 0.0))
            if hybrid is not None:
                hybrid.set_strip_depth(strip_depth)
            if mode == "squares only":  # the same tiles awake as the rule of W90 found, and no strip beside them
                model.stepper.adaptive_active = False
                model.backend.set_active(np.asarray(rows[-1]["awake_list"], np.int32))
            timed_steps(model, 32)  # compile, settle the time step
            wall, awake = timed_steps(model, STEPS)
            row = {
                "frame_t_s": t_s, "mode": mode, "tiles": tables.grid.ntiles - 1, "awake_tiles": round(awake, 1),
                "ms_per_step": round(1000.0 * wall, 4), "dt_s": round(model.stepper.dt, 4),
                "strip_cells": int(n), "strip_setup_s": round(watch_s, 2),
                "awake_list": model.backend.active_tiles.tolist(),
            }  # fmt: skip
            if hybrid is not None and hybrid.watch is not None:
                row["watch_reach_cells"] = hybrid.watch.reach
                row["watch_entries"] = int(hybrid.watch.from_squares.nnz + hybrid.watch.from_strip.nnz)
            rows.append(row)
            print(json.dumps({k: v for k, v in row.items() if k != "awake_list"}), flush=True)
            del model, hybrid
            if backend == "gpu":
                import cupy as cp

                cp.get_default_memory_pool().free_all_blocks()
    out.write_text(json.dumps([{k: v for k, v in r.items() if k != "awake_list"} for r in rows], indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
