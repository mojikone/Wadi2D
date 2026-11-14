"""W70 old-numbers check: the same two jobs run on any checkout, every output array and series file hashed.

    python "W70 inflow line momentum\\old_numbers.py" <checkout root> <out folder>

Job A has no flow line (a normal and a free boundary, a point inflow, uniform rain); job B has W61's flow line with
the momentum switched off where the checkout knows the switch. Run on the base commit and on this branch, the two
JSON files must be identical: then a job without flow lines, and a flow line at rest, give W61's numbers to the digit.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))

import h5py  # noqa: E402
import numpy as np  # noqa: E402

from tests.engine.conftest import X0, Y0, job, tilted_box, write_dem  # noqa: E402
from wadi2d.config.schema import FlowHydrograph  # noqa: E402
from wadi2d.run import run_job  # noqa: E402


def digest(run_dir: Path) -> dict:
    out = {}
    with h5py.File(run_dir / "results.h5", "r") as f:
        def visit(name, obj):
            if isinstance(obj, h5py.Dataset) and not name.startswith("series"):
                out[name] = hashlib.sha256(np.ascontiguousarray(obj[()]).tobytes()).hexdigest()

        f.visititems(visit)
    for csv in sorted((run_dir / "series").glob("*.csv")):
        out[f"series/{csv.name}"] = hashlib.sha256(csv.read_bytes()).hexdigest()
    return out


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    dem = write_dem(out / "plane.tif", tilted_box(200, 48, 2.0, 0.01), 2.0)
    west = [(X0 + 2.0, Y0 - 1.0), (X0 + 2.0, Y0 - 95.0)]
    outlet = {"kind": "free", "coordinates": [(X0 + 398.0, Y0 + 2.0), (X0 + 398.0, Y0 - 98.0)]}
    common = {
        "terrain": {"manning": 0.04},
        "outputs": {"map_every_s": 300.0, "series_every_s": 60.0,
                    "points": [{"name": "mid", "x": X0 + 250.0, "y": Y0 - 48.0}]},
    }  # fmt: skip
    a = job(
        dem, 100, 24, 4.0, **common,
        boundaries=[{"kind": "normal", "coordinates": west, "slope": 0.01}, outlet],
        hydrology={"inflows": [{"name": "p", "x": X0 + 60.0, "y": Y0 - 48.0, "times_s": [0.0, 300.0, 900.0],
                                "flows": [0.0, 5.0, 0.0]}]},
        storm={"kind": "uniform", "depth_mm": 30.0, "duration_min": 20.0},
        run={"duration_s": 1200.0, "backend": "cpu", "source_every_s": 10.0},
    )  # fmt: skip
    flow = {"times_s": [0.0, 1e5], "flows": [20.0, 20.0], "slope": 0.01}
    if "momentum" in FlowHydrograph.model_fields:
        flow["momentum"] = False
    b = job(
        dem, 100, 24, 4.0, **common, boundaries=[{"kind": "flow", "coordinates": west, "flow": flow}, outlet],
        run={"duration_s": 1200.0, "backend": "cpu", "source_every_s": 10.0},
    )  # fmt: skip
    result = {}
    for name, cfg in (("no_flow_line", a), ("flow_line_at_rest", b)):
        run = run_job(cfg, out / name)
        assert run.exit_code == 0, run.message
        result[name] = {"steps": run.steps if hasattr(run, "steps") else None, "arrays": digest(out / name)}
    (out / "digest.json").write_text(json.dumps(result, indent=1, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[2]))
