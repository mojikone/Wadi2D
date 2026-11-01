"""Run one job on the frozen engine with the project venv and append the wall time to wadi_timing.csv.

usage: python run_wadi.py NAME [OUT_NAME]
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time

import case

VENV = r"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe"


def main() -> None:
    name = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else name
    folder = case.HERE / "wadi_runs" / out
    if folder.exists():
        shutil.rmtree(folder)
    t0 = time.perf_counter()
    with open(case.HERE / "wadi_runs" / f"{out}.log", "w") as log:
        rc = subprocess.run(
            [VENV, "-m", "wadi2d.engine.cli", "run", str(case.HERE / "jobs" / f"{name}.json"), "--out", str(folder)],
            cwd=case.ENGINE,
            env={**os.environ, "PYTHONPATH": str(case.ENGINE)},
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        ).returncode
    wall = time.perf_counter() - t0
    done = json.loads((folder / "progress.jsonl").read_text(encoding="utf-8").strip().split("\n")[-1])
    line = f"{out},{rc},{wall:.1f},{done.get('loop_s')},{done.get('tables_s')},{done.get('steps')}"
    with open(case.HERE / "wadi_timing.csv", "a") as f:
        f.write(line + "\n")
    print(line)


if __name__ == "__main__":
    main()
