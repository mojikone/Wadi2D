"""HMS's culvert flow at its own pool levels against HDS-5 inlet control: fit c and Y of the submerged form, K and M
of the unsubmerged, from the steps where the culvert is in that regime (English units, as HMS's routine).

Usage: ``python fit_inlet.py <case> <rise m> <span m or 0 for a pipe> <barrels> <inlet invert> <slope>``.
"""

import sys
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parents[2] / "tests" / "data" / "hms_structures"
FT = 1.0 / 0.3048
CFS = FT**3
case, rise, span, barrels, invert, slope = sys.argv[1], *map(float, sys.argv[2:])
names = (DATA / f"{case}.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
data = np.loadtxt(DATA / f"{case}.csv", delimiter=",", skiprows=1)
s = {n: data[:, k] for k, n in enumerate(names)}
d = rise * FT
area = d * span * FT if span > 0 else np.pi * d * d / 4.0
hw = (s["elevation_m"] - invert) * FT
q = s["outlet_1"] * CFS / barrels
x = q / (area * np.sqrt(d))
for low, high, label in ((4.05, 99.0, "submerged"), (0.5, 3.45, "unsubmerged")):
    rows = (x > low) & (x < high)
    if rows.sum() < 3:
        print(label, "too few", rows.sum())
        continue
    if label == "submerged":
        c, y = np.polyfit(x[rows] ** 2, hw[rows] / d + 0.5 * slope, 1)
        resid = hw[rows] / d + 0.5 * slope - (c * x[rows] ** 2 + y)
        print(f"{label}: n {rows.sum()} X {x[rows].min():.2f}-{x[rows].max():.2f} c {c:.6f} Y {y:.6f} "
              f"resid {np.abs(resid).max():.2e}")
    else:
        m, logk = np.polyfit(np.log(x[rows]), np.log(hw[rows] / d), 1)
        print(f"{label} (form 2 fit): n {rows.sum()} X {x[rows].min():.2f}-{x[rows].max():.2f} K {np.exp(logk):.5f} "
              f"M {m:.5f}")
print("X range", x[x > 0].min(), x.max())
