"""The Block 2 window the pixel maps are checked on: Bidah 03's dam, its pool and the wadis round it.

W79's run 1 job (rain on every cell, aligned centre mesh at 20 m, dams as crest lines and spillways) cut to a box of
3.4 x 3.2 km, at the full 0.5 m pixel, on the CPU so the card stays free. The window holds square cells, the aligned
cells of the wadis and the dam's crest, dikes and spillway. No boundary is open: water that reaches the box's edge
ponds there, which does not matter to a comparison of two product steps on the same saved maps.

    python s01_window_job.py            writes jobs/window_bidah.json
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SOURCE = REPO / "W79 Block 2 four ways" / "jobs" / "run1_full_2d_aligned.json"
EXTENT = (436400.0, 2725200.0, 439800.0, 2728400.0)
HOURS = 30.0
DAM = "Bidah 03"


def main() -> None:
    job = json.loads(SOURCE.read_text(encoding="utf-8"))
    job["project"] = {"name": "window_bidah", "description": "W86: Block 2 window at Bidah 03 for the pixel maps"}
    job["grid"] = {"dx": 20.0, "domain": None, "extent": list(EXTENT), "cache_dir": str(HERE / "runs" / "cache")}
    job["terrain"]["pixel_stride"] = 1
    job["terrain"]["objects"] = [o for o in job["terrain"]["objects"] if o.get("name", "").startswith(DAM)]
    job["boundaries"] = []
    job["outputs"]["lines"] = [line for line in job["outputs"]["lines"] if line["name"].startswith(DAM)]
    job["outputs"]["edge_check"]["enabled"] = False
    job["run"]["duration_s"] = HOURS * 3600.0
    job["run"]["backend"] = "cpu"
    out = HERE / "jobs" / "window_bidah.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(job, indent=1), encoding="utf-8")
    print(out, len(job["terrain"]["objects"]), "objects")


if __name__ == "__main__":
    main()
