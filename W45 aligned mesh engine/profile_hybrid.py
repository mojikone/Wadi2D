"""Where the GPU hybrid step spends its time on Faydh 01 at 20 m: tiles alone, the hybrid, and the hybrid without its
per-step bookkeeping (maxima, boundary tally). Numbers for the speed work of W45.

    .venv\\Scripts\\python "W45 aligned mesh engine\\profile_hybrid.py" [steps]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wadi2d.config.schema import RunConfig  # noqa: E402
from wadi2d.run import prepare_grid  # noqa: E402
from wadi2d.solver.model import Model  # noqa: E402
from wadi2d.strips.hybrid import make_hybrid  # noqa: E402

W = ROOT / "W45 aligned mesh engine" / "race_faydh"
STEPS = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
NONE_JOB = Path(sys.argv[2]) if len(sys.argv) > 2 else W / "faydh20_none_gpu.json"
STRIPS_JOB = Path(sys.argv[3]) if len(sys.argv) > 3 else W / "faydh20_strips_gpu.json"


def model_of(job):
    cfg = RunConfig.model_validate(json.loads(Path(job).read_text(encoding="utf-8")))
    tables, _crs = prepare_grid(cfg, Path(cfg.grid.cache_dir))
    model = Model(tables, cfg.numerics, "gpu")
    hybrid = make_hybrid(model, tables.strip.mesh) if getattr(tables, "strip", None) is not None else None
    rate = np.where(tables.grid.mask, 50.0 / 3.6e6, 0.0)
    model.set_source(rate)
    if hybrid is not None:
        hybrid.rain(rate, 1.0)
    return model, hybrid


def timed(model, steps: int) -> tuple[float, int]:
    import cupy as cp

    st = model.stepper
    cp.cuda.Device().synchronize()
    t0 = time.perf_counter()
    n0 = st.nsteps
    target = st.t + 1e9
    while st.nsteps - n0 < steps:
        model.advance(min(target, st.t + 50.0))
    cp.cuda.Device().synchronize()
    return time.perf_counter() - t0, st.nsteps - n0


def main() -> None:
    import cupy as cp

    out = {}
    tiles, _ = model_of(NONE_JOB)
    tiles.advance(300.0)  # warm up: compile, first wet
    secs, n = timed(tiles, STEPS)
    out["tiles"] = {"ms_per_step": 1e3 * secs / n, "steps": n}
    print(f"tiles alone: {1e3 * secs / n:.3f} ms/step over {n} steps")
    del tiles
    cp.get_default_memory_pool().free_all_blocks()

    model, hybrid = model_of(STRIPS_JOB)
    model.advance(300.0)
    secs, n = timed(model, STEPS)
    out["hybrid"] = {"ms_per_step": 1e3 * secs / n, "steps": n}
    print(f"hybrid: {1e3 * secs / n:.3f} ms/step over {n} steps; strip cells {hybrid.nreal}, faces {hybrid.mesh.nfaces}, ghosts {hybrid.ghost.size}")

    # the bookkeeping: maxima and the boundary tally, switched off by hand
    s = hybrid.state
    original = hybrid.after_update

    def lean_after(dt, want_wave):
        b = model.backend
        b.src[hybrid.ghost_d] = hybrid.saved
        for _axis, (nslot, maps) in hybrid.edge_d.items():
            discharge, velocity = (b.qx, b.u1) if _axis == "x" else (b.qy, b.v1)
            s.edges(nslot, maps, discharge, velocity)

    hybrid.after_update = lean_after
    secs, n = timed(model, STEPS)
    out["hybrid_no_bookkeeping"] = {"ms_per_step": 1e3 * secs / n, "steps": n}
    print(f"hybrid without maxima and tally: {1e3 * secs / n:.3f} ms/step")
    hybrid.after_update = original

    # the strip's launches alone: before_update + after_update on the current state, repeated
    cp.cuda.Device().synchronize()
    t0 = time.perf_counter()
    for _ in range(500):
        hybrid.before_update(0.1, False)
        original(0.1, False)
    cp.cuda.Device().synchronize()
    strip_ms = 1e3 * (time.perf_counter() - t0) / 500
    out["strip_hooks_only"] = {"ms_per_step": strip_ms}
    print(f"strip hooks alone: {strip_ms:.3f} ms/step")
    (STRIPS_JOB.parent / "profile_hybrid.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
