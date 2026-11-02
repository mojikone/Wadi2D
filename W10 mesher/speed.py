"""Time frozen main against this branch against local stepping, alternating, with GPU use sampled during each run.

usage: python speed.py BASE_FOLDER REPEATS [job=PATH]. A timing counts as clean only when the GPU stayed free of other work:
the sampled use is printed so that is visible. Results are appended to speed.jsonl beside this file.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
QUERY = ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used", "--format=csv,noheader,nounits"]
SAMPLE_S = 2.0


def sampler(stop: threading.Event, out: list[tuple[int, int]]) -> None:
    while not stop.wait(SAMPLE_S):
        done = subprocess.run(QUERY, capture_output=True, text=True, check=False)
        use, memory = done.stdout.strip().split(",")
        out.append((int(use), int(memory)))


def run(name: str, path: str, extra: list[str]) -> dict:
    stop = threading.Event()
    samples: list[tuple[int, int]] = []
    thread = threading.Thread(target=sampler, args=(stop, samples), daemon=True)
    before = subprocess.run(QUERY, capture_output=True, text=True, check=False).stdout.strip()
    thread.start()
    env = {**os.environ, "PYTHONPATH": path}
    t0 = time.perf_counter()
    done = subprocess.run(
        [sys.executable, str(HERE / "bidah.py"), f"speed_{name}", *extra], capture_output=True, text=True, env=env, check=False
    )
    wall = time.perf_counter() - t0
    stop.set()
    thread.join()
    row = json.loads(done.stdout.strip().splitlines()[-1]) if done.returncode == 0 else {"error": done.stderr[-400:]}
    row.update(
        wall_s=round(wall, 1), before=before, use_mean=round(sum(u for u, _m in samples) / max(len(samples), 1), 1),
        memory_peak=max((m for _u, m in samples), default=0),
    )  # fmt: skip
    with open(HERE / "speed.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"case": name, **row}) + "\n")
    print(name, {k: row.get(k) for k in ("steps", "loop_s", "mass", "peaks", "use_mean", "memory_peak", "before", "error")}, flush=True)
    return row


def main() -> None:
    base, repeats = sys.argv[1], int(sys.argv[2])
    extra = sys.argv[3:]
    lts = ["numerics.local_time_stepping=true"]
    for _ in range(repeats):
        run("main", base, extra)
        run("branch", str(ROOT), extra)
        run("levels", str(ROOT), [*extra, *lts])
        run("levels_half", str(ROOT), [*extra, *lts, "numerics.lts_buffer=0.5"])


if __name__ == "__main__":
    main()
