"""The gauge run against W11's own job on the same engine, and the observed records compared again with no rerun.

W11's job starts its minute zero at 23:15 on 3 October as the gauge run does, so the two line series share a clock.
The second observed record is the project's HMS flow gage, DB839224AD - Shahin, 6-minute, read from its DSS file.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
PROJECT = Path(
    r"W:\2224 Flood Protection Scheme in North & South Batinah_MAFWWR\06-WORKING\03-Hydrology\calibration"
    r"\HMS_Albatinah_Calibration\Albatinah_Calibration"
)


def line(run: str) -> tuple[np.ndarray, np.ndarray]:
    rows = list(csv.reader((RUNS / run / "series" / "line_gauge.csv").open()))[1:]
    a = np.array(rows, float)
    return a[:, 0], np.abs(a[:, 1])


t1, q1 = line("gauges_phi")
t2, q2 = line("w11_hypothetical_phi")
same_clock = bool(np.array_equal(t1, t2))
out = {
    "same_series_times": same_clock,
    "series_samples": [int(t1.size), int(t2.size)],
    "largest_difference_m3s": float(np.max(np.abs(q1 - np.interp(t1, t2, q2)))),
    "peaks": {"gauges": float(q1.max()), "hypothetical": float(q2.max())},
    "rain_m3": {
        name: json.loads((RUNS / name / "progress.jsonl").read_text().splitlines()[-1])["balance"]["rain_m3"]
        for name in ("gauges_phi", "w11_hypothetical_phi")
    },
}
observed = [
    {"name": "Bani Umar 5 min", "file": str(HERE / "observed_flow_5min.csv"), "target": "gauge",
     "start": "2021-10-03 23:15"},
    {"name": "HMS gage DB839224AD - Shahin", "file": str(PROJECT / "Albatinah_Calibration.dss"),
     "record": "//DB839224AD - Shahin/FLOW//6MIN/GAGE/", "target": "gauge", "start": "2021-10-03 23:15"},
]  # fmt: skip
listing = HERE / "observed_again.json"
listing.write_text(json.dumps(observed, indent=1), encoding="utf-8")
for run in ("w11_hypothetical_phi", "gauges_phi"):
    done = subprocess.run(
        [sys.executable, "-m", "wadi2d.engine.cli", "compare", str(RUNS / run), "--observed", str(listing)],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    answer = [line for line in done.stdout.splitlines() if line.startswith("{")]
    stats = json.loads((RUNS / run / "observed" / "statistics.json").read_text())
    out[run] = {"exit": done.returncode, "answer": json.loads(answer[-1]) if answer else done.stderr[-400:], "records": [
        {k: r[k] for k in ("name", "points", "observed_peak", "observed_peak_t_s", "simulated_peak", "simulated_peak_t_s",
                           "peak_ratio", "nse", "rsr", "pbias_percent", "observed_volume_m3", "simulated_volume_m3")}
        for r in stats["records"]]}
(HERE / "comparison.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(json.dumps(out, indent=1))
