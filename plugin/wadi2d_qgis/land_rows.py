# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Manning in its four forms and the curve-number override, as plain values (W101 item 2; the engine's W96
``terrain.roughness`` and ``hydrology.cn_override``). No Qt here.

One value and a grid of n stay the job's ``terrain.manning`` and ``terrain.manning_raster``, as the dock always wrote
them, so an older model writes the job it wrote; squares and aligned cells apart, and land-use classes, write
``terrain.roughness``. The override is written only when one is chosen.

Interface: :func:`roughness_job`, :func:`roughness_problems`, :func:`cn_job`, :func:`cn_problems`, the forms' words.
"""

from __future__ import annotations

from pathlib import Path

ONE, SPLIT, GRID, LAND = "uniform", "split", "grid", "land_use"
ROUGH_WORDS = {
    ONE: "One value",
    SPLIT: "Squares and aligned cells apart",
    GRID: "A grid of n",
    LAND: "Land-use classes, a table of n",
}
NONE, BY_LAND, BY_RANGE, BY_SUBBASIN = "none", "land_use", "range", "subbasin"
CN_WORDS = {
    NONE: "None: the CN as given",
    BY_LAND: "By land-use class, a table of CN",
    BY_RANGE: "By CN range: every CN in a range becomes one",
    BY_SUBBASIN: "By subbasin",
}
CN_COLUMNS = {
    BY_LAND: (("Class code", "CN", "Name"), (2,)),
    BY_RANGE: (("From CN", "To CN", "Becomes CN"), ()),
    BY_SUBBASIN: (("Subbasin", "CN"), (0,)),
}
"""The table's columns for each override, and which hold words."""
LAND_COLUMNS = (("Class code", "Manning n", "Name"), (2,))
N_LOW, N_HIGH = 0.008, 0.5
SPLIT_WORDS = "Squares and aligned cells apart gives the aligned cells their own n: tick the aligned cells in Mesh, or choose one value."


def _land_raster(path: str | None, what: str) -> list[str]:
    if not path:
        return [f"{what} needs its land-use raster, a layer backed by a file."]
    return [] if Path(path).is_file() else [f"The land-use raster of {what.lower()} is not there: {path}"]


def roughness_problems(rough: dict | None, strips: bool) -> list[str]:
    if not rough or rough["form"] in (ONE, GRID):
        return []
    if rough["form"] == SPLIT:
        found = [] if strips else [SPLIT_WORDS]
        if not N_LOW <= rough.get("n_aligned", 0.0) <= N_HIGH:
            found.append(f"The aligned cells' Manning n lies between {N_LOW} and {N_HIGH}.")
        return found
    found = _land_raster(rough.get("land_use"), "Manning by land-use class")
    classes = rough.get("classes") or []
    if not classes:
        found.append("Fill the table of Manning n by land-use class.")
    codes = [int(row[0]) for row in classes]
    if len(set(codes)) != len(codes):
        found.append("A land-use class is in the Manning table twice.")
    if any(not N_LOW <= row[1] <= N_HIGH for row in classes):
        found.append(f"Every class's Manning n lies between {N_LOW} and {N_HIGH}.")
    return found


def roughness_job(rough: dict | None) -> dict | None:
    """``terrain.roughness`` for the two forms the old fields cannot say; None for one value and a grid."""
    if not rough or rough["form"] in (ONE, GRID):
        return None
    if rough["form"] == SPLIT:
        return {"form": SPLIT, "n": rough["n"], "n_aligned": rough["n_aligned"]}
    return {
        "form": LAND,
        "land_use": str(Path(rough["land_use"]).resolve()),
        "classes": [_named({"code": int(row[0]), "n": row[1]}, row) for row in rough["classes"]],
    }


def _named(entry: dict, row: tuple) -> dict:
    if len(row) > 2 and row[2]:
        entry["name"] = row[2]
    return entry


def cn_problems(override: dict | None) -> list[str]:
    if not override or override["by"] == NONE:
        return []
    by = override["by"]
    rows = override.get(by_rows(by)) or []
    found = _land_raster(override.get("land_use"), "The CN by land-use class") if by == BY_LAND else []
    if not rows:
        found.append(f"Fill the table of the CN override {CN_WORDS[by].split(',')[0].lower()}.")
        return found
    if by == BY_SUBBASIN and any(not row[0] for row in rows):
        found.append("Every row of the CN override by subbasin names its subbasin.")
    cns = [row[-1] for row in rows] + ([v for row in rows for v in row[:2]] if by == BY_RANGE else [])
    if any(not 0.0 < cn <= 100.0 for cn in cns):
        found.append("A curve number lies above 0 and at most 100.")
    if by == BY_RANGE:
        spans = sorted((row[0], row[1]) for row in rows)
        if any(high < low for low, high in spans):
            found.append("A CN range runs from its low to its high value.")
        if any(spans[k + 1][0] <= spans[k][1] for k in range(len(spans) - 1)):
            found.append("The CN ranges overlap: each CN may fall in one range.")
    if by == BY_LAND:
        codes = [int(row[0]) for row in rows]
        if len(set(codes)) != len(codes):
            found.append("A land-use class is in the CN table twice.")
    if by == BY_SUBBASIN and len({row[0] for row in rows}) != len(rows):
        found.append("A subbasin is in the CN table twice.")
    return found


def by_rows(by: str) -> str:
    return {BY_LAND: "classes", BY_RANGE: "ranges", BY_SUBBASIN: "subbasins"}[by]


def cn_job(override: dict | None) -> dict | None:
    """``hydrology.cn_override``; None when none is chosen."""
    if not override or override["by"] == NONE:
        return None
    by = override["by"]
    rows = override[by_rows(by)]
    if by == BY_LAND:
        return {
            "by": BY_LAND, "land_use": str(Path(override["land_use"]).resolve()),
            "classes": [_named({"code": int(row[0]), "curve_number": row[1]}, row) for row in rows],
        }  # fmt: skip
    if by == BY_RANGE:
        return {"by": BY_RANGE, "ranges": [{"low": row[0], "high": row[1], "curve_number": row[2]} for row in rows]}
    return {"by": BY_SUBBASIN, "subbasins": [{"name": row[0], "curve_number": row[1]} for row in rows]}


def rough_words(rough: dict | None, manning: float, raster: str | None) -> str:
    if not rough or rough["form"] == ONE:
        return f"Manning from {raster}" if raster else f"Manning {manning:g}"
    if rough["form"] == GRID:
        return f"Manning from {raster}" if raster else f"Manning {manning:g}"
    if rough["form"] == SPLIT:
        return f"Manning {rough['n']:g} on squares, {rough['n_aligned']:g} on aligned cells"
    return f"Manning by {len(rough.get('classes') or [])} land-use classes"


def cn_words(override: dict | None) -> str:
    if not override or override["by"] == NONE:
        return ""
    rows = override.get(by_rows(override["by"])) or []
    return f"CN override {CN_WORDS[override['by']].split(',')[0].split(':')[0].lower()}, {len(rows)} rows"
