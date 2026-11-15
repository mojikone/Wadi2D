"""W85 step 5: Faydh 01's dam-axis peak on the 20 m squares with ``numerics.plan_min`` raised, on the CPU.

    python s06_faydh_plan_min.py <W49 race job sq20.json> <out folder> [plan_min ...]

The job is the race's own (`W49 .../race_faydh_top_fix/sq20.json`), with its tables built into this folder's cache and
the CPU as the backend; the first run is the default 0.02, so every figure here is CPU against CPU. Writes
``faydh_plan_min.json``: peak at the axis, its hour, volume, steps, loop time and the smallest step per value.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

from wadi2d.run import load_job, run_job

LINE = "axis"


def axis(folder: Path) -> dict:
    with (folder / "series" / f"line_{LINE}.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    t = np.array([float(r["t_s"]) for r in rows])
    q = np.array([float(r["discharge_m3s"]) for r in rows])
    n = int(np.argmax(q))
    return {"peak": float(q[n]), "at_h": float(t[n] / 3600.0), "vol_Mm3": float(np.trapezoid(q, t) / 1e6)}


def main() -> None:
    source, out = Path(sys.argv[1]), Path(sys.argv[2])
    values = [float(a) for a in sys.argv[3:]] or [0.02, 0.10, 0.25]
    base = load_job(source)
    record_file = out / "faydh_plan_min.json"
    record = json.loads(record_file.read_text()) if record_file.is_file() else {}
    for value in values:
        cfg = base.model_copy(
            update={
                "grid": base.grid.model_copy(update={"cache_dir": str(out / "cache")}),
                "run": base.run.model_copy(update={"backend": "cpu"}),
                "numerics": base.numerics.model_copy(update={"plan_min": value}),
                "outputs": base.outputs.model_copy(update={"step_limiter": "layer", "map_every_s": 0.0}),
            }
        )
        folder = out / f"plan_min_{value:.2f}"
        s = run_job(cfg, folder)
        record[f"{value:.2f}"] = {
            **axis(folder), "exit": s.exit_code, "steps": s.done.get("steps"), "loop_s": s.done.get("loop_s"),
            "dt_min": s.done.get("dt_min"), "relative_error": s.done.get("balance", {}).get("relative_error"),
        }  # fmt: skip
        record_file.write_text(json.dumps(record, indent=1))
        print(value, record[f"{value:.2f}"], flush=True)
    ref = record.get("0.02")
    if ref:
        for key, r in record.items():
            print(
                f"plan_min {key}: peak {r['peak']:.2f} m3/s ({100.0 * (r['peak'] / ref['peak'] - 1.0):+.3f} %), steps {r['steps']:,}"
            )


if __name__ == "__main__":
    main()
