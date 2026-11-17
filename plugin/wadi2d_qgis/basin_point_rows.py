# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Basin points layer and the delineation ticks of the Generate box (W73), without Qt.

The kinds and fields are the engine's (``wadi2d.basin.points``, ``TerrainObject.delineates``); ``tests/plugin/test_contract.py``
holds the two in step.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

POINT_KINDS = (
    "outfall",
    "design_point",
    "dam",
    "diversion",
    "source",
    "junction",
    "remove_junction",
    "join_subbasins",
)
KIND_WORDS = {
    "outfall": "Outfall: an outlet; several make several networks",
    "design_point": "Design point: a junction with a computation point",
    "dam": "Dam: names a crest line of the job (field crest_line)",
    "diversion": "Diversion: method, divert_to, table, parameters, limits",
    "source": "Source: an inflow hydrograph (field file, a CSV or DSS)",
    "junction": "Junction: split the reach and the subbasin here",
    "remove_junction": "Remove the junction here: join the reaches",
    "join_subbasins": "Join the subbasins at the junction here",
}
NAME_STEMS = {
    "outfall": "Outfall",
    "design_point": "Point",
    "dam": "Dam",
    "diversion": "Diversion",
    "source": "Source",
    "junction": "Junction",
    "remove_junction": "Remove",
    "join_subbasins": "Join",
}
POINT_FIELDS = (
    ("name", "string"),
    ("kind", "string"),
    ("alias", "string"),
    ("crest_line", "string"),
    ("method", "string"),
    ("divert_to", "string"),
    ("table", "string"),
    ("parameters", "string"),
    ("limits", "string"),
    ("file", "string"),
    ("series", "string"),
    ("area_km2", "double"),
)
"""The fields of a Basin points layer the plugin makes; a layer of the user's carries those it needs."""
LAYER_TITLE = "Basin points"
DELINEATE_KINDS = ("crest_line", "wall", "burn_line", "embankment", "channel", "channel_dyke")
DELINEATE_DEFAULT = ("wall", "burn_line")
DELINEATE_WORDS = {
    "crest_line": "Crest lines",
    "wall": "Walls",
    "burn_line": "Burn lines",
    "embankment": "Embankments",
    "channel": "Channels",
    "channel_dyke": "Channels with dykes",
}


DIVERSION_METHODS = ("Inflow-Diversion Table", "Constant Flow", "Specified Flow", "Lateral Weir", "Pump Station")
"""HMS's five, as the engine names them (``wadi2d.basin.diversion.METHODS``)."""
DIVERSION_NEEDS = {
    "Inflow-Diversion Table": "table: inflow and diverted flow, m3/s",
    "Constant Flow": 'parameters {"rate_m3s": ...}; no table',
    "Specified Flow": "table: minutes from the start and diverted flow, m3/s (or a CSV or DSS flow record)",
    "Lateral Weir": 'table: channel stage, m, and flow, m3/s; parameters {"crest_m", "length_m", "coefficient"}, '
    'optional "tailwater" (a stage-flow table of the diverted side)',
    "Pump Station": 'table: channel stage, m, and flow, m3/s; parameters {"units", "on_m", "off_m", "lift_m", '
    '"pump"}, "pump" a head-flow table per unit',
}
"""What each method needs in the fields; limits for any: {"max_m3s": ..., "max_volume_m3": ...} (m3)."""
DIVERSION_COLUMNS = ["Point", "Method", "Divert to", "Table", "Parameters", "Limits", "Needs"]
DIVERSION_EDITS = ("method", "divert_to", "table", "parameters", "limits")
"""The fields the table writes, in column order after the point's name."""
TABLE_PARAMETERS = ("tailwater", "pump")


def diversion_rows(features: list[dict]) -> list[dict]:
    """The layer's diversion points, each a row: fid, name and the five fields as text (blank where unset)."""
    rows = []
    for feature in features:
        if str(feature.get("kind") or "").strip().lower() != "diversion":
            continue
        row = {"fid": feature["fid"], "name": str(feature.get("name") or "")}
        for key in DIVERSION_EDITS:
            value = feature.get(key)
            row[key] = "" if value is None or str(value) == "NULL" else str(value)
        rows.append(row)
    return rows


def needs_words(method: str) -> str:
    return DIVERSION_NEEDS.get(method, f"one of {', '.join(DIVERSION_METHODS)}")


def _is_path(text: str) -> bool:
    return bool(text.strip()) and not text.strip().startswith(("[", "{"))


def next_name(kind: str, taken: set[str]) -> str:
    """A free name for a new point of a kind."""
    stem, number = NAME_STEMS[kind], 1
    while f"{stem} {number}" in taken:
        number += 1
    return f"{stem} {number}"


def point_fields(names: list[str]) -> dict[str, str]:
    """Property to field for every Basin points field the layer has, in any case."""
    lower = {name.lower(): name for name in names}
    return {key: lower[key] for key, _type in POINT_FIELDS if key in lower}


def absolute_files(features: list, folder: Path | str | None) -> list:
    """Points whose ``file``, or a diversion's ``table`` and table parameters (W75), are relative to their layer's
    folder, made absolute: the dock writes the points elsewhere."""
    if folder is None:
        return features
    out = []
    for feature in features:
        properties = dict(feature.properties)
        for key in ("file", "table"):
            given = properties.get(key)
            if given and _is_path(str(given)) and not Path(str(given)).is_absolute():
                properties[key] = str(Path(folder) / str(given).strip())
        if "parameters" in properties:
            properties["parameters"] = _absolute_parameters(properties["parameters"], Path(folder))
        out.append(replace(feature, properties=properties) if properties != feature.properties else feature)
    return out


def _absolute_parameters(text, folder: Path):
    """A diversion's parameters JSON with its table paths made absolute; anything not JSON is left to the engine."""
    if not text or not str(text).strip().startswith("{"):
        return text
    try:
        parameters = json.loads(str(text))
    except json.JSONDecodeError:
        return text
    changed = False
    for key in TABLE_PARAMETERS:
        given = parameters.get(key)
        if isinstance(given, str) and _is_path(given) and not Path(given).is_absolute():
            parameters[key] = str(folder / given.strip())
            changed = True
    return json.dumps(parameters) if changed else text


def default_ticks() -> dict[str, bool]:
    return {kind: kind in DELINEATE_DEFAULT for kind in DELINEATE_KINDS}


def apply_delineate(objects: list[dict], ticks: dict[str, bool] | None) -> list[dict]:
    """The box's ticks on the job's terrain objects, in place: written only where they differ from the engine's default;
    a feature's own ``delineate`` field outranks its kind's tick."""
    for obj in objects:
        kind = obj.get("kind")
        if obj.get("delineate") is None and ticks and kind in ticks and ticks[kind] != (kind in DELINEATE_DEFAULT):
            obj["delineate"] = bool(ticks[kind])
    return objects


def delineate_field(value) -> bool | None:
    """A ``delineate`` attribute as the job takes it: empty is no word, else yes or no."""
    if value is None or str(value).strip() == "":
        return None
    return str(value).strip().lower() not in ("0", "false", "no", "off")


# Where each point snapped (W106, gap 6 of W104): which stream, and its drainage area, before any run.

SNAP_FLAG_M = 50.0
"""A point that moved farther than this to its stream is named for a look: W79's point below R2A moved over 100 m to a
0.08 km2 rill, and R2A's 176 km2 rained on the grid."""
SNAPPED_TITLE = "Basin points: where each snapped"


def snapped_rows(model: dict) -> list[dict]:
    """Each point of the Basin points layer and of the dams, with the node it snapped to: from ``basin.json``'s
    ``pour_point`` (the point as given) and the node's outlet and drainage area."""
    rows = []
    for element in model.get("elements", []):
        pour = element.get("pour_point")
        if not pour or pour.get("x") is None:
            continue
        x, y = float(pour["x"]), float(pour["y"])
        ox, oy = (float(v) for v in element["outlet"])
        area = ((element.get("parameters") or {}).get("drainage_area_km2") or {}).get("value")
        rows.append({
            "name": element["name"], "kind": pour.get("role") or pour.get("kind"), "element": element.get("kind"),
            "x": x, "y": y, "outlet": (ox, oy), "moved_m": ((ox - x) ** 2 + (oy - y) ** 2) ** 0.5, "area_km2": area,
        })  # fmt: skip
    return rows


def snapped_words(rows: list[dict]) -> str:
    """The points in words, the far moves first: which node each snapped to, how far it moved, what drains there."""
    if not rows:
        return ""
    far = [r for r in rows if r["moved_m"] > SNAP_FLAG_M]
    parts = []
    for row in sorted(rows, key=lambda r: -r["moved_m"]):
        area = "an unknown area" if row["area_km2"] is None else f"{row['area_km2']:,.2f} km2"
        parts.append(f"{row['name']} moved {row['moved_m']:.0f} m to the stream there, draining {area}")
    words = "Basin points: " + "; ".join(parts) + "."
    if far:
        words += (
            f" Check {', '.join(r['name'] for r in far)}: moved more than {SNAP_FLAG_M:g} m, so it may sit on another "
            "stream than meant (the map shows each move)."
        )
    return words


def provisional_words(name: str, reach: str | None, area_km2: float | None, distance_m: float, snap_m: float) -> str:
    """Before the basin is generated again: the stream of the last generated basin nearest the click."""
    if reach is None or distance_m > snap_m:
        return (
            f"{name}: no stream of the last generated basin within {snap_m:g} m: the next Generate basin takes the "
            "largest drainage area within reach and makes a stream there; it says where."
        )
    area = "" if area_km2 is None else f", which drains {area_km2:,.2f} km2 at its lower end"
    return (
        f"{name} lies {distance_m:.0f} m from reach {reach} of the last generated basin{area}: Generate basin snaps it "
        "and says the drainage area there."
    )
