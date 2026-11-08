"""W48's deep narrow gorge with the local hydraulic radius face table (W49, 2026-11-08).

The same two gorges as `W48 aligned cells race excess/narrow_gorge.py` (a 12 m bed, walls rising 7 m over 1.5 m, a
10 m ledge, hills at 50 %, bed slope 1 %, n 0.05, a steady 300 m3/s), straight and on the tight sine (radius 243 m),
run with `tables.face_conveyance: local_radius` (Spada et al. 2015, beta 9) on squares at 20, 10, 5 and 2 m and the
centre mesh at 20 and 10 m. Read with W48's `gorge_reading.py`: the water surface laid over the 0.5 m DEM between 1
and 8 km, the level 3 m either side of the axis. The W48 numbers are the strips sum on the same ground.

    .venv\Scripts\python "W49 local hydraulic radius face table\gorge_local_radius.py" [narrow narrow_sine] [run report]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "W48 aligned cells race excess"))
import gorge_reading as gr  # noqa: E402  (registers the gorge cases and W48's reader)
import wave_probe as wp  # noqa: E402

wp.OUT = HERE / "probe"
MESHES = ("sq20", "ce20", "sq10", "ce10", "sq5", "sq2")


def build_and_run(case: str) -> None:
    if not (wp.OUT / case / "dem.tif").is_file():
        wp.ground(case)
    for mesh in MESHES:
        if (wp.OUT / case / wp.name_of(case, "steady", mesh) / "results.h5").is_file():
            continue
        data = wp.job(case, "steady", mesh)
        data["outputs"]["map_every_s"] = 10_800.0
        data["tables"] = {"face_conveyance": "local_radius"}
        path = wp.OUT / case / f"{wp.name_of(case, 'steady', mesh)}.json"
        path.write_text(json.dumps(data, indent=1), encoding="utf-8")
        wp.run(case, "steady", mesh)


if __name__ == "__main__":
    cases = [a for a in sys.argv[1:] if a in wp.CASES] or ["narrow", "narrow_sine"]
    steps = [a for a in sys.argv[1:] if a in ("run", "report")] or ["run", "report"]
    for case in cases:
        if "run" in steps:
            build_and_run(case)
        if "report" in steps:
            gr.read(case)
