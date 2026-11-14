# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The dam workbook dialog without Qt (W60 in the dock): one finished run per return period, the elements, the target
period, and the arguments of ``wadi2d workbook``."""

from __future__ import annotations

import json
import re
from pathlib import Path

SERIES_DIR = "series"
PREFIXES = ("network_", "design_", "line_")
"""The series a run writes that the workbook reads, in the order it looks (``wadi2d.workbook.sources``)."""
PMP = "PMP"
YEARS = re.compile(r"^(\d+)\s*-?\s*(?:yr|year|years|y)?$", re.IGNORECASE)
WORKBOOK_FILE = "dam_workbook.xlsx"
WORKBOOK_TIMEOUT_S = 600
DEFAULT_TARGET = "200yr"


def period_key(text: str) -> str:
    """``200``, ``200 yr`` or ``200-year`` -> ``200yr``; ``pmp`` -> ``PMP``; anything else as typed, trimmed."""
    words = (text or "").strip()
    if words.upper() == PMP:
        return PMP
    found = YEARS.match(words)
    return f"{int(found.group(1))}yr" if found else words


def period_order(key: str) -> tuple[int, int, str]:
    found = re.fullmatch(r"(\d+)yr", key)
    if found:
        return (0, int(found.group(1)), key)
    return (1 if key == PMP else 2, 0, key)


def run_elements(run: Path | str) -> list[str]:
    """The names a run has series of that the workbook reads: lumped elements first, then design lines, then lines."""
    folder = Path(run) / SERIES_DIR
    if not folder.is_dir():
        return []
    found: list[str] = []
    for prefix in PREFIXES:
        for path in sorted(folder.glob(f"{prefix}*.csv")):
            name = path.stem[len(prefix) :]
            if name and name not in found:
                found.append(name)
    return found


def common_elements(runs: list[Path | str]) -> list[str]:
    """The names every run has, in the first run's order: a dam missing from one return period cannot be tabled."""
    lists = [run_elements(run) for run in runs if run]
    if not lists:
        return []
    return [name for name in lists[0] if all(name in other for other in lists[1:])]


def workbook_problems(rows: list[tuple[str, str]], elements: list[str], target: str, out: str) -> list[str]:
    found = []
    keys = [period_key(rp) for rp, _run in rows]
    if not rows:
        found.append("Add a finished run for each return period.")
    for (_rp, run), key in zip(rows, keys, strict=True):
        if not key:
            found.append(f"Name the return period of {Path(run).name or 'each run'} (200yr, PMP ...).")
        if not run or not (Path(run) / SERIES_DIR).is_dir():
            found.append(f"The run of {key or 'a return period'} is not a finished run folder with series.")
    duplicates = sorted({key for key in keys if key and keys.count(key) > 1})
    if duplicates:
        found.append(f"One run per return period: {', '.join(duplicates)} is given twice.")
    if not elements:
        found.append("Tick at least one element: a dam, a reservoir or a design line.")
    if target and period_key(target) not in keys:
        found.append(f"The target period {target} has no run.")
    if not out:
        found.append("Choose where the workbook goes.")
    return found


def workbook_args(rows: list[tuple[str, str]], elements: list[str], target: str, out: str, project: str = "") -> list[str]:
    """The arguments of ``wadi2d workbook``; return periods sorted by years, the PMP last, as the workbook sorts them."""
    args = ["workbook", "--out", str(out)]
    for name in elements:
        args += ["--element", name]
    for rp, run in sorted(rows, key=lambda row: period_order(period_key(row[0]))):
        args += ["--run", f"{period_key(rp)}={run}"]
    args += ["--target", period_key(target) or DEFAULT_TARGET]
    if project:
        args += ["--project", project]
    return args


def workbook_reply(stdout: str) -> str | None:
    """The path ``wadi2d workbook`` wrote, or None."""
    for line in reversed(stdout.splitlines()):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("ev") == "workbook":
            return str(event.get("path", ""))
    return None
