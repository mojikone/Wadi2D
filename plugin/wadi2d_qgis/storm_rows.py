# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The storm of the dock as plain values: table text, what is wrong with it, and the job's ``storm`` block. No Qt here."""

from __future__ import annotations

import itertools
import json
import re
from pathlib import Path

HOURS_TO_MINUTES = 60.0
SEPARATOR = re.compile(r"[\t;,]|\s+")
PERCENT = 100.0
KIND_HMS, KIND_STEADY, KIND_DESIGN, KIND_TABLE, KIND_GRID = "hms", "uniform", "hypothetical", "hyetograph", "gridded"


def pasted_rows(text: str, columns: int = 2) -> list[tuple[float, ...]]:
    """Rows of numbers from pasted text; a line that holds no numbers, such as a heading, is left out."""
    rows = []
    for line in text.splitlines():
        cells = [cell for cell in SEPARATOR.split(line.strip()) if cell]
        try:
            numbers = tuple(float(cell) for cell in cells[:columns])
        except ValueError:
            continue
        if len(numbers) == columns:
            rows.append(numbers)
    return rows


def _rising(values: list[float]) -> bool:
    return all(b > a for a, b in itertools.pairwise(values))


def _table_problems(storm: dict) -> list[str]:
    rows = storm["rows"]
    if not rows:
        return ["Fill the hyetograph table."]
    ends, depths = [r[0] for r in rows], [r[1] for r in rows]
    if ends[0] <= 0.0 or not _rising(ends):
        return ["Hyetograph times must rise, and each one closes its period, so the first is above zero."]
    if min(depths) < 0.0 or sum(depths) <= 0.0:
        return ["Hyetograph depths cannot go below zero and must hold some rain."]
    return []


def _design_problems(storm: dict) -> list[str]:
    found = []
    if storm["depth_mm"] <= 0.0 or storm["hours"] <= 0.0:
        found.append("A design storm needs a depth and a duration.")
    pattern = storm["pattern"]
    times, depths = [r[0] for r in pattern], [r[1] for r in pattern]
    if len(pattern) < 2:
        found.append("Fill the design pattern: percent of the duration against percent of the depth.")
    elif times[0] != 0.0 or times[-1] != PERCENT or depths[-1] != PERCENT or not _rising(times):
        found.append("The design pattern must run from 0 to 100 % of the duration and end at 100 % of the depth.")
    elif any(b < a for a, b in itertools.pairwise(depths)):
        found.append("The design pattern's depth cannot fall.")
    arf = storm["arf"]
    if arf and storm["area_km2"] <= 0.0:
        found.append("An area reduction table needs the storm area.")
    if arf and not _rising([r[0] for r in arf]):
        found.append("The areas of the reduction table must rise.")
    return found


def _grid_problems(storm: dict) -> list[str]:
    source = storm["file"]
    if not source:
        return ["Choose the rain file."]
    if not Path(source).exists():
        return [f"The rain file is not there: {source}"]
    if Path(source).is_dir() and storm["interval_min"] <= 0.0:
        return ["A folder of GeoTIFFs needs the length of each period."]
    if storm.get("choices") and not storm.get("variable"):
        return ["Choose which series in the rain file is the rain."]
    return []


def _steady_problems(storm: dict) -> list[str]:
    return [] if storm["mm_h"] > 0.0 and storm["hours"] > 0.0 else ["Set the rain and how many hours it lasts."]


def storm_problems(storm: dict) -> list[str]:
    """What stops a run, in plain words."""
    checks = {
        KIND_STEADY: _steady_problems, KIND_TABLE: _table_problems, KIND_DESIGN: _design_problems,
        KIND_GRID: _grid_problems,
    }  # fmt: skip
    return checks[storm["kind"]](storm)


def storm_notes(storm: dict, duration_h: float) -> list[str]:
    """What is allowed but probably not meant."""
    if storm["kind"] == KIND_TABLE and storm["rows"]:
        lasts_h = storm["rows"][-1][0] / HOURS_TO_MINUTES
    elif storm["kind"] in (KIND_DESIGN, KIND_STEADY):
        lasts_h = storm["hours"]
    else:
        return []
    return ["The rain outlasts the simulated time, so the run ends while it is still raining."] if lasts_h > duration_h else []


def _arf(storm: dict) -> dict:
    arf = storm["arf"]
    if not arf:
        return {}
    areas, factors = [r[0] for r in arf], [r[1] for r in arf]
    return {"storm_area_km2": storm["area_km2"], "arf": {"areas_km2": areas, "factors": factors}}


def storm_job(storm: dict) -> dict:
    """The job's ``storm`` block. Every number the job holds comes from the user; defaults stay the engine's."""
    kind = storm["kind"]
    if kind == KIND_STEADY:
        minutes = storm["hours"] * HOURS_TO_MINUTES
        return {"kind": kind, "depth_mm": storm["mm_h"] * storm["hours"], "duration_min": minutes}
    if kind == KIND_TABLE:
        rows = storm["rows"]
        return {"kind": kind, "hyetograph_min": [r[0] for r in rows], "hyetograph_mm": [r[1] for r in rows]}
    if kind == KIND_DESIGN:
        pattern = storm["pattern"]
        return {
            "kind": kind,
            "depth_mm": storm["depth_mm"],
            "duration_min": storm["hours"] * HOURS_TO_MINUTES,
            "time_percent": [r[0] for r in pattern],
            "depth_percent": [r[1] for r in pattern],
            **_arf(storm),
        }
    job = {
        "kind": kind,
        "rain_file": str(Path(storm["file"]).resolve()),
        "rain_units": storm["units"],
        "rain_stamp": storm["stamp"],
    }
    if storm.get("variable"):
        job["rain_variable"] = storm["variable"]
    if storm["interval_min"] > 0.0:
        job["rain_interval_min"] = storm["interval_min"]
    if storm.get("start"):
        job["rain_start"] = storm["start"]
    return job


def rain_args(storm: dict) -> list[str]:
    """The arguments of ``wadi2d rain`` for the file the dock holds."""
    args = ["rain", storm["file"], "--units", storm["units"], "--stamp", storm["stamp"]]
    if storm.get("variable"):
        args += ["--variable", storm["variable"]]
    if storm["interval_min"] > 0.0:
        args += ["--interval-min", f"{storm['interval_min']:g}"]
    if storm.get("start"):
        args += ["--start", storm["start"]]
    return args


def rain_reply(out: str) -> dict:
    """The answer of ``wadi2d rain``: the DSS library writes its own log to the same stream, before or after it."""
    for line in out.splitlines():
        if line.startswith("{"):
            return json.loads(line)
    raise ValueError("The engine gave no answer about this rain file.")


def rain_text(info: dict) -> str:
    """What the rain file holds, in one short paragraph."""
    if not info["frames"]:
        return "This file holds several series: choose one."
    hours = info["duration_min"] / HOURS_TO_MINUTES
    start = f", from {info['start'].replace('T', ' ')}" if info.get("start") else ""
    text = (
        f"{info['frames']} frames of {info['period_min']:g} min, {hours:g} h{start}. "
        f"{info['columns']} x {info['rows']} pixels. Total {info['mean_mm']:.1f} mm on average, {info['max_mm']:.1f} mm at most."
    )
    if not info.get("crs"):
        text += " No coordinate system in the file: it is read in the DEM's."
    if info.get("missing"):
        text += f" {info['missing']:.1%} of it has no data, counted as no rain."
    if info.get("cumulative"):
        text += " Every frame holds at least the one before: check this is not rain since the start of a forecast."
    return text
