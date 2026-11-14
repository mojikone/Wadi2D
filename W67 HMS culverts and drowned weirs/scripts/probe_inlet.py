"""The headwater HMS's culvert flows imply against HDS-5's forms, step by step: what K, Y and the slope term must be.

Usage: ``python probe_inlet.py <case> <rise> <span or 0> <barrels> <inlet invert> <slope> <K> <M> <c> <Y>``.
"""

import sys
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parents[2] / "tests" / "data" / "hms_structures"
FT = 1.0 / 0.3048
CFS = FT**3
G = 32.174
case = sys.argv[1]
rise, span, barrels, invert, slope, k, m, c, y = map(float, sys.argv[2:])
names = (DATA / f"{case}.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
data = np.loadtxt(DATA / f"{case}.csv", delimiter=",", skiprows=1)
s = {n: data[:, j] for j, n in enumerate(names)}
d = rise * FT
b = span * FT
area = d * b if span > 0 else np.pi * d * d / 4.0
hw = (s["elevation_m"] - invert) * FT
q = s["outlet_1"] * CFS / barrels
x = q / (area * np.sqrt(d))


def critical_head(flow: float) -> float:
    if span > 0:
        dc = (flow**2 / (G * b * b)) ** (1.0 / 3.0)
        return 1.5 * dc
    r = d / 2.0
    lo, hi = 1e-9, d * 0.999999
    for _ in range(200):
        yc = 0.5 * (lo + hi)
        theta = 2.0 * np.arccos(1.0 - yc / r)
        a = r * r * (theta - np.sin(theta)) / 2.0
        t = 2.0 * r * np.sin(theta / 2.0)
        if flow**2 / G > a**3 / t:
            lo = yc
        else:
            hi = yc
    return yc + a / (2.0 * t)


for j in np.flatnonzero(q > 0)[:: max(1, int(np.sum(q > 0)) // 25)]:
    hc = critical_head(q[j])
    unsub1 = hc / d + k * x[j] ** m - 0.5 * slope
    unsub2 = k * x[j] ** m
    sub = c * x[j] ** 2 + y - 0.5 * slope
    print(f"X {x[j]:6.3f} HW/D {hw[j] / d:8.5f} form1 {unsub1:8.5f} form2 {unsub2:8.5f} sub {sub:8.5f} "
          f"Hc/D {hc / d:.4f}")
