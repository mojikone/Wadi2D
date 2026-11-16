# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""What a ``job.json`` tells the dock, as section states (W99). No Qt and no QGIS here.

A run from before the model was saved has only its job. :func:`job_states` turns the job and the run's ``inputs``
folder into states of the shape a saved model holds, so the sections restore them the same way. Layers are named by
their files: the DEM, and the GeoJSON the job builder wrote into ``inputs``, whose properties carry what the dock's
fields gave. :func:`lost` compares the job a refilled dock would write with the run's own: what differs is what could
not be restored, found by comparison and not from a list kept here, so a part of the job this module does not know
cannot be lost in silence. Coordinates are compared to the millimetre, as the input files hold them.
"""

from __future__ import annotations

import json
from pathlib import Path

from .gauge_rows import RAIN
from .job_builder import COORDINATE_DECIMALS
from .model_doc import RASTER_PROVIDER
from .protocol import INPUTS_DIR
from .shaped import END_KEYS, SHAPED_KINDS, TABLE
from .storm_rows import (
    ARF_AREA,
    ARF_GIVEN,
    ARF_NONE,
    KIND_DESIGN,
    KIND_GAUGES,
    KIND_GRID,
    KIND_STEADY,
    KIND_TABLE,
    SOURCE_SINGLE,
)
from .study_rows import AREA_KEY

SECONDS_PER_HOUR = 3600.0
MINUTES_PER_HOUR = 60.0
PLAIN_KINDS = {
    "crest_line": ("crest_z",),
    "wall": (),
    "spillway": ("crest_z", "coefficient", "length"),
    "burn_line": ("crest_z",),
}
BREAKLINE_BOXES = {
    "bank_rise": "bank_rise_m", "bank_reach": "bank_reach_m", "bank_depth": "bank_depth_m", "bank_offset": "bank_offset_cells",
    "crest_height": "crest_height_m", "crest_disc": "disc_radius_m", "crest_slope": "ground_slope_max",
}  # fmt: skip
CORRIDOR_BOXES = {
    "corridor_cell_min": "cell_min_m", "corridor_cell_max": "cell_max_m", "corridor_fraction": "width_fraction",
    "corridor_outside": "rows_outside",
}  # fmt: skip
MOST_WORDS = 12
ROUNDING = 0.51 * 10.0**-COORDINATE_DECIMALS
"""How far a coordinate read back from an input file may stand from the job's own."""
IGNORED = ("project.name", "grid.cache_dir")
"""Parts of a job that say where it was written, not what it is."""
UNNAMED_TYPE = "run.model_type"
"""A job from before the model types names none; the dock gives it the one it runs as, which is not a loss."""


def layer(path: str | Path | None, raster: bool = False) -> dict | None:
    """A layer named by its file alone, for the sections to find in the project or add to it."""
    if not path:
        return None
    path = Path(path)
    return {
        "id": None,
        "source": str(path),
        "name": path.stem,
        "provider": RASTER_PROVIDER if raster else "ogr",
    }


def choice(data) -> dict:
    return {"data": data, "text": "" if data is None else str(data)}


def _properties(path: Path) -> set[str]:
    """The property names the features of an input file carry with a value."""
    try:
        features = json.loads(path.read_text(encoding="utf-8")).get("features", [])
    except (OSError, ValueError):
        return set()
    return {
        key
        for feature in features
        for key, value in (feature.get("properties") or {}).items()
        if value is not None
    }


def _put(widgets: dict, path: str, value) -> None:
    if value is not None:
        widgets[path] = value


def _arf(storm: dict, widgets: dict) -> None:
    if "arf_factor" in storm:
        widgets["arf_mode"], widgets["arf_factor"] = choice(ARF_GIVEN), storm["arf_factor"]
    elif "storm_area_km2" in storm:
        table = storm.get("arf") or {}
        widgets["arf_mode"], widgets["storm_area"] = choice(ARF_AREA), storm["storm_area_km2"]
        widgets["arf"] = [
            list(pair) for pair in zip(table.get("areas_km2", []), table.get("factors", []), strict=False)
        ]
    else:
        widgets["arf_mode"] = choice(ARF_NONE)


def _storm(storm: dict) -> dict:
    """The Storm section's state for the storm kinds the dock itself writes; another kind is left to the comparison."""
    widgets: dict = {}
    rows: dict = {}
    kind = storm.get("kind")
    if kind == KIND_STEADY:
        hours = storm.get("duration_min", 0.0) / MINUTES_PER_HOUR
        widgets.update(kind=choice(SOURCE_SINGLE), single=choice(KIND_STEADY), hours=hours)
        widgets["rain"] = storm.get("depth_mm", 0.0) / hours if hours > 0.0 else 0.0
    elif kind == KIND_TABLE:
        table = zip(storm.get("hyetograph_min", []), storm.get("hyetograph_mm", []), strict=False)
        widgets.update(
            kind=choice(SOURCE_SINGLE), single=choice(KIND_TABLE), hyetograph=[list(pair) for pair in table]
        )
    elif kind == KIND_DESIGN and "time_percent" in storm:
        pattern = zip(storm["time_percent"], storm.get("depth_percent", []), strict=False)
        widgets.update(
            kind=choice(KIND_DESIGN),
            design_depth=storm.get("depth_mm"),
            pattern=[list(pair) for pair in pattern],
        )
        widgets["design_hours"] = storm.get("duration_min", 0.0) / MINUTES_PER_HOUR
        _arf(storm, widgets)
    elif kind == KIND_GRID:
        source = storm.get("rain_file", "")
        widgets.update(
            kind=choice(KIND_GRID),
            rain_file=source,
            units=choice(None) | {"text": storm.get("rain_units", "")},
        )
        widgets["is_folder"] = {
            "data": None,
            "text": (
                "A folder of GeoTIFFs, one per period" if Path(source).is_dir() else "A NetCDF or DSS file"
            ),
        }
        widgets["variable"] = {"data": None, "text": storm.get("rain_variable", "")}
        widgets["stamp"] = choice(storm.get("rain_stamp"))
        widgets["period"] = storm.get("rain_interval_min", 0.0)
        widgets["start"] = storm.get("rain_start", "")
        _arf(storm, widgets)
    elif kind == KIND_GAUGES:
        spread = storm.get("gauges") or {}
        widgets.update(
            kind=choice(KIND_GAUGES),
            gauge_method=choice(spread.get("method")),
            gauge_gaps=choice(spread.get("gaps")),
        )
        widgets["gauge_radius"] = spread.get("search_radius_m") or 0.0
        widgets["gauge_start"] = storm.get("rain_start", "")
        stations = spread.get("gauges") or []
        if stations:
            widgets["gauge_values"] = choice(stations[0].get("values"))
        rows["gauge_table"] = [
            {"name": g.get("name", ""), "kind": RAIN, "file": g.get("file", ""), "series": g.get("record", ""),
             "x": g.get("x"), "y": g.get("y"), "values": g.get("values")}
            for g in stations
        ]  # fmt: skip
    return {"widgets": widgets, "rows": rows}


def _structures(job: dict, inputs_dir: Path) -> dict:
    widgets: dict = {}
    objects = job.get("terrain", {}).get("objects", [])
    for kind, keys in PLAIN_KINDS.items():
        path = inputs_dir / f"{kind}.geojson"
        if path.is_file():
            held = _properties(path)
            widgets[f"layers.{kind}"] = layer(path)
            for key in keys:
                _put(widgets, f"fields.{kind}.{key}", key if key in held else None)
    for kind in SHAPED_KINDS:
        path = inputs_dir / f"{kind}.geojson"
        if not path.is_file():
            continue
        widgets[f"layers.{kind}"] = layer(path)
        for key in _properties(path) - {TABLE, *END_KEYS}:
            widgets[f"fields.{kind}.{key}"] = key
        _put(widgets, f"shaped.{kind}.table_field", TABLE if TABLE in _properties(path) else None)
        first = next((entry for entry in objects if entry.get("kind") == kind), {})
        for box, key in (("start_end", "start_end"), ("end_end", "end_end")):
            if first.get(key) is not None:
                widgets[f"shaped.{kind}.{box}"] = {"data": None, "text": str(first[key])}
        _put(widgets, f"shaped.{kind}.taper", first.get("taper_length"))
    ponds = inputs_dir / "initial_water.geojson"
    if ponds.is_file():
        widgets["start_water.ponds"], widgets["start_water.pond_level"] = layer(ponds), "level"
    widgets["terrain_map"] = bool(job.get("outputs", {}).get("terrain_map"))
    dams = []
    for entry in job.get("dam_levels") or []:
        start = entry.get("start")
        named = isinstance(start, str)
        dams.append(
            {
                "name": entry.get("name", ""),
                "start": start if named else "level",
                "level": None if named else start,
            }
        )
    return {"widgets": widgets, "rows": {"start_water": dams}}


def _mesh(job: dict, inputs_dir: Path) -> dict:
    widgets: dict = {}
    mesh, strips, breaks = job.get("mesh") or {}, job.get("strips") or {}, job.get("breaklines") or {}
    widgets["enabled"] = bool(mesh.get("enabled"))
    for box, key in (
        ("coarse", "coarse_dx"),
        ("fine_area", "stream_area_fine_km2"),
        ("mid_area", "stream_area_mid_km2"),
    ):
        _put(widgets, box, mesh.get(key))
    lines = inputs_dir / "mesh_lines.geojson"
    if lines.is_file():
        widgets["lines.layer"] = layer(lines)
    widgets["local_steps"] = bool((job.get("numerics") or {}).get("local_time_stepping"))
    for box, key in BREAKLINE_BOXES.items():
        _put(widgets, box, breaks.get(key))
    _put(widgets, "bank_depth_layer", layer(breaks.get("bank_depth_map"), raster=True))
    widgets["corridors"] = bool(strips.get("enabled"))
    _put(widgets, "corridor_layer", layer(strips.get("banks")))
    for box, key in CORRIDOR_BOXES.items():
        _put(widgets, box, strips.get(key))
    return {"widgets": widgets}


def _hydrology(job: dict, inputs_dir: Path) -> dict:
    widgets: dict = {}
    extra: dict = {}
    hydrology, terrain, run = job.get("hydrology") or {}, job.get("terrain") or {}, job.get("run") or {}
    hms = hydrology.get("hms_basin")
    if hms:
        widgets["folder"] = str(Path(hms).parent)
        widgets["files.basin"] = {"data": None, "text": Path(hms).name}
    elif hydrology.get("basin_json"):
        basin = job.get("basin") or {}
        widgets["basin#checked"] = True
        _put(widgets, "basin.threshold", basin.get("stream_threshold_km2") or 0.0)
        _put(widgets, "basin.lag", choice(basin["lag_method"]) if basin.get("lag_method") else None)
        extra["basin_json"] = hydrology["basin_json"]
    extra["modes"] = {
        entry["name"]: entry["mode"] for entry in hydrology.get("subbasins") or [] if "mode" in entry
    }
    _put(
        widgets, "lumped_entry", choice(hydrology["lumped_entry"]) if hydrology.get("lumped_entry") else None
    )
    widgets["lumped_only"] = bool(run.get("lumped_only"))
    widgets["arf_by_element"] = bool(hydrology.get("arf_by_element"))
    _put(widgets, "routing", choice(hydrology["reach_routing"]) if hydrology.get("reach_routing") else None)
    widgets["exclude"] = bool((job.get("grid") or {}).get("exclude_lumped"))
    handbacks = inputs_dir / "handbacks.geojson"
    if handbacks.is_file():
        widgets["handbacks.layer"] = layer(handbacks)
    loss = job.get("transmission") or {}
    widgets["loss.enabled"] = bool(loss.get("enabled"))
    _put(widgets, "loss.rate", loss.get("rate_mm_h"))
    _put(widgets, "cn.box", hydrology.get("curve_number"))
    _put(widgets, "cn.raster", layer(terrain.get("cn_raster"), raster=True))
    return {"widgets": widgets, "extra": extra}


def job_states(job: dict, run_folder: Path | str) -> dict:
    """Section states, by section key, of what ``job`` tells; ``run_folder`` holds its ``inputs``."""
    root = Path(run_folder)
    inputs_dir = root / INPUTS_DIR
    grid, terrain, run, outputs = (job.get(key) or {} for key in ("grid", "terrain", "run", "outputs"))
    ground = {"dem": layer(terrain.get("dem"), raster=True), "fill_pits": bool(terrain.get("fill_pits"))}
    _put(ground, "dx", grid.get("dx"))
    _put(ground, "domain", layer(grid.get("domain")))
    _put(ground, "manning.box", terrain.get("manning"))
    _put(ground, "manning.raster", layer(terrain.get("manning_raster"), raster=True))
    edges, design = inputs_dir / "boundaries.geojson", inputs_dir / "design_points.geojson"
    points = {}
    if design.is_file():
        held = _properties(design)
        points = {
            "layer": layer(design),
            "name": "name" if "name" in held else "",
            "area": AREA_KEY if AREA_KEY in held else "",
        }
    panel = {"folder": str(root), "pixels": (outputs.get("pixels") or {}).get("enabled", True)}
    _put(panel, "duration", run["duration_s"] / SECONDS_PER_HOUR if "duration_s" in run else None)
    _put(panel, "maps", choice(outputs["map_every_s"]) if "map_every_s" in outputs else None)
    _put(panel, "smooth", (outputs.get("smooth") or {}).get("enabled"))
    panel["limiter"] = bool(outputs.get("step_limiter"))
    _put(panel, "backend", choice(run["backend"]) if run.get("backend") else None)
    return {
        "terrain": {"widgets": ground},
        "mesh": _mesh(job, inputs_dir),
        "hydrology": _hydrology(job, inputs_dir),
        "storm": _storm(job.get("storm") or {}),
        "structures": _structures(job, inputs_dir),
        "boundaries": {"widgets": {"layer": layer(edges)} if edges.is_file() else {}},
        "points": {"widgets": points},
        "run": {"widgets": panel},
    }


# The comparison: what the refilled dock would write against what the run wrote.


def comparable(job: dict, out: Path | str) -> dict:
    """A job with its own folder taken out of every path, so that two folders' jobs can be compared."""
    text = json.dumps(job)
    for form in (str(Path(out).resolve()), str(Path(out).resolve()).replace("\\", "/")):
        text = text.replace(json.dumps(form)[1:-1], "<run>")
    return json.loads(text)


def alike(a, b) -> bool:
    """Equal, numbers to the millimetre: an input file holds its coordinates rounded, the job that wrote it does not."""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(alike(a[key], b[key]) for key in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(alike(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= ROUNDING
    return a == b


def differing(a, b, path: str = "") -> list[str]:
    """The dotted paths, two levels deep at most, under which two jobs differ."""
    if isinstance(a, dict) and isinstance(b, dict) and path.count(".") < 2:
        found = []
        for key in sorted(set(a) | set(b)):
            found += differing(a.get(key), b.get(key), f"{path}{key}.")
        return found
    return [] if alike(a, b) or (not a and not b) else [path.rstrip(".")]


def lost(job: dict, run_folder: Path, rebuilt: dict, out: Path) -> list[str]:
    ignored = IGNORED if "model_type" in (job.get("run") or {}) else (*IGNORED, UNNAMED_TYPE)
    paths = [p for p in differing(comparable(job, run_folder), comparable(rebuilt, out)) if p not in ignored]
    if len(paths) > MOST_WORDS:
        paths = [*paths[:MOST_WORDS], f"and {len(paths) - MOST_WORDS} more"]
    return [f"these parts of the job, which stay as the dock has them: {', '.join(paths)}"] if paths else []
