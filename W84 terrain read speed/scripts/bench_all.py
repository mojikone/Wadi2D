"""Run bench_read.py over a list of cases, each in a fresh process. Args: a case list name."""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASES = {
    "scaling": [
        (mode, w, kind, pitch)
        for kind, pitch in (("raw", 1280), ("raw", 1857), ("bed", 1280))
        for mode, ws in (("threads", (1, 2, 4, 8, 16)), ("procs", (4, 8, 16)))
        for w in ws
    ],
    "cache": [("threads", w, "raw", 1280, c) for c in ("0", "64MB", "512MB") for w in (1, 8, 16)],
    "stored": [
        (mode, w, kind, 1280)
        for kind in ("bed", "stored")
        for mode, ws in (("threads", (1, 2, 4, 8, 16)), ("procs", (8, 16)))
        for w in ws
    ],
    "masked": [("threads", w, kind, 1857) for kind in ("raw", "masked", "bed") for w in (1, 16)],
}

for case in CASES[sys.argv[1]]:
    subprocess.run([sys.executable, str(HERE / "bench_read.py"), *map(str, case)], check=True)
