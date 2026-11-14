# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The depth-area study as plain values: its storm areas, what stops it, the job's ``arf`` block, and the table it
writes. No Qt here.

The engine runs one 2D job per storm area with the rain read from the storm's area table at that area. Each design
line, and each lumped element a hand-back feeds, reads ln Q against ln A between the two runs either side of its own
drainage area; a lumped element with no 2D water above it is rerun lumped at its own area (``wadi2d/arf.py``).
"""

from __future__ import annotations

import bisect
import itertools
import json
import math
import re
from pathlib import Path

from .protocol import STUDY_FILE
from .storm_rows import KIND_DESIGN, KIND_GRID

AREA_KEY = "drainage_area_km2"
AREA_DECIMALS = 4
"""The engine rounds a storm area to this many decimals; a contract test holds the whole list to the engine's."""
BRACKET, SPACED, LISTED, ARF_STEP = "bracket", "spaced", "listed", "arf_step"
AREA_COUNT, AREA_MIN, AREA_MAX = "arf.n_areas", "arf.area_min_km2", "arf.area_max_km2"
ARF_STEP_MAX = "arf.arf_step_max"
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
    "A study needs a design storm with an area reduction table: in Storm, choose As in the HMS project, Design "
    "storm with area reduction and fill its table, or Gridded rain with Reduce by area ticked."
)
TABLE_WORDS = "Fill the area reduction table of the design storm in Storm: without it every run is the same run."
GRID_WORDS = (
    "Tick Reduce by area for the gridded rain in Storm: without an area reduction table every run is the same run."
)
STUDY_KINDS = (KIND_DESIGN, KIND_GRID)
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
    elif form["spacing"] == ARF_STEP and not 0.0 < form.get("arf_step", 0.0) < 1.0:
        found.append("The largest change of the area reduction between runs must lie between 0 and 1, as 0.05.")
    if form["composite"] and not form["accumulation"]:
        found.append(ACCUMULATION_WORDS)
    return found


def study_areas(form: dict) -> list[float] | None:
    """The storm areas the engine will run, as ``wadi2d.arf.storm_areas`` lists them; None when the engine picks them
    at the start, around drainage areas that only it knows in full."""
    if form["spacing"] in (BRACKET, ARF_STEP):
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
    elif form["spacing"] == ARF_STEP:
        block = {"by_arf_step": True, "arf_step_max": form["arf_step"]}
    elif form["spacing"] == LISTED:
        block = {"areas_km2": parse_areas(form["listed"]) or []}
    else:
        block = {"n_areas": form["count"], "area_min_km2": form["smallest"], "area_max_km2": form["largest"]}
    if form["accumulation"]:  # the lines read after the study take their area from it, with or without the map
        block["accumulation"] = str(Path(form["accumulation"]).resolve())
        block["accumulation_units"] = form["units"]
        if not form["composite"]:
            block["composite"] = False
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
    if (storm is None and not values.get("hms")) or (storm is not None and storm.get("kind") not in STUDY_KINDS):
        found.append(STORM_WORDS)
    elif storm is not None and storm.get("kind") == KIND_GRID and not storm.get("arf_on"):
        found.append(GRID_WORDS)
    elif storm is not None and storm.get("kind") == KIND_DESIGN and not storm.get("arf"):
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
    runs = "1 run" if len(areas) == 1 else f"{len(areas)} runs"
    return f"{runs}, one per storm area: {listed} km2."


def _factor(areas: list[float], factors: list[float], whole_below: bool, area: float) -> float:
    """The table's factor as the engine reads it: linear in area, the end values beyond (``ArfTable.factor``)."""
    if area < areas[0]:
        return 1.0 if whole_below else factors[0]
    if area >= areas[-1]:
        return factors[-1]
    k = next(n for n in range(1, len(areas)) if area < areas[n])
    share = (area - areas[k - 1]) / (areas[k] - areas[k - 1])
    return factors[k - 1] + share * (factors[k] - factors[k - 1])


def step_areas(table: dict, low: float, high: float, largest: float) -> list[float]:
    """The engine's ``ArfTable.step_areas`` in plain Python: equal steps of the factor's path from ``low`` to ``high``,
    each at most ``largest``. A contract test holds the two to the same areas."""
    if high <= low * (1.0 + 1e-9):
        return [low]
    areas, factors = list(table["areas_km2"]), list(table["factors"])
    whole_below = not table.get("reduces_below_table", True)
    knots = sorted({low, high, *(a for a in areas if low < a < high)})
    values = [_factor(areas, factors, whole_below, a) for a in knots]
    if whole_below and low < areas[0] < high:
        at = knots.index(areas[0])
        knots.insert(at, areas[0])
        values.insert(at, 1.0)
    path = [0.0]
    for a, b in itertools.pairwise(values):
        path.append(path[-1] + abs(b - a))
    steps = max(1, math.ceil(path[-1] / largest - 1e-9))
    found = [low]
    for n in range(1, steps):
        target = path[-1] * n / steps
        k = min(max(bisect.bisect_left(path, target), 1), len(knots) - 1)
        rise = path[k] - path[k - 1]
        share = (target - path[k - 1]) / rise if rise > 0.0 else 1.0
        found.append(knots[k - 1] + share * (knots[k] - knots[k - 1]))
    found.append(high)
    return sorted(set(found))


def study_table(values: dict) -> dict | None:
    """The area reduction table the study will read, as the dock holds it; None when it is the HMS project's, which
    the dock sees only when the job is written."""
    storm = values.get("storm")
    if storm is None:
        return None
    rows = storm.get("arf") or []
    if not rows or (storm.get("kind") == KIND_GRID and not storm.get("arf_on")):
        return None
    return {"areas_km2": [r[0] for r in rows], "factors": [r[1] for r in rows]}


def arf_step_areas(form: dict, values: dict, table: dict | None = None) -> list[float] | None:
    """The storm areas of the ARF-step rule from the design lines' drainage areas, as the engine places them; None
    when the table is not known yet or no line has an area. A lumped element a hand-back feeds can widen the span: the
    engine says so when it starts."""
    table = table if table is not None else study_table(values)
    wanted = [area for _name, area in design_lines(values.get("design") or [])[0]]
    if table is None or not wanted:
        return None
    found = step_areas(table, min(wanted), max(wanted), form["arf_step"])
    return sorted({round(float(a), AREA_DECIMALS) for a in found})


def arf_step_text(areas: list[float] | None, largest: float) -> str:
    """How many runs the ARF-step rule gives, at which areas; or the rule, when the table is not known yet."""
    rule = f"the area reduction changes by at most {largest:.3g} between neighbouring runs"
    if areas is None:
        return (
            f"Runs placed when the study starts, from the smallest to the largest drainage area of the design lines, so "
            f"that {rule}: give the design lines their drainage areas and the storm its reduction table to see them here."
        )
    return f"{areas_text(areas, 0.0, 0)[:-1]}; {rule}."


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
