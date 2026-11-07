"""The Block 2 hybrid with corridors: W41's PMP job on Bidah 03 at 30 m through the HMS route (S13 lumped above the
dam, the rest rain-on-grid, the design line's record from the network and the grid), with and without corridors from
W26's suggested banks on Bidah, on the GPU. The dock wrote this job; the corridors are what the dock would add.

    .venv\\Scripts\\python "W45 aligned mesh engine\\race_bidah_hybrid.py" <work folder> [build|run|report]
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
JOB = ROOT / "W41 hybrid design lines" / "jobs" / "pmp_hybrid_s13_above.json"
BANKS = ROOT / "W26 suggested breaklines" / "suggested" / "bidah" / "suggested_breaklines.gpkg"
LINE = "Bidah 03"


def jobs(work: Path) -> dict[str, Path]:
    work.mkdir(parents=True, exist_ok=True)
    base = json.loads(JOB.read_text(encoding="utf-8"))
    base["grid"]["cache_dir"] = str(work / "cache")
    base["outputs"]["map_every_s"] = 0.0
    base["outputs"]["live_every_s"] = 0.0
    base["outputs"]["pixels"] = {"enabled": False}
    base["run"]["backend"] = "gpu"
    base["run"]["checkpoint_every_s"] = 0.0
    base.setdefault("mesh", {})["enabled"] = False
    out = {}
    for name, strips in (("squares", None), ("corridors", {"enabled": True, "banks": str(BANKS), "layer_m": 10.0, "rows_per_side": 3})):
        data = json.loads(json.dumps(base))
        if strips:
            data["strips"] = strips
        path = work / f"bidah_pmp_{name}.json"
        path.write_text(json.dumps(data, indent=1), encoding="utf-8")
        out[name] = path
    return out


def run(work: Path, name: str, job: Path) -> None:
    exe = ROOT / ".venv" / "Scripts" / "wadi2d.exe"
    t0 = time.perf_counter()
    done = subprocess.run([str(exe), "run", str(job), "--out", str(work / name)], capture_output=True, text=True)
    (work / f"{name}.log").write_text(done.stdout + "\n" + done.stderr, encoding="utf-8")
    print(f"{name}: exit {done.returncode} in {time.perf_counter() - t0:.0f} s")


def column_peak(path: Path, column: str) -> tuple[float, float]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    t = np.array([float(r["t_s"]) for r in rows])
    q = np.array([float(r[column]) for r in rows])
    k = int(np.argmax(np.abs(q)))
    return float(abs(q[k])), float(t[k] / 3600.0)


def report(work: Path) -> None:
    out = {}
    for name in ("squares", "corridors"):
        folder = work / name
        done = [json.loads(s) for s in (folder / "progress.jsonl").read_text(encoding="utf-8").splitlines() if '"ev": "done"' in s]
        strips = [json.loads(s) for s in (folder / "progress.jsonl").read_text(encoding="utf-8").splitlines() if '"ev": "strips"' in s]
        design = folder / "series" / f"design_{LINE.replace(' ', '_')}.csv"
        line = folder / "series" / f"line_{LINE.replace(' ', '_')}.csv"
        record = column_peak(design, "total_m3s") if design.is_file() else None
        grid = column_peak(line, "discharge_m3s")
        d = done[-1]
        out[name] = {
            "record_peak_m3s": record, "grid_line_peak_m3s": grid, "steps": d["steps"], "loop_s": d["loop_s"],
            "mass_error": d["balance"]["relative_error"], "rain_m3": d["balance"]["rain_m3"],
            "inflow_m3": d["balance"]["inflow_m3"], "outflow_m3": d["balance"]["outflow_m3"],
            "strips": strips[-1] if strips else None,
        }  # fmt: skip
        print(f"{name}: record {record}, grid line {grid}, steps {d['steps']}, {d['loop_s']:.0f} s, mass {d['balance']['relative_error']:.1e}, rain {d['balance']['rain_m3']:.0f}, inflow {d['balance']['inflow_m3']:.0f}")
        if strips:
            s = strips[-1]
            print(f"  corridors {s['corridors']}, cells {s['cells']}, triangles {s['triangles']}, replaced {s['replaced']}, cut {len(s['cut'])}")
    (work / "race.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    work = Path(sys.argv[1])
    what = sys.argv[2] if len(sys.argv) > 2 else "all"
    made = jobs(work)
    if what in ("run", "all"):
        for name, job in made.items():
            run(work, name, job)
    if what in ("report", "all"):
        report(work)
