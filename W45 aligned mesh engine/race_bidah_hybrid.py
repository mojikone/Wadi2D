"""The Block 2 hybrid with corridors: W41's PMP job on Bidah 03 at 30 m through the HMS route (S13 lumped above the
dam, the rest rain-on-grid, the design line's record from the network and the grid), with and without corridors from
W26's suggested banks on Bidah, on the GPU. The dock wrote this job; the corridors are what the dock would add.

    .venv\\Scripts\\python "W45 aligned mesh engine\\race_bidah_hybrid.py" <work folder> [build|run|report|all]
        [--banks <gpkg>] [--cells <min> <max> <fraction> <rows_outside>] [--tag <name>]

The corridors take the engine's width rule (``strips.cell_min_m`` and company) at the schema's defaults unless
``--cells`` gives them; ``--tag`` names the corridor run, so several rules can sit side by side in one folder.
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


def options(argv: list[str]) -> dict:
    out = {"banks": BANKS, "cells": None, "tag": ""}
    if "--banks" in argv:
        out["banks"] = Path(argv[argv.index("--banks") + 1])
    if "--cells" in argv:
        k = argv.index("--cells")
        out["cells"] = (float(argv[k + 1]), float(argv[k + 2]), float(argv[k + 3]), int(argv[k + 4]))
    if "--tag" in argv:
        out["tag"] = argv[argv.index("--tag") + 1]
    return out


def jobs(work: Path, opts: dict) -> dict[str, Path]:
    work.mkdir(parents=True, exist_ok=True)
    base = json.loads(JOB.read_text(encoding="utf-8"))
    base["grid"]["cache_dir"] = str(work / "cache")
    base["outputs"]["map_every_s"] = 0.0
    base["outputs"]["live_every_s"] = 0.0
    base["outputs"]["pixels"] = {"enabled": False}
    base["run"]["backend"] = "gpu"
    base["run"]["checkpoint_every_s"] = 0.0
    base.setdefault("mesh", {})["enabled"] = False
    strips = {"enabled": True, "banks": str(opts["banks"])}
    if opts["cells"]:
        lo, hi, share, outside = opts["cells"]
        strips.update({"cell_min_m": lo, "cell_max_m": hi, "width_fraction": share, "rows_outside": outside})
    corridors = "corridors" + (f"_{opts['tag']}" if opts["tag"] else "")
    out = {}
    for name, section in (("squares", None), (corridors, strips)):
        data = json.loads(json.dumps(base))
        if section:
            data["strips"] = section
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


def report(work: Path, made: dict[str, Path], tag: str) -> None:
    out = {}
    for name in made:
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
            rules = s.get("rules", [])
            words = f"; cells across {min(r['cells_across'] for r in rules)} to {max(r['cells_across'] for r in rules)}, cell across {min(r['across_m'] for r in rules):.0f} to {max(r['across_m'] for r in rules):.0f} m" if rules else ""
            print(f"  corridors {s['corridors']}, cells {s['cells']}, triangles {s['triangles']}, replaced {s['replaced']}, cut {len(s['cut'])}{words}")
    (work / f"race{'_' + tag if tag else ''}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    work = Path(sys.argv[1])
    what = sys.argv[2] if len(sys.argv) > 2 else "all"
    opts = options(sys.argv)
    made = jobs(work, opts)
    if what in ("run", "all"):
        for name, job in made.items():
            if name == "squares" and (work / name / "progress.jsonl").is_file() and "--rerun-squares" not in sys.argv:
                continue
            run(work, name, job)
    if what in ("report", "all"):
        report(work, made, opts["tag"])
