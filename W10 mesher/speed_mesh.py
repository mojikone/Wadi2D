"""What the mesh and local stepping buy, measured: uniform, mesh on one step, mesh with local stepping.

usage: python speed_mesh.py bidah|block2 [CODE_FOLDER] [SKIP_UNIFORM]. CODE_FOLDER holds the wadi2d to time, so a timing can
run from a frozen copy while the working tree moves. Rows go to speed_mesh.jsonl; the sampling shows if the GPU stayed free.
"""

from __future__ import annotations

import sys
from pathlib import Path

import speed
from speed import ROOT, run

BLOCK2 = r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\jobs\c20_A74_h100.json"
CACHE = str(Path(__file__).parent / "runs" / "cache")
MESH = ["mesh.enabled=true", "mesh.coarse_dx=40.0"]
LEVELS = ["numerics.local_time_stepping=true"]


def main() -> None:
    speed.LOG = "speed_mesh.jsonl"
    which = sys.argv[1]
    here = sys.argv[2] if len(sys.argv) > 2 else str(ROOT)
    extra: list[str] = []
    if which == "block2":
        extra = [f"job={BLOCK2}", f"grid.cache_dir={CACHE}", "grid.dx=10.0", "run.duration_s=50400.0"]
    if len(sys.argv) <= 3:
        run(f"{which}_uniform", here, extra)
    run(f"{which}_mesh_levels", here, [*extra, *MESH, *LEVELS])
    run(f"{which}_mesh_levels_half", here, [*extra, *MESH, *LEVELS, "numerics.lts_buffer=0.5"])
    run(f"{which}_mesh_one_step", here, [*extra, *MESH])


if __name__ == "__main__":
    main()
