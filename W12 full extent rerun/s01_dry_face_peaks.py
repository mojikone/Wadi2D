"""Why every full-extent peak rose against W2: the Block 2 job at the same 30 m, with the dry-face fix on and off.

Writes s01_dry_face_peaks.json beside this file. If the change with the fix switched off explains the rise, the sign of
the expected effect in the README was simply wrong; if it does not, something else moved between the two engines.
"""

import json
from pathlib import Path

import h5py
import numpy as np

from wadi2d.run import load_job, run_job

HERE = Path(__file__).resolve().parent
JOB = HERE.parent / "W1 research and design note/validation/block2_full/jobs/c20_A74_h200.json"
HOURS = 16.0
DX = 30.0


def peaks(path: Path) -> dict[str, float]:
    with h5py.File(path, "r") as f:
        g = f["series/lines"]
        return {name: float(np.abs(g[name]["discharge_m3s"][()]).max()) for name in g}


def main() -> None:
    out = {}
    for name, mirror in (("fix_on", True), ("fix_off", False)):
        data = load_job(JOB).model_dump(mode="json")
        data["grid"]["dx"] = DX
        data["grid"]["cache_dir"] = str(HERE / "runs" / "cache")
        data["run"]["duration_s"] = HOURS * 3600.0
        data["outputs"]["map_every_s"] = 0.0
        data["outputs"]["pixels"]["enabled"] = False
        data["numerics"]["mirror_dry_faces"] = mirror
        folder = HERE / "runs" / f"block2_{name}"
        run = run_job(type(load_job(JOB)).model_validate(data), folder)
        if run.exit_code:
            raise RuntimeError(run.message)
        out[name] = {"steps": run.steps, "loop_s": round(run.loop_s, 1), "peaks": peaks(folder / "results.h5")}
        print(name, out[name]["steps"], out[name]["loop_s"], flush=True)
    change = {k: round(100.0 * (v / out["fix_off"]["peaks"][k] - 1.0), 2) for k, v in out["fix_on"]["peaks"].items()}
    out["change_pct"] = change
    (HERE / "s01_dry_face_peaks.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(change)


if __name__ == "__main__":
    main()
