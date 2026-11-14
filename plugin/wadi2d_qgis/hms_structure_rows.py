# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Hydrology section's read-only table of the reservoirs an HMS basin holds (W75), without Qt.

The engine reads the file (``wadi2d hms-structures``) and builds each reservoir as the run would, so a refusal in the
table is the run's own words; the plugin parses nothing of the HMS structures itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

COLUMNS = ["Reservoir", "Routes by", "Structures, as HMS holds them", "The engine"]
ROUTES = "routes as HMS does"


@dataclass(frozen=True)
class ReservoirRow:
    name: str
    method: str
    structures: str
    word: str
    refused: bool


def structures_args(basin_file: str | Path, out: str | Path) -> list[str]:
    return ["hms-structures", str(basin_file), "--out", str(out)]


def reservoir_rows(found: dict) -> list[ReservoirRow]:
    """One row per reservoir: its blocks in file order, a fixed tailwater beside them, the engine's word."""
    rows = []
    for item in found.get("reservoirs", []):
        parts = list(item.get("structures") or [])
        if item.get("tailwater"):
            parts.append(f"main tailwater {item['tailwater']} (a crest under it is drowned)")
        refused = item.get("refused")
        rows.append(
            ReservoirRow(
                item["name"], item.get("method") or "", "; ".join(parts) or "none", f"refused: {refused}" if refused
                else ROUTES, bool(refused),
            )
        )
    return rows


def structures_note(found: dict) -> str:
    """The line under the table: how many route, and why the tables could not be read, if so."""
    rows = reservoir_rows(found)
    if not rows:
        return "The basin has no reservoir."
    refused = sum(row.refused for row in rows)
    words = f"{len(rows) - refused} of {len(rows)} reservoirs route by their HMS structures"
    if refused:
        words += f"; the run stops on the {refused} refused, in the words shown"
    if found.get("tables"):
        words += f". Note: {found['tables']}"
    return words + "."
