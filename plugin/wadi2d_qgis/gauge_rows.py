# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The rows of the gauges table, without Qt: rain gauges for the storm, flow and level gauges to check the run against.

A rain gauge stands at a position and its record is spread over the cells and the lumped subbasins by the method of
the section, as HEC-HMS spreads precipitation gages. A flow gauge names a result line, or a lumped element, and a
level gauge a result point; after the run its record is drawn beside the computed series with a summary of agreement,
as HEC-HMS draws an observed discharge gage. Which of line, point or element is decided here from the Results points
layer's names, so a gauge says only the name.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

RAIN, FLOW, LEVEL = "rain", "flow", "level"
KIND_WORDS = {RAIN: "Rain", FLOW: "Flow", LEVEL: "Water level"}
INCREMENTAL, CUMULATIVE = "incremental", "cumulative"
VALUE_WORDS = {INCREMENTAL: "Depth in each period", CUMULATIVE: "Depth since the start"}
THIESSEN, INVERSE_DISTANCE = "thiessen", "inverse_distance"
METHOD_WORDS = {THIESSEN: "Nearest gauge (Thiessen)", INVERSE_DISTANCE: "Inverse distance squared"}
GAPS_ERROR, GAPS_ZERO, GAPS_NEIGHBOURS = "error", "zero", "neighbours"
GAP_WORDS = {
    GAPS_ERROR: "Stops the run, naming the gauge and the time",
    GAPS_ZERO: "Counts as no rain",
    GAPS_NEIGHBOURS: "Takes what the other gauges give at that place",
}
COMPARE_LINE, COMPARE_POINT, COMPARE_ELEMENT = "line", "point", "element"


@dataclass
class GaugeRow:
    name: str
    kind: str = RAIN
    file: str = ""
    series: str = ""
    """A column heading of a CSV, or a DSS pathname or its B/C parts; empty takes the only one."""
    x: float | None = None
    y: float | None = None
    at: str = ""
    """A flow or level gauge's result line, result point or lumped element, by name."""
    values: str = INCREMENTAL
    from_layer: bool = False
    """The row came from the gauge points layer: its name and position are the layer's."""


def merge_rows(points: list[tuple[str, float, float]], old: list[GaugeRow]) -> list[GaugeRow]:
    """The table after the gauge points layer changed: each point a rain gauge row, keeping what was set on it, then the
    rows typed by hand."""
    known = {row.name: row for row in old if row.from_layer}
    rows = []
    for name, x, y in points:
        row = known.get(name, GaugeRow(name, RAIN, from_layer=True))
        row.x, row.y = x, y
        rows.append(row)
    return rows + [row for row in old if not row.from_layer]


def _target(row: GaugeRow, lines: set[str], points: set[str]) -> tuple[str, str] | None:
    """(compare, target) of a flow or level gauge, or None when the name is nothing it can be compared with."""
    if row.kind == LEVEL:
        return (COMPARE_POINT, row.at) if row.at in points else None
    if row.at in lines:
        return COMPARE_LINE, row.at
    return (COMPARE_ELEMENT, row.at) if row.at and row.at not in points else None


def gauge_problems(rows: list[GaugeRow], rain_storm: bool, lines: set[str], points: set[str]) -> list[str]:
    """What stops a run, in plain words. ``rain_storm`` is true when the Storm section takes its rain from the gauges."""
    found = []
    names = [row.name.strip() for row in rows]
    if any(not name for name in names):
        found.append("Every gauge needs a name.")
    if len(set(names)) != len(names):
        found.append("Two gauges have the same name: their results are kept by name.")
    for row in rows:
        if not row.file:
            found.append(f"Gauge {row.name}: choose its record, a CSV table or a DSS file.")
        elif not Path(row.file).is_file():
            found.append(f"Gauge {row.name}: the record is not there: {row.file}")
        if row.kind == RAIN and (row.x is None or row.y is None):
            found.append(f"Rain gauge {row.name} needs its position, x and y.")
        if row.kind != RAIN and _target(row, lines, points) is None:
            where = "a result point" if row.kind == LEVEL else "a result line or a lumped element"
            found.append(f"Gauge {row.name} must name {where} to be compared with.")
    if rain_storm and not any(row.kind == RAIN for row in rows):
        found.append("The storm is set to the rain gauges: add one in the Gauges section.")
    return found


def rain_storm(rows: list[GaugeRow], settings: dict) -> dict:
    """The job's ``storm`` block for rain from the gauges; ``settings`` holds method, radius_m, gaps and start."""
    gauges = []
    for row in rows:
        if row.kind != RAIN:
            continue
        entry = {
            "name": row.name,
            "x": row.x,
            "y": row.y,
            "file": str(Path(row.file).resolve()),
            "values": row.values,
        }
        if row.series:
            entry["record"] = row.series
        gauges.append(entry)
    spread = {
        "gauges": gauges,
        "method": settings.get("method", THIESSEN),
        "gaps": settings.get("gaps", GAPS_ERROR),
    }
    if spread["method"] == INVERSE_DISTANCE and settings.get("radius_m"):
        spread["search_radius_m"] = settings["radius_m"]
    storm = {"kind": "gauges", "gauges": spread}
    if settings.get("start"):
        storm["rain_start"] = settings["start"]
    return storm


def observed_records(rows: list[GaugeRow], lines: set[str], points: set[str], start: str = "") -> list[dict]:
    """The job's ``outputs.observed``: every flow and level gauge with what it is compared with."""
    found = []
    for row in rows:
        target = _target(row, lines, points) if row.kind != RAIN else None
        if target is None:
            continue
        entry = {
            "name": row.name, "file": str(Path(row.file).resolve()), "quantity": FLOW if row.kind == FLOW else LEVEL,
            "compare": target[0], "target": target[1],
        }  # fmt: skip
        if row.series:
            entry["record"] = row.series
        if start:
            entry["start"] = start
        found.append(entry)
    return found


def position_text(row: GaugeRow) -> str:
    """What the table's last column shows."""
    if row.kind == RAIN:
        return "" if row.x is None or row.y is None else f"{row.x:.1f}, {row.y:.1f}"
    return row.at


def read_position(text: str) -> tuple[float, float] | None:
    """x and y typed as two numbers, separated by a comma, a semicolon or spaces; None when they are not."""
    cells = [cell for cell in text.replace(";", " ").replace(",", " ").split() if cell]
    if len(cells) != 2:
        return None
    try:
        return float(cells[0]), float(cells[1])
    except ValueError:
        return None


GRIDDED = "gridded"
"""The storm kind of a rain file, as ``storm_rows.KIND_GRID`` has it; a test holds the two together."""


def joined_gauges(values: dict) -> dict:
    """The dock's values with W54's one ``gauges`` table, from the Storm section's rain gauges (``rain_gauges``, given
    only when the storm takes its rain from them) and the Gauges section's flow and level gauges (``observed_gauges``).

    The two tables keep their own orders, and the job lists rain gauges and observed records apart, so the job is the
    one W54's single table wrote for the same rows. W54 had one start for both; now the records' own start wins, and
    left empty it is the rain gauges' start, which is what one field for both gave.
    """
    rain = values.pop("rain_gauges", None) or {}
    observed = values.pop("observed_gauges", None) or {}
    settings = dict(rain.get("settings") or {})
    own = observed.get("start", "")
    storm = values.get("storm") or {}
    if own and storm.get("kind") == GRIDDED and own == storm.get("start"):
        own = ""  # the run's one start (W99) is the gridded rain's already, and the engine reads the records from it
    settings["observed_start"] = own or settings.get("start", "")
    values["gauges"] = {"rows": list(rain.get("rows") or []) + list(observed.get("rows") or []), "settings": settings}
    return values
