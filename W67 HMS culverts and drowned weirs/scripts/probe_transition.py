"""HMS's inlet-control headwater between Q/(A D^0.5) = 3.5 and 4.0 against two readings of HDS-5's interpolation:
the end values of the two forms joined by a line, or the two forms blended at the same ratio.

Usage: ``python probe_transition.py <case> <chart> <scale> <rise> <span or 0> <inlet>``.
"""

import sys
from pathlib import Path

import numpy as np

from wadi2d.hydrology import culvert as cv

DATA = Path(__file__).resolve().parents[2] / "tests" / "data" / "hms_structures"
FT = cv.FEET_PER_METRE
case = sys.argv[1]
chart, scale = int(sys.argv[2]), int(sys.argv[3])
rise, span, inlet = map(float, sys.argv[4:7])
shape = cv.BOX if span > 0 else cv.CIRCULAR
pipe = cv.Barrel(shape, rise * FT, (span or rise) * FT, 40 * FT, inlet * FT, 100 * FT, 0.013, 0.5, 1.0)
spec = cv.INLET_CHARTS[chart, scale]
names = (DATA / f"{case}.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
data = np.loadtxt(DATA / f"{case}.csv", delimiter=",", skiprows=1)
s = {n: data[:, j] for j, n in enumerate(names)}
flow = s["outlet_1"] * cv.CFS_PER_M3S / 2
hw = (s["elevation_m"] - inlet) * FT / pipe.rise
x = flow / (pipe.full_area * np.sqrt(pipe.rise))
band = np.flatnonzero((x > 3.45) & (x < 4.05))
slope_term = cv.SLOPE_TERM * pipe.slope if spec.form == 1 else 0.0


def form(q_ratio: float, submerged: bool) -> float:
    saved = cv.UNSUBMERGED_BELOW, cv.SUBMERGED_ABOVE
    cv.UNSUBMERGED_BELOW, cv.SUBMERGED_ABOVE = (-1.0, -1.0) if submerged else (99.0, 99.0)
    try:
        return cv._inlet(pipe, spec, q_ratio * pipe.full_area * np.sqrt(pipe.rise)) / pipe.rise
    finally:
        cv.UNSUBMERGED_BELOW, cv.SUBMERGED_ABOVE = saved


for j in band:
    share = (x[j] - 3.5) / 0.5
    ends = form(3.5, False) + share * (form(4.0, True) - form(3.5, False))
    blend = form(x[j], False) + share * (form(x[j], True) - form(x[j], False))
    print(f"X {x[j]:.4f} HMS {hw[j]:.6f} ends {ends:.6f} blend {blend:.6f} unsub {form(x[j], False):.6f} "
          f"sub {form(x[j], True):.6f}")
