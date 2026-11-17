# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Widget values and layers to a job dict and its input files.

Pure Python down to the section "QGIS adapters", whose imports stay inside the functions. Keys and defaults come
from the engine's JSON Schema: this module says where a widget's value goes, never what its number is.
"""

from __future__ import annotations

import json
import math
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .basin_point_rows import apply_delineate, delineate_field
from .breach_rows import breach_jobs, breach_problems
from .dam_rows import dam_problems, initial_problems, initial_water
from .entry_rows import apply_edits, edit_problems, inflow_jobs, inflow_problems
from .gauge_rows import gauge_problems, observed_records, rain_storm
from .land_rows import cn_job, cn_problems, roughness_job, roughness_problems
from .mesh_rows import reversed_note, rounded_note
from .model_types import type_problems
from .protocol import CACHE_DIR, INPUTS_DIR, JOB_FILE
from .reduction_rows import curves_read, lumped_form, reduction_job, reduction_problems
from .sections.basin_rows import basin_settings
from .shaped import SHAPED_KINDS, TABLE, shaped_object, shaped_problems
from .simulation_rows import LUMPED_REPLACES, simulation_problems
from .storm_rows import (
    KIND_DEPTH,
    KIND_DEPTH_GRID,
    KIND_DESIGN,
    KIND_GAUGES,
    storm_job,
    storm_notes,
    storm_problems,
    takes_hms_table,
)
from .study_rows import AREA_KEY, line_area
from .table_rows import CURVES, pattern_name, store_job, store_problems

DX = "grid.dx"
MANNING = "terrain.manning"
DURATION = "run.duration_s"
RAIN_DEPTH = "storm.depth_mm"
RAIN_DURATION = "storm.duration_min"
CURVE_NUMBER = "hydrology.curve_number"
SUBBASIN_MODE = "hydrology.subbasins.mode"
BOUNDARY_KIND = "boundaries.kind"
BOUNDARY_STAGE = "boundaries.stage"
BOUNDARY_SLOPE = "boundaries.slope"
SPILLWAY_C = "terrain.objects.coefficient"
DAM_LEVELS = "dam_levels"
NO_HMS_TABLE = (
    "The gridded rain is to take the HMS project's area reduction table, and the project has none: fill the table "
    "in Storm."
)
MESH_ENABLED = "mesh.enabled"
MESH_COARSE = "mesh.coarse_dx"
STRIPS_ENABLED = "strips.enabled"
STRIPS_CELL_MIN = "strips.cell_min_m"
STRIPS_CELL_MAX = "strips.cell_max_m"
STRIPS_FRACTION = "strips.width_fraction"
STRIPS_OUTSIDE = "strips.rows_outside"
STRIPS_GORGE = "strips.gorge_rows"
STRIPS_KEYS = ("cell_min_m", "cell_max_m", "width_fraction", "rows_outside")
CORRIDOR_NOTE = (
    "A corridor of cells aligned with each pair of suggested banks: its rows span the wadi between the banks, the cell "
    "across the given share of the width held between the two sizes, one row more beyond each bank; the squares under "
    "it are replaced and the gap triangulated, the rest of the domain stays squares. A wadi with one bank or none keeps "
    "its squares. Press Suggest breaklines first and choose its layer. Corridors run on the uniform grid, without the "
    "mesh refinement above (W45)."
)
BREAK_RISE = "breaklines.bank_rise_m"
BREAK_REACH = "breaklines.bank_reach_m"
BREAK_DEPTH = "breaklines.bank_depth_m"
BREAK_CREST = "breaklines.crest_height_m"
BREAK_DISC = "breaklines.disc_radius_m"
BREAK_SLOPE = "breaklines.ground_slope_max"
BREAK_OFFSET = "breaklines.bank_offset_cells"
BREAK_SCARP = "breaklines.bank_scarp_m"
BREAK_SLOPE_CAP = "breaklines.bank_slope"
BREAK_CAP = "breaklines.bank_slope_cap"
BREAK_KEYS = frozenset(
    {
        "bank_rise_m", "bank_reach_m", "bank_depth_m", "bank_offset_cells", "crest_height_m", "disc_radius_m",
        "ground_slope_max", "bank_depth_map", "bank_scarp_m", "bank_slope", "bank_slope_cap",
    }
)  # fmt: skip
"""What the Mesh section's Suggest settings write into the job's ``breaklines`` section."""
MESH_FINE_AREA = "mesh.stream_area_fine_km2"
MESH_MID_AREA = "mesh.stream_area_mid_km2"
MESH_ZONE_DX = "mesh.zones.dx"
MESH_LINE_NEAR = "mesh.lines.near_dx"
MESH_LINE_ROWS = "mesh.lines.rows"
MESH_LINE_FAR = "mesh.lines.far_dx"
LOCAL_STEPS = "numerics.local_time_stepping"
ZONE_DX_FIELD = "dx"
TILE_CELLS = 32
"""Cells along a tile, for the words below; a contract test holds it to the engine's."""
SPEED_NOTE = (
    "Local time stepping saves no time on a uniform grid; it helps on a large mesh. "
    "A mesh saves time above about 1 M cells, and only memory below that."
)
LINES_NOTE = (
    "The mesh only doubles a cell, so each size goes down to the finest cell times 1, 2, 4 or 8, never coarser than "
    f"you asked: the Actual columns show what you get. Bands are whole tiles of {TILE_CELLS} cells, so a band is usually "
    f"wider than its rows, and up to {TILE_CELLS} rows the 2:1 grading alone sets the sizes outside it, so Far changes "
    "nothing. A line only refines: it blocks no flow. For a wall use Structures. A band does not replace the wadi areas "
    "above: on one wadi alone it left the side wadis coarse and lost more of the peak than the two together."
)
MAP_EVERY = "outputs.map_every_s"
PIXELS_ON = "outputs.pixels.enabled"
PIXEL_M = "outputs.pixels.pixel_m"
DV_RASTER = "outputs.pixels.dv_raster"
"""His item 7 (W101): the pixel of the maps of record and the depth x speed raster, each written only when set."""
FILL_PITS = "terrain.fill_pits"
EXCLUDE_LUMPED = "grid.exclude_lumped"
"""The 2D mesh leaves out the catchments the lumped network carries (W88)."""
LUMPED_ENTRY = "hydrology.lumped_entry"
LUMPED_ENTRY_WORDS = {
    "outlet": "At each subbasin's outlet: the 2D model routes it from there",
    "network": "Down the HMS reaches and dams, entering where rain-on-grid joins",
}
LUMPED_ONLY = "run.lumped_only"
ARF_BY_ELEMENT = "hydrology.arf_by_element"
STEP_LIMITER = "outputs.step_limiter"
STEP_LIMITER_ON = "layer"
"""What the dock's tick asks for: the limiter in the progress and as a layer (W85)."""
SMOOTH_ON = "outputs.smooth.enabled"
SMOOTH_TIP = (
    "Smooth polygons of the hazard classes and a depth picture with a soft wet edge, for map sheets. They take "
    "several times as long as the pixel maps themselves, which are the numbers of record either way. Left unticked, "
    "Make map has them made when a sheet needs them."
)
BACKEND = "run.backend"
BACKEND_WORDS = {
    "auto": "Automatic: the GPU if there is one",
    "gpu": "GPU only",
    "cpu": "CPU only",
}
"""One phrase per engine choice of the schema; a contract test holds the keys to the engine's."""
BACKEND_TIP = (
    "Automatic takes an NVIDIA GPU when one answers and the CPU otherwise. GPU only refuses to run without one. "
    "CPU only never touches the graphics card: choose it when there is no NVIDIA card or its driver misbehaves. "
    "The method is the same; the CPU is many times slower."
)

ANIMATION_MAP_S = 300.0
"""Saved maps for a film: the dock's other choice. A display choice, so it lives here; the default is the schema's."""

PREFERRED_DX = 20.0
"""The dock's starting cell size, his choice for a first look: the schema's default is the finer engine one."""

SECONDS_PER_HOUR = 3600.0
MINUTES_PER_HOUR = 60.0
COORDINATE_DECIMALS = 3
STRUCTURE_KINDS = ("crest_line", "wall", "spillway", "burn_line", *SHAPED_KINDS)
ELEVATED_KINDS = ("crest_line", "spillway")
GROUND_KINDS = ("burn_line", *SHAPED_KINDS)
"""Objects that change the ground, so a preview has something to show."""
HMS_KEYS = ("basin", "met", "control")


class SchemaView:
    """Read-only walk through the engine's JSON Schema by dotted path; lists are stepped through."""

    def __init__(self, schema: dict) -> None:
        self._schema = schema

    def _resolve(self, node: dict) -> dict:
        while True:
            if "$ref" in node:
                target = self._schema
                for key in node["$ref"].lstrip("#/").split("/"):
                    target = target[key]
                node = {**target, **{key: value for key, value in node.items() if key != "$ref"}}
            elif "anyOf" in node:
                options = [option for option in node["anyOf"] if option.get("type") != "null"]
                rest = {key: value for key, value in node.items() if key != "anyOf"}
                node = {**(options[0] if options else {}), **rest}
            else:
                return node

    def field(self, path: str) -> dict:
        """The resolved schema of a field; empty when the engine does not have it."""
        node = self._schema
        for key in path.split("."):
            node = self._resolve(node)
            if node.get("type") == "array":
                node = self._resolve(node.get("items", {}))
            if key not in node.get("properties", {}):
                return {}
            node = node["properties"][key]
        return self._resolve(node)

    def has(self, path: str) -> bool:
        return bool(self.field(path))

    def default(self, path: str, fallback=None):
        return self.field(path).get("default", fallback)

    def bounds(self, path: str) -> tuple[float | None, float | None]:
        node = self.field(path)
        low = node.get("minimum", node.get("exclusiveMinimum"))
        return low, node.get("maximum", node.get("exclusiveMaximum"))

    def enum(self, path: str) -> list:
        return list(self.field(path).get("enum", []))

    def tip(self, path: str) -> str:
        return self.field(path).get("description", "")


class LayerError(ValueError):
    """A layer that cannot be used; the text is for the user."""


@dataclass(frozen=True)
class Feature:
    """One single-part geometry in the DEM CRS with the attributes the job needs."""

    kind: str  # "Point", "LineString" or "Polygon"
    coordinates: list
    properties: dict = field(default_factory=dict)

    def xy(self) -> list[list[float]]:
        """Line vertices without their Z."""
        return [[point[0], point[1]] for point in self.coordinates]

    def vertex_z(self) -> list[float] | None:
        """One Z per vertex, when the geometry has them."""
        if self.coordinates and all(len(point) == 3 for point in self.coordinates):
            return [point[2] for point in self.coordinates]
        return None

    def name(self, index: int) -> str:
        return str(self.properties.get("name") or f"P{index + 1}")


def snap_dx(dx: float, pixel: float) -> float:
    """The nearest multiple of the DEM pixel, at least one pixel: the engine wants an exact multiple."""
    if pixel <= 0:
        return dx
    return max(1, round(dx / pixel)) * pixel


def feature_collection(features: list[Feature], crs: str) -> dict:
    """GeoJSON in the DEM CRS, the CRS named by the pre-RFC member that GDAL and QGIS honour."""
    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": crs}},
        "features": [
            {
                "type": "Feature",
                "properties": feature.properties,
                "geometry": {"type": feature.kind, "coordinates": _rounded(feature.coordinates)},
            }
            for feature in features
        ],
    }


def _rounded(value):
    if isinstance(value, (list, tuple)):
        return [_rounded(item) for item in value]
    return round(value, COORDINATE_DECIMALS)


def write_geojson(path: Path, features: list[Feature], crs: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(feature_collection(features, crs)), encoding="utf-8")
    return path


def problems(values: dict) -> list[str]:
    """What stops a run, in plain words. Empty means the job can be built."""
    if not values.get("dem"):
        return ["Choose a DEM layer backed by a file."]
    found = []
    if values.get("geographic"):
        found.append("The DEM must be in a projected CRS, in metres.")
    if not values.get("output"):
        found.append("Choose an output folder.")
    hms = values.get("hms")
    found.extend(_rain_problems(values))
    found.extend(_reduction_problems(values))
    found.extend(roughness_problems(values.get("roughness"), bool(values.get("strips"))))  # W101 item 2
    found.extend(cn_problems(values.get("cn_override")))
    if hms and not all(hms.get(key) for key in HMS_KEYS):
        found.append("The HMS folder needs a basin, a meteorologic and a control file.")
    basin = values.get("basin")
    if basin is not None and not basin.get("json"):
        found.append("Press Generate basin first, or untick it: the run needs the generated basin.json.")
    if any(not feature.properties.get("element") for feature in values.get("handbacks") or []):
        found.append("Every hand-back line needs an element to enter: choose one in the table.")
    found.extend(_entry_problems(values))
    found.extend(_structure_problems(values.get("structures", {})))
    found.extend(dam_problems(values.get("dam_rows") or []))
    dams = [row.name for row in values.get("dam_rows") or []]
    found.extend(breach_problems(values.get("breach_rows") or [], dams, values))
    found.extend(initial_problems(values.get("initial_water") or []))
    unlevelled = [p["name"] for p in values.get("initial_points") or [] if not isinstance(p.get("level"), (int, float))]
    if unlevelled:
        found.append(f"Initial level points need a level: choose the field that holds it ({', '.join(unlevelled)}).")
    found.extend(boundary_problems(values))
    found.extend(type_problems(values))
    found.extend(simulation_problems(values))
    return found + _mesh_problems(values) + _strip_problems(values) + _gauge_problems(values)


NO_NETWORK = (
    "Point inflows take the outflow of a lumped element: choose an HMS project or generate the basin, in Hydrology, or "
    "remove them."
)


def _entry_problems(values: dict) -> list[str]:
    """The subbasins' own storm areas, entries and outlets and the point inflows (W103), in plain words."""
    hms = values.get("hms") or {}
    found = list(values.get("entry_problems") or []) + list(values.get("last_point_problems") or [])  # W105
    form = None  # the HMS project's own storm carries its table
    if values.get("storm"):  # the kind the job is written as: a depth that fits it is the design storm (_reduced)
        kind = KIND_DESIGN if _design_table(values) is not None else values["storm"].get("kind")
        form = lumped_form(values.get("reduction"), kind)
    found += edit_problems(hms.get("edits"), hms.get("modes") or {}, form)
    rows = values.get("inflows") or []
    found += inflow_problems(rows)
    if rows and not (values.get("hms") or values.get("basin")):
        found.append(NO_NETWORK)
    return found


def _uses_gauges(values: dict) -> bool:
    return (values.get("storm") or {}).get("kind") == KIND_GAUGES


def _design_names(values: dict) -> tuple[set[str], set[str]]:
    """(result lines, result points) by name, as ``_design_outputs`` names them."""
    lines, points = set(), set()
    for index, feature in enumerate(values.get("design") or []):
        (points if feature.kind == "Point" else lines).add(feature.name(index))
    return lines, points


def _gauge_problems(values: dict) -> list[str]:
    gauges = values.get("gauges") or {}
    rows = gauges.get("rows") or []
    if not rows and not _uses_gauges(values):
        return []
    return gauge_problems(rows, _uses_gauges(values), *_design_names(values))


def _strip_problems(values: dict) -> list[str]:
    """What stops the corridors: they need the Suggest breaklines file and the uniform grid."""
    strips = values.get("strips")
    if not strips:
        return []
    found = []
    banks = strips.get("banks") or ""
    if not banks:
        found.append("Choose the Suggested breaklines layer for the corridors, or untick them.")
    elif not Path(banks).is_file():
        found.append("The corridors need the Suggest breaklines GeoPackage: choose the layer it wrote.")
    if strips.get("cell_min_m", 0.0) > strips.get("cell_max_m", math.inf):
        found.append("The smallest cell across a corridor must not exceed the largest.")
    if values.get("mesh"):
        found.append("Corridors run on the uniform grid: untick the mesh refinement or the corridors.")
    return found


def _rain_problems(values: dict) -> list[str]:
    if values.get("storm"):
        return storm_problems(values["storm"])
    if values.get("hms"):
        return []
    rain = values.get("rain_mm_h", 0.0)
    if rain <= 0.0:
        return ["Set the rain, or choose an HMS project."]
    return [] if values.get("rain_hours", 0.0) > 0.0 else ["Set how many hours the rain lasts."]


DEPTH_KINDS = (KIND_DEPTH, KIND_DEPTH_GRID)
"""The storms that read a pattern by name (W101); a design storm of the old dict carries its rows as ``pattern``."""


def _for_study(values: dict) -> bool:
    """A depth-area study's job, or the check before one: the 2D part reads the study's areas (W101)."""
    return bool(values.get("study") or values.get("for_study"))


def _reduction_problems(values: dict) -> list[str]:
    """The area reduction and the stored tables the storm reads (W101): a name Data tables does not hold, a curve or a
    pattern the engine would refuse, a part set to what this run cannot read."""
    storm = values.get("storm") or {}
    kind = storm.get("kind")
    store = values.get("data_tables") or {}
    reduction = values.get("reduction")
    found = []
    if reduction is not None:
        found += reduction_problems(
            reduction, kind, store.get(CURVES, {}), study=_for_study(values), hms=bool(values.get("hms"))
        )
    if found:
        return found
    patterns = {pattern_name(storm.get("pattern"))} - {None} if kind in DEPTH_KINDS else set()
    curves = curves_read(reduction, kind, _for_study(values)) if reduction is not None else set()
    return store_problems(store, patterns, curves)


def _design_table(values: dict) -> dict | None:
    """The stored pattern of a depth storm when the design storm's own form holds it to the digit: percent of the
    duration, cumulative, from 0 to 100 % of the depth; None otherwise."""
    storm = values.get("storm") or {}
    name = pattern_name(storm.get("pattern")) if storm.get("kind") == KIND_DEPTH else None
    table = ((values.get("data_tables") or {}).get("patterns") or {}).get(name) if name else None
    if not table or table.get("time_units", "percent") != "percent" or table.get("form", "cumulative") != "cumulative":
        return None
    t, d = table.get("time") or [], table.get("depth") or []
    return table if len(t) >= 2 and t[0] == 0.0 and d[0] == 0.0 and t[-1] == 100.0 and d[-1] == 100.0 else None


def _reduced(values: dict, job_storm: dict) -> tuple[dict, dict]:
    """The storm block with what the area reduction adds, and the job's ``data_tables``: only the tables the storm
    names. A depth whose pattern and reduction the design storm's form holds is written in that form (W101), so a job
    of that form, read into the dock, writes itself again."""
    storm = values.get("storm") or {}
    kind = storm.get("kind")
    store = values.get("data_tables") or {}
    reduction = values.get("reduction")
    curves_of = store.get(CURVES, {})
    design = _design_table(values)
    if design is not None and reduction is not None:
        extra, curves = reduction_job(reduction, KIND_DESIGN, curves_of, _for_study(values))
        if "area_reduction" not in extra:  # one reduction for every part: the design storm's form
            shaped = {
                "kind": KIND_DESIGN, "depth_mm": job_storm["depth_mm"], "duration_min": job_storm["duration_min"],
                "time_percent": list(design["time"]), "depth_percent": list(design["depth"]), **extra,
            }  # fmt: skip
            return shaped, store_job(store, set(), curves)
    extra, curves = reduction_job(reduction, kind, curves_of, _for_study(values)) if reduction else ({}, set())
    patterns = {pattern_name(storm.get("pattern"))} - {None} if kind in DEPTH_KINDS else set()
    return {**job_storm, **extra}, store_job(store, patterns, curves)


def _structure_problems(structures: dict) -> list[str]:
    found = []
    for kind in ELEVATED_KINDS:
        if any(_elevation(feature) is None for feature in structures.get(kind, [])):
            label = kind.replace("_", " ")
            found.append(f"Every {label} needs an elevation: choose a field, or use a layer with Z values.")
    return found + shaped_problems(structures)


def _mesh_problems(values: dict) -> list[str]:
    """What stops a mesh, in plain words."""
    mesh = values.get("mesh")
    if not mesh:
        return []
    found = []
    dx = snap_dx(values.get("dx", 0.0), values.get("pixel", 0.0))
    ratio = mesh["coarse_dx"] / dx if dx > 0.0 else 0.0
    if ratio < 1.0 or abs(2.0 ** round(math.log2(ratio)) - ratio) > 1e-6:
        found.append(f"The coarsest cell must be {dx:g} m times 1, 2, 4 or 8.")
    if mesh["mid_km2"] > mesh["fine_km2"]:
        found.append("The wadi area for the finest cell must be the larger of the two.")
    if mesh.get("zones_unset"):
        found.append("Refinement zones need a cell size: choose the field that holds it.")
    if any(not _zone_dx(zone) for zone in mesh.get("zones", [])):
        found.append("Every refinement zone needs a cell size above zero.")
    for line in mesh.get("lines", []):
        text = reversed_note(line.properties["name"], line.properties["near_dx"], line.properties["far_dx"])
        if text:
            found.append(text)
    return found


def preview_problems(values: dict) -> list[str]:
    """What stops a terrain preview: it needs no rain, no boundary and no output folder."""
    if not values.get("dem"):
        return ["Choose a DEM layer backed by a file."]
    found = ["The DEM must be in a projected CRS, in metres."] if values.get("geographic") else []
    structures = values.get("structures", {})
    if not any(structures.get(kind) for kind in GROUND_KINDS):
        found.append("Choose an embankment, a channel or a burn line layer to preview.")
    return found + _structure_problems(structures)


def _zone_dx(zone: Feature) -> float:
    try:
        return float(zone.properties.get(ZONE_DX_FIELD) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def notes(values: dict) -> list[str]:
    """What is allowed but probably not meant."""
    found = []
    if not values.get("boundaries"):
        found.append("No boundary set: every edge is a wall, so water cannot leave the domain.")
    elif all(getattr(f, "properties", {}).get("kind") == "flow" for f in values["boundaries"]):
        found.append("Only flow lines are set: water comes in and every edge is a wall, so none can leave the domain.")
    if not values.get("hms") and values.get("rain_hours", 0.0) > values.get("duration_h", 0.0):
        found.append("The rain outlasts the simulated time, so the run ends while it is still raining.")
    if values.get("storm"):
        found.extend(storm_notes(values["storm"], values.get("duration_h", 0.0)))
    lumped = values.get("hms") or values.get("basin")
    if lumped and not values.get("curve_number") and not values.get("cn_raster"):
        found.append(
            "No curve number: rain on the 2D area outside the lumped subbasins runs off with no losses."
        )
    dx, pixel = values.get("dx"), values.get("pixel", 0.0)
    if dx and snap_dx(dx, pixel) != dx:
        found.append(
            f"The cell size becomes {snap_dx(dx, pixel):g} m, a whole number of {pixel:g} m DEM pixels."
        )
    if values.get("mesh") and not values.get("local_steps"):
        found.append(
            "Without local time stepping every tile takes the smallest cell's step: fewer cells, little time saved."
        )
    return found + _line_notes(values)


def _line_notes(values: dict) -> list[str]:
    """Each mesh line whose sizes move, so that nobody starts a run on a size they did not get."""
    mesh = values.get("mesh")
    if not mesh or not mesh.get("lines"):
        return []
    finest = snap_dx(values.get("dx", 0.0), values.get("pixel", 0.0))
    found = []
    for line in mesh["lines"]:
        text = rounded_note(
            line.properties["name"], line.properties["near_dx"], line.properties["far_dx"], finest, mesh["coarse_dx"]
        )
        if text:
            found.append(text)
    return found


def merge_notes(job: dict, merged: dict, imported: dict | None = None) -> list[str]:
    """What the HMS import changed from the form, for the user to see before the run starts; and, given the import
    itself, what the form changed from it."""
    found = []
    asked, set_by_hms = job["run"]["duration_s"], merged["run"]["duration_s"]
    if asked != set_by_hms:
        found.append(
            f"The HMS control file sets {set_by_hms / SECONDS_PER_HOUR:g} h of simulated time, "
            f"not the {asked / SECONDS_PER_HOUR:g} h in the form."
        )
    if takes_hms_table(job.get("storm") or {}):
        found.append("The gridded rain is reduced by the area reduction table of the HMS project.")
    own = job.get("hydrology", {}).get("time_step_min")
    theirs = ((imported or {}).get("hydrology") or {}).get("time_step_min")
    if own is not None and theirs is not None and own != theirs:
        found.append(LUMPED_REPLACES.format(own=own, theirs=theirs))
    return found


def _elevation(feature: Feature):
    constant = feature.properties.get("crest_z")
    return constant if constant is not None else feature.vertex_z()


def _object(kind: str, feature: Feature) -> dict:
    entry = {"kind": kind, "coordinates": feature.xy()}
    if feature.properties.get("name"):
        entry["name"] = str(feature.properties["name"])
    constant = feature.properties.get("crest_z")
    if constant is not None:
        entry["z_constant"] = constant
    elif feature.vertex_z() is not None:
        entry["z"] = feature.vertex_z()
    for key in ("coefficient", "length"):
        if feature.properties.get(key) is not None:
            entry[key] = feature.properties[key]
    own = delineate_field(feature.properties.get("delineate"))
    if own is not None:  # the feature's own tick for the basin's delineation (W73)
        entry["delineate"] = own
    return entry


def _boundary(feature: Feature) -> dict:
    kind = str(feature.properties["kind"]).strip().lower()
    entry = {"kind": kind, "coordinates": feature.xy()}
    value = feature.properties.get("value")
    if kind == "stage" and value is not None:
        entry["stage"] = value
    elif kind == "normal" and value is not None:
        entry["slope"] = value
    elif kind == "flow":  # HEC-RAS's Flow Hydrograph line: the engine shares it by normal depth (W61)
        if feature.properties.get("flows"):  # typed at a step in the dock (W101 item 3)
            entry["flow"] = {"step_s": feature.properties["step_s"], "flows": list(feature.properties["flows"])}
        else:
            entry["flow"] = {"file": feature.properties.get("file")}
        if feature.properties.get("slope") is not None:
            entry["flow"]["slope"] = feature.properties["slope"]
        for key in ("momentum", "direction"):  # W70's two, written only where the table moved them off the default
            if feature.properties.get(key) is not None:
                entry["flow"][key] = feature.properties[key]
    return entry


def boundary_problems(values: dict) -> list[str]:
    """A flow line with no hydrograph file stops the run."""
    lines = values.get("boundaries") or []
    kinds = [getattr(f, "properties", {}) for f in lines]
    missing = [n for n, p in enumerate(kinds, start=1) if p.get("kind") == "flow" and not p.get("file") and not p.get("flows")]
    found = [
        f"Boundary line {n}: a typed hydrograph needs a step above zero and two flows at least, none below zero."
        for n, p in enumerate(kinds, start=1)
        if p.get("flows") is not None and (len(p["flows"]) < 2 or p.get("step_s", 0.0) <= 0.0 or min(p["flows"]) < 0.0)
    ]
    if not missing:
        return found
    return found + [
        f"Boundary line {', '.join(map(str, missing))}: a flow line needs its hydrograph, a file (CSV or DSS) or a table "
        "typed at a step, in the table."
    ]


def _design_outputs(features: list[Feature]) -> dict:
    points = []
    lines = []
    for index, feature in enumerate(features):
        if feature.kind == "Point":
            x, y = feature.coordinates[:2]
            points.append({"name": feature.name(index), "x": x, "y": y})
        else:
            entry = {"name": feature.name(index), "coordinates": feature.xy()}
            area = line_area(feature)
            if area is not None:  # only when a field gives one: an old job stays the job it was
                entry[AREA_KEY] = area
            lines.append(entry)
    return {"points": points, "lines": lines}


def build_job(values: dict, out_dir: Path | str) -> dict:
    """The job dict; every vector layer lands in ``inputs/`` as GeoJSON, and every path is absolute."""
    out = Path(out_dir).resolve()
    inputs = out / INPUTS_DIR
    crs = values["crs"]
    job = {
        "project": {"name": values.get("name") or out.name},
        "grid": {
            "dx": snap_dx(values["dx"], values.get("pixel", 0.0)),
            "cache_dir": str(out.parent / CACHE_DIR),
        },
        "terrain": {
            "dem": str(Path(values["dem"]).resolve()),
            "manning": values["manning"],
            "objects": [],
        },
        "hydrology": {},
        "boundaries": [],
        "outputs": {},
        "run": {"duration_s": values["duration_h"] * SECONDS_PER_HOUR},
    }
    if values.get("backend"):  # only a choice away from the engine's default: an old job stays the job it was
        job["run"]["backend"] = values["backend"]
    if values.get("model_type"):  # only when a type was chosen on the start page (W99): the same
        job["run"]["model_type"] = values["model_type"]
    if values.get("domain"):
        job["grid"]["domain"] = str(write_geojson(inputs / "domain.geojson", values["domain"], crs))
    elif values.get("extent"):
        job["grid"]["extent"] = list(values["extent"])
    for key in ("manning_raster", "cn_raster"):
        if values.get(key):
            job["terrain"][key] = str(Path(values[key]).resolve())
    rough = roughness_job(values.get("roughness"))
    if rough is not None:  # squares and aligned apart, or land-use classes (W101 item 2): one value and a grid stay
        job["terrain"]["roughness"] = rough  # terrain.manning and terrain.manning_raster, as the dock always wrote them
    override = cn_job(values.get("cn_override"))
    if override is not None:
        job["hydrology"]["cn_override"] = override
    if values.get("fill_pits"):  # only a tick away from the engine's default: an old job stays the job it was
        job["terrain"]["fill_pits"] = True
    if values.get("exclude_lumped"):  # the same
        job["grid"]["exclude_lumped"] = True
    if values.get("lumped_entry") == "network":  # the same: the outlets are the engine's default
        job["hydrology"]["lumped_entry"] = "network"
    if values.get("lumped_only"):
        job["run"]["lumped_only"] = True
        if values.get("arf_by_element"):
            job["hydrology"]["arf_by_element"] = True
    if values.get("curve_number"):
        job["hydrology"]["curve_number"] = values["curve_number"]
    if values.get("inflows"):  # W103: the point inflows of lumped elements, only when there are rows
        job["hydrology"]["inflows"] = inflow_jobs(values["inflows"])
    if values.get("last_points") is not None:  # W105: only off the engine's default, every dam
        job["hydrology"]["last_points"] = list(values["last_points"])
    if values.get("reach_routing"):
        job["hydrology"]["reach_routing"] = values["reach_routing"]
    if values.get("basin") and values.get("reach_manning_n"):  # W106: the generated reaches' n, written when given
        job["hydrology"]["reach_manning_n"] = values["reach_manning_n"]
    if values.get("basin") and values.get("reach_manning"):
        job["hydrology"]["reach_manning"] = dict(values["reach_manning"])
    if values.get("reach_routing") == "muskingum" and values.get("muskingum"):  # the reach table's rows (W89)
        job["hydrology"]["muskingum"] = [dict(row) for row in values["muskingum"]]
    gauges = values.get("gauges") or {}
    if _uses_gauges(values):
        job["storm"] = rain_storm(gauges.get("rows") or [], gauges.get("settings") or {})
    elif values.get("storm"):
        job["storm"], tables = _reduced(values, storm_job(values["storm"]))  # the Area reduction, Data tables (W101)
        if tables:
            job["data_tables"] = tables
    elif not values.get("hms"):
        hours = values["rain_hours"]
        job["storm"] = {
            "kind": "uniform",
            "depth_mm": values["rain_mm_h"] * hours,
            "duration_min": hours * MINUTES_PER_HOUR,
        }
    for kind, features in values.get("structures", {}).items():
        if features:
            write_geojson(inputs / f"{kind}.geojson", features, crs)
            job["terrain"]["objects"].extend(
                _shaped(kind, n, feature, inputs) if kind in SHAPED_KINDS else _object(kind, feature)
                for n, feature in enumerate(features)
            )
    if values.get("dam_levels"):
        job["dam_levels"] = values["dam_levels"]
    if values.get("breach_rows"):
        job["breaches"] = breach_jobs(values["breach_rows"])
    if values.get("initial_points"):  # W101 item 3: levels from points (W96)
        job["initial_points"] = [dict(point) for point in values["initial_points"]]
    if values.get("initial_water"):
        write_geojson(inputs / "initial_water.geojson", values["initial_water"], crs)
        job["initial_levels"] = initial_water(values["initial_water"])
    if values.get("boundaries"):
        write_geojson(inputs / "boundaries.geojson", values["boundaries"], crs)
        job["boundaries"] = [_boundary(feature) for feature in values["boundaries"]]
    if values.get("design"):
        write_geojson(inputs / "design_points.geojson", values["design"], crs)
        job["outputs"] = _design_outputs(values["design"])
    settings = gauges.get("settings") or {}
    start = settings.get("observed_start", settings.get("start", ""))  # W77: the records' own start, else W54's one
    observed = observed_records(gauges.get("rows") or [], *_design_names(values), start)
    if observed:  # only when the table has flow or level gauges: an old job stays the job it was
        job["outputs"]["observed"] = observed
    if values.get("basin"):
        basin = values["basin"]
        job["hydrology"]["basin_json"] = str(Path(basin["json"]).resolve())
        job["hydrology"]["subbasins"] = [{"name": n, "mode": m} for n, m in basin.get("modes", {}).items()]
        job["basin"] = basin_settings(**basin["settings"])
    if values.get("handbacks"):
        write_geojson(inputs / "handbacks.geojson", values["handbacks"], crs)
        job["hydrology"]["handbacks"] = [
            {"name": f.properties["name"], "coordinates": f.xy(), "element": f.properties["element"]}
            for f in values["handbacks"]
        ]
    if values.get("transmission"):
        job["transmission"] = {"enabled": True, "rate_mm_h": values["transmission"]["rate_mm_h"]}
    if values.get("map_every_s") is not None:
        job["outputs"]["map_every_s"] = values["map_every_s"]
    if values.get("series_every_s") is not None:  # only moved off the engine's default (W99): an old job stays itself
        job["outputs"]["series_every_s"] = values["series_every_s"]
    if values.get("lumped_step_min") is not None:  # the same
        job["hydrology"]["time_step_min"] = values["lumped_step_min"]
    if values.get("pixels") is False:
        job["outputs"]["pixels"] = {"enabled": False}
    elif values.get("smooth") is not None:  # only a choice away from the engine's default
        job["outputs"]["smooth"] = {"enabled": bool(values["smooth"])}
    if values.get("pixels") is not False:  # his item 7 (W101): only what was set: an old job stays the job it was
        chosen = {"pixel_m": values.get("map_pixel"), "dv_raster": True if values.get("dv_raster") else None}
        chosen = {key: value for key, value in chosen.items() if value is not None}
        if chosen:
            job["outputs"]["pixels"] = {**job["outputs"].get("pixels", {}), **chosen}
    if values.get("map_threshold") is not None:  # his one depth threshold for every map (W101)
        floor = values["map_threshold"]
        floors = {"depth_floor": floor, "hazard_depth_floor": floor, "cell_depth_floor": floor}
        job["outputs"]["pixels"] = {**job["outputs"].get("pixels", {}), **floors}
    if values.get("terrain_map"):
        job["outputs"]["terrain_map"] = True
    if values.get("step_limiter"):
        job["outputs"]["step_limiter"] = STEP_LIMITER_ON
    if values.get("local_steps"):
        job["numerics"] = {"local_time_stepping": True}
    if values.get("numerics"):  # the 2D step: a fixed one, or what was moved off the engine's defaults (W99)
        job["numerics"] = {**job.get("numerics", {}), **values["numerics"]}
    if values.get("study"):  # the depth-area study's job only: a run never carries one
        job["arf"] = values["study"]
    if values.get("mesh"):
        job["mesh"] = _mesh(values["mesh"])
        if values["mesh"].get("lines"):
            write_geojson(inputs / "mesh_lines.geojson", values["mesh"]["lines"], crs)
    if values.get("strips"):
        strips = values["strips"]
        job["strips"] = {
            "enabled": True,
            "banks": str(Path(strips["banks"]).resolve()),
            **{key: strips[key] for key in STRIPS_KEYS if key in strips},
        }
        if strips.get("generator") == "centres":  # only off the engine's default: an old job stays the job it was
            job["strips"]["generator"] = "centres"
        if strips.get("gorge_rows"):  # rows across a narrow gorge (W52), the centre mesh only (W101 item 4)
            job["strips"]["gorge_rows"] = int(strips["gorge_rows"])
    if values.get("stream_km2") is not None and "mesh" not in job:  # Suggest's streams without the quadtree (W101)
        job["mesh"] = {"stream_area_mid_km2": values["stream_km2"]}
    if values.get("breaklines"):
        job["breaklines"] = _breaklines(values["breaklines"])
    return job


def _breaklines(settings: dict) -> dict:
    """The Suggest settings as the job carries them: the depth map only when a raster layer with a file was chosen."""
    out = {key: value for key, value in settings.items() if key in BREAK_KEYS and value is not None}
    if out.get("bank_depth_map"):
        out["bank_depth_map"] = str(Path(out["bank_depth_map"]).resolve())
    else:
        out.pop("bank_depth_map", None)
    return out


def _mesh(mesh: dict) -> dict:
    out = {
        "enabled": True,
        "coarse_dx": mesh["coarse_dx"],
        "stream_area_fine_km2": mesh["fine_km2"],
        "stream_area_mid_km2": mesh["mid_km2"],
        "zones": [
            {"coordinates": zone.coordinates[0], "dx": _zone_dx(zone)} for zone in mesh.get("zones", [])
        ],
    }
    if mesh.get("lines"):
        out["lines"] = [{**line.properties, "coordinates": line.xy()} for line in mesh["lines"]]
    return out


def preview_job(values: dict, out_dir: Path | str) -> dict:
    """A job with the terrain and its objects only: a preview needs no water."""
    blank = {"hms": values.get("hms") or True, "boundaries": [], "design": [], "terrain_map": False}
    job = build_job({**values, **blank}, out_dir)
    job.pop("storm", None)
    job["run"] = {}
    return job


def domain_job(values: dict, out_dir: Path | str) -> dict:
    """What ``wadi2d domain`` reads (W101 item 5): the terrain and its objects, the boundary lines as the edges kept as
    drawn (their place only, so a flow line with no hydrograph yet does not stop it), and the generated basin's
    delineation settings when the model has them, so the domain and the basin read the same streams (W97)."""
    job = preview_job({**values, "basin": None, "handbacks": [], "transmission": None}, out_dir)  # no water
    lines = [f.xy() for f in values.get("boundaries") or [] if getattr(f, "kind", "LineString") == "LineString"]
    job["boundaries"] = [{"kind": "free", "coordinates": xy} for xy in lines if len(xy) > 1]
    basin = values.get("basin") or {}
    if basin.get("settings"):
        job["basin"] = basin_settings(**basin["settings"])
        apply_delineate(job["terrain"]["objects"], basin.get("delineate"))
    return job


def basin_job(values: dict, out_dir: Path | str) -> dict:
    """What ``wadi2d basin`` reads: the terrain, its dams, the CN and Manning, the design lines and points as pour
    points, and the settings of the box. No water, no basin of its own."""
    settings = values["basin"]["settings"]
    blank = {"hms": True, "basin": None, "handbacks": [], "transmission": None, "boundaries": [], "terrain_map": False}
    job = build_job({**values, **blank}, out_dir)
    job.pop("storm", None)
    job["run"] = {}
    job["basin"] = basin_settings(**settings)
    apply_delineate(job["terrain"]["objects"], values["basin"].get("delineate"))  # W73: the box's ticks
    if values.get("reach_manning_n"):  # W106: the reaches are generated with the n the runs give them
        job["hydrology"]["reach_manning_n"] = values["reach_manning_n"]
    return job


def _shaped(kind: str, index: int, feature: Feature, inputs: Path) -> dict:
    """A shaped object; its section table is copied beside the job, so the run folder holds what made it."""
    table = feature.properties.get(TABLE)
    if not table:
        return shaped_object(kind, feature)
    inputs.mkdir(parents=True, exist_ok=True)
    copied = inputs / f"{kind}_{index + 1}_{Path(table).name}"
    shutil.copy2(table, copied)
    return shaped_object(kind, feature, copied.resolve())


def hms_import_args(hms: dict, out_file: Path | str) -> list[str]:
    """The arguments of ``wadi2d hms-import``, with the files named as they sit in the folder."""
    args = ["hms-import", str(Path(hms["folder"]).resolve())]
    for key in HMS_KEYS:
        args += [f"--{key}", hms[key]]
    return [*args, "--out", str(out_file)]


def merge_hms(job: dict, imported: dict, hms: dict) -> dict:
    """The hydrology and storm of an imported HMS project, inside the job the dock built.

    The import owns the network and the simulated time, and the storm unless the dock's Storm section replaced it.
    The dock owns the mode of each subbasin, and what it sets of each one's storm area, entry and outlet (W103).
    """
    merged = {**job}
    for key in ("storm", "arf"):
        if key in imported and key not in job:
            merged[key] = imported[key]
    if takes_hms_table(merged.get("storm") or {}):
        table = (imported.get("storm") or {}).get("arf")
        if not table:
            raise ValueError(NO_HMS_TABLE)
        merged["storm"] = {**merged["storm"], "arf": table}
    if "duration_s" in imported.get("run", {}):
        merged["run"] = {**job["run"], "duration_s": imported["run"]["duration_s"]}
    hydrology = {**imported.get("hydrology", {}), **job.get("hydrology", {})}
    modes = hms.get("modes", {})
    known = {entry["name"]: entry for entry in hydrology.get("subbasins", [])}
    hydrology["subbasins"] = [
        {**known.get(name, {}), "name": name, "mode": mode} for name, mode in modes.items()
    ] or list(known.values())
    if hms.get("edits"):  # only what was set: a model with none writes the job it wrote
        hydrology["subbasins"] = apply_edits(hydrology["subbasins"], hms["edits"])
    merged["hydrology"] = hydrology
    return merged


def write_job(job: dict, out_dir: Path | str) -> Path:
    path = Path(out_dir) / JOB_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(job, indent=2), encoding="utf-8")
    return path


def hms_files(folder: Path | str) -> dict[str, list[str]]:
    """The basin, meteorologic and control files of an HMS project folder, by name."""
    root = Path(folder)
    return {key: sorted(path.name for path in root.glob(f"*.{key}")) for key in HMS_KEYS}


def hms_subbasins(basin_file: Path | str) -> list[str]:
    """The subbasin names of a ``.basin`` file, in file order."""
    text = Path(basin_file).read_text(encoding="utf-8", errors="replace")
    return re.findall(r"^Subbasin:\s*(.+?)\s*$", text, re.MULTILINE)


# QGIS adapters: from here down the imports need QGIS.


def raster_path(layer) -> str | None:
    """The file behind a raster layer, or None when it has no file."""
    if layer is None:
        return None
    path = layer.source().split("|")[0]
    return path if Path(path).is_file() else None


def finite(coordinates) -> bool:
    """Every number in nested coordinates is a real number; a failed reprojection gives infinities."""
    if isinstance(coordinates, (list, tuple)):
        return all(finite(item) for item in coordinates)
    return math.isfinite(coordinates)


def layer_features(layer, crs, fields: dict[str, str] | None = None, with_id: bool = False) -> list[Feature]:
    """Every feature of a layer, one per part, reprojected to ``crs``; ``fields`` maps property to field.

    ``with_id`` adds the feature id as the property ``fid``, for a table that keeps its rows by feature.
    """
    from qgis.core import QgsCoordinateTransform, QgsGeometry, QgsProject, QgsWkbTypes

    transform = QgsCoordinateTransform(layer.crs(), crs, QgsProject.instance())
    features = []
    for source in layer.getFeatures():
        geometry = QgsGeometry(source.geometry())
        if geometry.isNull() or geometry.isEmpty():
            continue
        geometry.transform(transform)
        properties = {key: _plain(source[name]) for key, name in (fields or {}).items() if name}
        if with_id:
            properties["fid"] = source.id()
        for part in geometry.asGeometryCollection():
            kind = part.type()
            if kind == QgsWkbTypes.PointGeometry:
                point = part.asPoint()
                features.append(Feature("Point", [point.x(), point.y()], properties))
            elif kind == QgsWkbTypes.LineGeometry:
                vertices = [_vertex(vertex) for vertex in part.vertices()]
                features.append(Feature("LineString", vertices, properties))
            elif kind == QgsWkbTypes.PolygonGeometry:
                rings = [[[p.x(), p.y()] for p in ring] for ring in part.asPolygon()]
                features.append(Feature("Polygon", rings, properties))
    if not all(finite(feature.coordinates) for feature in features):
        raise LayerError(
            f'Layer "{layer.name()}" lands nowhere in the DEM coordinate system. Check the CRS set on that '
            "layer: a GeoJSON that names no CRS is read as degrees."
        )
    return features


def _vertex(point) -> list[float]:
    return [point.x(), point.y(), point.z()] if point.is3D() else [point.x(), point.y()]


def _plain(value):
    """A field value as a number, text or None; QGIS's NULL is not a Python None."""
    if isinstance(value, str):
        text = value.strip()
        try:
            return float(text)
        except ValueError:
            return text or None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def map_extent(canvas, crs, limit) -> tuple[float, float, float, float]:
    """The map's extent in ``crs``, kept inside ``limit``; the whole limit when the map is elsewhere."""
    from qgis.core import QgsCoordinateTransform, QgsProject

    source = canvas.mapSettings().destinationCrs()
    box = QgsCoordinateTransform(source, crs, QgsProject.instance()).transformBoundingBox(canvas.extent())
    clipped = box.intersect(limit)
    box = limit if clipped.isEmpty() else clipped
    return box.xMinimum(), box.yMinimum(), box.xMaximum(), box.yMaximum()
