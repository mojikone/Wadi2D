# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A job the dock did not write, read into the dock (W101, his item of 2026-11-16). No Qt and no QGIS here.

A job written by a script or the engine holds its lines and polygons inline, and its run folder may keep only
``config.resolved.json``. This module finds the job of a folder, turns the geometry it holds inline into layers for a
GeoPackage beside the model (:func:`inline_layers`), chooses the HMS files the dock's HMS route needs, and compares the
job the refilled dock writes with the original, field by field, after both have their defaults filled in or taken out
alike, so what the dock cannot hold yet is listed by section and nothing is lost in silence (:func:`not_held`).

Interface: :func:`find_job`, :func:`inline_layers`, :func:`layer_source`, :func:`hms_choice`, :func:`differences`,
:func:`strip_defaults`, :func:`not_held`, :func:`held_words`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .protocol import CONFIG_FILE, JOB_FILE

GPKG_NAME = "imported_inputs.gpkg"
"""The GeoPackage of an imported job's lines and polygons, written beside the model."""
TOLERANCE = 0.51e-3
"""Coordinates and numbers compared to the millimetre: a layer may hold what a job held to the last digit or not."""
IGNORED = ("project", "grid.cache_dir", "run.model_type", "strips.banks")
"""What says where or how a job was written, not what it does. ``strips.banks`` is the same file through a layer."""
SECTION_OF = (
    ("grid.domain", "Terrain"), ("grid.extent", "Terrain"), ("grid.exclude", "Hydrology"), ("grid", "Terrain"),
    ("terrain.objects", "Structures"), ("terrain", "Terrain"), ("mesh", "Mesh"), ("strips", "Mesh"),
    ("breaklines", "Mesh"), ("tables", "Engine settings"), ("numerics", "Simulation"), ("storm.area_reduction", "Area reduction"),
    ("storm.arf", "Area reduction"), ("storm.storm_area_km2", "Area reduction"), ("storm.arf_factor", "Area reduction"),
    ("storm", "Storm"), ("data_tables", "Data tables"), ("hydrology", "Hydrology"), ("transmission", "Hydrology"),
    ("boundaries", "Boundaries"), ("initial", "Structures"), ("dam_levels", "Structures"), ("breaches", "Structures"),
    ("outputs.lines", "Points"), ("outputs.points", "Points"), ("outputs.observed", "Gauges"),
    ("outputs.pixels", "Run"), ("outputs.smooth", "Run"), ("outputs.step_limiter", "Run"), ("outputs", "Simulation"),
    ("run", "Simulation"), ("arf", "Depth-area study"), ("basin", "Hydrology"),
)  # fmt: skip
"""The dock section a part of the job belongs to, the longest prefix first."""
PLAIN_KINDS = {"crest_line": ("crest_z",), "wall": (), "spillway": ("crest_z", "coefficient", "length"), "burn_line": ("crest_z",)}
DEPTH_LINE = re.compile(r"^\s*Storm Depth:\s*([0-9.]+)", re.MULTILINE)


def find_job(folder: Path | str) -> Path | None:
    """The job of a run folder: its ``job.json``, else the ``config.resolved.json`` the engine wrote."""
    root = Path(folder)
    for name in (JOB_FILE, CONFIG_FILE):
        if (root / name).is_file():
            return root / name
    return None


def layer_source(gpkg: Path | str, name: str) -> str:
    return f"{Path(gpkg)}|layername={name}"


def _xy(coordinates) -> list:
    return [list(point) for point in coordinates]


def inline_layers(job: dict) -> dict:
    """The lines, points and polygons a job holds inline, as layers: ``{name: {"geometry", "fields", "features"}}``,
    a feature ``(coordinates, properties)``. Fields hold what the dock's sections read from a layer."""
    layers: dict = {}
    lines = [b for b in job.get("boundaries") or [] if b.get("coordinates")]
    if lines:
        features = []
        for b in lines:
            props = {"kind": b.get("kind")}
            value = b.get("stage") if b.get("kind") == "stage" else b.get("slope") if b.get("kind") == "normal" else None
            if value is not None:
                props["value"] = value
            flow = b.get("flow") or {}
            if flow.get("file"):
                props["file"] = flow["file"]
            features.append((_xy(b["coordinates"]), props))
        layers["boundaries"] = {"geometry": "LineString", "fields": {"kind": str, "value": float, "file": str}, "features": features}
    objects = (job.get("terrain") or {}).get("objects") or []
    for kind, keys in PLAIN_KINDS.items():
        found = [o for o in objects if o.get("kind") == kind]
        if not found:
            continue
        features = []
        for obj in found:
            props = {"name": obj.get("name")}
            if "crest_z" in keys and obj.get("z_constant") is not None:
                props["crest_z"] = obj["z_constant"]
            for key in ("coefficient", "length"):
                if key in keys and obj.get(key) is not None:
                    props[key] = obj[key]
            coordinates = obj["coordinates"]
            if obj.get("z") is not None:  # a profile given per vertex: a line with Z
                coordinates = [[x, y, z] for (x, y), z in zip(coordinates, obj["z"], strict=False)]
            features.append((_xy(coordinates), props))
        fields = {"name": str, **{key: float for key in keys}}
        layers[kind] = {"geometry": "LineString", "fields": fields, "features": features}
    outputs = job.get("outputs") or {}
    design_lines = [(_xy(line["coordinates"]), {"name": line.get("name"), "drainage_area_km2": line.get("drainage_area_km2")}) for line in outputs.get("lines") or []]
    design_points = [([p["x"], p["y"]], {"name": p.get("name")}) for p in outputs.get("points") or []]
    if design_lines:
        layers["design_lines"] = {"geometry": "LineString", "fields": {"name": str, "drainage_area_km2": float}, "features": design_lines}
    if design_points:
        layers["design_points"] = {"geometry": "Point", "fields": {"name": str}, "features": design_points}
    points = job.get("initial_points") or []
    if points:
        layers["initial_points"] = {
            "geometry": "Point", "fields": {"name": str, "level": float},
            "features": [([p["x"], p["y"]], {"name": p.get("name"), "level": p.get("level")}) for p in points],
        }  # fmt: skip
    ponds = [lv for lv in job.get("initial_levels") or [] if lv.get("coordinates")]
    if ponds:
        layers["initial_water"] = {
            "geometry": "Polygon", "fields": {"level": float},
            "features": [([_xy(lv["coordinates"])], {"level": lv.get("level")}) for lv in ponds],
        }  # fmt: skip
    return layers


def hms_choice(folder: Path | str, job: dict) -> dict:
    """The meteorologic and control files of an HMS folder the dock's HMS route needs and a job does not name: the
    only control file, and the met file whose storm depth is the job's (both say so in words when they guess)."""
    root = Path(folder)
    found, words = {}, []
    controls = sorted(path.name for path in root.glob("*.control"))
    if len(controls) == 1:
        found["control"] = controls[0]
    elif controls:
        words.append(f"the HMS folder holds {len(controls)} control files and the job names none: choose one in Hydrology")
    depth = (job.get("storm") or {}).get("depth_mm")
    for path in sorted(root.glob("*.met")):
        match = DEPTH_LINE.search(path.read_text(encoding="utf-8", errors="replace"))
        if match and depth and abs(float(match.group(1)) - float(depth)) < 1e-6:
            found["met"] = path.name
            words.append(
                f"the meteorologic file {path.name} was chosen, its storm depth the job's; the rain itself is the "
                "Storm section's, as the job's own"
            )
            break
    else:
        if (job.get("hydrology") or {}).get("hms_basin"):
            words.append("no meteorologic file of the HMS folder has the job's storm depth: choose one in Hydrology")
    return {"files": found, "words": words}


def _alike(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= TOLERANCE
    return a == b


def differences(a, b, path: str = "") -> list[str]:
    """The paths under which two jobs differ, a list's position written ``[]`` so that 104 subbasins with one key
    each are one path; a list of another length is one difference."""
    if (isinstance(a, dict) and b is None) or (a is None and isinstance(b, dict)):  # a part one side leaves out
        a, b = a or {}, b or {}
    if isinstance(a, dict) and isinstance(b, dict):
        found: list[str] = []
        for key in sorted(set(a) | set(b)):
            found += differences(a.get(key), b.get(key), f"{path}.{key}" if path else key)
        return list(dict.fromkeys(found))
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        found = []
        for x, y in zip(a, b, strict=True):
            found += differences(x, y, f"{path}[]")
        return list(dict.fromkeys(found))
    return [] if _alike(a, b) else [path]


def strip_defaults(value, schema, path: str = ""):
    """A job with every value its schema's default would give taken out, at every depth: what a job says, not how
    fully it was written out. ``schema`` is the dock's :class:`SchemaView`."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            here = f"{path}.{key}" if path else key
            if item is None:
                continue
            node = schema.field(here)
            if node and "default" in node and _same(node["default"], item):
                continue
            stripped = strip_defaults(item, schema, here)
            if stripped == {} and isinstance(item, dict):
                continue
            out[key] = stripped
        return out
    if isinstance(value, list):
        return [strip_defaults(item, schema, path) for item in value]
    return value


def _same(default, value) -> bool:
    if isinstance(default, dict) or isinstance(value, dict):
        return default == value
    if isinstance(default, list) or isinstance(value, list):
        return default == value
    return _alike(default, value)


def _ignored(path: str) -> bool:
    return any(path == item or path.startswith(f"{item}.") for item in IGNORED)


def section_of(path: str) -> str:
    return next((name for prefix, name in SECTION_OF if path == prefix or path.startswith((f"{prefix}.", f"{prefix}[", prefix))), "Other")


def not_held(original: dict, rebuilt: dict) -> dict[str, list[str]]:
    """What differs between the original job and the refilled dock's, by dock section; both with their defaults
    filled in, or both stripped of them, by the caller."""
    found: dict[str, list[str]] = {}
    for path in differences(in_phase_order(original), in_phase_order(rebuilt)):
        if not _ignored(path):
            found.setdefault(section_of(path), []).append(path)
    return found


def held_words(found: dict[str, list[str]]) -> list[str]:
    """One line a section: what of the job the dock cannot hold yet."""
    return [f"{section}: the dock cannot hold yet {', '.join(paths)}" for section, paths in found.items()]


PHASES = {"spillway": 1, "wall": 2}
"""The engine applies terrain objects by phase, a stable sort (``wadi2d/terrain/objects.py``): crest lines and the other
kinds 0, spillways 1, walls 2. Two jobs that list the same objects in another order of kinds are one job."""


def in_phase_order(job: dict) -> dict:
    """The job with its terrain objects in the order the engine applies them."""
    objects = (job.get("terrain") or {}).get("objects")
    if not objects:
        return job
    ordered = sorted(objects, key=lambda obj: PHASES.get(obj.get("kind"), 0))
    return {**job, "terrain": {**job["terrain"], "objects": ordered}}


def read_job(path: Path | str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
