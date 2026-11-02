"""Run the Bidah rain-on-grid job with changed numerics and print peak, balance and loop time.

usage: python bidah.py OUT_NAME [job=PATH] [key=value ...], each key part.field of the job, as
numerics.local_time_stepping=true. Without job= it is the Bidah job frozen in W1; nothing in that file is edited. Maps are
off: this measures the loop and the hydrographs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from wadi2d.config.schema import RunConfig
from wadi2d.run import load_job, run_job

JOB = Path(
    r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\ras_rain_on_grid\jobs\10m_n050_em.json"
)
SCRATCH = Path(__file__).parent / "runs"


def parse(value: str):
    return json.loads(value) if value[0] in '-0123456789tf[{"' else value


def job_with(changes: dict[str, object], job: Path = JOB) -> RunConfig:
    cfg = load_job(job)
    data = cfg.model_dump(mode="json")
    data["outputs"]["map_every_s"] = 0.0
    if job == JOB:
        data["grid"]["cache_dir"] = str(SCRATCH / "cache")
    for key, value in changes.items():
        part, name = key.split(".", 1)
        data.setdefault(part, {})[name] = value
    return RunConfig.model_validate(data)


def main() -> None:
    name = sys.argv[1]
    changes = {k: parse(v) for k, v in (a.split("=", 1) for a in sys.argv[2:] if not a.startswith("job="))}
    job = next((Path(a[4:]) for a in sys.argv[2:] if a.startswith("job=")), JOB)
    summary = run_job(job_with(changes, job), SCRATCH / name)
    b = summary.balance
    print(
        json.dumps(
            {
                "name": name,
                "status": summary.status,
                "message": summary.message[:300],
                "cells": summary.cells,
                "steps": summary.steps,
                "loop_s": round(summary.loop_s, 2),
                "dt_min": summary.dt_min,
                "mass": b.relative,
                "wet_km2": summary.wet_area_km2,
                "peaks": {k: [round(v[0], 3), round(v[1], 0)] for k, v in summary.peaks.items()},
            }
        )
    )


if __name__ == "__main__":
    main()
