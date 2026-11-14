"""Wadi2D's culvert rating at HMS's own pool levels against HMS's culvert flow, every W67 culvert case: the law alone,
with no routing in between. Prints the worst difference, relative to the case's peak culvert flow, and where.

Usage: ``python probe_culvert.py [case ...]``.
"""

import sys
from pathlib import Path

import numpy as np

from wadi2d.hydrology import culvert as cv

DATA = Path(__file__).resolve().parents[2] / "tests" / "data" / "hms_structures"
FT = cv.FEET_PER_METRE


def barrel(shape, rise, span, length, inlet, n, outlet=100.0, entrance=0.5, exit_=1.0):
    return cv.Barrel(shape, rise * FT, span * FT, length * FT, inlet * FT, outlet * FT, n, entrance, exit_)


BOX_SHORT = barrel(cv.BOX, 3, 3, 40, 100.5, 0.013)
BOX_LONG = barrel(cv.BOX, 3, 3, 300, 100.3, 0.02)
PIPE_SHORT = barrel(cv.CIRCULAR, 2.5, 2.5, 40, 100.5, 0.013)
PIPE_LONG = barrel(cv.CIRCULAR, 2.5, 2.5, 250, 100.3, 0.024)
CASES = {
    "culvert_box_ic": (BOX_SHORT, (8, 1), cv.INLET_CONTROL, None),
    "culvert_box_form2": (BOX_SHORT, (10, 2), cv.INLET_CONTROL, None),
    "culvert_box_auto": (BOX_LONG, (8, 1), cv.AUTOMATIC, None),
    "culvert_box_oc": (BOX_LONG, (8, 1), cv.OUTLET_CONTROL, None),
    "culvert_box_tw_full": (BOX_LONG, (8, 1), cv.AUTOMATIC, 104.0),
    "culvert_box_tw_part": (BOX_LONG, (8, 1), cv.AUTOMATIC, 101.5),
    "culvert_pipe_ic": (PIPE_SHORT, (1, 1), cv.INLET_CONTROL, None),
    "culvert_pipe_auto": (PIPE_LONG, (2, 3), cv.AUTOMATIC, 101.5),
}

for chart, scale in cv.INLET_CHARTS:
    shape = PIPE_SHORT if cv.INLET_CHARTS[chart, scale].shape == cv.CIRCULAR else BOX_SHORT
    if (DATA / f"culvert_chart_{chart}_{scale}.csv").exists():
        CASES[f"culvert_chart_{chart}_{scale}"] = (shape, (chart, scale), cv.INLET_CONTROL, None)

for case in sys.argv[1:] or CASES:
    pipe, chart, control, tailwater = CASES[case]
    names = (DATA / f"{case}.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
    data = np.loadtxt(DATA / f"{case}.csv", delimiter=",", skiprows=1)
    s = {n: data[:, j] for j, n in enumerate(names)}
    levels, flows = cv.rating(pipe, cv.INLET_CHARTS[chart], control, 2, tailwater, 126.0)
    ours = np.interp(s["elevation_m"], levels, flows)
    hms = s["outlet_1"]
    gap = ours - hms
    worst = int(np.argmax(np.abs(gap)))
    print(f"{case:22s} peak {hms.max():8.3f} worst {gap[worst] / hms.max():+.2e} at pool {s['elevation_m'][worst]:.3f} "
          f"(HMS {hms[worst]:.3f}, ours {ours[worst]:.3f}); median |gap| {np.median(np.abs(gap)) / hms.max():.1e}")
