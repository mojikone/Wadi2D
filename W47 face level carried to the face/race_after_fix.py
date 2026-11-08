"""The Faydh race rerun on the kernels of W47: the face section read at the level carried to the face and, on
polygons, the upwind cell's advection rate. The jobs are the W45 and W46 race jobs copied here with their own cache,
so the old runs stay as they were; the report sets the new peaks beside the old ones.

    .venv\\Scripts\\python "W47 face level carried to the face\\race_after_fix.py" [build|run|report|all] [names ...]
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
WORK = HERE / "race_faydh"
W45 = ROOT / "W45 aligned mesh engine" / "race_faydh"
W46 = ROOT / "W46 centre-based mesh generator" / "race_faydh"
SOURCES = {
    "sq20": W45 / "faydh20_none_gpu.json",
    "rings20": W45 / "faydh20_strips_gpu.json",
    "ce20": W46 / "faydh20_centres_gpu.json",
    "sq10": W46 / "faydh10_none_gpu.json",
    "ce10": W46 / "faydh10_centres_gpu.json",
    "sq5": W46 / "faydh5_none_gpu.json",
}
OLD_RUNS = {
    "sq20": W45 / "faydh20_none_gpu", "rings20": W45 / "faydh20_strips_gpu", "ce20": W46 / "faydh20_centres_gpu",
    "sq10": W46 / "faydh10_none_gpu", "ce10": W46 / "faydh10_centres_gpu", "sq5": W46 / "faydh5_none_gpu",
}


def build(names: list[str]) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    for name in names:
        job = json.loads(SOURCES[name].read_text(encoding="utf-8"))
        job["grid"]["cache_dir"] = str(WORK / "cache")
        (WORK / f"{name}.json").write_text(json.dumps(job, indent=1), encoding="utf-8")
    print("jobs written:", ", ".join(names))


def run(name: str) -> None:
    exe = ROOT / ".venv" / "Scripts" / "wadi2d.exe"
    t0 = time.perf_counter()
    done = subprocess.run([str(exe), "run", str(WORK / f"{name}.json"), "--out", str(WORK / name)], capture_output=True, text=True)
    (WORK / f"{name}.log").write_text(done.stdout + "\n" + done.stderr, encoding="utf-8")
    print(f"{name}: exit {done.returncode} in {time.perf_counter() - t0:.0f} s", flush=True)


def shape(folder: Path, line: str = "axis") -> dict:
    rows = (folder / "series" / f"line_{line}.csv").read_text(encoding="utf-8").splitlines()[1:]
    a = np.array([[float(v) for v in r.split(",")[:2]] for r in rows])
    t, q = a[:, 0], np.abs(a[:, 1])
    dt = float(np.median(np.diff(t)))
    k = int(q.argmax())
    return {"peak": float(q[k]), "at_h": float(t[k] / 3600), "vol_Mm3": float(q.sum() * dt / 1e6),
            "half_min": float((q >= 0.5 * q[k]).sum() * dt / 60), "centroid_h": float((q * t).sum() / q.sum() / 3600)}


def report(names: list[str]) -> None:
    out = {}
    print(f"{'run':8s} {'old peak':>9s} {'new peak':>9s} {'change':>8s} {'new vol Mm3':>12s} {'half min':>9s} {'centroid h':>11s} {'storage end Mm3':>16s}")
    for name in names:
        folder = WORK / name
        if not (folder / "series" / "line_axis.csv").is_file():
            print(f"{name}: no run")
            continue
        new = shape(folder)
        old = shape(OLD_RUNS[name]) if (OLD_RUNS[name] / "series" / "line_axis.csv").is_file() else None
        prog = (folder / "progress.jsonl").read_text(encoding="utf-8").splitlines()
        done = [json.loads(s) for s in prog if '"done"' in s[:14]][-1]
        new["storage_end_Mm3"] = done["balance"]["storage_end_m3"] / 1e6
        new["loop_s"] = done["loop_s"]
        out[name] = {"new": new, "old_peak": old["peak"] if old else None}
        change = f"{100 * (new['peak'] / old['peak'] - 1):+.1f} %" if old else ""
        print(f"{name:8s} {old['peak'] if old else float('nan'):9.1f} {new['peak']:9.1f} {change:>8s} {new['vol_Mm3']:12.3f} {new['half_min']:9.0f} {new['centroid_h']:11.3f} {new['storage_end_Mm3']:16.3f}")
    if "sq5" in out:
        ref = out["sq5"]["new"]["peak"]
        print("\nagainst the 5 m squares (new): " + ", ".join(f"{n} {100 * (out[n]['new']['peak'] / ref - 1):+.1f} %" for n in out if n != "sq5"))
    if "sq20" in out and "ce20" in out:
        print(f"centres against no lines at 20 m: {100 * (out['ce20']['new']['peak'] / out['sq20']['new']['peak'] - 1):+.1f} % (the 3 % rule); was +8.3 %")
    (WORK / "race_after_fix.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    names = [a for a in sys.argv[2:] if a in SOURCES] or list(SOURCES)
    if what in ("build", "all"):
        build(names)
    if what in ("run", "all"):
        for name in names:
            run(name)
    if what in ("report", "all"):
        report(names)
