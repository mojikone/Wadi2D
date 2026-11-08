"""The race of W46 on Faydh 01 at 20 m: the centre generator against no lines and against W45's ring corridors.

W45's rule: the dam-axis peak within 3 % of the run with no lines. The job is W45's race base (W11's rain-on-grid job
at 20 m, 16 h, no maps); the centre job sets ``strips.generator: centres`` with the W26 Faydh suggestion file, whose
thalwegs are the guide lines, and the floor rule at the schema's defaults. The no-lines and the ring runs are read
from W45's race folder, not rerun.

    .venv\\Scripts\\python "W46 centre-based mesh generator\\race_faydh_centres.py" <work folder> [build|run|report|all] [cpu|gpu] [--tag <name>]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "W45 aligned mesh engine"))
from race_faydh import RULE, W26, base, peak, run  # noqa: E402

W45_RACE = ROOT / "W45 aligned mesh engine" / "race_faydh"


def name_of(backend: str, tag: str) -> str:
    return "faydh20_centres" + ("_gpu" if backend == "gpu" else "") + (f"_{tag}" if tag else "")


def build(work: Path, backend: str, tag: str, floor: dict | None = None, strips: dict | None = None) -> None:
    """``floor`` overrides fields of the job's breaklines section (the bank rule), ``strips`` fields of its strips."""
    work.mkdir(parents=True, exist_ok=True)
    job = base(work, backend)
    job["strips"] = {"enabled": True, "generator": "centres", "banks": str(W26), "along": 20.0} | (strips or {})
    if floor:
        job["breaklines"] = job.get("breaklines", {}) | floor
    (work / f"{name_of(backend, tag)}.json").write_text(json.dumps(job, indent=1), encoding="utf-8")
    print("job written:", name_of(backend, tag), "floor", floor or "defaults", "strips", strips or "defaults")


def report(work: Path, backend: str, tag: str) -> None:
    name = name_of(backend, tag)
    suffix = "_gpu" if backend == "gpu" else ""
    out = {}
    for label, folder in (("none", W45_RACE / f"faydh20_none{suffix}"), ("rings", W45_RACE / f"faydh20_strips{suffix}"), ("centres", work / name)):
        if not (folder / "progress.jsonl").is_file():
            print(f"{label}: no run at {folder}")
            continue
        lines = (folder / "progress.jsonl").read_text(encoding="utf-8").splitlines()
        done = [json.loads(s) for s in lines if '"done"' in s[:14]]
        built = [json.loads(s) for s in lines if '"ev": "strips"' in s]
        p, at = peak(folder, "axis")
        out[label] = {"axis_peak_m3s": p, "at_h": at, "steps": done[-1]["steps"], "loop_s": done[-1]["loop_s"], "mass_error": done[-1]["balance"]["relative_error"]}
        if built:
            s = built[-1]
            out[label]["strips"] = {k: s.get(k) for k in ("corridors", "cells", "triangles", "replaced")} | {"cut": len(s.get("cut", []))}
        print(f"{label}: axis peak {p:.1f} m3/s at {at:.2f} h, {done[-1]['steps']} steps, {done[-1]['loop_s']:.0f} s, mass error {done[-1]['balance']['relative_error']:.1e}"
              + (f"; strip cells {built[-1]['cells']}, squares replaced {built[-1]['replaced']}" if built else ""))
    if "none" in out and "centres" in out:
        ratio = out["centres"]["axis_peak_m3s"] / out["none"]["axis_peak_m3s"]
        out["centres_against_none"] = ratio
        print(f"centres against no lines: {ratio:.4f} ({100 * (ratio - 1):+.1f} %); the rule is {100 * RULE:.0f} %: {'PASS' if abs(ratio - 1) <= RULE else 'FAIL'}")
    if "rings" in out and "centres" in out:
        out["rings_against_none"] = out["rings"]["axis_peak_m3s"] / out["none"]["axis_peak_m3s"] if "none" in out else None
        print(f"rings against no lines: {out['rings_against_none']:.4f}" if out["rings_against_none"] else "")
    (work / f"race_centres{suffix}{'_' + tag if tag else ''}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    work = Path(sys.argv[1])
    what = sys.argv[2] if len(sys.argv) > 2 else "all"
    backend = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] in ("cpu", "gpu") else "gpu"
    tag = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else ""
    if what in ("build", "all"):
        build(work, backend, tag)
    if what in ("run", "all"):
        run(work, name_of(backend, tag))
    if what in ("report", "all"):
        report(work, backend, tag)
