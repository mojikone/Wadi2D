"""HMS's drowned dam top as a fraction of free flow against submergence h2/h1: the breakpoints of a piecewise-linear
curve, found by the slope between neighbouring points (W59's level_dam_tw oracle).

Usage: ``python submergence_breaks.py [case crest length coefficient column]``.
"""

import sys
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parents[2] / "tests" / "data" / "hms_structures"
case, top, length, c, column = (sys.argv[1:] + [None] * 5)[:5]
case = case or "level_dam_tw"
top, length, c = float(top or 109.5), float(length or 150.0), float(c or 1.7)
column = column or "damtop_1"
names = (DATA / f"{case}.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
data = np.loadtxt(DATA / f"{case}.csv", delimiter=",", skiprows=1)
s = {n: data[:, k] for k, n in enumerate(names)}
z, tw, q = s["elevation_m"], s["tailwater_m"], s[column]
rows = np.flatnonzero((q > 0) & (z > top))
h1, h2 = z[rows] - top, tw[rows] - top
fraction = q[rows] / (c * length * h1**1.5)
sub = h2 / h1
order = np.argsort(sub)
sub, fraction = sub[order], fraction[order]
keep = np.concatenate(([True], np.diff(sub) > 1e-7))
sub, fraction = sub[keep], fraction[keep]
slope = np.diff(fraction) / np.diff(sub)
previous = None
for k in range(len(slope)):
    if previous is None or abs(slope[k] - previous) > 1e-3 * max(1.0, abs(previous)):
        print(f"from s {sub[k]:.6f} f {fraction[k]:.6f}: slope {slope[k]:.4f}")
    previous = slope[k]
print(f"last s {sub[-1]:.6f} f {fraction[-1]:.6f}; {len(sub)} points")
