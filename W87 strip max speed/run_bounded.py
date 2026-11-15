"""W87, diagnosis only: run a job on the CPU with the step's unbounded velocities bounded in memory (see
``kernel_probe.py``), to see what the fault moves on real ground. Nothing in the source is changed.

    .venv\\Scripts\\python "W87 strip max speed\\run_bounded.py" <job.json> <out folder> [cell|join|both]
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import kernel_probe as kp  # noqa: E402

from wadi2d.engine.cli import main  # noqa: E402

if __name__ == "__main__":
    job, out = sys.argv[1], sys.argv[2]
    what = sys.argv[3] if len(sys.argv) > 3 else "both"
    if what in ("cell", "both"):
        kp.kernel.perot_velocity = kp.perot_bounded
        kp.hybrid.ghost_rates = kp.rates_bounded
    if what in ("join", "both"):
        kp.hybrid.HybridCpu.after_update = kp.after_bounded
    print("bounded:", what, flush=True)
    sys.exit(main(["run", job, "--out", out]))
