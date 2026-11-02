"""The full-extent job itself, cut to the Block 2 domain, with the dry-face fix on and off.

s01 moved the five dams by +0.06 to +0.85 % on Block 2's own terrain and a smaller storm, against +0.23 to +3.62 % between W2
and this rerun. This run keeps the rerun's terrain, storm, losses and Manning, so only the domain differs from it. If the fix
then gives the rise, s01 was too small a flood to show it; if not, something else moved between the two engines.
Writes s02_same_ground.json beside this file.
"""

import json
from pathlib import Path

import h5py
import numpy as np

from wadi2d.config.schema import RunConfig
from wadi2d.run import load_job, run_job

HERE = Path(__file__).resolve().parent
JOB = HERE / "jobs/full_30m_200yr.json"
BLOCK2 = HERE.parent / "W1 research and design note/validation/block2_full/jobs/c20_A74_h200.json"
HOURS = 16.0


def peaks(path: Path) -> dict[str, float]:
    with h5py.File(path, "r") as f:
        g = f["series/lines"]
        return {name: float(np.abs(g[name]["discharge_m3s"][()]).max()) for name in g}


def main() -> None:
    block2 = load_job(BLOCK2).model_dump(mode="json")
    out = {}
    for name, mirror in (("fix_on", True), ("fix_off", False)):
        data = load_job(JOB).model_dump(mode="json")
        data["grid"]["domain"] = block2["grid"]["domain"]
        data["grid"]["cache_dir"] = str(HERE / "runs" / "cache_same_ground")
        data["boundaries"] = block2["boundaries"]
        data["run"]["duration_s"] = HOURS * 3600.0
        data["outputs"]["map_every_s"] = 0.0
        data["outputs"]["pixels"]["enabled"] = False
        data["outputs"]["smooth"]["enabled"] = False
        data["numerics"]["mirror_dry_faces"] = mirror
        folder = HERE / "runs" / f"same_ground_{name}"
        run = run_job(RunConfig.model_validate(data), folder)
        if run.exit_code:
            raise RuntimeError(run.message)
        out[name] = {"steps": run.steps, "loop_s": round(run.loop_s, 1), "peaks": peaks(folder / "results.h5")}
        print(name, out[name]["steps"], out[name]["loop_s"], flush=True)
    change = {k: round(100.0 * (v / out["fix_off"]["peaks"][k] - 1.0), 2) for k, v in out["fix_on"]["peaks"].items()}
    out["change_pct"] = change
    (HERE / "s02_same_ground.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(change)


if __name__ == "__main__":
    main()
