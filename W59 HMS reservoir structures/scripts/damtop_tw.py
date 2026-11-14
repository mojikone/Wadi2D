"""The drowned dam top: HMS's flow as a fraction of free flow against the submergence h2/h1, level_dam_tw case."""

from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parents[2] / "tests" / "data" / "hms_structures"
TOP, LENGTH, C = 109.5, 150.0, 1.7
names = (DATA / "level_dam_tw.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
data = np.loadtxt(DATA / "level_dam_tw.csv", delimiter=",", skiprows=1)
s = {n: data[:, k] for k, n in enumerate(names)}
z, tw, q = s["elevation_m"], s["tailwater_m"], s["damtop_1"]
rows = np.flatnonzero(q > 0)
h1, h2 = z[rows] - TOP, tw[rows] - TOP
fraction = q[rows] / (C * LENGTH * h1**1.5)
sub = h2 / h1
order = np.argsort(sub)
villemonte = (1.0 - sub**1.5) ** 0.385
for k in order[:: max(1, len(order) // 14)]:
    print(f"s {sub[k]:.6f} f {fraction[k]:.6f} villemonte {villemonte[k]:.6f} (1-s) {1 - sub[k]:.3e}")
slope, intercept = np.polyfit(np.log(1.0 - sub), np.log(fraction), 1)
print(f"log f = {slope:.4f} log(1 - s) + {intercept:.4f}; max residual "
      f"{np.abs(np.log(fraction) - slope * np.log(1 - sub) - intercept).max():.3e}")
