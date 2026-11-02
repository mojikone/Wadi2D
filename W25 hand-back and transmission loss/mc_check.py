"""Is the Muskingum-Cunge volume gain the method's own? Route 20-minute triangles directly: no grid, no link.

python mc_check.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from wadi2d.hydrology.routing import MuskingumCunge

for name, mc in {
    "test reach 3 km": MuskingumCunge(3000.0, 0.01, 0.04, 10.0, 1.0, 2.0),
    "Block 2 R1 26 km": MuskingumCunge(26008.98, 0.01241, 0.1, 60.0, 0.7, 1.524),
    "Block 2 R6 4.3 km": MuskingumCunge(4259.46, 0.01474, 0.1, 30.0, 1.0, 1.524),
}.items():
    for dt_min in (1.0, 2.0, 5.0):
        for peak in (8.0, 80.0, 800.0):
            n = int(40 * 60 / dt_min)
            t = np.arange(n + 1) * dt_min
            q = np.interp(t, [0.0, 10.0, 20.0], [0.0, peak, 0.0])
            o = mc.route(q, dt_min)
            vin, vout = q.sum(), o.sum()
            print(
                f"{name:18s} dt {dt_min:3.0f} min peak {peak:6.0f}: out/in {vout / vin:.5f} tail {o[-1]:.2e}"
            )
