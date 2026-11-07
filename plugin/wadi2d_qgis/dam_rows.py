# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The rows of the dam start table, without Qt: each dam by name, and where its pool stands when the run starts.

A dam is a crest line or an embankment with a name; a generated basin names its reservoir after the crest line, so one row
sets the lumped pool or the grid pool, whichever the run routes. Empty is the default and goes nowhere in the job.
"""

from __future__ import annotations

from dataclasses import dataclass

START_EMPTY, START_SPILLWAY, START_LEVEL = "empty", "spillway", "level"
START_WORDS = {START_EMPTY: "Empty", START_SPILLWAY: "Spillway crest", START_LEVEL: "Level"}
START_TIPS = {
    START_EMPTY: "Empty pool: a design run reads the dam's attenuation",
    START_SPILLWAY: "Full to the lowest spillway crest",
    START_LEVEL: "Water at the level typed in the next column, m",
}


@dataclass
class DamRow:
    name: str
    start: str = START_EMPTY
    level: float | None = None


def dam_names(names: list) -> list[str]:
    """The named dams of the layers, each once, in the order met; a line with no name is no dam of this table."""
    seen: list[str] = []
    for name in names:
        text = "" if name is None else str(name).strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def merge_dams(names: list[str], old: list[DamRow]) -> list[DamRow]:
    """The dams as the layers are now: a dam still there keeps its choice, a new one starts empty."""
    known = {row.name: row for row in old}
    return [known.get(name, DamRow(name)) for name in names]


def dam_levels(rows: list[DamRow]) -> list[dict]:
    """The job's ``dam_levels``: every dam that does not start empty."""
    out = []
    for row in rows:
        if row.start == START_SPILLWAY:
            out.append({"name": row.name, "start": START_SPILLWAY})
        elif row.start == START_LEVEL and row.level is not None:
            out.append({"name": row.name, "start": row.level})
    return out


def dam_problems(rows: list[DamRow]) -> list[str]:
    return [f"Dam {row.name} starts at a level: type the level." for row in rows if row.start == START_LEVEL and row.level is None]


def initial_water(features: list) -> list[dict]:
    """The job's ``initial_levels`` from polygons whose ``level`` property holds the water level."""
    return [{"coordinates": f.coordinates[0], "level": float(f.properties["level"])} for f in features]


def initial_problems(features: list) -> list[str]:
    if any(f.properties.get("level") is None for f in features):
        return ["Every initial water polygon needs a level: choose the field that holds it."]
    return []
