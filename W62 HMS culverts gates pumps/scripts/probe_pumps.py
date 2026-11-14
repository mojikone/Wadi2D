"""Each pump case: the head law's fit when on, where the pump switches (step, time, pool, flow), and HMS's books.

``unbooked`` is storage change minus the trapezoid of inflow less outflow, m3, over the run: zero when HMS's books
close. Usage: ``python probe_pumps.py [case ...]``.
"""

import sys

import fit_gates as f
import numpy as np
from hms_cases import NEW_CASES, PUMP_HEAD, PUMP_Q

DT = 300.0

for case in sys.argv[1:] or [c for c in NEW_CASES if c.startswith("pump")]:
    hms = f.load(case)
    units = int(NEW_CASES[case][1].split("Number Of Pumps: ")[1].split("\n")[0])
    z, q = hms["elevation_m"], hms["pump_1"]
    model = units * np.interp(112 - z + 0.5, PUMP_HEAD, PUMP_Q)
    on = q > 0
    balance = np.diff(hms["storage_m3"]) - DT * 0.5 * (
        hms["inflow"][1:] + hms["inflow"][:-1] - hms["outflow"][1:] - hms["outflow"][:-1]
    )
    worst = (np.abs(model - q)[on] / q[on]).max() if on.any() else float("nan")
    print(f"{case}: on {on.sum()} steps, head law worst rel {worst:.1e}, unbooked {balance.sum():.0f} m3")
    for k in np.flatnonzero(np.diff(on.astype(int))):
        print(f"   {'ON ' if on[k + 1] else 'OFF'} step {k + 1} t {(k + 1) * 5 / 60:6.3f} h  "
              f"z {z[k]:.5f} -> {z[k + 1]:.5f}  q {q[k]:.3f} -> {q[k + 1]:.3f}")
