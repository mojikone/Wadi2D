"""Where a case parts from HMS: the pool difference over time, a few rows."""

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parent / "tests" / "hydrology"))
from test_hms_structures import load_case, reservoir_of  # noqa: E402

case = sys.argv[1]
hms = load_case(case)
run = reservoir_of(case).run(hms["inflow"], 5.0)
dz = run.pool_m - hms["elevation_m"]
print("max |dz|", np.abs(dz).max(), "at", np.argmax(np.abs(dz)))
for k in sorted({0, 1, 2, 3, 5, 10, 20, 40, 60, 72, 100, 140, 144, 145, 150, 200, 300, 576, int(np.argmax(np.abs(dz)))}):
    evap = run.evaporation_m3s[k] * 300.0
    print(f"{k:4d} z {hms['elevation_m'][k]:.6f} dz {dz[k]:+.3e} Q {hms['outflow'][k]:9.4f} dQ {run.main_m3s[k] - hms['outflow'][k]:+.3e}"
          f" in {hms['inflow'][k]:8.3f} evap/step ours {evap:8.3f} hms {hms.get('evaporation_m3', np.zeros(1))[min(k, len(hms['inflow']) - 1)]:8.3f}")
