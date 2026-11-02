"""The pixel step on a real mesh at the DEM's own 0.5 m: Bidah, 10 m to 40 m cells, through the peak of the storm."""

import json
import time
from pathlib import Path

from wadi2d.run import load_job, run_job

JOB = Path(
    r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\ras_rain_on_grid\jobs\10m_n050_em.json"
)
OUT = Path(__file__).parent / "runs" / "pixels_05m"

data = load_job(JOB).model_dump(mode="json")
data["grid"]["cache_dir"] = str(OUT.parent / "cache")
data["run"]["duration_s"] = 14.0 * 3600.0
data["outputs"]["map_every_s"] = 1800.0
data["mesh"] = {"enabled": True, "coarse_dx": 40.0}
data["outputs"]["pixels"]["enabled"] = True
data["outputs"]["pixels"]["pixel_m"] = 0.0
start = time.monotonic()
summary = run_job(type(load_job(JOB)).model_validate(data), OUT)
print(
    json.dumps(
        {
            "status": summary.status,
            "message": summary.message[:300],
            "cells": summary.cells,
            "loop_s": round(summary.loop_s, 1),
            "wall_s": round(time.monotonic() - start, 1),
            "mass": summary.balance.relative,
            "peaks": {k: [round(v[0], 2), round(v[1], 0)] for k, v in summary.peaks.items()},
        }
    )
)
