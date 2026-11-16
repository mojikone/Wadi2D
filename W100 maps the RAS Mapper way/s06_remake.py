"""The maps of record of a finished run made again in a folder of this iteration, timed, with the peak memory.

    python s06_remake.py RUN TAG --cache CACHE [--set key=value ...] [--backend gpu]

RUN is a finished run folder (its results are hard-linked, never written; its resolved configuration copied); the
remake lands in ``runs/<TAG>/``. The copy's ``outputs.pixels`` are the defaults of this branch (the run's own say
``pixel_m 0``, ``cell_depth 0.05`` and nothing of the rest), changed by ``--set`` (``--set surface=cell_fill``).
The grid cache is CACHE, so the run's own and W79's stay as they are. Writes ``runs/<TAG>.json``: seconds by stage,
the engine process's own peak working set, the most the card held over what it held at the start (the whole card's
count, so other work on it moves the figure), and the size of every raster written. W93's ``s02_remake.py``, with the
settings and the sizes added.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
POLL_S = 0.5
CHILD = """
import ctypes, json, sys, threading, time
from ctypes import wintypes
from wadi2d.engine.cli import main

class Counters(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [(n, ctypes.c_size_t) for n in "abcdefgh"]

def handles():
    kernel, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    return kernel, psapi

def sample():
    kernel, psapi = handles()
    while True:
        c = Counters()
        c.cb = ctypes.sizeof(Counters)
        if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(c), c.cb):
            print(json.dumps({"ev": "mem", "ws": c.b, "commit": c.g}), flush=True)
        time.sleep(2.0)

threading.Thread(target=sample, daemon=True).start()
code = main(sys.argv[1:])
kernel, psapi = handles()
counters = Counters()
counters.cb = ctypes.sizeof(Counters)
peak = counters.a if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb) else None
print(json.dumps({"ev": "peak", "bytes": peak}), flush=True)
sys.exit(code)
"""


def card_used_mb() -> float | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, check=False,
        )  # fmt: skip
        return float(out.stdout.split()[0])
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None


def _value(text: str):
    try:
        return json.loads(text)
    except ValueError:
        return text


def place(run: Path, tag: str, cache: Path, settings: dict) -> Path:
    out = HERE / "runs" / tag
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*"):
        if old.is_file() and old.name != "results.h5":
            old.unlink()
    config = json.loads((run / "config.resolved.json").read_text(encoding="utf-8"))
    config["grid"]["cache_dir"] = str(cache.resolve())
    config["outputs"]["pixels"] = {"enabled": True, **settings}  # this branch's defaults, but what is set
    config["outputs"]["smooth"] = {**config["outputs"].get("smooth", {}), "enabled": False}
    (out / "config.resolved.json").write_text(json.dumps(config), encoding="utf-8")
    if not (out / "results.h5").exists():
        os.link(run / "results.h5", out / "results.h5")  # the same volume: no copy of a file of gigabytes
    return out


def sizes(folder: Path) -> dict:
    return {p.name: round(p.stat().st_size / 2**20, 1) for p in sorted(folder.glob("*.tif"))}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("tag")
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--backend", default="gpu")
    args = parser.parse_args()
    settings = {k: _value(v) for k, v in (item.split("=", 1) for item in args.set)}
    out = place(args.run, args.tag, args.cache, settings)
    env = {**os.environ, "NUMBA_NUM_THREADS": os.environ.get("NUMBA_NUM_THREADS", "8")}
    card0 = card_used_mb()
    peak = {"card": card0 or 0.0, "host": None}
    stages: dict[str, list[float]] = {}
    start = time.time()
    child = subprocess.Popen(
        [sys.executable, "-c", CHILD, "products", str(out), "--backend", args.backend],
        cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
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
        for line in child.stdout:
            log.write(f"{time.time() - start:.1f} {line}")
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get("ev") == "products":
                stages.setdefault(event["stage"], []).append(time.time())
            elif event.get("ev") == "mem":
                peak["ws"] = max(peak.get("ws", 0), event["ws"])
                peak["commit"] = max(peak.get("commit", 0), event["commit"])
            elif event.get("ev") == "peak":
                peak["host"] = event["bytes"]
    code = child.wait()
    wall = time.time() - start
    pixels = out / "pixels"
    report = {
        "run": str(args.run), "settings": settings, "backend": args.backend, "exit": code, "wall_s": round(wall, 1),
        "to_first_stage_s": round(min(min(ts) for ts in stages.values()) - start, 1) if stages else None,
        "stage_s": {name: round(max(ts) - min(ts), 1) for name, ts in stages.items()},
        "peak_host_gb": None if peak["host"] is None else round(peak["host"] / 2**30, 2),
        "peak_sampled_commit_gb": round(peak.get("commit", 0) / 2**30, 2),
        "peak_card_over_start_gb": None if card0 is None or args.backend == "cpu" else round((peak["card"] - card0) / 1024, 2),
        "rasters_mb": sizes(pixels) if pixels.is_dir() else {},
        "stats": json.loads((pixels / "pixels.json").read_text(encoding="utf-8")) if (pixels / "pixels.json").is_file() else None,
    }  # fmt: skip
    (HERE / "runs" / f"{args.tag}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "stats"}, indent=1))


if __name__ == "__main__":
    main()
