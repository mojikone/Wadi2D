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
from .simulation_rows import NUMERIC_KEYS, STEP_AUTO, STEP_FIXED, fixed_step
from .storm_rows import (
    KIND_DEPTH,
    KIND_DEPTH_GRID,
    KIND_DESIGN,
    KIND_FIXED,
    KIND_GAUGES,
    KIND_GRID,
    KIND_STEADY,
    KIND_TABLE,
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
    """A layer named by its file alone, for the sections to find in the project or add to it; a GeoPackage's layer by
    its ``path|layername=name`` source and that name (W101)."""
    if not path:
        return None
    source = str(path)
    name = source.split("|layername=")[1] if "|layername=" in source else Path(source).stem
    return {
        "id": None,
        "source": source,
        "name": name,
        "provider": RASTER_PROVIDER if raster else "ogr",
    }


def _inline(gpkg, held: dict, name: str):
    """The GeoPackage layer that holds a job's inline geometry of this name, or None (W101)."""
    from .job_import import layer_source

    return layer(layer_source(gpkg, name)) if gpkg is not None and name in held else None


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


DESIGN_PATTERN, ARF_CURVE, HMS_TABLE = "Design pattern", "Area reduction", "(hms)"


def _part(reduction: dict, which: str, entry: dict | None) -> None:
    """One part of ``storm.area_reduction`` as the Area reduction section's widgets (W101)."""
    if entry is None:
        reduction[f"{which}.form"] = choice("none")
        return
    form = entry.get("form")
    if form == "coefficient":
        reduction[f"{which}.form"], reduction[f"{which}.coefficient"] = choice("coefficient"), entry.get("coefficient")
        return
    name = entry.get("curve") or ARF_CURVE
    reduction[f"{which}.curve"] = choice(name)
    if form == "area":
        reduction[f"{which}.form"], reduction[f"{which}.area"] = choice("area"), entry.get("area_km2")
    elif which == "grid":  # a 2D curve: the depth-area study's
        reduction[f"{which}.form"] = choice("study")
    else:
        reduction[f"{which}.form"] = choice("curve")


def _reduction(storm: dict, store: dict) -> dict:
    """The Area reduction section's widgets from a job's storm, the curves it reads put into ``store`` (W101)."""
    widgets: dict = {}
    split = storm.get("area_reduction")
    if split:
        for which in ("lumped", "grid"):
            _part(widgets, which, split.get(which))
        return widgets
    if storm.get("arf_factor") is not None:  # a resolved job writes the key out as null (W101)
        for which in ("lumped", "grid"):
            _part(widgets, which, {"form": "coefficient", "coefficient": storm["arf_factor"]})
    elif storm.get("storm_area_km2") is not None:
        table = storm.get("arf")
        name = HMS_TABLE
        if table:
            name = ARF_CURVE
            store["arf_curves"][name] = {
                "areas_km2": list(table.get("areas_km2", [])), "factors": list(table.get("factors", [])),
                "reduces_below_table": table.get("reduces_below_table", True),
                **({"table_type": table["table_type"]} if table.get("table_type", "fixed-area") != "fixed-area" else {}),
            }  # fmt: skip
        for which in ("lumped", "grid"):
            _part(widgets, which, {"form": "area", "curve": name, "area_km2": storm["storm_area_km2"]})
    return widgets


def _tables(job: dict) -> dict:
    """The job's ``data_tables`` as the Data tables section holds them."""
    held = job.get("data_tables") or {}
    store: dict = {"patterns": {}, "arf_curves": {}}
    for name, table in (held.get("patterns") or {}).items():
        store["patterns"][name] = {
            "time": list(table["time"]), "depth": list(table["depth"]),
            "time_units": table.get("time_units", "percent"), "form": table.get("form", "cumulative"),
        }  # fmt: skip
    for name, table in (held.get("arf_curves") or {}).items():
        store["arf_curves"][name] = {
            "areas_km2": list(table["areas_km2"]), "factors": list(table["factors"]),
            "reduces_below_table": table.get("reduces_below_table", True),
        }  # fmt: skip
    return store


def _pattern_choice(pattern: dict | None) -> dict:
    if not pattern or pattern.get("kind") == "uniform":
        return choice("uniform")
    if pattern.get("kind") == "scs":
        return choice(f"scs:{pattern.get('scs_type')}")
    return choice(f"table:{pattern.get('table')}")


def _storm(storm: dict, store: dict) -> dict:
    """The Storm section's state for the storm kinds the dock itself writes; another kind is left to the comparison.
    A design storm of a run from before W101 comes back as a depth with its pattern put into ``store``."""
    widgets: dict = {}
    rows: dict = {}
    kind = storm.get("kind")
    hours = storm.get("duration_min", 0.0) / MINUTES_PER_HOUR
    if kind == KIND_STEADY:
        widgets.update(kind=choice(KIND_FIXED), hours=hours, fixed_depth=storm.get("depth_mm", 0.0))
    elif kind == KIND_TABLE:
        table = zip(storm.get("hyetograph_min", []), storm.get("hyetograph_mm", []), strict=False)
        widgets.update(kind=choice(KIND_TABLE), hyetograph=[list(pair) for pair in table])
    elif kind == KIND_DESIGN and "time_percent" in storm:
        store["patterns"][DESIGN_PATTERN] = {
            "time": list(storm["time_percent"]), "depth": list(storm.get("depth_percent", [])),
            "time_units": "percent", "form": "cumulative",
        }  # fmt: skip
        widgets.update(
            kind=choice(KIND_DEPTH), depth_mm=storm.get("depth_mm"), depth_hours=hours,
            depth_pattern=choice(f"table:{DESIGN_PATTERN}"),
        )  # fmt: skip
    elif kind == KIND_DEPTH:
        widgets.update(
            kind=choice(KIND_DEPTH), depth_mm=storm.get("depth_mm"), depth_hours=hours,
            depth_pattern=_pattern_choice(storm.get("pattern")),
        )  # fmt: skip
    elif kind == KIND_DEPTH_GRID:
        widgets.update(
            kind=choice(KIND_DEPTH_GRID), depth_raster=layer(storm.get("depth_grid"), raster=True), grid_hours=hours,
            grid_pattern=_pattern_choice(storm.get("pattern")),
        )  # fmt: skip
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
    elif kind == KIND_GAUGES:
        spread = storm.get("gauges") or {}
        widgets.update(
            kind=choice(KIND_GAUGES),
            gauge_method=choice(spread.get("method")),
            gauge_gaps=choice(spread.get("gaps")),
        )
        widgets["gauge_radius"] = spread.get("search_radius_m") or 0.0
        stations = spread.get("gauges") or []
        if stations:
            widgets["gauge_values"] = choice(stations[0].get("values"))
        rows["gauge_table"] = [
            {"name": g.get("name", ""), "kind": RAIN, "file": g.get("file", ""), "series": g.get("record", ""),
             "x": g.get("x"), "y": g.get("y"), "values": g.get("values")}
            for g in stations
        ]  # fmt: skip
    return {"widgets": widgets, "rows": rows}


def _structures(job: dict, inputs_dir: Path, gpkg=None, inline: dict | None = None) -> dict:
    widgets: dict = {}
    inline = inline or {}
    objects = job.get("terrain", {}).get("objects", [])
    for kind, keys in PLAIN_KINDS.items():
        path = inputs_dir / f"{kind}.geojson"
        if path.is_file():
            held = _properties(path)
            widgets[f"layers.{kind}"] = layer(path)
            for key in keys:
                _put(widgets, f"fields.{kind}.{key}", key if key in held else None)
        elif _inline(gpkg, inline, kind) is not None:  # a job written elsewhere: its objects inline (W101)
            held = {k for _xy, props in inline[kind]["features"] for k, v in props.items() if v is not None}
            widgets[f"layers.{kind}"] = _inline(gpkg, inline, kind)
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
    elif _inline(gpkg, inline, "initial_water") is not None:
        widgets["start_water.ponds"], widgets["start_water.pond_level"] = _inline(gpkg, inline, "initial_water"), "level"
    if _inline(gpkg, inline, "initial_points") is not None:  # W101 item 3
        widgets["start_water.points"] = _inline(gpkg, inline, "initial_points")
        widgets["start_water.point_level"], widgets["start_water.point_name"] = "level", "name"
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
    _put(widgets, "corridor_generator", choice(strips["generator"]) if strips.get("generator") else None)
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
        from .job_import import hms_choice

        widgets["folder"] = str(Path(hms).parent)
        widgets["files.basin"] = {"data": None, "text": Path(hms).name}
        if Path(hms).parent.is_dir():  # a job written elsewhere names no met or control file (W101)
            chosen = hms_choice(Path(hms).parent, job)
            for key, name in chosen["files"].items():
                widgets[f"files.{key}"] = {"data": None, "text": name}
            extra["hms_words"] = chosen["words"]
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
    override = hydrology.get("cn_override") or {}
    if override.get("by"):  # W101 item 2
        widgets["cn_by"] = choice(override["by"])
        _put(widgets, "cn_landuse", layer(override.get("land_use"), raster=True))
        rows = {
            "land_use": [[c["code"], c["curve_number"], c.get("name", "")] for c in override.get("classes") or []],
            "range": [[r["low"], r["high"], r["curve_number"]] for r in override.get("ranges") or []],
            "subbasin": [[b["name"], b["curve_number"]] for b in override.get("subbasins") or []],
        }[override["by"]]
        widgets["cn_table"] = rows
    return {"widgets": widgets, "extra": extra}


def _simulation(job: dict) -> dict:
    """The Simulation section: the run's start (the rain's, else the first observed record's), the times, the 2D step
    as fixed where the job holds both bounds equal, and the numbers a job gives only when they left the defaults.
    """
    run, outputs, storm, numerics, hydrology = (
        job.get(key) or {} for key in ("run", "outputs", "storm", "numerics", "hydrology")
    )
    widgets: dict = {}
    observed = [entry.get("start") for entry in outputs.get("observed") or [] if entry.get("start")]
    _put(widgets, "start", storm.get("rain_start") or (observed[0] if observed else None))
    _put(widgets, "duration", run["duration_s"] / SECONDS_PER_HOUR if "duration_s" in run else None)
    _put(widgets, "maps", choice(outputs["map_every_s"]) if "map_every_s" in outputs else None)
    _put(widgets, "backend", choice(run["backend"]) if run.get("backend") else None)
    held = fixed_step(numerics)
    widgets["step_mode"] = choice(STEP_FIXED if held is not None else STEP_AUTO)
    if held is not None:
        widgets["fixed_step"] = held
    else:
        for key in NUMERIC_KEYS:
            _put(widgets, key, numerics.get(key))
    _put(widgets, "lumped_step", hydrology.get("time_step_min"))
    _put(widgets, "series", outputs.get("series_every_s"))
    return widgets


def _boundary_rows(job: dict) -> list[dict]:
    """The table's rows of a job's boundary lines, by their place in the layer the dock writes (fid 1, 2, ...): what a
    layer's fields cannot hold, a flow line's typed hydrograph and its slope (W101 item 3)."""
    rows = []
    for number, line in enumerate(job.get("boundaries") or [], start=1):
        kind = line.get("kind")
        flow = line.get("flow") or {}
        value = line.get("stage") if kind == "stage" else line.get("slope") if kind == "normal" else None
        row = {"fid": number, "label": f"Line {number}", "kind": kind, "value": value, "kind_pinned": True,
               "value_pinned": value is not None, "file": flow.get("file")}  # fmt: skip
        if flow.get("flows") is not None and flow.get("step_s"):
            row.update(typed=True, step_min=flow["step_s"] / 60.0, flows=list(flow["flows"]))
        if flow.get("slope") is not None and flow.get("slope") != 0.005:
            row["slope"] = flow["slope"]
        for key in ("momentum", "direction"):
            if flow.get(key) is not None:
                row[key] = flow[key]
        rows.append(row)
    return rows


def job_states(job: dict, run_folder: Path | str, gpkg: Path | str | None = None) -> dict:
    """Section states, by section key, of what ``job`` tells; ``run_folder`` holds its ``inputs``. A job written
    elsewhere holds its lines and polygons inline: with ``gpkg``, the GeoPackage :func:`job_import.inline_layers` was
    written into, its layers stand where the run's input files would (W101)."""
    from .job_import import inline_layers

    root = Path(run_folder)
    inputs_dir = root / INPUTS_DIR
    inline = inline_layers(job) if gpkg is not None else {}
    grid, terrain, outputs = (job.get(key) or {} for key in ("grid", "terrain", "outputs"))
    ground = {"dem": layer(terrain.get("dem"), raster=True), "fill_pits": bool(terrain.get("fill_pits"))}
    _put(ground, "dx", grid.get("dx"))
    _put(ground, "domain", layer(grid.get("domain")))
    _put(ground, "manning.box", terrain.get("manning"))
    _put(ground, "manning.raster", layer(terrain.get("manning_raster"), raster=True))
    rough = terrain.get("roughness") or {}
    if rough.get("form") in ("split", "land_use"):  # W101 item 2: the two forms the old fields cannot say
        ground["manning_form"] = choice(rough["form"])
        _put(ground, "manning.box", rough.get("n"))
        _put(ground, "manning_aligned", rough.get("n_aligned"))
        _put(ground, "rough_landuse", layer(rough.get("land_use"), raster=True))
        if rough.get("classes"):
            ground["rough_classes"] = [[c["code"], c["n"], c.get("name", "")] for c in rough["classes"]]
    elif terrain.get("manning_raster"):
        ground["manning_form"] = choice("grid")
    edges, design = inputs_dir / "boundaries.geojson", inputs_dir / "design_points.geojson"
    points = {}
    inline_design = next((name for name in ("design_lines", "design_points") if name in inline), None)
    if design.is_file():
        held = _properties(design)
        points = {
            "layer": layer(design),
            "name": "name" if "name" in held else "",
            "area": AREA_KEY if AREA_KEY in held else "",
        }
    elif inline_design is not None:
        held = {k for _xy, props in inline[inline_design]["features"] for k, v in props.items() if v is not None}
        points = {
            "layer": _inline(gpkg, inline, inline_design),
            "name": "name" if "name" in held else "",
            "area": AREA_KEY if AREA_KEY in held else "",
        }
    panel = {"folder": str(root), "pixels": (outputs.get("pixels") or {}).get("enabled", True)}
    _put(panel, "smooth", (outputs.get("smooth") or {}).get("enabled"))
    panel["limiter"] = bool(outputs.get("step_limiter"))
    pixels = outputs.get("pixels") or {}
    panel["map_pixel"] = pixels["pixel_m"] if pixels.get("pixel_m") is not None else -1.0  # W101: -1 is Automatic
    panel["dv_raster"] = bool(pixels.get("dv_raster"))
    floors = {pixels.get(key) for key in ("depth_floor", "hazard_depth_floor", "cell_depth_floor")}
    panel["cutoff"] = floors.pop() if len(floors) == 1 and None not in floors else -0.001  # one threshold, or the engine's
    store = _tables(job)
    storm = job.get("storm") or {}
    storm_state = _storm(storm, store)
    reduction = _reduction(storm, store)
    if (job.get("hydrology") or {}).get("arf_by_element"):
        reduction["by_element"] = True
    return {
        "terrain": {"widgets": ground},
        "mesh": _mesh(job, inputs_dir),
        "hydrology": _hydrology(job, inputs_dir),
        "tables": {"widgets": {}, "extra": {"store": store}},
        "storm": storm_state,
        "reduction": {"widgets": reduction},
        "structures": _structures(job, inputs_dir, gpkg, inline),
        "boundaries": {
            "widgets": {"layer": layer(edges)} if edges.is_file()
            else ({"layer": _inline(gpkg, inline, "boundaries")} if "boundaries" in inline else {}),
            "rows": {"": _boundary_rows(job)} if not edges.is_file() and "boundaries" in inline else {},
        },
        "points": {"widgets": points},
        "simulation": {"widgets": _simulation(job)},
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
