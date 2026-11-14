"""What each reservoir of an HMS basin routes by, and whether the engine takes it, without a run (W75).

For the dock's read-only table: per reservoir its HMS method, its outlet and option blocks in file order (culverts,
orifices, gates, pumps, spillways, dam tops, seepage, evaporation), its main tailwater (a fixed stage over a crest
drowns it, W67), and the engine's own words when it refuses the reservoir: the same build the run makes
(:func:`wadi2d.hydrology.from_hms.reservoir_from_hms`), so the words are the run's.

Interface: :func:`reservoir_structures`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

SUMMARY_KEYS = ("Culvert Shape", "Number Barrels", "Number Of Pumps", "Spillway Gate Type")
"""Keys worth a word beside a block's kind and name."""


def _block_words(block) -> str:
    words = f"{block.kind}: {block.name}"
    facts = [f"{key.lower()} {block.get(key)}" for key in SUMMARY_KEYS if block.get(key)]
    if block.blocks:
        facts.append(", ".join(f"{sub.kind}: {sub.name}" for sub in block.blocks))
    return f"{words} ({'; '.join(facts)})" if facts else words


def _tailwater(route) -> str | None:
    condition = getattr(route, "main_tailwater_condition", None)
    stage = getattr(route, "main_fixed_tailwater_stage", None)
    if condition in (None, "None"):
        return None
    return f"{condition} {stage:g} m" if stage is not None else str(condition)


def _tables(basin_file: Path, hms_basin, project: Path | None):
    from wadi2d.hms import load_pdata
    from wadi2d.hydrology.from_hms import load_project_tables

    found = [project] if project else sorted(basin_file.parent.glob("*.hms"))
    if not found:
        raise ValueError(f"{basin_file.name} has reservoirs: no .hms project beside it for their tables")
    stem = found[0].with_suffix("")
    return load_project_tables(load_pdata(stem.with_suffix(".pdata")), stem.with_suffix(".dss"))


def reservoir_structures(basin_file: str | Path, project: str | Path | None = None) -> dict[str, Any]:
    """Every reservoir of a ``.basin`` file: method, blocks, tailwater, and ``refused`` with the engine's words."""
    from wadi2d.hms import load_basin
    from wadi2d.hydrology.from_hms import reservoir_from_hms

    path = Path(basin_file)
    hms_basin = load_basin(path)
    rows: list[dict[str, Any]] = []
    if not hms_basin.reservoirs:
        return {"basin": str(path), "reservoirs": rows, "tables": None}
    tables, words = None, None
    try:
        tables = _tables(path, hms_basin, Path(project) if project else None)
    except (OSError, ValueError, KeyError) as error:
        words = f"the project's paired tables could not be read: {error}"
    for name, element in hms_basin.reservoirs.items():
        route = element.route
        row = {
            "name": name,
            "method": element.route_method,
            "structures": [_block_words(block) for block in element.blocks],
            "tailwater": _tailwater(route),
            "refused": None,
        }
        try:
            reservoir_from_hms(element, tables)
        except (ValueError, KeyError, TypeError) as error:
            row["refused"] = str(error)
        rows.append(row)
    return {"basin": str(path), "reservoirs": rows, "tables": words}
