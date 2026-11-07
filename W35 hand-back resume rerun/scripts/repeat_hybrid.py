"""Is the Block 2 hybrid at 80 m repeatable on one backend? The dock's HMS-storm job of the storm scenario (as the dock
wrote it), run twice on the GPU and once on the CPU by the command line; step counts, line peaks and the balance set
side by side. Separates "the backends differ" from "the run differs from itself".

    python repeat_hybrid.py <the dock's job.json> <scratch folder>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402

RESULTS = Path(__file__).resolve().parents[1] / "results"


def main(job_path: Path, scratch: Path) -> None:
    job = json.loads(job_path.read_text(encoding="utf-8"))
    job["grid"]["cache_dir"] = str(scratch / "cache_block2_80")
    job["outputs"]["pixels"] = {"enabled": False}
    job["outputs"]["smooth"] = {"enabled": False}
    job["outputs"]["map_every_s"] = 0.0
    out = {}
    for label, backend in (("gpu1", "gpu"), ("gpu2", "gpu"), ("cpu1", "cpu")):
        job["run"]["backend"] = backend
        path = c.write(job, scratch / "repeat" / f"{label}.json")
        code, wall = c.run(path, scratch / "repeat" / label)
        folder = scratch / "repeat" / label
        start, done = c.start_event(folder), c.done_event(folder)
        out[label] = {"exit": code, "backend": start.get("backend"), "cells": start.get("cells"), "steps": done.get("steps"),
                      "loop_s": done.get("loop_s"), "balance": done.get("balance", {}), "lines": c.line_peaks(folder)}  # fmt: skip
        c.say(f"{label}: exit {code}, {start.get('backend')}, steps {done.get('steps')}, lines {out[label]['lines']}")
    names = sorted(out["gpu1"]["lines"])
    table = []
    for n in names:
        a, b, d = out["gpu1"]["lines"][n][0], out["gpu2"]["lines"][n][0], out["cpu1"]["lines"][n][0]
        table.append({"line": n, "gpu1": a, "gpu2": b, "cpu1": d, "gpu2/gpu1-1": b / a - 1.0 if a else None, "cpu1/gpu1-1": d / a - 1.0 if a else None})
        c.say(f"{n:16s} gpu1 {a:10.3f} gpu2 {b:10.3f} cpu1 {d:10.3f}   gpu2 {((b / a - 1.0) if a else 0):+.2e}  cpu1 {((d / a - 1.0) if a else 0):+.2e}")
    c.dump({"runs": out, "table": table}, RESULTS / "repeat_hybrid.json")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
