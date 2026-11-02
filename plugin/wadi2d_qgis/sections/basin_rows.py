# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The rows of the generated basin, without Qt: what ``basin.json`` says per subbasin and per junction, the hand-back
lines, and what the job takes from them. The file is read as data; the engine's own words come back in its ``basin`` event.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

STREAM_THRESHOLD = "basin.stream_threshold_km2"
LAG_METHOD = "basin.lag_method"
BASIN_JSON = "hydrology.basin_json"
HANDBACK_ELEMENT = "hydrology.handbacks.element"
TRANSMISSION_ON = "transmission.enabled"
TRANSMISSION_RATE = "transmission.rate_mm_h"
MODE_LUMPED, MODE_2D = "lumped", "2d"
ROUTE_REACH, ROUTE_NONE = "reach", "none"
ELEMENT_KINDS = ("reach", "junction", "reservoir")
"""What a hand-back line can enter."""
LAG_WORDS = {"nrcs": "NRCS watershed lag", "hms_kirpich": "HMS-style: 0.474 x Kirpich (W24 finding)"}
JUNCTION_COLUMNS = ["Junction", "Route", "Next", "At this junction"]


@dataclass
class SubbasinRow:
    name: str
    missing: list[str]
    mode: str
    tip: str


@dataclass
class HandbackRow:
    fid: int
    label: str
    element: str
    pinned: bool = False


def read_basin(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def mode_tip(name: str, missing: list[str], mode: str) -> str:
    if missing:
        return (
            f"{name} lacks {', '.join(missing)}, so it runs as rain-on-grid whatever is chosen here. Fill the value in "
            "basin.json, then generate again."
        )
    return f"{name}: lumped masks its rain in 2D and routes its hydrograph; 2d rains on its cells."


def subbasin_rows(model: dict, asked: dict[str, str] | None = None) -> list[SubbasinRow]:
    """Every subbasin: lumped by default, 2d where asked, 2d whatever was asked where a parameter is missing."""
    asked = asked or {}
    rows = []
    for element in model.get("elements", []):
        if element.get("kind") != "subbasin":
            continue
        name, missing = element["name"], list(element.get("missing", []))
        mode = MODE_2D if missing else asked.get(name, MODE_LUMPED)
        rows.append(SubbasinRow(name, missing, mode, mode_tip(name, missing, mode)))
    return rows


def junction_rows(model: dict) -> list[dict]:
    """The routes as the file holds them; the run's event completes them (``merge_event``)."""
    kinds = {e["name"]: e.get("kind", "junction") for e in model.get("elements", [])}
    return [
        {
            "junction": route["junction"],
            "kind": kinds.get(route["junction"], "junction"),
            "route": route["route"],
            "reach": route.get("reach"),
            "next_junction": route.get("next_junction"),
            "reach_missing": list(route.get("reach_missing", [])),
            "enters_2d": None,
            "handback": None,
            "two_d_sources": [],
        }
        for route in model.get("routes", [])
    ]


def merge_event(rows: list[dict], event: dict) -> list[dict]:
    """What the run decided at each junction, over the file's rows; a junction the file did not list is added."""
    by_name = {row["junction"]: row for row in rows}
    for plan in event.get("junctions", []):
        row = by_name.setdefault(plan["junction"], {"junction": plan["junction"], "reach_missing": []})
        row.update(plan)
    return list(by_name.values())


def route_words(row: dict) -> list[str]:
    """The cells of one junction row: route, next, what happens there."""
    if row["route"] == ROUTE_REACH:
        route = f"reach {row['reach']}"
    elif row.get("reach"):
        route = f"no reach: {row['reach']} lacks {', '.join(row.get('reach_missing', []))}"
    else:
        route = "no reach: over the ground"
    following = row.get("next_junction") or "leaves the model"
    there = []
    if row.get("enters_2d"):
        there.append("water enters the 2D grid here")
    if row.get("handback"):
        sources = ", ".join(row.get("two_d_sources", []))
        there.append(f"hand-back line: 2D flow from {sources} enters the reach")
    elif row.get("enters_2d") is None and row["route"] == ROUTE_REACH:
        there.append("routed; a line is built here if 2D water reaches it")
    elif row.get("enters_2d") is None:
        there.append("water enters the 2D grid here")
    return [row["junction"], route, following, "; ".join(there)]


def summary_text(model: dict, rows: list[SubbasinRow]) -> str:
    kinds = [e.get("kind") for e in model.get("elements", [])]
    counts = {kind: kinds.count(kind) for kind in ("subbasin", "reach", "junction", "reservoir")}
    text = (
        f"{counts['subbasin']} subbasins, {counts['reach']} reaches, {counts['junction']} junctions, "
        f"{counts['reservoir']} reservoirs"
    )
    unassigned = model.get("analysis", {}).get("unassigned_km2")
    if unassigned:
        text += f"; {unassigned:g} km2 reach the edge without meeting a stream and rain on the grid"
    lacking = [row for row in rows if row.missing]
    if lacking:
        named = ", ".join(f"{row.name} ({', '.join(row.missing)})" for row in lacking)
        text += f". Rain-on-grid for lack of a parameter: {named}"
    others = [
        f"{e['name']} ({', '.join(e['missing'])})"
        for e in model.get("elements", [])
        if e.get("kind") != "subbasin" and e.get("missing")
    ]
    if others:
        text += f". Routed as a junction, no reach or no rating, for lack of: {', '.join(others)}"
    notes = model.get("notes", [])
    if notes:
        text += ". " + "; ".join(notes)
    return text + "."


def element_choices(model: dict) -> list[str]:
    """What a hand-back line of a generated basin can enter."""
    return [e["name"] for e in model.get("elements", []) if e.get("kind") in ELEMENT_KINDS]


def hms_elements(basin_file: str | Path) -> list[str]:
    """The reaches, junctions and reservoirs of a ``.basin`` file, in file order."""
    text = Path(basin_file).read_text(encoding="utf-8", errors="replace")
    return re.findall(r"^(?:Reach|Junction|Reservoir):\s*(.+?)\s*$", text, re.MULTILINE)


def line_label(number: int, name: Any) -> str:
    text = "" if name is None else str(name).strip()
    return text or f"Line {number}"


def merge_handbacks(lines: list[dict], old: list[HandbackRow], choices: list[str]) -> list[HandbackRow]:
    """The layer as it is now: a line's ``element`` field pins it; a row the user set keeps its element."""
    known = {row.fid: row for row in old}
    rows = []
    for line in lines:
        row = known.get(line["fid"])
        own = str(line.get("element") or "").strip()
        if row is None:
            rows.append(HandbackRow(line["fid"], line["label"], own or (choices[0] if choices else ""), bool(own)))
        else:
            row.label = line["label"]
            if not row.pinned and row.element not in choices and choices:
                row.element = choices[0]
            rows.append(row)
    return rows


def set_element(row: HandbackRow, element: str) -> None:
    row.element = element
    row.pinned = True


def handback_properties(row: HandbackRow) -> dict:
    return {"name": row.label, "element": row.element}


def basin_settings(stream_threshold_km2: float, lag_method: str) -> dict:
    """The ``basin`` part of a job: 0 km2 means the pour points only, as the command takes it."""
    threshold = stream_threshold_km2 if stream_threshold_km2 > 0.0 else None
    return {"stream_threshold_km2": threshold, "lag_method": lag_method}


def basin_problems(values: dict) -> list[str]:
    """What stops a generation, in plain words."""
    if not values.get("dem"):
        return ["Choose a DEM layer backed by a file."]
    found = ["The DEM must be in a projected CRS, in metres."] if values.get("geographic") else []
    if not values.get("output"):
        found.append("Choose an output folder first: the basin files are kept beside the runs.")
    return found
