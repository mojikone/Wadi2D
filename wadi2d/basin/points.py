"""The Basin points layer (W73): one point layer of kinds, the user's clicks on the map, read into pour points and edits.

A feature's ``kind`` field says what the point is (W58 section 4):

| kind | what the generator does |
|---|---|
| ``outfall`` | a node and an outlet: with any outfall in the layer, the model keeps only what drains to one, and every outfall is an outlet, so several outfalls make several networks in one generation |
| ``design_point`` | a node with a computation point; ``alias`` names it again (W1's R5 for junction R5A) |
| ``dam`` | names a crest line of the job in ``crest_line``: that dam's node takes the point's name as an alias. With no such crest line it stays a junction, said in the notes (W58 decision 4 is his) |
| ``diversion`` | a junction carrying a ``diversion`` block (``method``, ``divert_to``, ``table``, ``parameters``, ``limits``), read at generation and run as W72's diversion element (W75, :mod:`wadi2d.basin.diversion`) |
| ``source`` | an external hydrograph (``file``, a CSV table or a DSS file, ``series`` picking a record, optional ``area_km2``) entering the network at the junction it snaps to |
| ``junction`` | a forced junction: splits the reach and the subbasin it lands in |
| ``remove_junction`` | drops the junction it snaps to: the reaches either side become one, a tributary there runs on to the next junction |
| ``join_subbasins`` | keeps the junction and makes one subbasin of the local subbasins draining to it, HMS's merge |

A layer with no ``kind`` field reads as plain break points, as before W73, so old jobs keep their numbers. Every edit is a
point, never an element name, so a regeneration replays it after the threshold or the DEM has changed.

Interface: the ``POINT_*`` kinds, :class:`PointEdit`, :func:`read_points`, :func:`read_source`, :func:`keep_outfalls`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from wadi2d.io.series import FLOW, read_record

POINT_OUTFALL, POINT_DESIGN, POINT_DAM, POINT_DIVERSION, POINT_SOURCE = (
    "outfall",
    "design_point",
    "dam",
    "diversion",
    "source",
)
POINT_JUNCTION, POINT_REMOVE, POINT_JOIN = "junction", "remove_junction", "join_subbasins"
BREAK_KINDS = (POINT_OUTFALL, POINT_DESIGN, POINT_DAM, POINT_DIVERSION, POINT_SOURCE, POINT_JUNCTION)
"""Kinds that make a node where they snap."""
EDIT_KINDS = (POINT_REMOVE, POINT_JOIN)
"""Kinds that change the node they snap to, after the network is found."""
POINT_KINDS = BREAK_KINDS + EDIT_KINDS
KIND_FIELDS = ("kind", "Kind", "KIND")
DIVERSION_FIELDS = ("method", "divert_to", "table", "parameters", "limits")
CFS_TO_M3S = 0.028316846592
CFS_UNITS = ("CFS", "FT3/S", "CU FT/S")


@dataclass(frozen=True)
class PointEdit:
    """A point that changes a node: ``remove_junction`` or ``join_subbasins``."""

    kind: str
    name: str
    x: float
    y: float


def point_kind(properties: dict[str, Any], name: str) -> str | None:
    """The kind of a feature; None for a layer that has no kind (plain break points)."""
    raw = next((properties[key] for key in KIND_FIELDS if key in properties), None)
    if raw is None or str(raw).strip() == "":
        return None
    kind = str(raw).strip().lower().replace(" ", "_")
    if kind not in POINT_KINDS:
        raise ValueError(f"basin point {name}: kind {raw!r} is not one of {', '.join(POINT_KINDS)}")
    return kind


def _text(properties: dict[str, Any], key: str) -> str | None:
    value = properties.get(key)
    return None if value is None or str(value).strip() == "" else str(value).strip()


def diversion_block(properties: dict[str, Any], name: str, folder: Path | None = None) -> dict[str, Any]:
    """What a diversion point says, read for the diversion element (W75, :mod:`wadi2d.basin.diversion`): the method's
    name, its parameters and limits from JSON text, as a GIS field holds them, its tables read from beside the layer."""
    from wadi2d.basin.diversion import resolve_block

    block: dict[str, Any] = {key: _text(properties, key) for key in DIVERSION_FIELDS}
    if block["limits"] is not None:
        try:
            json.loads(block["limits"])
        except json.JSONDecodeError as error:
            raise ValueError(f"diversion {name}: limits {block['limits']!r} is not JSON, e.g. {{\"max_m3s\": 50}}") from error
    block["point"] = name
    return resolve_block(block, folder)


def read_source(properties: dict[str, Any], name: str, folder: Path, notes: list[str]) -> dict[str, Any]:
    """A source point's hydrograph, read now so ``basin.json`` carries it; a relative ``file`` is beside the layer."""
    given = _text(properties, "file")
    if given is None:
        raise ValueError(f"source {name}: the point needs a file, a CSV table or a DSS file of the hydrograph")
    path = Path(given) if Path(given).is_absolute() else folder / given
    record = read_record(path, record=_text(properties, "series"), want=FLOW)
    flows = np.asarray(record.values, dtype=np.float64)
    if record.units.strip().upper() in CFS_UNITS:
        flows = flows * CFS_TO_M3S
    if not np.all(np.isfinite(flows)):
        raise ValueError(f"source {name}: {path.name} has missing flows; fill them before the generation")
    if record.dated:
        minutes = (record.dates - record.dates[0]) / np.timedelta64(1, "s") / 60.0
        notes.append(f"source {name}: {path.name} is dated from {record.dates[0]}; it enters from the start of the run")
    else:
        minutes = record.minutes
    area = properties.get("area_km2")
    return {
        "name": name,
        "file": str(path),
        "series": _text(properties, "series"),
        "area_km2": None if area in (None, "") else float(area),
        "minutes": [round(float(v), 4) for v in minutes],
        "flow_m3s": [round(float(v), 6) for v in flows],
    }


def keep_outfalls(elements: list[dict], outfalls: list[str], notes: list[str]) -> list[dict]:
    """The elements draining to an outfall, each outfall an outlet; an outfall above another stays a node of its network."""
    if not outfalls:
        return elements
    by_name = {e["name"]: e for e in elements}
    kept: set[str] = set()
    for element in elements:
        chain, name = [], element["name"]
        while name is not None:
            chain.append(name)
            if name in outfalls:
                kept.update(chain)
                break
            name = by_name[name]["downstream"]
    for name in outfalls:
        below, lower = by_name[name]["downstream"], None
        while below is not None and lower is None:
            lower = below if below in outfalls else None
            below = by_name[below]["downstream"]
        if lower is not None:
            notes.append(f"outfall {name} drains to outfall {lower}: it stays a node of that network")
        else:
            by_name[name]["downstream"] = None
    dropped = len(elements) - len(kept)
    if dropped:
        notes.append(f"{dropped} elements drain to no outfall of the Basin points layer: left out")
    return [e for e in elements if e["name"] in kept]


def read_points(properties: dict[str, Any], name: str, folder: Path | None = None) -> tuple[str | None, dict[str, Any]]:
    """A feature's kind and the fields its kind carries; ``folder`` is the layer's, for a diversion's tables."""
    kind = point_kind(properties, name)
    extra: dict[str, Any] = {}
    if kind == POINT_DESIGN and _text(properties, "alias"):
        extra["alias"] = _text(properties, "alias")
    if kind == POINT_DAM:
        extra["crest_line"] = _text(properties, "crest_line")
    if kind == POINT_DIVERSION:
        extra["diversion"] = diversion_block(properties, name, folder)
    return kind, extra
