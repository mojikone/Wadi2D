"""How much bed loss would it take to bring the 100-yr flood at the Fizh gauge down to the record? A sensitivity.

The W11 job as it stood (100-yr Block 2 storm at the gauge's 262 km2, project CN grid, n 0.05, 20 m, 36 h), run again
on this branch with the loss off and then at rates across Lane's bed groups (NEH 630 chapter 19, table 19-1). The loss
acts on every channel cell, mountain wadis included, which is an upper bound: the bedrock wadis of the hills lose
little. Nothing is fitted; the gauge's Q100 of 770 m3/s is read against the results, not used to choose a rate.

    python fizh_sensitivity.py run <runs folder>
    python fizh_sensitivity.py table <runs folder>   # writes fizh_sensitivity.json here
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # this branch's wadi2d, not the editable install of the main checkout
JOB = HERE.parent / "W11 validation round two" / "t3_envelope" / "jobs" / "fizh_gauge.json"
RATES_MM_H = (0.0, 25.0, 75.0, 150.0, 300.0)
"""Off, then group 3 to past group 1 of Lane's table."""
GAUGE_Q100 = 770.0
GAUGE = "gauge"


def job(rate: float, runs: Path) -> dict:
    data = json.loads(JOB.read_text(encoding="utf-8"))
    data["grid"]["cache_dir"] = str(runs / "cache")
    data["outputs"]["map_every_s"] = 0.0
    data["outputs"]["pixels"] = {"enabled": False}
    if rate > 0.0:
        data["transmission"] = {"enabled": True, "rate_mm_h": rate, "min_depth_m": 0.1}
    return data


def run(runs: Path) -> None:
    from wadi2d.config.schema import RunConfig
    from wadi2d.run import run_job

    for rate in RATES_MM_H:
        out = runs / f"rate_{rate:g}"
        if (out / "results.h5").is_file():
            continue
        summary = run_job(RunConfig.model_validate(job(rate, runs)), out)
        print(rate, summary.exit_code, summary.message, flush=True)


def table(runs: Path) -> list[dict]:
    rows = []
    for rate in RATES_MM_H:
        out = runs / f"rate_{rate:g}"
        with h5py.File(out / "results.h5", "r") as f:
            g = f[f"series/lines/{GAUGE}"]
            t, q = g["t_s"][()], np.abs(g["discharge_m3s"][()])
            attrs = dict(f.attrs)
        lines = (out / "progress.jsonl").read_text(encoding="utf-8").splitlines()
        done = [json.loads(s) for s in lines if json.loads(s)["ev"] == "done"][-1]
        b = done["balance"]
        k = int(np.argmax(q))
        rows.append({
            "rate_mm_h": rate,
            "peak_m3s": float(q[k]),
            "peak_over_q100": float(q[k] / GAUGE_Q100),
            "peak_at_h": float(t[k] / 3600.0),
            "volume_at_gauge_m3": float(np.trapezoid(q, t)),
            "rain_m3": b["rain_m3"],
            "lost_m3": b.get("transmission_m3", 0.0),
            "relative_error": b["relative_error"],
            "status": str(attrs.get("status")),
        })  # fmt: skip
    (HERE / "fizh_sensitivity.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return rows


if __name__ == "__main__":
    command, runs = sys.argv[1], Path(sys.argv[2])
    if command == "run":
        run(runs)
    else:
        for row in table(runs):
            print(row)
