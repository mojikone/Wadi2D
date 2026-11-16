"""The area reduction of each part of the model: the lumped subbasins and the 2D cells (W95, his rule of 2026-11-15).

Interface: :func:`arf_from_config`, :func:`part_reduction`, :func:`with_reduction`, :func:`lumped_curve`,
:func:`grid_curve`, :func:`at_study_area`, :func:`part_words`.

A job without ``storm.area_reduction`` gives both parts the storm's own table and area, or its given factor, as
before. With it, each part takes one of three forms:

- ``coefficient``: one factor, at every area;
- ``area``: the curve read at one area, one factor for the part;
- ``curve``: the curve read at an area of each element's own. On the lumped part that is each element's drainage area
  in a lumped-only run (HMS's depth-area analysis, W88) and, in a run with a 2D part, each lumped subbasin's
  ``storm_area_km2``, else the total upstream area of the element where its water enters the grid, found from the
  network and never refused (W98, his rule of 2026-11-15; :mod:`wadi2d.engine.entry_area`). On the 2D part it is each
  run's storm area in a depth-area study; a single run refuses it, since the cells have no area of their own to read
  it at.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from wadi2d.config.rain import (
    ARF_AREA,
    ARF_COEFFICIENT,
    ARF_CURVE,
    PART_GRID,
    PART_LUMPED,
    ArfPart,
    ArfTableConfig,
)
from wadi2d.storm.arf import ArfTable, GivenFactor, factor_at

Reduction = tuple[ArfTable | GivenFactor | None, float | None]
"""What a storm builder takes: the table or the given factor, and the storm area it is read at."""
PART_NAMES = {PART_LUMPED: "lumped part", PART_GRID: "2D part"}


def arf_from_config(table: ArfTableConfig) -> ArfTable:
    """The engine's table of a job's table."""
    return ArfTable(np.asarray(table.areas_km2), np.asarray(table.factors), reduces_below_table=table.reduces_below_table)


def _part(storm, part: str) -> ArfPart | None:
    return getattr(storm.area_reduction, part) if storm.area_reduction is not None else None


def part_reduction(storm, part: str) -> Reduction:
    """The reduction of ``part`` (``"lumped"`` or ``"grid"``) of a job's storm section."""
    if storm.area_reduction is None:
        if storm.arf_factor is not None:
            return GivenFactor(storm.arf_factor), None
        return (None if storm.arf is None else arf_from_config(storm.arf)), storm.storm_area_km2
    given = _part(storm, part)
    if given is None:
        return None, None
    if given.form == ARF_COEFFICIENT:
        return GivenFactor(given.coefficient), None
    return arf_from_config(given.table), given.area_km2 if given.form == ARF_AREA else None


def with_reduction(storm, reduction: Reduction):
    """``storm`` with this reduction in place of its own; a storm that takes none comes back as it is."""
    if storm is None or not hasattr(storm, "arf") or not hasattr(storm, "storm_area_km2"):
        return storm
    arf, area = reduction
    return replace(storm, arf=arf, storm_area_km2=area)


def lumped_curve(storm) -> bool:
    """The lumped part reads its curve at each element's own area."""
    given = _part(storm, PART_LUMPED)
    return given is not None and given.form == ARF_CURVE


def grid_curve(storm) -> bool:
    """The 2D part reads its curve at each storm area of a depth-area study."""
    given = _part(storm, PART_GRID)
    return given is not None and given.form == ARF_CURVE


def at_study_area(storm, area_km2: float):
    """The storm section of one run of a depth-area study at ``area_km2``: the old storm area, or every part that
    reads a curve read at that area; a fixed area or a coefficient stays as it is."""
    if storm.area_reduction is None:
        return storm.model_copy(update={"storm_area_km2": area_km2})
    parts = {}
    for name in (PART_LUMPED, PART_GRID):
        given = _part(storm, name)
        if given is not None and given.form == ARF_CURVE:
            parts[name] = given.model_copy(update={"form": ARF_AREA, "area_km2": area_km2})
    reduction = storm.area_reduction.model_copy(update=parts)
    return storm.model_copy(update={"area_reduction": reduction})


def part_record(storm, part: str) -> dict | None:
    """What a run says about one part's reduction: form, factor, area and curve; None for a part not reduced."""
    given = _part(storm, part)
    if given is None:
        return None
    arf, area = part_reduction(storm, part)
    record = {"part": part, "form": given.form, "curve": given.curve, "storm_area_km2": area}
    record["factor"] = None if given.form == ARF_CURVE else factor_at(arf, area)
    record["arf_table_type"] = given.table.table_type if given.table is not None else None
    return record


def part_words(record: dict) -> str:
    """One line of the run's warnings for a part's reduction."""
    where = PART_NAMES[record["part"]]
    named = f" {record['curve']!r}" if record["curve"] else ""
    if record["form"] == ARF_COEFFICIENT:
        return f"rain on the {where}: every depth is multiplied by {record['factor']:.4f}, the given coefficient"
    if record["form"] == ARF_AREA:
        return (
            f"rain on the {where}: every depth is multiplied by {record['factor']:.4f}, the curve{named} at "
            f"{record['storm_area_km2']:g} km2"
        )
    if record["part"] == PART_LUMPED:
        return (
            f"rain on the {where}: the curve{named} is read at each element's own drainage area in a lumped-only run, "
            "and at the drainage area of the element where a subbasin's water enters the grid in a run with a 2D part"
        )
    return f"rain on the {where}: the curve{named} is read at each element's own area"
