"""The part-full barrel that reaches its crown (normal depth at or over the rise): HMS's pool against Wadi2D's with
the direct step cut into different numbers of depth increments. Long box of W67, box_oc case.

Usage: ``python probe_profile.py``.
"""

from pathlib import Path

import numpy as np

from wadi2d.hydrology import culvert as cv

DATA = Path(__file__).resolve().parents[2] / "tests" / "data" / "hms_structures"
FT = cv.FEET_PER_METRE
pipe = cv.Barrel(cv.BOX, 3 * FT, 3 * FT, 300 * FT, 100.3 * FT, 100 * FT, 0.02, 0.5, 1.0)
names = (DATA / "culvert_box_oc.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
data = np.loadtxt(DATA / "culvert_box_oc.csv", delimiter=",", skiprows=1)
s = {n: data[:, j] for j, n in enumerate(names)}
flow = s["outlet_1"] * cv.CFS_PER_M3S / 2
pool = s["elevation_m"] * FT
rows = [j for j in range(len(flow)) if flow[j] > 0 and cv.normal_depth(pipe, flow[j]) >= pipe.rise]
for j in rows[:: max(1, len(rows) // 15)]:
    print(f"Q {s['outlet_1'][j]:7.3f} HMS {(pool[j] - pipe.inlet) / FT:.4f} gap "
          f"{(cv._outlet(pipe, flow[j], -np.inf)[0] - pool[j]) / FT:+.4f} dc {cv.critical_depth(pipe, flow[j]) / FT:.3f}")
for steps in (5, 10, 15, 20, 50, 400, 4000):
    cv.PROFILE_STEPS = steps
    gaps = [(cv._outlet(pipe, flow[j], -np.inf)[0] - pool[j]) / FT for j in rows]
    print(f"steps {steps:5d}: ours - HMS, m: max {max(gaps):+.4f} min {min(gaps):+.4f} mean {np.mean(gaps):+.4f}")
