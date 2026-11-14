"""Is HMS's ELEVATION its STORAGE read back through the table? Per case, and the evaporation it books."""

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parent / "tests" / "hydrology"))
from test_hms_structures import load_case, reservoir_of  # noqa: E402

for case in sys.argv[1:]:
    hms = load_case(case)
    routing = reservoir_of(case)
    back = np.interp(hms["storage_m3"], routing.storage_m3, routing.elevations_m)
    print(case, "max |z(S) - z|", np.abs(back - hms["elevation_m"]).max(), "rows 1..3", (back - hms["elevation_m"])[1:4])
    dt = 300.0
    i, o, s = hms["inflow"], hms["outflow"], hms["storage_m3"]
    residual = np.diff(s) - dt * 0.5 * (i[1:] + i[:-1] - o[1:] - o[:-1])
    if "evaporation_m3" in hms:
        print("   residual rows 1..4", residual[:4], "evaporation", hms["evaporation_m3"][1:5])
        extra = residual + hms["evaporation_m3"][1:]
        print("   unbooked loss: total", extra.sum(), "of inflow volume", dt * np.trapezoid(i) , "; by row 50", extra[:50].sum(),
              "; rows 50.. ", extra[50:].sum(), "; largest", extra.min(), extra.max(), "at", np.argmin(extra), np.argmax(extra))
