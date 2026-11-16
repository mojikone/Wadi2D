# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The area reduction of the dock as plain values (W101): one setting for the lumped part, one for the 2D part, and
what each writes into the job's storm. No Qt here.

A part is a dict ``{"form", "curve", "area_km2", "coefficient", "single_km2"}``. The lumped part is none, a coefficient,
a fixed area read on a stored curve, or the curve itself, read at each element's own area (W95, W98). The 2D part is
none, a coefficient, a fixed area, or the depth-area study, which reads the curve at each run's storm area; a single
run of a 2D part set to the study reads it at ``single_km2``, since the cells of one run have no area of their own.

What the job holds: where every part the model has is the same coefficient or the same fixed area, the storm keeps the
single-storm form the engine always read (``storm.arf_factor``, or ``storm.storm_area_km2`` with ``storm.arf``), which
applies one factor to the lumped subbasins and the 2D cells alike, so a model of the dock before W101 writes the job it
wrote. Anything else, and every ``depth`` or ``depth_grid`` storm, writes ``storm.area_reduction`` with the curves by
name, and the job's ``data_tables`` holds those curves.

Interface: :func:`reduction_problems`, :func:`reduction_job`, :func:`factor_at`, :func:`words`.
"""

from __future__ import annotations

NONE, COEFFICIENT, AREA, CURVE, STUDY = "none", "coefficient", "area", "curve", "study"
LUMPED_FORMS = (NONE, COEFFICIENT, AREA, CURVE)
GRID_FORMS = (NONE, COEFFICIENT, AREA, STUDY)
LUMPED, GRID = "lumped", "grid"
HMS_TABLE = "(hms)"
"""The curve choice that stands for the HMS project's own table, which the job reads only when it is imported."""
REDUCED_KINDS = ("fixed", "depth", "depth_grid", "gridded", "hypothetical", "uniform")
"""The dock's storm kinds that take an area reduction: a depth and a grid of point depths. Observed rain takes none."""
LEGACY_KINDS = {"fixed": "uniform", "gridded": "gridded", "uniform": "uniform", "hypothetical": "hypothetical"}
"""The dock's kinds whose job may keep the single-storm form, with the job's kind each one writes."""
PART_WORDS = {LUMPED: "lumped part", GRID: "2D part"}
FORM_WORDS = {
    NONE: "No reduction",
    COEFFICIENT: "A coefficient",
    AREA: "At one storm area, read on a curve",
    CURVE: "A curve: each lumped subbasin read at its dam's (last point's) drainage area",
    STUDY: "By the depth-area study: each run at its own storm area",
}
CURVE_NOTE = (
    "Each lumped subbasin read at its dam's (last point's) drainage area: in Hybrid 2D, where the lumped subbasins "
    "enter at their own outlets and the 2D model routes them once, every one at the drainage area of the first last "
    "point below it (a dam, or a junction added in Hydrology), one factor per dam (his rule of 2026-11-16, W105). In "
    "Lumped and Hybrid Lumped each element at its own drainage area, the HMS depth-area way: the water a dam hands to "
    "the 2D model is the dam's own, at the dam's area (W98). In a depth-area study at each run's storm area. A "
    "subbasin with a storm area of its own keeps it."
)
STUDY_NOTE = (
    "The study (section 9) reads the curve at each of its storm areas, run by run. A single Run reads it at the area "
    "below, since the cells of one run have no area of their own."
)
COEFFICIENT_WORDS = "The {part}'s coefficient lies above 0 and at most 1: 0.7 is a 30 % reduction."
AREA_WORDS = "The {part} is read at one storm area: give the area, in km2."
CURVE_WORDS = "Choose the {part}'s curve, from Data tables."
MISSING_CURVE = 'The {part} reads curve "{name}", which Data tables does not hold.'
SINGLE_WORDS = (
    "The 2D part is set to the depth-area study: start the study in section 9, or give the area a single Run reads."
)
STUDY_WANTS = (
    "A depth-area study reads the 2D part's curve at each storm area: set the 2D part of the area reduction to By the "
    "depth-area study, with its curve."
)
HMS_SPLIT = (
    "The HMS project's table can be read at one storm area for both parts alike; for anything else, copy it into Data "
    "tables and choose it there."
)
HMS_DEPTH = "A depth or a depth grid takes its area reduction from Data tables: the HMS project's table is read only for gridded rain."
UNUSED_WORDS = "No area reduction for this rain: it is the rain itself, at one area"


def part(form: str = NONE, curve: str = "", area_km2: float = 0.0, coefficient: float = 1.0, single_km2: float = 0.0) -> dict:
    return {"form": form, "curve": curve, "area_km2": area_km2, "coefficient": coefficient, "single_km2": single_km2}


def _form(entry: dict | None) -> str:
    return NONE if entry is None else entry.get("form", NONE)


def _effective(entry: dict | None, study: bool) -> dict | None:
    """The part as a run of this kind reads it: the study's 2D part is a fixed area in a single run."""
    if entry is None or _form(entry) == NONE:
        return None
    if _form(entry) == STUDY and not study:
        return {**entry, "form": AREA, "area_km2": entry.get("single_km2", 0.0)}
    return entry


def _key(entry: dict | None) -> tuple | None:
    """What makes two parts the same reduction."""
    if entry is None:
        return None
    form = entry["form"]
    if form == COEFFICIENT:
        return (form, float(entry["coefficient"]))
    if form == AREA:
        return (form, entry["curve"], float(entry["area_km2"]))
    return (form, entry["curve"])


def factor_at(table: dict, area: float) -> float:
    """The curve's factor at ``area`` as the engine reads it (``ArfTable.factor``): linear in area, the end values beyond,
    and the whole depth below the first area when the curve says so."""
    areas, factors = list(table["areas_km2"]), list(table["factors"])
    if not areas:
        return 1.0
    if area < areas[0]:
        return 1.0 if not table.get("reduces_below_table", True) else factors[0]
    if area >= areas[-1]:
        return factors[-1]
    k = next(n for n in range(1, len(areas)) if area < areas[n])
    share = (area - areas[k - 1]) / (areas[k] - areas[k - 1])
    return factors[k - 1] + share * (factors[k] - factors[k - 1])


def _part_problems(entry: dict | None, which: str, curves: dict, hms: bool) -> list[str]:
    form = _form(entry)
    words = PART_WORDS[which]
    if form == NONE:
        return []
    if form == COEFFICIENT:
        return [] if 0.0 < entry.get("coefficient", 0.0) <= 1.0 else [COEFFICIENT_WORDS.format(part=words)]
    found = []
    name = entry.get("curve") or ""
    if not name:
        found.append(CURVE_WORDS.format(part=words))
    elif name == HMS_TABLE and not hms:
        found.append(f"The {words} reads the HMS project's table, and no HMS project is in use: choose a curve.")
    elif name != HMS_TABLE and name not in curves:
        found.append(MISSING_CURVE.format(part=words, name=name))
    if form == AREA and not entry.get("area_km2", 0.0) > 0.0:
        found.append(AREA_WORDS.format(part=words))
    return found


def reduction_problems(
    reduction: dict, storm_kind: str | None, curves: dict, study: bool = False, hms: bool = False
) -> list[str]:
    """What stops a run (or, with ``study``, a depth-area study) as the parts stand, in plain words."""
    if storm_kind not in REDUCED_KINDS:
        return []
    lumped, grid = (None if reduction.get(f"{w}_absent") else reduction.get(w) for w in (LUMPED, GRID))
    found = _part_problems(lumped, LUMPED, curves, hms) + _part_problems(grid, GRID, curves, hms)
    if found:
        return found
    if study and _form(grid) != STUDY:
        return [STUDY_WANTS]
    if not study and _form(grid) == STUDY and not grid.get("single_km2", 0.0) > 0.0:
        return [SINGLE_WORDS]
    uses_hms = any((p or {}).get("curve") == HMS_TABLE and _form(p) in (AREA, CURVE, STUDY) for p in (lumped, grid))
    if uses_hms and storm_kind in ("depth", "depth_grid"):
        return [HMS_DEPTH]
    if uses_hms and _legacy(reduction, storm_kind, study) is None:
        return [HMS_SPLIT]
    return []


def _legacy(reduction: dict, storm_kind: str, study: bool) -> tuple | None:
    """The one reduction every part the model has takes, when it fits the single-storm form; None when it does not."""
    if storm_kind not in LEGACY_KINDS or study:
        return None
    present = [
        _effective(reduction.get(which), study) for which in (LUMPED, GRID) if not reduction.get(f"{which}_absent")
    ]
    if not present:
        return (NONE,)
    keys = {_key(entry) for entry in present}
    if len(keys) != 1:
        return None
    (key,) = keys
    if key is None:
        return (NONE,)
    return key if key[0] in (COEFFICIENT, AREA) else None


def _table_job(table: dict) -> dict:
    """A curve as the job's storm.arf holds it: what the dock wrote before W101, and the rest only off the defaults."""
    found = {"areas_km2": list(table["areas_km2"]), "factors": list(table["factors"])}
    if not table.get("reduces_below_table", True):
        found["reduces_below_table"] = False
    if table.get("table_type", "fixed-area") != "fixed-area":  # what the table is, as a job not of the dock said
        found["table_type"] = table["table_type"]
    return found


def _part_job(entry: dict) -> dict:
    form = entry["form"]
    if form == COEFFICIENT:
        return {"form": COEFFICIENT, "coefficient": float(entry["coefficient"])}
    if form == AREA:
        return {"form": AREA, "curve": entry["curve"], "area_km2": float(entry["area_km2"])}
    return {"form": CURVE, "curve": entry["curve"]}


def reduction_job(reduction: dict, storm_kind: str, curves: dict, study: bool = False) -> tuple[dict, set[str]]:
    """The keys the reduction adds to the job's storm block, and the names of the stored curves it reads by name.

    ``reduction_problems`` must have found nothing."""
    if storm_kind not in REDUCED_KINDS:
        return {}, set()
    legacy = _legacy(reduction, storm_kind, study)
    if legacy is not None:
        if legacy[0] == NONE:
            return {}, set()
        if legacy[0] == COEFFICIENT:
            return {"arf_factor": legacy[1]}, set()
        _, name, area = legacy
        if name == HMS_TABLE:  # the HMS import fills the table in (job_builder.merge_hms)
            return {"storm_area_km2": area}, set()
        return {"storm_area_km2": area, "arf": _table_job(curves[name])}, set()
    parts: dict = {}
    used: set[str] = set()
    for which in (LUMPED, GRID):
        if reduction.get(f"{which}_absent"):
            continue
        entry = _effective(reduction.get(which), study)
        if entry is None:
            continue
        if entry["form"] == STUDY:
            entry = {**entry, "form": CURVE}
        parts[which] = _part_job(entry)
        if "curve" in parts[which]:
            used.add(parts[which]["curve"])
    return ({"area_reduction": parts} if parts else {}), used


OBSERVED, SPLIT = "observed", "split"


def lumped_form(reduction: dict | None, storm_kind: str | None) -> str:
    """What a lumped subbasin's own storm area meets in a single run's job (W103): ``curve`` (a lumped curve), ``area``
    (one curve read at one storm area for every part, the single-storm form), :data:`OBSERVED` (a rain that takes no
    reduction), :data:`SPLIT` (a lumped part at one area beside another reduction, ``storm.area_reduction``), or the
    form itself. The engine reads an own storm area only on a lumped curve or the single-storm form."""
    if storm_kind not in REDUCED_KINDS:
        return OBSERVED
    if reduction is None:
        return NONE
    legacy = _legacy(reduction, storm_kind, False)
    if legacy is not None:
        return legacy[0]
    entry = None if reduction.get(f"{LUMPED}_absent") else _effective(reduction.get(LUMPED), False)
    if entry is None:
        return NONE
    return CURVE if entry["form"] == CURVE else SPLIT if entry["form"] == AREA else entry["form"]


def curves_read(reduction: dict, storm_kind: str | None, study: bool = False) -> set[str]:
    """The stored curves a run of this storm reads, by name, whatever form the job holds them in."""
    if storm_kind not in REDUCED_KINDS:
        return set()
    found = set()
    for which in (LUMPED, GRID):
        entry = None if reduction.get(f"{which}_absent") else _effective(reduction.get(which), study)
        if entry is not None and entry["form"] != COEFFICIENT and entry.get("curve") and entry["curve"] != HMS_TABLE:
            found.add(entry["curve"])
    return found


def study_curve(reduction: dict, curves: dict) -> dict | None:
    """The curve a depth-area study reads at its storm areas, as the dock holds it; None when the 2D part is no study."""
    grid = reduction.get(GRID)
    if _form(grid) != STUDY or grid.get("curve") not in curves:
        return None
    return curves[grid["curve"]]


def words(entry: dict | None, which: str, curves: dict) -> str:
    """One part in a few words, for the section's status."""
    form = _form(entry)
    label = "lumped" if which == LUMPED else "2D"
    if form == NONE:
        return f"{label}: none"
    if form == COEFFICIENT:
        return f"{label}: {entry['coefficient']:g}"
    name = entry.get("curve") or "?"
    shown = "the HMS table" if name == HMS_TABLE else name
    if form == AREA:
        table = curves.get(name)
        factor = f" ({factor_at(table, entry['area_km2']):.3f})" if table and entry["area_km2"] > 0.0 else ""
        return f"{label}: {shown} at {entry['area_km2']:g} km2{factor}"
    if form == STUDY:
        return f"{label}: {shown} by the depth-area study"
    return f"{label}: {shown} at each entry's area"
