"""HMS's storage balance per step: S2 - S1 - dt (I mean - O mean), against the evaporation and seepage it reports."""

import sys
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parents[2] / "tests" / "data" / "hms_structures"
DT = 300.0
for case in sys.argv[1:]:
    names = (DATA / f"{case}.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
    data = np.loadtxt(DATA / f"{case}.csv", delimiter=",", skiprows=1)
    s = {n: data[:, k] for k, n in enumerate(names)}
    i, o, st = s["inflow"], s["outflow"], s["storage_m3"]
    residual = np.diff(st) - DT * 0.5 * (i[1:] + i[:-1] - o[1:] - o[:-1])
    print(case, "residual m3 per step: min", residual.min(), "max", residual.max(), "rows 1..3", residual[:3])
    if "evaporation_m3" in s:
        print("   + evaporation:", np.abs(residual + s["evaporation_m3"][1:]).max())
    if "seepage" in s and "tailwater_m" in s:
        seep_in = np.interp(s["tailwater_m"] - s["elevation_m"], [0.0, 5.0, 25.0], [0.0, 0.2, 1.0])
        mean_in = 0.5 * (seep_in[1:] + seep_in[:-1]) * DT
        print("   - inflow seepage mean*dt:", np.abs(residual - mean_in).max(), "first", mean_in[:3])
