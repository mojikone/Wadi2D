"""The pixel maps of a finished run made again in a folder of their own, timed, with the peak memory.

    python s02_remake.py RUN TAG [--engine FOLDER] [--backend cpu|gpu] [--memory-mb N]

RUN is a finished run folder (its results are linked and its resolved configuration copied, never touched); the
remake lands in ``runs/<TAG>/``. ``--engine`` is a folder that holds the ``wadi2d`` package to make them with (a
``git archive`` of another commit, say); without it, this checkout. ``--memory-mb`` sets WADI2D_PIXEL_MEMORY_MB, the
cap on a block's memory. Writes ``runs/<TAG>.json``: seconds by stage, the engine process's own peak working set,
and the most the card held over what it held at the start (the whole card's count, so other work on it moves the
figure).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
POLL_S = 0.5
CHILD = """
import ctypes, json, sys
from ctypes import wintypes
from wadi2d.engine.cli import main

class Counters(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [(n, ctypes.c_size_t) for n in "abcdefgh"]

code = main(sys.argv[1:])
peak = None
if sys.platform == "win32":
    counters = Counters()
    counters.cb = ctypes.sizeof(Counters)
    kernel, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        peak = counters.a  # PeakWorkingSetSize, the first of the sizes
print(json.dumps({"ev": "peak", "bytes": peak}), flush=True)
sys.exit(code)
"""
"""The engine's own command with its own count of the most memory it held: the venv's python.exe on Windows only
starts the real interpreter, so the count has to come from inside."""


def card_used_mb() -> float | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, check=False,
        )  # fmt: skip
        return float(out.stdout.split()[0])
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None


def place(run: Path, tag: str, cache: Path | None = None) -> Path:
    out = HERE / "runs" / tag
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    if cache is None:
        shutil.copy2(run / "config.resolved.json", out / "config.resolved.json")
    else:  # the copy keeps its tables, strip and DEM chunks in a folder of this iteration, not in the run's own
        config = json.loads((run / "config.resolved.json").read_text(encoding="utf-8"))
        config["grid"]["cache_dir"] = str(cache.resolve())
        (out / "config.resolved.json").write_text(json.dumps(config), encoding="utf-8")
    try:
        os.link(run / "results.h5", out / "results.h5")  # the same volume: no copy of a file of gigabytes
    except OSError:
        shutil.copy2(run / "results.h5", out / "results.h5")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("tag")
    parser.add_argument("--engine", type=Path, default=REPO)
    parser.add_argument("--backend", default="cpu")
    parser.add_argument("--memory-mb", type=int, default=0)
    parser.add_argument("--cache", type=Path, default=None, help="a cache folder to use in place of the run's own")
    args = parser.parse_args()
    out = place(args.run, args.tag, args.cache)
    env = dict(os.environ)
    if args.memory_mb:
        env["WADI2D_PIXEL_MEMORY_MB"] = str(args.memory_mb)
    card0 = card_used_mb()
    peak = {"card": card0 or 0.0, "host": None}
    stages: dict[str, list[float]] = {}
    start = time.time()
    child = subprocess.Popen(
        [sys.executable, "-c", CHILD, "products", str(out), "--backend", args.backend],
        cwd=args.engine, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
    )  # fmt: skip

    def watch() -> None:
        while child.poll() is None:
            used = card_used_mb()
            if used is not None:
                peak["card"] = max(peak["card"], used)
            time.sleep(POLL_S)

    if args.backend != "cpu":
        threading.Thread(target=watch, daemon=True).start()
    with open(HERE / "runs" / f"{args.tag}.log", "w", encoding="utf-8") as log:
        for line in child.stdout:  # the engine's own events, stamped as they come
            log.write(line)
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get("ev") == "products":
                stages.setdefault(event["stage"], []).append(time.time())
            elif event.get("ev") == "peak":
                peak["host"] = event["bytes"]
    code = child.wait()
    wall = time.time() - start
    report = {
        "run": str(args.run), "engine": str(args.engine), "backend": args.backend, "memory_mb": args.memory_mb,
        "exit": code, "wall_s": round(wall, 1),
        "to_first_stage_s": round(min(min(ts) for ts in stages.values()) - start, 1) if stages else None,
        "stage_s": {name: round(max(ts) - min(ts), 1) for name, ts in stages.items()},
        "peak_host_gb": None if peak["host"] is None else round(peak["host"] / 2**30, 2),
        "peak_card_over_start_gb": None if card0 is None or args.backend == "cpu" else round((peak["card"] - card0) / 1024, 2),
    }  # fmt: skip
    (HERE / "runs" / f"{args.tag}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
