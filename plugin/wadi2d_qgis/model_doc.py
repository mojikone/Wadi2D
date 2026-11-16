# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The saved model: one versioned document of everything the dock holds. No Qt here.

Interface: :func:`new_doc` (a document from the sections' states), :func:`dumps` / :func:`loads` (text and back, with
the refusals in words), :func:`fingerprint` (what two documents must share to be the same model), the files a
document lives in (:data:`MODEL_FILE` in a run folder, :func:`scenario_path` in the model's folder) and
:func:`write_doc` / :func:`read_doc`.

The same document is kept in three places (W99): with the QGIS project, so a model survives closing QGIS; in every run
folder, so a finished run can be opened back into the dock; and as named scenarios in the model's folder.
A later format adds a function to :data:`MIGRATIONS`; nothing else changes for an old file.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

FORMAT = "wadi2d-model"
VERSION = 4
"""4 (W101, his item 7): the one depth threshold for the maps is the model's (Run). 3 (W101): Data tables and the Area reduction are sections; the Steady rain is a fixed depth and the design storm a
depth and a pattern. 2 (W99 step 4): the Simulation section holds the run's one start, the simulated time, the saved
maps and the engine choice. 1 kept three starts, in Storm (two) and Gauges, and the other three in Run."""
MIGRATED = "migrated"
"""The key of a document's list of words on what a migration moved or dropped, for whoever opens it."""
MODEL_FILE = "model.wadi2d.json"
"""The model document of a run, written into its folder beside ``job.json`` when Run is pressed."""
SCENARIO_DIR = "scenarios"
"""Inside the model's folder (the Run section's output folder), as the generated basin's folder is."""
SCENARIO_SUFFIX = ".wadi2d.json"
MATTERS = ("model_type", "show_all", "sections")
"""What makes two documents the same model: not the stamp, not the plugin that wrote it, not the page shown."""
GRIDDED, GAUGES = "gridded", "gauges"
"""The storm kinds whose rain carries a start: a rain file, and rain gauges."""
ONE_START = 'The run has one start now, in the Simulation section: it took "{start}" from {source}.'
OBSERVED_DROPPED = (
    'The observed gauges had a start of their own, "{own}": it is dropped, and their records are read from the run\'s '
    'start, "{start}".'
)
RAIN_FOLLOWS = 'The rain now starts there too: rain before "{start}" is left out, where it was read from its first period.'
UNUSED_DROPPED = 'A start typed for a rain source that was not in use, "{own}", is dropped.'


def _widgets(doc: dict, key: str) -> dict:
    section = doc["sections"].setdefault(key, {})
    return section.setdefault("widgets", {})


def _to_2(doc: dict) -> dict:
    """Format 1 to 2: Run's simulated time, saved maps and engine choice move to Simulation as they are; the three
    starts become one. The start in use wins, the rain's before the observed records': whatever that changes in the
    job is said in words under :data:`MIGRATED`, and a start that was typed and not in use is not lost in silence.
    """
    run, storm, gauges, simulation = (_widgets(doc, key) for key in ("run", "storm", "gauges", "simulation"))
    for key in ("duration", "maps", "backend"):
        if key in run:
            simulation[key] = run.pop(key)
    kind = (storm.get("kind") or {}).get("data") if isinstance(storm.get("kind"), dict) else None
    held = {GRIDDED: storm.pop("start", "") or "", GAUGES: storm.pop("gauge_start", "") or ""}
    observed = gauges.pop("start", "") or ""
    rain = held.get(kind, "")
    start = rain or observed
    words = []
    if start:
        simulation["start"] = start
        words.append(ONE_START.format(start=start, source="the rain" if rain else "the observed gauges"))
    if rain and observed and observed != rain:
        words.append(OBSERVED_DROPPED.format(own=observed, start=rain))
    if kind in held and not rain and observed:
        words.append(RAIN_FOLLOWS.format(start=observed))
    words += [
        UNUSED_DROPPED.format(own=own)
        for source, own in held.items()
        if own and source != kind and own != start
    ]
    if words:
        doc[MIGRATED] = [*doc.get(MIGRATED, []), *words]
    return doc


FIXED_WORDS = (
    "The constant rain of {rain:g} mm/h for {hours:g} h is now a fixed depth of {depth:g} mm over {hours:g} h with a "
    "uniform pattern, in Storm: the same rain, and the same job."
)
DESIGN_WORDS = (
    'The design storm is now a Depth and pattern, in Storm: its pattern is the table "{name}" of Data tables, the same '
    "numbers, and the job is the design storm it was."
)
CURVE_MOVED = 'The area reduction table is now the curve "{name}" of Data tables, read by the Area reduction section (4b).'
STUDY_SPLIT = (
    "The area reduction by the depth-area study is now the 2D part's choice in section 4b, at {area:g} km2 for a single "
    "Run; the lumped part reads the curve at each subbasin's entry area, so a single Run's lumped subbasins are no "
    "longer all read at {area:g} km2. A study reads every part at its storm areas, as before."
)
BY_ELEMENT_CURVE = (
    "Each element at its own drainage area (Hydrology) is now the lumped part's curve, in section 4b: the same rule "
    "(W95). The job names storm.area_reduction in place of hydrology.arf_by_element."
)
BY_ELEMENT_HMS = "Each element at its own drainage area (Hydrology) is now a tick of section 4b, for the HMS storm."
DESIGN_PATTERN, ARF_CURVE = "Design pattern", "Area reduction"
OLD_STORM = ("single", "design_depth", "design_hours", "pattern", "arf_mode", "storm_area", "arf", "arf_factor", "rain")
"""The Storm section's widgets of format 2 that format 3 moved out or retired."""


def _data(widgets: dict, key: str):
    held = widgets.get(key)
    return held.get("data") if isinstance(held, dict) else None


def _combo(data, text: str = "") -> dict:
    return {"data": data, "text": text or ("" if data is None else str(data))}


def _parts(reduction: dict, which: str, **fields) -> None:
    for name, value in fields.items():
        reduction[f"{which}.{name}"] = value


def _to_3(doc: dict) -> dict:
    """Format 2 to 3 (W101): the Steady rain is a fixed depth, the design storm a depth and a pattern of Data tables,
    the area reduction its own section with a lumped and a 2D part, and Hydrology's by-element tick its lumped curve.
    Everything a model changes in the job is said in words under :data:`MIGRATED`."""
    storm, hydrology = _widgets(doc, "storm"), _widgets(doc, "hydrology")
    reduction = _widgets(doc, "reduction")
    held = doc["sections"].setdefault("tables", {})
    held.setdefault("widgets", {})
    tables = held.setdefault("extra", {}).setdefault("store", {})
    patterns, curves = tables.setdefault("patterns", {}), tables.setdefault("arf_curves", {})
    words = []
    kind = _data(storm, "kind")
    single = _data(storm, "single")
    if kind == "single" and single == "hyetograph":
        storm["kind"] = _combo("hyetograph")
    elif kind == "single":  # the Steady rain, the default source of format 2
        rain, hours = float(storm.get("rain") or 0.0), float(storm.get("hours") or 0.0)
        storm["kind"], storm["fixed_depth"] = _combo("fixed"), rain * hours
        if rain > 0.0:
            words.append(FIXED_WORDS.format(rain=rain, hours=hours, depth=rain * hours))
    elif kind == "hypothetical":
        storm["kind"] = _combo("depth")
        storm["depth_mm"], storm["depth_hours"] = storm.get("design_depth", 0.0), storm.get("design_hours", 0.0)
        rows = storm.get("pattern") or []
        if rows:
            patterns[DESIGN_PATTERN] = {
                "time": [r[0] for r in rows], "depth": [r[1] for r in rows], "time_units": "percent", "form": "cumulative",
            }  # fmt: skip
            storm["depth_pattern"] = _combo(f"table:{DESIGN_PATTERN}")
            words.append(DESIGN_WORDS.format(name=DESIGN_PATTERN))
    curve = ""
    rows = storm.get("arf") or []
    if kind in ("hypothetical", "gridded") or hydrology.get("arf_by_element"):
        if rows:
            curves[ARF_CURVE] = {"areas_km2": [r[0] for r in rows], "factors": [r[1] for r in rows], "reduces_below_table": True}
            curve = ARF_CURVE
        elif kind == "gridded" and hydrology.get("folder"):
            curve = "(hms)"  # the HMS project's table, as format 2 read an empty table under an HMS project
    mode = _data(storm, "arf_mode") if kind in ("hypothetical", "gridded") else None
    area = float(storm.get("storm_area") or 0.0)
    if mode == "area":
        for which in ("lumped", "grid"):
            _parts(reduction, which, form=_combo("area"), curve=_combo(curve or None, curve), area=area)
    elif mode == "given":
        factor = float(storm.get("arf_factor") or 1.0)
        for which in ("lumped", "grid"):
            _parts(reduction, which, form=_combo("coefficient"), coefficient=factor)
    elif mode == "study":
        _parts(reduction, "lumped", form=_combo("curve"), curve=_combo(curve or None, curve))
        _parts(reduction, "grid", form=_combo("study"), curve=_combo(curve or None, curve), single=area)
        words.append(STUDY_SPLIT.format(area=area))
    if curve and curve != "(hms)" and mode in ("area", "given", "study"):
        words.append(CURVE_MOVED.format(name=curve))
    if hydrology.pop("arf_by_element", False):
        if kind == "hms":
            reduction["by_element"] = True
            words.append(BY_ELEMENT_HMS)
        else:
            _parts(reduction, "lumped", form=_combo("curve"), curve=_combo(curve or None, curve))
            words.append(BY_ELEMENT_CURVE)
    for key in OLD_STORM:
        storm.pop(key, None)
    if words:
        doc[MIGRATED] = [*doc.get(MIGRATED, []), *words]
    return doc


def _to_4(doc: dict) -> dict:
    """Format 3 to 4: the one depth threshold for the maps. A model from before it says nothing of the floors, so it
    keeps the engine's own (0.05 m for depth, 0.1 m for the hazard, every wet cell in the cell maps) and the job it
    writes; the field shows "The engine's own floors"."""
    _widgets(doc, "run")["cutoff"] = -0.001  # nothing of its job changes, so nothing is said: the field says it
    return doc


MIGRATIONS: dict = {1: _to_2, 2: _to_3, 3: _to_4}
"""``{from_version: function(doc) -> doc}``; each takes a document one version up."""
RASTER_PROVIDER = "gdal"
"""The provider of a raster layer in a saved layer choice; any other is read as a vector file."""
UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def new_doc(sections: dict, plugin: str = "", **parts) -> dict:
    """A document of the sections' states; ``parts`` are the dock's own (the model type, the show-all switch)."""
    return {
        "format": FORMAT,
        "version": VERSION,
        "plugin": plugin,
        "saved": datetime.now().isoformat(timespec="seconds"),
        **parts,
        "sections": sections,
    }


def fingerprint(doc: dict) -> str:
    """The text two documents share exactly when they are the same model."""
    return json.dumps({key: doc.get(key) for key in MATTERS}, sort_keys=True)


def dumps(doc: dict) -> str:
    return json.dumps(doc, indent=1)


def loads(text: str) -> dict:
    """The document in ``text``, brought up to this format. ``ValueError`` says in words why it cannot be read."""
    try:
        doc = json.loads(text)
    except ValueError as problem:
        raise ValueError(f"This is not a Wadi2D model file: {problem}") from None
    if not isinstance(doc, dict) or doc.get("format") != FORMAT or not isinstance(doc.get("sections"), dict):
        raise ValueError("This is not a Wadi2D model file.")
    version = doc.get("version")
    if not isinstance(version, int) or version < 1:
        raise ValueError("This Wadi2D model file gives no format version.")
    if version > VERSION:
        raise ValueError(
            f"This model was saved by a newer Wadi2D (model format {version}); this plugin reads format {VERSION}. "
            "Update the plugin to open it."
        )
    while version < VERSION:
        doc = MIGRATIONS[version](doc)
        version += 1
        doc["version"] = version
    return doc


def write_doc(path: Path | str, doc: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(doc), encoding="utf-8")
    return path


def read_doc(path: Path | str) -> dict:
    return loads(Path(path).read_text(encoding="utf-8"))


# Scenarios: named copies of the document in the model's folder.


def safe_name(name: str) -> str:
    """A scenario's name as a file name: what Windows refuses is replaced, the ends trimmed."""
    return UNSAFE.sub("_", name).strip(" .")


def scenario_path(model_folder: Path | str, name: str) -> Path:
    return Path(model_folder) / SCENARIO_DIR / f"{safe_name(name)}{SCENARIO_SUFFIX}"


def list_scenarios(model_folder: Path | str) -> list[tuple[str, Path]]:
    """``(name, file)`` of each scenario of the model, by name."""
    folder = Path(model_folder) / SCENARIO_DIR
    if not model_folder or not folder.is_dir():
        return []
    return sorted((path.name[: -len(SCENARIO_SUFFIX)], path) for path in folder.glob(f"*{SCENARIO_SUFFIX}"))
