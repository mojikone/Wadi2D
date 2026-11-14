"""W70 GPU check: the steep plane of the tests (3 %, 50 m3/s across the west edge) on the GPU against the CPU.

    python "W70 inflow line momentum\\gpu_check.py" <out folder>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.engine.conftest import X0, Y0, job, tilted_box, write_dem  # noqa: E402
from wadi2d.run import run_job  # noqa: E402


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    cells, q, slope = 12, 50.0, 0.03
    dem = write_dem(out / "steep.tif", tilted_box(200, 2 * cells, 2.0, slope), 2.0)
    west = [(X0 + 2.0, Y0 - 1.0), (X0 + 2.0, Y0 - 4.0 * cells + 1.0)]
    outlet = {"kind": "free", "coordinates": [(X0 + 398.0, Y0 + 2.0), (X0 + 398.0, Y0 - 4.0 * cells - 2.0)]}
    found = {}
    for backend in ("cpu", "gpu"):
        line = {"kind": "flow", "coordinates": west, "flow": {"times_s": [0.0, 1e5], "flows": [q, q], "slope": slope}}
        cfg = job(
            dem, 100, cells, 4.0, terrain={"manning": 0.04}, boundaries=[line, outlet],
            run={"duration_s": 600.0, "backend": backend, "source_every_s": 10.0},
            outputs={"map_every_s": 300.0, "series_every_s": 60.0},
        )  # fmt: skip
        run = run_job(cfg, out / backend)
        assert run.exit_code == 0, run.message
        with h5py.File(out / backend / "results.h5", "r") as f:
            last = max(f["maps"], key=lambda k: f["maps"][k].attrs["t_s"])
            h = f["maps"][last]["mean_depth"][()][:cells, :100].mean(axis=0)
        first = int(np.argmax(h > 0.0))
        found[backend] = {"line_cell_over_far": float(h[first] / h[62]), "far_m": float(h[62]),
                          "balance": run.balance.relative, "profile": h[first : first + 6].round(4).tolist()}  # fmt: skip
    found["max_abs_diff_m"] = float(np.max(np.abs(np.array(found["cpu"]["profile"]) - np.array(found["gpu"]["profile"]))))
    (Path(__file__).parent / "gpu_check.json").write_text(json.dumps(found, indent=1), encoding="utf-8")
    print(json.dumps(found, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
