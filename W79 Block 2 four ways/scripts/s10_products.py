"""Remake a finished run's products (``wadi2d products``) and its time-slider file (``wadi2d frames``), timing each
stage and sampling the memory of the engine process.

Usage: s10_products.py <run number> [products|frames|both]. Waits for the GPU as s09_run.py does, except for frames alone. Writes
runs/<name>.<what>_remake.json: per stage its first and last event time, and the peak working set and commit of the
engine's processes (sampled every 5 s), plus the command's exit code; the engine's own lines go to
runs/<name>.products_remake.log.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s09_run import POLL_S, busy  # noqa: E402
from w79 import REPO, RUN_NAMES, RUNS, write_json  # noqa: E402

SAMPLE_S = 5.0


def memory(marker: str) -> tuple[float, float]:
    """Working set and commit, GB, summed over the processes whose command line holds ``marker``."""
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name like 'python%' or Name like 'wadi2d%'\" | "
        f"Where-Object {{ $_.CommandLine -like '*{marker}*' }} | "
        "ForEach-Object { \"$($_.WorkingSetSize) $($_.PrivatePageCount)\" }"
    )
    out = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True).stdout
    ws = commit = 0.0
    for line in out.split("\n"):
        parts = line.split()
        if len(parts) == 2:
            ws += float(parts[0])
            commit += float(parts[1])
    return ws / 1e9, commit / 1e9


def timed(command: str, folder: Path, log) -> dict:
    exe = REPO / ".venv" / "Scripts" / "wadi2d.exe"
    marker = f"{command} "
    peak = {"working_set_gb": 0.0, "commit_gb": 0.0}
    stages: dict[str, dict] = {}
    done = threading.Event()

    def sample() -> None:
        while not done.is_set():
            ws, commit = memory(f"*{marker}*{folder.name}")
            peak["working_set_gb"] = max(peak["working_set_gb"], ws)
            peak["commit_gb"] = max(peak["commit_gb"], commit)
            current = stages.get("_now")
            if current:
                s = stages[current]
                s["peak_working_set_gb"] = max(s.get("peak_working_set_gb", 0.0), ws)
                s["peak_commit_gb"] = max(s.get("peak_commit_gb", 0.0), commit)
            done.wait(SAMPLE_S)

    t0 = time.time()
    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    proc = subprocess.Popen([str(exe), command, str(folder), *(["--backend", "gpu"] if command == "products" else [])],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(REPO))
    for line in proc.stdout:
        now = time.time() - t0
        log.write(f"{now:9.1f} {line}")
        log.flush()
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        stage = ev.get("stage") if ev.get("ev") == "products" else None
        if stage:
            entry = stages.setdefault(stage, {"first_s": now})
            entry["last_s"] = now
            stages["_now"] = stage
    code = proc.wait()
    done.set()
    thread.join()
    stages.pop("_now", None)
    return {"command": command, "exit": code, "wall_s": time.time() - t0, **peak, "stages": stages}


def main(number: int, what: str) -> None:
    name = RUN_NAMES[number]
    folder = RUNS / name
    while what != "frames" and busy():  # the frames file is made on the CPU: it does not wait for the GPU
        time.sleep(POLL_S)
    report = {"run": number, "folder": str(folder)}
    with (RUNS / f"{name}.products_remake.log").open("a", encoding="utf-8") as log:
        for command in (("products", "frames") if what == "both" else (what,)):
            report[command] = timed(command, folder, log)
    write_json(RUNS / f"{name}.{what}_remake.json", report)
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else "both")
