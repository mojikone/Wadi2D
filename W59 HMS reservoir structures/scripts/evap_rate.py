"""HMS's evaporation per step over the area, as mm per day, at chosen steps."""

import sys
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parents[2] / "tests" / "data" / "hms_structures"
case = sys.argv[1]
names = (DATA / f"{case}.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
data = np.loadtxt(DATA / f"{case}.csv", delimiter=",", skiprows=1)
s = {n: data[:, k] for k, n in enumerate(names)}
per_day = 288.0
for k in [1, 2, 50, 140, 143, 144, 145, 146, 150, 200, 400, 575, 576]:
    for label, area in (("end", s["area_m2"][k]), ("start", s["area_m2"][k - 1]), ("mean", 0.5 * (s["area_m2"][k] + s["area_m2"][k - 1]))):
        print(f"step {k:3d} {label:5s} {s['evaporation_m3'][k] / area * per_day * 1000.0:10.6f} mm/day", end="  ")
    print()
print("Jan 300/31", 300 / 31, "Feb 450/29", 450 / 29, "Feb 450/28", 450 / 28, "Feb 450/30", 450 / 30)
