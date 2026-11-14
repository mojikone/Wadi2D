"""What the chart's header says of each element of an HEC-HMS basin (W74), as :func:`element_facts` says it of a
generated one: kind, drainage area and, for a subbasin, Kirpich's tc and its lag.

HMS keeps a subbasin's longest flow path and its 10-85 slope in the basin's ``.sqlite`` (``subbasin_statistics``, filled
when the terrain characteristics were computed), not in the ``.basin`` text. Where they are there, the tc is his HMS
expression on them (:func:`wadi2d.basin.parameters.kirpich_tc_minutes`, the one his lags follow); where they are not, and
on every reach, junction, reservoir, diversion, source and sink (HMS holds no flow path to their outlet), the tc is not
available and the header says so. The drainage area follows the ``Downstream`` links alone, HMS's own reading: a
diversion's branch is not counted below it.

Interface: :func:`hms_element_facts`.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

KINDS = ("subbasin", "reach", "junction", "reservoir", "diversion", "source", "sink")
LENGTH_TO_M = {"m": 1.0, "meter": 1.0, "meters": 1.0, "km": 1000.0, "ft": 0.3048, "feet": 0.3048, "mi": 1609.344}
SQ_MI_TO_KM2 = 2.589988110336
ENGLISH = "english"
NO_PATH = "the HMS basin's .sqlite holds no flow path for it"
NOT_A_SUBBASIN = "HMS holds no flow path to an element's outlet"


def _statistics(basin_path: Path, sqlite_path: str | Path | None) -> dict:
    from wadi2d.hms.sqlite import subbasin_statistics

    path = Path(sqlite_path) if sqlite_path else basin_path.with_suffix(".sqlite")
    if not path.is_file():
        return {}
    try:
        return subbasin_statistics(path)
    except (OSError, sqlite3.Error):
        return {}


def _tc(stats) -> float | None:
    from wadi2d.basin.parameters import kirpich_tc_minutes

    if stats is None or not stats.longest_length or not stats.slope_10_85 or stats.slope_10_85 <= 0.0:
        return None
    factor = LENGTH_TO_M.get((stats.length_units or "m").strip().lower())
    return None if factor is None else kirpich_tc_minutes(stats.longest_length * factor, stats.slope_10_85)


def hms_element_facts(basin_path: str | Path, sqlite_path: str | Path | None = None) -> dict[str, dict]:
    """Facts by element name; empty when the basin file cannot be read."""
    from wadi2d.hms import basin as hms_basin

    basin_path = Path(basin_path)
    try:
        basin = hms_basin.load(basin_path)
    except (OSError, ValueError):
        return {}
    groups = {
        "subbasin": basin.subbasins, "reach": basin.reaches, "junction": basin.junctions,
        "reservoir": basin.reservoirs, "diversion": basin.diversions, "source": basin.sources, "sink": basin.sinks,
    }  # fmt: skip
    kind_of = {name: kind for kind in KINDS for name in groups[kind]}
    to_km2 = SQ_MI_TO_KM2 if (basin.unit_system or "").strip().lower() == ENGLISH else 1.0
    upstream = basin.connectivity().upstream
    statistics = _statistics(basin_path, sqlite_path)
    facts: dict[str, dict] = {}
    for element in basin.elements:
        name = element.name
        seen, todo, area = set(), [name], 0.0
        while todo:
            here = todo.pop()
            if here in seen:
                continue
            seen.add(here)
            if here in basin.subbasins:
                area += float(basin.subbasins[here].area or 0.0) * to_km2
            todo.extend(upstream.get(here, []))
        kind = kind_of.get(name, "")
        found = {"kind": kind, "drainage_area_km2": round(area, 4) if area > 0.0 else None, "tc_minutes": None}
        if kind == "subbasin":
            tc = _tc(statistics.get(name))
            found["tc_minutes"] = None if tc is None else round(tc, 2)
            lag = getattr(basin.subbasins[name].transform, "lag", None)
            found["lag_minutes"] = None if lag is None else float(lag)
            if tc is None:
                found["tc_note"] = NO_PATH
        else:
            found["tc_note"] = NOT_A_SUBBASIN
        facts[name] = found
    return facts
