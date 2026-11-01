"""The SCS lag that reaches a given peak on S13's excess. The least-squares lag cannot: the SCS shape is too broad here.

Writes peak_lag.json: for each result file, the lag whose unit hydrograph peaks at the 2D peak at the S13 edge.
"""

from __future__ import annotations

import json
import sys

import numpy as np

import case

sys.path.insert(0, str(case.ENGINE))
from wadi2d.hydrology.transforms import ScsUnitHydrograph, convolve  # noqa: E402

mm = np.loadtxt(case.HERE / "excess_5min.csv", delimiter=",", skiprows=1)[:, 1]
excess = np.zeros(576)
excess[: mm.size] = mm
lags = np.arange(3.0, 80.0, 0.5)
peaks = np.array([convolve(excess, ScsUnitHydrograph(float(g)).unit_hydrograph(case.AREA_KM2, 5.0), 577).max() for g in lags])
out = {}
for name in case.CONFIGS:
    p = case.HERE / f"results_{name}.json"
    if not p.exists():
        continue
    r = json.loads(p.read_text(encoding="utf-8"))["sections"]["s13_edge"]
    row = {}
    for model in ("ras", "wadi"):
        q = r[model]["peak"]
        row[model] = {"peak": q, "lag_for_peak_min": float(np.interp(-q, -peaks, lags))}
    out[name] = row
out["lag_53.3_peak"] = float(np.interp(53.3, lags, peaks))
(case.HERE / "peak_lag.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(json.dumps(out, indent=1))
