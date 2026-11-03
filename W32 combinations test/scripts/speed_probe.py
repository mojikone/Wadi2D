"""How much slower the CPU twin is on Bidah ground, to size the shortened dock runs. Not a finding: the card is shared.

    python speed_probe.py <scratch folder>
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402

scratch = Path(sys.argv[1])
out = {}
for backend in ("gpu", "cpu"):
    job = c.write(c.bidah_job(f"speed_{backend}", scratch / "cache", hours=1.5, backend=backend), scratch / "speed" / f"job_{backend}.json")
    code, wall = c.run(job, scratch / "speed" / f"run_{backend}")
    start, done = c.start_event(scratch / "speed" / f"run_{backend}"), c.done_event(scratch / "speed" / f"run_{backend}")
    out[backend] = {"exit": code, "wall_s": round(wall, 1), "backend": start.get("backend"), "cells": start.get("cells"),
                    "steps": done.get("steps"), "loop_s": done.get("loop_s"), "peaks": c.line_peaks(scratch / "speed" / f"run_{backend}")}  # fmt: skip
    c.say(f"{backend}: {out[backend]}")
c.dump(out, Path(__file__).resolve().parents[1] / "results" / "speed_probe.json")
