"""Run one rerun job on the GPU, one job at a time: wait until no other engine run (another worker's, W82's) and no
other worker's driver holds the GPU, then ``wadi2d run``, then ``s04_check.py``.

Usage: s09_run.py <run number>. Writes runs/<name>.log (the engine's progress lines), runs/<name>.wait.json (how long it
waited and for what) and runs/<name>.wall.json (start, end, exit code).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from w79 import JOBS, REPO, RUN_NAMES, RUNS, write_json  # noqa: E402

POLL_S = 60.0
BUSY = ("wadi2d.engine.cli run", "wadi2d.exe run", "wadi2d.exe\" run", "wadi2d.exe\" products", "wadi2d.exe\" frames", "block2.py\" run", "race.py", "s08_tables.py")
"""Command lines that hold or are about to hold the GPU: an engine run, or another worker's driver that starts them;
and this folder's own table build, which writes the cache the run reads."""


def busy() -> list[str]:
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name like 'python%' or Name like 'wadi2d%'\" | "
        "ForEach-Object { \"$($_.ProcessId) $($_.CommandLine)\" }"
    )
    out = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True).stdout
    me = str(Path(__file__).name)
    return [line for line in out.splitlines() if any(b in line for b in BUSY) and me not in line]


def main(number: int) -> None:
    name = RUN_NAMES[number]
    t0 = time.time()
    seen = set()
    while True:
        others = busy()
        if not others:
            break
        seen.update(o[:200] for o in others)
        time.sleep(POLL_S)
    write_json(RUNS / f"{name}.wait.json", {"waited_s": time.time() - t0, "for": sorted(seen)})
    exe = REPO / ".venv" / "Scripts" / "wadi2d.exe"
    start = time.time()
    with (RUNS / f"{name}.log").open("w", encoding="utf-8") as log:
        code = subprocess.run([str(exe), "run", str(JOBS / f"{name}.json"), "--out", str(RUNS / name),
                               "--backend", "gpu"], stdout=log, stderr=subprocess.STDOUT, cwd=str(REPO)).returncode
    write_json(RUNS / f"{name}.wall.json", {"start": start, "end": time.time(), "wall_s": time.time() - start,
                                            "exit": code})
    if code == 0:
        subprocess.run([sys.executable, str(Path(__file__).with_name("s04_check.py")), str(number)], cwd=str(REPO),
                       stdout=(RUNS / f"{name}.check.txt").open("w", encoding="utf-8"), stderr=subprocess.STDOUT)
    print(json.dumps({"run": number, "exit": code, "wall_s": time.time() - start}))


if __name__ == "__main__":
    main(int(sys.argv[1]))
