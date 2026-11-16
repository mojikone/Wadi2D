# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Each subbasin's own storm area, entry and outlet, and the point inflows of lumped elements (W103), as plain values.
No Qt here.

What a job written outside the dock holds per subbasin and per element, and the dock held before only as the HMS import
gave it (W102 found the Block 2 Hybrid jobs could not be held without them):

- **A subbasin edit** is ``{"storm_area_km2", "entry", "outlet"}``, each None for "as the basin gives": the HMS import's
  outlet and its entry ``wadi``, the storm's own area. ``outlet`` is ``[x, y]`` in the DEM's CRS, or :data:`NO_OUTLET`,
  an outlet taken away: a lumped subbasin whose water an inflow from an element below it brings in has no outlet of its
  own, or it would enter twice (W88). Only what is set is written (:func:`apply_edits`), so a model with no edit writes
  the job it wrote.
- **An inflow row** is ``(name, element, x, y, entry, enters)``: the outflow of a lumped element (a dam, a junction, a
  reach) entering the grid at a point in the DEM's CRS, ``hydrology.inflows``. ``entry`` is the engine's ``point`` or
  ``wadi``, ``enters`` False where the element's water leaves the model there, as at an HMS sink. A table hydrograph at a
  point (``times_s`` and ``flows``) is not held here: the dock's flow lines carry hydrographs.

Interface: :func:`outlet_text`, :func:`parse_outlet`, :func:`clean`, :func:`apply_edits`, :func:`edits_from_job`,
:func:`edit_problems`, :func:`inflow_rows`, :func:`inflow_jobs`, :func:`inflow_problems`, :func:`words`.
"""

from __future__ import annotations

import math

STORM_AREA = "hydrology.subbasins.storm_area_km2"
SUBBASIN_ENTRY = "hydrology.subbasins.entry"
SUBBASIN_OUTLET = "hydrology.subbasins.outlet"
INFLOW_ELEMENT = "hydrology.inflows.element"
INFLOW_ENTRY = "hydrology.inflows.entry"
INFLOW_ENTERS = "hydrology.inflows.enters"
"""The engine's fields this module writes; a contract test holds them to the engine's schema."""
ENTRY_POINT, ENTRY_WADI, ENTRY_EDGE = "point", "wadi", "edge"
"""The engine's entry rules; ``point`` is its default, which a contract test holds. ``edge`` is an inflow's alone: at
the pour point of the catchments it brings in that the mesh leaves out (W105)."""
NO_OUTLET = "none"
"""An outlet taken away, as the table's cell shows and takes it."""
KEYS = ("storm_area_km2", "entry", "outlet")
ENTRY_WORDS = {
    None: "As the basin gives",
    ENTRY_WADI: "At the wadi outlet of its polygon",
    ENTRY_POINT: "At its outlet point",
}
INFLOW_ENTRY_WORDS = {
    ENTRY_POINT: "At the point",
    ENTRY_WADI: "Up the wadi from the point",
    ENTRY_EDGE: "At the edge of the catchments left out",
}
INFLOW_COLUMNS = ("Name", "Element", "X", "Y", "Enters", "Enters the grid")
OUTLET_WORDS = (
    'Subbasin {name}: the outlet "{text}" is not a point. Give x, y in the DEM\'s coordinates, "none" for no outlet of '
    "its own (an inflow below it carries its water), or leave it empty for the basin's."
)
OWN_AREA_2D = (
    "Subbasin {name} has a storm area of its own and is treated as 2D: a storm area of its own is for a lumped subbasin "
    "(a 2D subbasin's rain falls on its cells at the storm's area). Clear it, or treat the subbasin as lumped."
)
OWN_AREA_TABLE = (
    "Subbasins {names} read the area-reduction curve at a storm area of their own: set the lumped part of the area "
    "reduction (4b) to the curve, or both parts to one storm area, or clear their storm areas."
)
OWN_AREA_OBSERVED = "Subbasins {names} have a storm area of their own, and this rain takes no area reduction: clear their storm areas."
TABLE_FORMS = ("area", "curve")
"""What a subbasin's own storm area needs of the area reduction (``reduction_rows.lumped_form``): the single-storm form
at one area, or a lumped curve; the engine's rule."""


def outlet_text(outlet) -> str:
    """The table's cell for an outlet: empty for the basin's, "none", or x, y to the millimetre."""
    if outlet is None:
        return ""
    if outlet == NO_OUTLET:
        return NO_OUTLET
    return f"{float(outlet[0]):.3f}, {float(outlet[1]):.3f}"


def parse_outlet(text: str, name: str = ""):
    """The outlet a cell holds: None (the basin's), :data:`NO_OUTLET`, or ``[x, y]``. ``ValueError`` in words."""
    text = (text or "").strip()
    if not text:
        return None
    if text.lower() == NO_OUTLET:
        return NO_OUTLET
    parts = [part for part in text.replace(";", ",").replace(" ", ",").split(",") if part]
    try:
        x, y = (float(part) for part in parts)
    except ValueError:
        raise ValueError(OUTLET_WORDS.format(name=name, text=text)) from None
    if not (math.isfinite(x) and math.isfinite(y)):
        raise ValueError(OUTLET_WORDS.format(name=name, text=text))
    return [x, y]


def clean(edit: dict | None) -> dict:
    """An edit with what is not set taken out; empty when nothing is set."""
    return {key: (list(value) if isinstance(value, (list, tuple)) else value)
            for key, value in (edit or {}).items() if key in KEYS and value is not None}  # fmt: skip


def clean_all(edits: dict | None) -> dict:
    """Every subbasin's edit, cleaned; a subbasin with nothing set is left out."""
    return {name: clean(edit) for name, edit in (edits or {}).items() if clean(edit)}


def apply_edits(subbasins: list[dict], edits: dict | None) -> list[dict]:
    """The job's subbasins with each one's edit laid over: a storm area or an entry set, an outlet set or taken away.
    A subbasin with no edit stays as it was, to the key."""
    edits = clean_all(edits)
    out = []
    for entry in subbasins:
        edit = edits.get(entry.get("name"), {})
        if not edit:
            out.append(entry)
            continue
        changed = dict(entry)
        for key, value in edit.items():
            changed[key] = None if value == NO_OUTLET else value
        out.append(changed)
    return out


def edits_from_job(subbasins: list[dict]) -> dict:
    """What a job's own subbasins say, as edits, every value pinned: the storm area where it has one, the entry (the
    engine's default where the job leaves it out) and the outlet, :data:`NO_OUTLET` where it has none. A job written
    outside the dock lists its subbasins whole, so the dock writes them back as they stand, whatever the HMS file's
    icons say now."""
    edits = {}
    for sub in subbasins or []:
        name = sub.get("name")
        if not name:
            continue
        outlet = sub.get("outlet")
        edit = {
            "storm_area_km2": sub.get("storm_area_km2"),
            "entry": sub.get("entry") or ENTRY_POINT,
            "outlet": [float(outlet[0]), float(outlet[1])] if outlet else NO_OUTLET,
        }
        edits[name] = clean(edit)
    return edits


def edit_problems(edits: dict | None, modes: dict[str, str], lumped_form: str | None = None) -> list[str]:
    """What stops a run in the subbasins' edits, in plain words. ``lumped_form`` is the lumped part's form of the area
    reduction when the dock's Storm sets the rain (None for the HMS project's own storm, which carries its table)."""
    edits = clean_all(edits)
    found = []
    own = [name for name, edit in edits.items() if edit.get("storm_area_km2") is not None]
    for name in own:
        if modes.get(name, "lumped") != "lumped":
            found.append(OWN_AREA_2D.format(name=name))
    lumped_own = [name for name in own if modes.get(name, "lumped") == "lumped"]
    if lumped_own and lumped_form is not None and lumped_form not in TABLE_FORMS:
        shown = ", ".join(lumped_own[:6]) + (
            f" and {len(lumped_own) - 6} more" if len(lumped_own) > 6 else ""
        )
        words = OWN_AREA_OBSERVED if lumped_form == "observed" else OWN_AREA_TABLE
        found.append(words.format(names=shown))
    return found


def inflow_rows(inflows: list[dict]) -> list[tuple]:
    """A job's inflows from lumped elements as the table's rows; a table hydrograph at a point is not held here."""
    rows = []
    for inflow in inflows or []:
        if inflow.get("element") is None:
            continue
        rows.append((
            str(inflow.get("name") or ""), str(inflow["element"]), float(inflow["x"]), float(inflow["y"]),
            inflow.get("entry") or ENTRY_POINT, bool(inflow.get("enters", True)),
        ))  # fmt: skip
    return rows


def inflow_jobs(rows: list[tuple]) -> list[dict]:
    """The rows as ``hydrology.inflows``: the entry and ``enters`` only where they leave the engine's defaults."""
    out = []
    for name, element, x, y, entry, enters in rows:
        job = {"name": name, "x": float(x), "y": float(y), "element": element}
        if entry and entry != ENTRY_POINT:
            job["entry"] = entry
        if not enters:
            job["enters"] = False
        out.append(job)
    return out


def inflow_problems(rows: list[tuple]) -> list[str]:
    """What stops a run in the inflow table, in plain words."""
    found = []
    names = [str(row[0]).strip() for row in rows]
    for number, (name, element, x, y, _entry, _enters) in enumerate(rows, start=1):
        label = f'Point inflow {number} ("{name}")' if name else f"Point inflow {number}"
        if not str(name).strip():
            found.append(f"{label} needs a name: the run keeps its series by name.")
        if not str(element or "").strip():
            found.append(f"{label} needs the lumped element whose outflow enters there.")
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (x, y)):
            found.append(f"{label} needs its point: x and y in the DEM's coordinates.")
    twice = sorted({name for name in names if name and names.count(name) > 1})
    if twice:
        found.append(f"Point inflows need names of their own: {', '.join(twice)} stands twice.")
    return found


def words(edits: dict | None, rows: list[tuple]) -> str:
    """The section's line on what is set here."""
    edits = clean_all(edits)
    own = sum(1 for edit in edits.values() if "storm_area_km2" in edit)
    placed = sum(1 for edit in edits.values() if "entry" in edit or "outlet" in edit)
    parts = [
        f"{own} at a storm area of {'their' if own > 1 else 'its'} own" if own else "",
        f"{placed} entr{'ies' if placed > 1 else 'y'} set by subbasin" if placed else "",
        f"{len(rows)} point inflow{'s' if len(rows) > 1 else ''}" if rows else "",
    ]
    return " \N{MIDDLE DOT} ".join(part for part in parts if part)
