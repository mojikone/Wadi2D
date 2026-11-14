"""Existing jobs give the same numbers: the same job files run by the base commit's engine and by this branch's.

usage: same_numbers.py BASE_CODE BASE_RUNS NEW_CODE NEW_RUNS OUT.json      (venv python)

For every run folder present in both roots: each series CSV byte for byte, the six cell maps value for value, the
step count and the balance to the last digit, and the job's hash as each engine computes it (what a checkpoint must
match, so a run stopped under the old engine resumes under the new one).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import rasterio

HASH = "import sys; from wadi2d.run import job_hash, load_job; print(job_hash(load_job(sys.argv[1])))"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def job_hash(code: Path, job: Path) -> str:
    env = {**os.environ, "PYTHONPATH": str(code)}
    done = subprocess.run([sys.executable, "-c", HASH, str(job)], capture_output=True, text=True, env=env, cwd=str(code))
    return done.stdout.strip().splitlines()[-1] if done.returncode == 0 else f"failed: {done.stderr[-300:]}"


def done_event(folder: Path) -> dict:
    lines = (folder / "progress.jsonl").read_text(encoding="utf-8").splitlines()
    return next(json.loads(s) for s in reversed(lines) if '"done"' in s[:20])


def compare(base: Path, new: Path, base_code: Path, new_code: Path) -> dict:
    series = sorted(p.name for p in (base / "series").glob("*.csv"))
    same_series = {name: digest(base / "series" / name) == digest(new / "series" / name) for name in series}
    maps = {}
    for path in sorted((base / "maps").glob("*.tif")):
        with rasterio.open(path) as a, rasterio.open(new / "maps" / path.name) as b:
            maps[path.name] = bool(np.array_equal(a.read(1), b.read(1), equal_nan=True))
    a, b = done_event(base), done_event(new)
    hashes = (job_hash(base_code, base / "job.json"), job_hash(new_code, base / "job.json"))
    return {
        "series_files": len(series), "series_identical": all(same_series.values()),
        "series_set_identical": series == sorted(p.name for p in (new / "series").glob("*.csv")),
        "maps": maps, "maps_identical": all(maps.values()),
        "steps": [a["steps"], b["steps"]], "balance_identical": a["balance"] == b["balance"],
        "rain_m3": a["balance"]["rain_m3"], "job_hash": hashes, "job_hash_identical": hashes[0] == hashes[1],
    }  # fmt: skip


def main() -> None:
    base_code, base_runs, new_code, new_runs = (Path(a).resolve() for a in sys.argv[1:5])
    found = {}
    for folder in sorted(p for p in base_runs.iterdir() if (p / "progress.jsonl").is_file() and (new_runs / p.name).is_dir()):
        found[folder.name] = compare(folder, new_runs / folder.name, base_code, new_code)
        f = found[folder.name]
        print(folder.name, "series", f["series_identical"], "maps", f["maps_identical"], "balance", f["balance_identical"],
              "steps", f["steps"], "hash", f["job_hash_identical"], flush=True)  # fmt: skip
    Path(sys.argv[5]).write_text(json.dumps(found, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
