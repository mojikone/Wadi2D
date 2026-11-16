# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The last points of the lumped model (W105, his rule of 2026-11-16: "the dams are actually the last point of the
lumped model"), as plain values. No Qt here.

The engine's ``hydrology.last_points``: None is every dam of the lumped network; a list names them all, dams and
junctions alike, and ``[]`` none. The dock shows the dams it finds, each ticked, and the junctions added to them (from
the basin's junctions or the map). A row is ``(name, kind, ticked)``. Only a choice away from the engine's default is
written (:func:`job_value`): every dam ticked and no junction writes nothing, so a model that never touched the list
writes the job it wrote.

Interface: :func:`hms_candidates`, :func:`model_candidates`, :func:`default_rows`, :func:`rows_from_job`,
:func:`merge`, :func:`job_value`, :func:`problems`, :func:`words`, :func:`nearest_junction`.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

LAST_POINTS = "hydrology.last_points"
"""The engine's field; a contract test holds it to the schema."""
DAM, JUNCTION = "dam", "junction"
KIND_WORDS = {DAM: "Dam", JUNCTION: "Junction"}
TIP = (
    "Where the lumped model ends: every dam by default, and any junction added here (HAT-J4 on Block 2). In Hybrid "
    "Lumped the lumped water enters the 2D model at these points, on the edge of the catchments left out of the mesh, "
    "never further down a reach. With the lumped part of the area reduction a curve, a lumped subbasin that enters at "
    "its own outlet (Hybrid 2D) is read at its dam's (last point's) drainage area, one factor per dam, since the 2D "
    "routing runs once; in Lumped and Hybrid Lumped each element is read at its own drainage area."
)
_ELEMENT = re.compile(r"^(Reservoir|Junction|Reach|Subbasin|Sink|Source|Diversion):\s*(.+?)\s*$")
_CANVAS = re.compile(r"^\s*Canvas ([XY]):\s*(\S+)\s*$")


def hms_candidates(basin_file: str | Path) -> tuple[list[str], list[str], dict[str, tuple[float, float]]]:
    """The dams (reservoirs) and junctions of a ``.basin`` file in file order, and each one's icon."""
    dams: list[str] = []
    junctions: list[str] = []
    icons: dict[str, tuple[float, float]] = {}
    current, kind, xy = None, None, {}
    for line in Path(basin_file).read_text(encoding="utf-8", errors="replace").splitlines():
        head = _ELEMENT.match(line)
        if head:
            kind, current, xy = head.group(1), head.group(2), {}
            if kind == "Reservoir":
                dams.append(current)
            elif kind == "Junction":
                junctions.append(current)
            continue
        canvas = _CANVAS.match(line)
        if canvas and current is not None and kind in ("Reservoir", "Junction"):
            try:
                xy[canvas.group(1)] = float(canvas.group(2))
            except ValueError:
                continue
            if "X" in xy and "Y" in xy:
                icons[current] = (xy["X"], xy["Y"])
        if line.strip() == "End:":
            current, kind = None, None
    return dams, junctions, icons


def model_candidates(model: dict | None) -> tuple[list[str], list[str], dict[str, tuple[float, float]]]:
    """The same for a generated basin (``basin.json``): its reservoirs and junctions, each at its outlet point."""
    dams, junctions, icons = [], [], {}
    for element in (model or {}).get("elements", []):
        kind, name = element.get("kind"), element.get("name")
        if kind == "reservoir":
            dams.append(name)
        elif kind == "junction":
            junctions.append(name)
        else:
            continue
        outlet = element.get("outlet")
        if isinstance(outlet, (list, tuple)) and len(outlet) == 2:
            icons[name] = (float(outlet[0]), float(outlet[1]))
    return dams, junctions, icons


def default_rows(dams: list[str]) -> list[tuple[str, str, bool]]:
    """Every dam ticked: the engine's default."""
    return [(name, DAM, True) for name in dams]


def rows_from_job(
    last_points: list[str] | None, dams: list[str], junctions: list[str]
) -> list[tuple[str, str, bool]]:
    """A job's ``hydrology.last_points`` as rows over the dams the basin holds: None ticks every dam; a list ticks the
    dams it names and adds the rest of its names as junctions (a name the basin does not hold is kept, for the engine
    to refuse in words)."""
    if last_points is None:
        return default_rows(dams)
    named = list(dict.fromkeys(last_points))
    rows = [(name, DAM, name in named) for name in dams]
    rows += [(name, JUNCTION, True) for name in named if name not in dams]
    return rows


def merge(rows: list[tuple], dams: list[str]) -> list[tuple[str, str, bool]]:
    """The rows over a basin's dams as they are now: a dam keeps its tick, a dam new to the basin comes ticked, a dam
    gone is dropped; the junctions added stay."""
    held = {name: bool(ticked) for name, kind, ticked in rows if kind == DAM}
    out = [(name, DAM, held.get(name, True)) for name in dams]
    out += [(name, JUNCTION, bool(ticked)) for name, kind, ticked in rows if kind != DAM and name not in dams]
    return out


def job_value(rows: list[tuple], dams: list[str]) -> list[str] | None:
    """``hydrology.last_points`` of the rows: None (not written) when every dam the basin holds is ticked and no
    junction is, else every ticked name in order."""
    ticked = [name for name, _kind, on in rows if on]
    extra = [name for name, kind, on in rows if on and kind != DAM]
    if not extra and set(ticked) == set(dams) and all(name in ticked for name in dams):
        return None
    return ticked


def problems(rows: list[tuple], known: list[str]) -> list[str]:
    """What stops a run in the list, in plain words: a junction the basin does not hold, or one named twice."""
    found = []
    names = [name for name, _kind, _on in rows]
    unknown = [name for name, kind, on in rows if on and kind != DAM and known and name not in known]
    if unknown:
        found.append(
            f"Last points {', '.join(unknown)} are not junctions of the basin: choose them from its junctions, or "
            "remove them."
        )
    twice = sorted({name for name in names if names.count(name) > 1})
    if twice:
        found.append(f"Last points name {', '.join(twice)} twice.")
    return found


def words(rows: list[tuple]) -> str:
    """The section's line: the last points of the lumped model."""
    dams = [name for name, kind, on in rows if on and kind == DAM]
    off = [name for name, kind, on in rows if not on and kind == DAM]
    junctions = [name for name, kind, on in rows if on and kind != DAM]
    if not rows:
        return ""
    if not dams and not junctions:
        return "no last point: the lumped model ends where the grid takes its water"
    parts = []
    if dams:
        parts.append(f"{len(dams)} dam{'s' if len(dams) > 1 else ''}")
    parts += junctions
    said = "ends at " + " + ".join(parts)
    if off:
        said += f" ({len(off)} dam{'s' if len(off) > 1 else ''} not)"
    return f"the lumped model {said}"


def nearest_junction(
    icons: dict[str, tuple[float, float]], junctions: list[str], x: float, y: float
) -> tuple[str, float] | None:
    """The junction whose icon lies nearest a point clicked on the map, and how far, m; None when none has an icon."""
    best = None
    for name in junctions:
        if name not in icons:
            continue
        d = math.hypot(icons[name][0] - x, icons[name][1] - y)
        if best is None or d < best[1]:
            best = (name, d)
    return best
