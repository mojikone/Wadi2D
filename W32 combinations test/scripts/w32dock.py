"""What the W32 dock scenarios add to the originals: the backend they expect, longer harness limits for the CPU, and
every series peak of every run written to ``w32_numbers.json`` in the throwaway folder, unrounded, so a GPU pass and a
CPU pass of the same scenario can be set side by side afterwards (``compare_backends.py``).

The backend is not a dock setting: ``run.backend`` stays ``auto`` and the engine takes the GPU when CuPy sees a device.
``run_dock.ps1`` hides the card with ``CUDA_VISIBLE_DEVICES=-1`` for the CPU pass; the engine inherits it through the
plugin's ``engine_environment()``. The scenario reads the same variable to know what to expect.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path

EXPECTED = "cpu" if os.environ.get("CUDA_VISIBLE_DEVICES") == "-1" else "gpu"


def setup(h) -> None:
    """Longer limits: the harness reads these globals at every tick."""
    h.TOTAL_LIMIT = 6000.0
    h.STEP_LIMIT = 3000.0
    h.log(f"W32: expecting the {EXPECTED} backend; CUDA_VISIBLE_DEVICES={os.environ.get('CUDA_VISIBLE_DEVICES')!r}")


def _event(folder: Path, kind: str) -> dict:
    found = h_events(folder, kind)
    return found[-1] if found else {}


def h_events(folder: Path, kind: str) -> list[dict]:
    path = Path(folder) / "progress.jsonl"
    if not path.exists():
        return []
    return [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if f'"{kind}"' in s[:30]]


def series_peaks(folder: Path) -> dict:
    """For every series CSV, the largest |value| of every numeric column and the hour it stands at."""
    out = {}
    for f in sorted((Path(folder) / "series").glob("*.csv")):
        with f.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        if not rows or "t_s" not in rows[0]:
            continue
        columns = {}
        for name in rows[0]:
            if name == "t_s":
                continue
            try:
                best = max(rows, key=lambda r: abs(float(r[name])))
                columns[name] = [abs(float(best[name])), float(best["t_s"]) / 3600.0]
            except ValueError:
                continue
        out[f.stem] = columns
    return out


def record(h, folder: Path, label: str) -> dict:
    """The run's backend, size, steps, balance and every series peak, kept under ``label``; checks the backend."""
    folder = Path(folder)
    start, done = _event(folder, "start"), _event(folder, "done")
    entry = {
        "folder": str(folder),
        "backend": start.get("backend"),
        "cells": start.get("cells"),
        "tiles": start.get("tiles"),
        "dx": start.get("dx"),
        "exit": done.get("code"),
        "steps": done.get("steps"),
        "loop_s": done.get("loop_s"),
        "balance": done.get("balance", {}),
        "peaks": series_peaks(folder) if (folder / "series").is_dir() else {},
        "warnings": [e.get("message", "") for e in h_events(folder, "warn")],
    }
    path = Path(h.P) / "w32_numbers.json"
    numbers = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    numbers[label] = entry
    path.write_text(json.dumps(numbers, indent=1), encoding="utf-8")
    h.check(f"W32 {label}: ran on the {EXPECTED}", entry["backend"] == EXPECTED, entry["backend"])
    h.log(f"W32 {label}: backend {entry['backend']}, cells {entry['cells']}, steps {entry['steps']}, loop {entry['loop_s']} s")
    return entry
