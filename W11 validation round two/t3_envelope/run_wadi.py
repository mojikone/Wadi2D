"""Run one job on the frozen engine with the project venv. usage: run_wadi.py NAME [OUT]. Works in the caller's folder."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

VENV = r"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe"
ENGINE = Path(r"D:\Mojtaba\Renardet\Wadi2D\W11 validation round two\engine_f976c23")


def main() -> None:
    here = Path.cwd()
    name = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else name
    (here / "wadi_runs").mkdir(exist_ok=True)
    folder = here / "wadi_runs" / out
    if folder.exists():
        shutil.rmtree(folder)
    t0 = time.perf_counter()
    with open(here / "wadi_runs" / f"{out}.log", "w") as log:
        rc = subprocess.run(
            [VENV, "-m", "wadi2d.engine.cli", "run", str(here / "jobs" / f"{name}.json"), "--out", str(folder)],
            cwd=ENGINE,
            env={**os.environ, "PYTHONPATH": str(ENGINE)},
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        ).returncode
    wall = time.perf_counter() - t0
    progress = folder / "progress.jsonl"
    done = json.loads(progress.read_text(encoding="utf-8").strip().split("\n")[-1]) if progress.exists() else {}
    print(f"{out} rc={rc} wall={wall:.0f}s steps={done.get('steps')}")


if __name__ == "__main__":
    main()
