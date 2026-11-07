# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The depth-area study as plain values: its storm areas, what stops it, the job's ``arf`` block, and the table it
writes. No Qt here.

The engine runs one 2D job per storm area with the rain read from the storm's area table at that area. Each design
line, and each lumped element a hand-back feeds, reads ln Q against ln A between the two runs either side of its own
drainage area; a lumped element with no 2D water above it is rerun lumped at its own area (``wadi2d/arf.py``).
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

from .protocol import STUDY_FILE
from .storm_rows import KIND_DESIGN

AREA_KEY = "drainage_area_km2"
AREA_DECIMALS = 4
"""The engine rounds a storm area to this many decimals; a contract test holds the whole list to the engine's."""
BRACKET, SPACED, LISTED = "bracket", "spaced", "listed"
AREA_COUNT, AREA_MIN, AREA_MAX = "arf.n_areas", "arf.area_min_km2", "arf.area_max_km2"
BRACKET_RATIO, BRACKET_MAX, UNITS = "arf.bracket_ratio", "arf.bracket_max", "arf.accumulation_units"
UNIT_WORDS = {"cells": "Cells of the raster", "km2": "km2"}
"""One phrase per unit of the schema's accumulation raster; a contract test holds the keys to the engine's."""
SEPARATOR = re.compile(r"[\s,;]+")
SECONDS_PER_HOUR = 3600.0
COLUMNS = (
    "Design line or element",
    "Drainage area, km2",
    "Design peak, m3/s",
    "Storm areas read, km2",
    "Their peaks, m3/s",
    "Time of peak, h",
    "Read as",
)
STORM_WORDS = (
    "A study needs a design storm with an area reduction table: in Storm, choose As in the HMS project, or Design "
    "storm with area reduction and fill its table."
)
TABLE_WORDS = "Fill the area reduction table of the design storm in Storm: without it every run is the same run."
LINE_WORDS = (
    "The study needs a design line with a drainage area: in Results points, choose the line layer and the field that "
    "holds each line's drainage area in km2."
)
ACCUMULATION_WORDS = "The composite map needs a flow accumulation raster backed by a file."


def parse_areas(text: str) -> list[float] | None:
    """Storm areas typed as ``10, 30, 90``; None when one of them is not a number above zero."""
    found = []
    for cell in SEPARATOR.split(text.strip()):
        if not cell:
            continue
        try:
            value = float(cell)
        except ValueError:
            return None
        if not math.isfinite(value) or value <= 0.0:
            return None
        found.append(value)
    return found


def spaced_areas(smallest: float, largest: float, count: int) -> list[float]:
    """``count`` areas from ``smallest`` to ``largest``, equal steps in log A, both ends included."""
    if count < 2:
        return [smallest]
    ratio = largest / smallest
    return [smallest * ratio ** (k / (count - 1)) for k in range(count)]


def form_problems(form: dict) -> list[str]:
    """What is wrong with the storm areas and the composite map as set."""
    found = []
    if form["spacing"] == LISTED:
        areas = parse_areas(form["listed"])
        if areas is None:
            found.append("Storm areas must be numbers above zero, as 10, 30, 90.")
        elif len({round(a, AREA_DECIMALS) for a in areas}) < 2:
            found.append("A study needs two storm areas at least.")
    elif form["spacing"] == SPACED and (form["smallest"] <= 0.0 or form["largest"] <= form["smallest"]):
        found.append("The smallest storm area must be above zero and below the largest.")
    if form["composite"] and not form["accumulation"]:
        found.append(ACCUMULATION_WORDS)
    return found


def study_areas(form: dict) -> list[float] | None:
    """The storm areas the engine will run, as ``wadi2d.arf.storm_areas`` lists them; None when the engine picks them
    at the start, around drainage areas that only it knows in full."""
    if form["spacing"] == BRACKET:
        return None
    if form["spacing"] == LISTED:
        base = parse_areas(form["listed"]) or []
    else:
        base = spaced_areas(form["smallest"], form["largest"], form["count"])
    return sorted({round(float(a), AREA_DECIMALS) for a in base})


def study_job(form: dict) -> dict:
    """The job's ``arf`` block: what the form asks for; everything else stays the engine's."""
    if form["spacing"] == BRACKET:
        block: dict = {"bracket": True}
    elif form["spacing"] == LISTED:
        block = {"areas_km2": parse_areas(form["listed"]) or []}
    else:
        block = {"n_areas": form["count"], "area_min_km2": form["smallest"], "area_max_km2": form["largest"]}
    if form["composite"] and form["accumulation"]:
        block["accumulation"] = str(Path(form["accumulation"]).resolve())
        block["accumulation_units"] = form["units"]
    return block


def line_area(feature) -> float | None:
    """A design line's drainage area from its field, km2, or None when it has none."""
    area = feature.properties.get(AREA_KEY)
    return float(area) if isinstance(area, (int, float)) and math.isfinite(area) and area > 0.0 else None


def design_lines(design: list) -> tuple[list[tuple[str, float]], list[str], int]:
    """(name, area) of each line with a drainage area, the names of the lines without one, and the number of points.

    Names as the job gives them, so the table's rows can be found by them.
    """
    with_area, without, points = [], [], 0
    for index, feature in enumerate(design):
        if feature.kind == "Point":
            points += 1
            continue
        area = line_area(feature)
        if area is None:
            without.append(feature.name(index))
        else:
            with_area.append((feature.name(index), area))
    return with_area, without, points


def study_problems(values: dict) -> list[str]:
    """What stops a study beyond what stops a run, in plain words."""
    found = []
    storm = values.get("storm")
    if (storm is None and not values.get("hms")) or (storm is not None and storm.get("kind") != KIND_DESIGN):
        found.append(STORM_WORDS)
    elif storm is not None and not storm.get("arf"):
        found.append(TABLE_WORDS)
    if not design_lines(values.get("design") or [])[0]:
        found.append(LINE_WORDS)
    return found


def _area(value: float) -> str:
    return f"{value:.4g}"


def study_notes(values: dict, areas: list[float] | None) -> list[str]:
    """What is allowed but probably not meant: lines with no flow to give, and lines outside the storm areas."""
    with_area, without, points = design_lines(values.get("design") or [])
    found = []
    if without:
        found.append(f"No drainage area, so no design flow: {', '.join(without)}.")
    if points:
        found.append("Points carry no flow: only lines get a design flow.")
    for name, area in with_area if areas else []:
        if round(area, AREA_DECIMALS) < areas[0] or round(area, AREA_DECIMALS) > areas[-1]:
            side, edge = ("below the smallest", areas[0]) if area < areas[0] else ("above the largest", areas[-1])
            found.append(
                f"{name} drains {_area(area)} km2, {side} storm area of {_area(edge)} km2: it takes that run's "
                "peak, not an interpolation."
            )
    return found


def areas_text(areas: list[float] | None, ratio: float, most: int) -> str:
    """How many runs, at which storm areas; or, for bracketing areas, the rule the engine follows."""
    if areas is None:
        return (
            f"Up to {most} runs, picked when the study starts: log-spaced from the smallest to the largest drainage area "
            f"of the design lines and of the lumped elements a hand-back feeds, neighbours at most {ratio:g} x apart. "
            "A lumped element with no 2D water above it needs no run: it is rerun lumped at its own area."
        )
    if not areas:
        return "Set the storm areas."
    listed = ", ".join(_area(a) for a in areas[:-1])
    listed = f"{listed} and {_area(areas[-1])}" if listed else _area(areas[-1])
    return f"{len(areas)} runs, one per storm area: {listed} km2."


def read_study(folder: Path | str) -> tuple[list[dict], str, list[str]]:
    """The rows of a finished study, the type of its area table, and the elements whose water is on the grid."""
    data = json.loads((Path(folder) / STUDY_FILE).read_text(encoding="utf-8"))
    return list(data.get("table") or []), str(data.get("arf_table_type") or ""), list(data.get("on_grid") or [])


def on_grid_text(names: list[str]) -> str:
    if not names:
        return ""
    return (
        f"No lumped flow of their own, because water above them runs on the grid and does not come back: "
        f"{', '.join(names)}. A design line there gives their flow."
    )


def table_cells(row: dict) -> list[str]:
    """One row of the dock's table, from one row of the study's."""
    low, high = row["storm_area_low_km2"], row["storm_area_high_km2"]
    if low == high:
        areas, peaks = _area(low), f"{row['peak_low_m3s']:.1f}"
    else:
        areas = f"{_area(low)} and {_area(high)}"
        peaks = f"{row['peak_low_m3s']:.1f} and {row['peak_high_m3s']:.1f}"
    return [
        str(row["design_point"]),
        _area(row["drainage_area_km2"]),
        f"{row['design_peak_m3s']:.1f}",
        areas,
        peaks,
        f"{row['time_of_peak_s'] / SECONDS_PER_HOUR:.2f}",
        str(row.get("read_as", "")),
    ]
