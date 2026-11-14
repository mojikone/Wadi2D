"""The Faydh 01 race with gorge rows (W52): the centre mesh at 20 m and 10 m, rain on Faydh 01's grid, the dam axis.

The jobs are W47's option A race jobs (`W47 face level carried to the face/depth_carry/race`, read from the main
checkout) with the local hydraulic radius (the default face table on this branch, set outright) and
`strips.gorge_rows`, their cache and runs here. The converged answer is W49's 5 m squares after the table-top fix,
1,796.2 m3/s; W49's centres read +3.9 % at 20 m and +2.4 % at 10 m.

    .venv\Scripts\python "W52 gorge rows in the aligned mesh\race_rows.py" run|report [ce20 ce10] [rows=0,4] [meanface]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MAIN = Path(os.environ.get("WADI2D_MAIN", r"D:\Mojtaba\Renardet\Wadi2D"))
OPTION_A = MAIN / "W47 face level carried to the face" / "depth_carry" / "race"
WORK = HERE / "race"
CONVERGED = 1796.2
"""W49's 5 m squares with the local radius after the table-top fix, m3/s at the dam axis."""


MEAN_FACE = "meanface" in sys.argv
"""Run through `mean_face_engine.py` (the strip faces' ground the mean of the two pixels either side, diagnosis)."""
TAG = "_meanface" if MEAN_FACE else ""


def job(name: str, rows: int) -> Path:
    data = json.loads((OPTION_A / f"{name}.json").read_text(encoding="utf-8"))
    data["grid"]["cache_dir"] = str(WORK / "cache")
    data.setdefault("tables", {})["face_conveyance"] = "local_radius"
    data["strips"]["gorge_rows"] = rows
    data["project"]["name"] = f"w52_race_{name}_rows{rows}"
    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / f"{name}_rows{rows}{TAG}.json"
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return path


def run(name: str, rows: int) -> None:
    path = job(name, rows)
    folder = WORK / path.stem
    if (folder / "series" / "line_axis.csv").is_file():
        return
    t0 = time.perf_counter()
    engine = [sys.executable, str(HERE / "mean_face_engine.py")] if MEAN_FACE else [sys.executable, "-m", "wadi2d.engine.cli"]
    done = subprocess.run([*engine, "run", str(path), "--out", str(folder)],
                          capture_output=True, text=True, cwd=ROOT, env=dict(os.environ, PYTHONPATH=str(ROOT)))  # fmt: skip
    (WORK / f"{path.stem}.log").write_text(done.stdout + "\n" + done.stderr, encoding="utf-8")
    print(f"{path.stem}: exit {done.returncode} in {time.perf_counter() - t0:.0f} s", flush=True)


def peak(folder: Path) -> float:
    rows = (folder / "series" / "line_axis.csv").read_text(encoding="utf-8").splitlines()[1:]
    return float(np.abs(np.array([float(r.split(",")[1]) for r in rows])).max())


def report(names: list[str], rows: tuple[int, ...]) -> dict:
    out = {}
    for name in names:
        for n in rows:
            folder = WORK / f"{name}_rows{n}{TAG}"
            if not (folder / "series" / "line_axis.csv").is_file():
                continue
            lines = (folder / "progress.jsonl").read_text(encoding="utf-8").splitlines()
            done = [json.loads(s) for s in lines if '"done"' in s[:14]][-1]
            strips = [json.loads(s) for s in lines if '"ev": "strips"' in s]
            p = peak(folder)
            out[folder.name] = {"peak": p, "vs_converged": p / CONVERGED - 1, "steps": done["steps"], "loop_s": done["loop_s"],
                                "tables_s": done["tables_s"], "dt_min": done["dt_min"], "mass_error": done["balance"].get("relative_error"),
                                "strip_cells": strips[-1].get("cells") if strips else None, "notes": strips[-1].get("cut") if strips else None}  # fmt: skip
            r = out[folder.name]
            print(f"{folder.name:12s} {p:8.1f} m3/s {100 * r['vs_converged']:+5.1f} %  steps {r['steps']:>7d}  loop {r['loop_s']:6.1f} s  tables {r['tables_s']:5.1f} s  dt_min {r['dt_min']:.3f} s  strip cells {r['strip_cells']}")
    (WORK / f"race_rows{TAG}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    what = sys.argv[1]
    names = [a for a in sys.argv[2:] if a in ("ce20", "ce10")] or ["ce20", "ce10"]
    rows = next((tuple(int(v) for v in a.split("=")[1].split(",")) for a in sys.argv[2:] if a.startswith("rows=")), (0, 4))
    if what == "run":
        for name in names:
            for n in rows:
                run(name, n)
    report(names, rows)
