"""W11's Shaheen run at Lihban rebuilt on the gauge storm and the observed overlay. Nothing is tuned here.

W11 ran the gauge's 5-minute rain less a phi index, the index set so the excess equals the observed runoff depth
(150.67 mm over 197.51 km2), as a hypothetical storm whose pattern is that excess. Here the same excess is a rain gauge's
record with dates, at the gauge's position, and the 5-minute observed flow beside it is an observed record with dates: the
run starts at the start of the first period with excess, W11's minute -45. Everything else is W11's job as it ran.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
W11 = HERE.parents[1] / "W11 validation round two" / "t3_envelope"
ROOT = Path(r"D:\Mojtaba\Renardet\Wadi2D")
DAY = np.datetime64("2021-10-04T00:00", "s")
GX, GY = 488963.0, 2632307.0
"""Bani Umar rain and flow gauge DB839224AD, as W11 placed it (s18)."""


def stamp(minutes: float) -> str:
    return str(DAY + np.timedelta64(round(minutes * 60), "s")).replace("T", " ")


a = np.loadtxt(W11 / "shaheen_5min.csv", delimiter=",", skiprows=1)
tq, p, obs = a[:, 0], a[:, 1], a[:, 2]
depth = json.loads((W11 / "shaheen_fit.json").read_text())["obs_depth_mm"]
lo, hi = 0.0, p.max()
for _ in range(60):  # W11's own bisection (s18), to the same index
    m = 0.5 * (lo + hi)
    if np.maximum(p - m, 0.0).sum() > depth:
        lo = m
    else:
        hi = m
excess = np.maximum(p - hi, 0.0)
k0 = int(np.argmax(excess > 0.0))
k1 = len(excess) - int(np.argmax(excess[::-1] > 0.0))
start = tq[k0] - 5.0
duration_min = 5.0 * (k1 - k0)
rows = "".join(f"{stamp(t)},{e:.6f}\n" for t, e in zip(tq, excess, strict=True))
(HERE / "gauge_excess_phi.csv").write_text("time,excess_mm\n" + rows, encoding="utf-8")
(HERE / "observed_flow_5min.csv").write_text(
    "time,flow_m3s\n" + "".join(f"{stamp(t)},{q:g}\n" for t, q in zip(tq, obs, strict=True)), encoding="utf-8"
)
job = json.loads((W11 / "jobs" / "lihban_phi.json").read_text(encoding="utf-8"))
job["project"] = {"name": "lihban_gauges_phi", "description": "W11's Shaheen phi run, rain as a gauge record (W54)"}
job["grid"]["domain"] = str(W11 / "domain_lihban.geojson")
job["grid"]["cache_dir"] = str(HERE / "cache")
job["storm"] = {
    "kind": "gauges",
    "rain_start": stamp(start),
    "gauges": {
        "gauges": [
            {"name": "DB839224AD", "x": GX, "y": GY, "file": "gauge_excess_phi.csv", "interval_min": 5.0},
        ],
        "method": "thiessen",
    },
}
job["outputs"]["observed"] = [
    {"name": "Bani Umar 5 min", "file": "observed_flow_5min.csv", "target": "gauge"},
]
assert job["run"]["duration_s"] == duration_min * 60.0 + 12 * 3600.0
(HERE / "job_gauges_phi.json").write_text(json.dumps(job, indent=1), encoding="utf-8")
print("phi mm per 5 min", hi, "excess mm", excess.sum(), "start", stamp(start), "duration min", duration_min)
