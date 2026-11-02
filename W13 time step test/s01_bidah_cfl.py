"""Does a rain-on-grid peak depend on the time step? Bidah at 20 m, the job of the HEC-RAS head-to-head, smaller and smaller steps.

Writes results.json beside this file. Rule, fixed before the first run: the peak at the axis moves by under 2 % from the
default step to a quarter of it: the step does not matter for a design peak. Otherwise the cause is found first.
"""

import json
import sys
from pathlib import Path

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from wadi2d.config.schema import RunConfig  # noqa: E402
from wadi2d.run import run_job  # noqa: E402

JOB = HERE.parent / "W1 research and design note/validation/ras_rain_on_grid/jobs/20m_n050_em.json"
CASES = (
    ("cfl_0450", {"cfl": 0.45}),
    ("cfl_0225", {"cfl": 0.225}),
    ("cfl_0113", {"cfl": 0.1125}),
    ("cfl_0056", {"cfl": 0.05625}),
)
HOURS = 18.0


def peak(path: Path, name: str) -> tuple[float, float, float]:
    with h5py.File(path, "r") as f:
        group = f[f"series/lines/{name}"]
        q = np.abs(group["discharge_m3s"][()])
        t = group["t_s"][()] if "t_s" in group else f["series/t_s"][()]
    k = int(np.argmax(q))
    volume = float(np.trapezoid(q, t))
    return float(q[k]), float(t[k]) / 3600.0, volume / 1e6


def main() -> None:
    results = []
    for name, numerics in CASES:
        data = json.loads(JOB.read_text(encoding="utf-8"))
        data["numerics"] = numerics
        data["run"]["duration_s"] = HOURS * 3600.0
        data["grid"]["cache_dir"] = str(HERE / "cache")
        out = HERE / "runs" / name
        run = run_job(RunConfig.model_validate(data), out)
        if run.exit_code:
            raise RuntimeError(run.message)
        row = {
            "case": name,
            **numerics,
            "steps": run.steps,
            "mean_dt_s": round(run.t_end / run.steps, 3),
            "mass_error": run.balance.error if hasattr(run.balance, "error") else None,
        }
        for line in ("axis", "s13_edge"):
            q, hour, volume = peak(out / "results.h5", line)
            row[line] = {"peak_m3s": round(q, 2), "hour": round(hour, 3), "volume_Mm3": round(volume, 4)}
        results.append(row)
        print(row, flush=True)
        (HERE / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
