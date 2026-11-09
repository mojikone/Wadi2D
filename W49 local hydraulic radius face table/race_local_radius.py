"""The Faydh race with the local hydraulic radius face table (W49, 2026-11-08).

Option A's race jobs (`W47 face level carried to the face/depth_carry/race`, the W45 and W46 race jobs on the kernels
of this branch) copied here with `tables.face_conveyance: local_radius` and their own cache, so option A's runs stay as
they were. The report sets the dam axis's peaks at 16 h beside option A's, against the 5 m squares and, for the 3 %
rule, the centres at 20 m against the squares at 20 m.

    .venv\Scripts\python "W49 local hydraulic radius face table\race_local_radius.py" [build|run|report|all] [names ...] [--out=race_faydh_top_fix]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "W47 face level carried to the face"))
import race_after_fix as raf  # noqa: E402

OPTION_A = ROOT / "W47 face level carried to the face" / "depth_carry" / "race"
WORK = HERE / next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--out=")), "race_faydh")
"""The run folder: `race_faydh` holds the first runs, made before the table-top fix; `race_faydh_top_fix` the runs after it."""
NAMES = ("sq20", "rings20", "ce20", "sq10", "ce10", "sq5")


def build(names: list[str]) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    for name in names:
        job = json.loads((OPTION_A / f"{name}.json").read_text(encoding="utf-8"))
        job["grid"]["cache_dir"] = str(WORK / "cache")
        job.setdefault("tables", {})["face_conveyance"] = "local_radius"
        (WORK / f"{name}.json").write_text(json.dumps(job, indent=1), encoding="utf-8")
    print("jobs written:", ", ".join(names), flush=True)


def report(names: list[str]) -> dict:
    out = {}
    for name in names:
        if not (WORK / name / "series" / "line_axis.csv").is_file():
            continue
        new, old = raf.shape(WORK / name), raf.shape(OPTION_A / name)
        done = [json.loads(s) for s in (WORK / name / "progress.jsonl").read_text(encoding="utf-8").splitlines() if '"done"' in s[:14]][-1]
        new["tables_s"], new["loop_s"] = done["tables_s"], done["loop_s"]
        out[name] = {"local_radius": new, "option_a": old}
    ref_new, ref_old = (out.get("sq5", {}).get(k, {}).get("peak") for k in ("local_radius", "option_a"))
    print(f"{'run':8s} {'option A':>9s} {'local R':>9s} {'change':>8s} {'A vs sq5':>9s} {'R vs sq5':>9s} {'tables s':>9s}")
    for name, r in out.items():
        a, b = r["option_a"]["peak"], r["local_radius"]["peak"]
        va = f"{100 * (a / ref_old - 1):+.1f} %" if ref_old else ""
        vb = f"{100 * (b / ref_new - 1):+.1f} %" if ref_new else ""
        print(f"{name:8s} {a:9.1f} {b:9.1f} {100 * (b / a - 1):+7.1f} % {va:>9s} {vb:>9s} {r['local_radius']['tables_s']:9.1f}")
    if "sq20" in out and "ce20" in out:
        for k in ("option_a", "local_radius"):
            print(f"centres against squares at 20 m, {k}: {100 * (out['ce20'][k]['peak'] / out['sq20'][k]['peak'] - 1):+.1f} % (the 3 % rule)")
    (WORK / "race_local_radius.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    names = [a for a in sys.argv[2:] if a in NAMES] or list(NAMES)
    raf.WORK = WORK
    if what in ("build", "all"):
        build(names)
    if what in ("run", "all"):
        for name in names:
            raf.run(name)
    if what in ("report", "all"):
        report(names)
