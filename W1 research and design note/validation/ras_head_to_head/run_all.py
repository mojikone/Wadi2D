"""The whole head-to-head for one cell size and RAS solver, from nothing but the clipped DEM. One command.

usage: run_all.py --dx 10 --equation 2        (equation: 1 SWE-ELM, 2 SWE-EM)

Steps: RAS terrain (RasProcess CreateTerrain, once) -> RAS text project -> Ras.exe -c -> Wadi2D job -> Wadi2D run
-> table comparison -> result comparison. No GUI at any step. The RAS terrain needs the templates in ras_common.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RASPROCESS = r"C:\Program Files (x86)\HEC\HEC-RAS\6.6\RasProcess.exe"
EQ = {1: "swe_elm", 2: "swe_em"}


CODE = [str(ROOT)]


def run(*cmd: str) -> None:
    print(">", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=HERE, check=True, env={**os.environ, "PYTHONPATH": CODE[0]})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dx", type=float, default=10.0)
    ap.add_argument("--equation", type=int, default=2, choices=(1, 2))
    ap.add_argument("--code", default=None, help="folder holding the wadi2d package; the default is this repo")
    a = ap.parse_args()
    if a.code:
        CODE[0] = a.code
    py = sys.executable
    tag = f"{a.dx:g}m_{EQ[a.equation]}"
    folder = f"ras_{tag}"
    terrain = HERE / "ras_common" / "Terrain" / "Terrain.hdf"
    if not terrain.exists():
        run(
            RASPROCESS, "CreateTerrain", "units=Meter", "stitch=false",
            f"prj={HERE / 'ras_common' / 'Projection UTM40.prj'}", f"out={terrain}",
            str(HERE / "terrain" / "fan_window_0p5m.tif"),
        )  # fmt: skip
    if not (HERE / folder / "Fan.p01.hdf").exists():
        run(py, "build_ras_project.py", folder, "--dx", f"{a.dx:g}", "--equation", str(a.equation))
        run(py, "run_ras.py", folder)
    job = f"job_{a.dx:g}m.json"
    wadi = f"wadi_runs/w{a.dx:g}m"
    run(py, "build_wadi_job.py", folder, job, "--dx", f"{a.dx:g}")
    run(py, "-m", "wadi2d.engine.cli", "run", job, "--out", wadi)
    run(py, "compare_tables.py", folder, "--dx", f"{a.dx:g}", "--out", f"tables_{a.dx:g}m.json")
    run(py, "compare_results.py", folder, wadi, "--dx", f"{a.dx:g}",
        "--out", f"results_{tag}.json", "--png", f"fig_{tag}.png")  # fmt: skip


if __name__ == "__main__":
    main()
