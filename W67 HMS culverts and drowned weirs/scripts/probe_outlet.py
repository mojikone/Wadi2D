"""HMS's outlet-control pool against the pieces of Wadi2D's: at HMS's flow, critical, normal and inlet depth, the
barrel velocity head, and what pool each reading gives. Box, 2 barrels (the W67 long box).

Usage: ``python probe_outlet.py <case> [tailwater]``.
"""

import sys
from pathlib import Path

import numpy as np

from wadi2d.hydrology import culvert as cv

DATA = Path(__file__).resolve().parents[2] / "tests" / "data" / "hms_structures"
FT = cv.FEET_PER_METRE
case = sys.argv[1]
tailwater = float(sys.argv[2]) * FT if len(sys.argv) > 2 else -np.inf
pipe = cv.Barrel(cv.BOX, 3 * FT, 3 * FT, 300 * FT, 100.3 * FT, 100 * FT, 0.02, 0.5, 1.0)
if "pipe" in case:
    pipe = cv.Barrel(cv.CIRCULAR, 2.5 * FT, 2.5 * FT, 250 * FT, 100.3 * FT, 100 * FT, 0.024, 0.5, 1.0)
names = (DATA / f"{case}.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
data = np.loadtxt(DATA / f"{case}.csv", delimiter=",", skiprows=1)
s = {n: data[:, j] for j, n in enumerate(names)}
flow = s["outlet_1"] * cv.CFS_PER_M3S / 2
pool = s["elevation_m"] * FT
for j in np.flatnonzero(flow > 0)[:: max(1, int(np.sum(flow > 0)) // 30)]:
    q = flow[j]
    dc = cv.critical_depth(pipe, q)
    yn = cv.normal_depth(pipe, q)
    ours = cv._outlet(pipe, q, tailwater)[0]
    print(f"Q {q / cv.CFS_PER_M3S:7.3f} m3s HMS pool-zin {(pool[j] - pipe.inlet) / FT:7.4f} m ours "
          f"{(ours - pipe.inlet) / FT:7.4f} dc {dc / FT:.3f} yn {yn / FT:.3f} V2/2g full "
          f"{(q / pipe.full_area) ** 2 / 64.348 / FT:.3f}")
