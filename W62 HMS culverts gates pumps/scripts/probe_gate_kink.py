"""Does bisecting the steps that cross a gate's regime boundary (head = 1 or 1.25 openings) bring the gate cases
nearer HMS? A probe of HMS's sub-stepping near the kink, on a copy of the kernel's step with that extra test; the
engine is not changed by it. Run from the repository root with PYTHONPATH=.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path("tests/hydrology").resolve()))
from test_hms_structures import load_case, reservoir_of

import wadi2d.hydrology.structure_kernel as k

source = Path(k.__file__).read_text(encoding="utf-8")
old = "if (above or abs(solved - level) > level_change_limit) and depth < max_bisections:"
new = ("if (above or abs(solved - level) > level_change_limit or _crosses(level, solved, kinds, parameters)) "
       "and depth < max_bisections:")
helper = '''
@njit(cache=False)
def _crosses(a, b, kinds, parameters):
    for i in range(len(kinds)):
        if kinds[i] == GATE:
            lo, hi = min(a, b), max(a, b)
            for edge in (GATE_WEIR_BELOW, GATE_LAW_ABOVE):
                z = parameters[i, 0] + edge * parameters[i, 3]
                if lo < z < hi:
                    return True
    return False

'''
probe = source.replace(old, new).replace("@njit(cache=True)\ndef route_structures(", helper + "@njit(cache=True)\ndef route_structures(")
probe = probe.replace("cache=True", "cache=False")
namespace: dict = {"__name__": "probe_kernel"}
exec(compile(probe, "probe_kernel", "exec"), namespace)

for depth_limit in (8, 12):
    for case in ("gate_sluice", "gate_radial", "gate_two"):
        hms = load_case(case)
        routing = reservoir_of(case)
        import wadi2d.hydrology.reservoir as reservoir_module

        reservoir_module.route_structures = namespace["route_structures"]
        run = routing.run(hms["inflow"], 5.0) if depth_limit == 8 else type(routing).run(
            __import__("dataclasses").replace(routing, max_bisections=depth_limit), hms["inflow"], 5.0)
        peak = np.abs(hms["outflow"]).max()
        print(depth_limit, case, "dQ of peak", np.abs(run.main_m3s - hms["outflow"]).max() / peak,
              "dz", np.abs(run.pool_m - hms["elevation_m"]).max())
