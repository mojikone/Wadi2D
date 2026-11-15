"""W87: the steady channel numbers of the strips and polygon tests, printed in full, so the code before and after the
step was bounded can be compared to the digit. Below the cap of 25 m/s the bound changes nothing, and W3's channel
runs at about 2 m/s.

    set PYTHONPATH=<source tree with wadi2d>;<this repository, for tests>
    .venv\\Scripts\\python "W87 strip max speed\\channel_values.py" <out.json>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import wadi2d
from tests.solver.test_poly import run_channel
from tests.strips.test_centres import run_centre_channel
from tests.strips.test_hybrid import run_hybrid_channel

if __name__ == "__main__":
    found = {"wadi2d": Path(wadi2d.__file__).parent.parent.name}
    for theta in (0.0, 45.0):
        depth, steps = run_channel(theta, "polygons")
        found[f"polygons_{theta:g}"] = [repr(depth), steps]
        depth, steps = run_hybrid_channel(theta)
        found[f"patch_in_tiles_{theta:g}"] = [repr(depth), steps]
        found[f"centre_mesh_{theta:g}"] = [repr(v) for v in run_centre_channel(theta)]
    text = json.dumps(found, indent=1)
    print(text)
    Path(sys.argv[1]).write_text(text, encoding="utf-8")
