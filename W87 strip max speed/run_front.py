"""W87: the test's gully job (two floods over a dry gully that weaves through a corridor's gap triangles) run once
with whatever ``wadi2d`` is first on the path, so the same job can be run on the code before and after the change:

    set PYTHONPATH=<source tree with wadi2d>;<this repository, for tests>
    .venv\\Scripts\\python "W87 strip max speed\\run_front.py" <out folder> [cpu|gpu] [strips|plain]
"""

from __future__ import annotations

import sys
from pathlib import Path

from wadi2d.solver.poly import kernel

if not hasattr(kernel, "SPEED_CAP"):  # the code before W87: the test module reads the constant at import
    kernel.SPEED_CAP = 2.0**0.5

import wadi2d
from tests.engine.test_strips_run import corridor
from tests.strips.test_speed_record import front_job, gully_dem
from wadi2d.run import run_job

if __name__ == "__main__":
    out = Path(sys.argv[1])
    backend = sys.argv[2] if len(sys.argv) > 2 else "cpu"
    what = sys.argv[3] if len(sys.argv) > 3 else "strips"  # or "plain": the same job on squares alone
    out.mkdir(parents=True, exist_ok=True)
    print("wadi2d from", Path(wadi2d.__file__).parent)
    run = run_job(front_job(gully_dem(out), corridor() if what == "strips" else None, backend), out / what)
    print(
        "exit",
        run.exit_code,
        "steps",
        run.steps,
        "storage",
        repr(run.balance.storage),
        "outflow",
        repr(run.balance.outflow),
    )
