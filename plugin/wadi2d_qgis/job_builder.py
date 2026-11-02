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

from .protocol import CACHE_DIR, INPUTS_DIR, JOB_FILE
from .shaped import SHAPED_KINDS, TABLE, shaped_object, shaped_problems

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
MESH_ENABLED = "mesh.enabled"
MESH_COARSE = "mesh.coarse_dx"
MESH_FINE_AREA = "mesh.stream_area_fine_km2"
MESH_MID_AREA = "mesh.stream_area_mid_km2"
MESH_ZONE_DX = "mesh.zones.dx"
LOCAL_STEPS = "numerics.local_time_stepping"
ZONE_DX_FIELD = "dx"

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
    rain = values.get("rain_mm_h", 0.0)
    if not hms and rain <= 0.0:
        found.append("Set the rain, or choose an HMS project.")
    if not hms and rain > 0.0 and values.get("rain_hours", 0.0) <= 0.0:
        found.append("Set how many hours the rain lasts.")
    if hms and not all(hms.get(key) for key in HMS_KEYS):
        found.append("The HMS folder needs a basin, a meteorologic and a control file.")
    found.extend(_structure_problems(values.get("structures", {})))
    return found + _mesh_problems(values)


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
    if not values.get("hms") and values.get("rain_hours", 0.0) > values.get("duration_h", 0.0):
        found.append("The rain outlasts the simulated time, so the run ends while it is still raining.")
    if values.get("hms") and not values.get("curve_number") and not values.get("cn_raster"):
        found.append(
            "No curve number: rain on the 2D area outside the HMS subbasins runs off with no losses."
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
    return found


def merge_notes(job: dict, merged: dict) -> list[str]:
    """What the HMS import changed from the form, for the user to see before the run starts."""
    asked, set_by_hms = job["run"]["duration_s"], merged["run"]["duration_s"]
    if asked == set_by_hms:
        return []
    return [
        f"The HMS control file sets {set_by_hms / SECONDS_PER_HOUR:g} h of simulated time, "
        f"not the {asked / SECONDS_PER_HOUR:g} h in the form."
    ]


def _elevation(feature: Feature):
    constant = feature.properties.get("crest_z")
    return constant if constant is not None else feature.vertex_z()


def _object(kind: str, feature: Feature) -> dict:
    entry = {"kind": kind, "coordinates": feature.xy()}
    constant = feature.properties.get("crest_z")
    if constant is not None:
        entry["z_constant"] = constant
    elif feature.vertex_z() is not None:
        entry["z"] = feature.vertex_z()
    for key in ("coefficient", "length"):
        if feature.properties.get(key) is not None:
            entry[key] = feature.properties[key]
    return entry


def _boundary(feature: Feature) -> dict:
    kind = str(feature.properties["kind"]).strip().lower()
    entry = {"kind": kind, "coordinates": feature.xy()}
    value = feature.properties.get("value")
    if kind == "stage" and value is not None:
        entry["stage"] = value
    elif kind == "normal" and value is not None:
        entry["slope"] = value
    return entry


def _design_outputs(features: list[Feature]) -> dict:
    points = []
    lines = []
    for index, feature in enumerate(features):
        if feature.kind == "Point":
            x, y = feature.coordinates[:2]
            points.append({"name": feature.name(index), "x": x, "y": y})
        else:
            lines.append({"name": feature.name(index), "coordinates": feature.xy()})
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
    if values.get("domain"):
        job["grid"]["domain"] = str(write_geojson(inputs / "domain.geojson", values["domain"], crs))
    elif values.get("extent"):
        job["grid"]["extent"] = list(values["extent"])
    for key in ("manning_raster", "cn_raster"):
        if values.get(key):
            job["terrain"][key] = str(Path(values[key]).resolve())
    if values.get("curve_number"):
        job["hydrology"]["curve_number"] = values["curve_number"]
    if not values.get("hms"):
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
    if values.get("boundaries"):
        write_geojson(inputs / "boundaries.geojson", values["boundaries"], crs)
        job["boundaries"] = [_boundary(feature) for feature in values["boundaries"]]
    if values.get("design"):
        write_geojson(inputs / "design_points.geojson", values["design"], crs)
        job["outputs"] = _design_outputs(values["design"])
    if values.get("terrain_map"):
        job["outputs"]["terrain_map"] = True
    if values.get("local_steps"):
        job["numerics"] = {"local_time_stepping": True}
    if values.get("mesh"):
        job["mesh"] = _mesh(values["mesh"])
    return job


def _mesh(mesh: dict) -> dict:
    return {
        "enabled": True,
        "coarse_dx": mesh["coarse_dx"],
        "stream_area_fine_km2": mesh["fine_km2"],
        "stream_area_mid_km2": mesh["mid_km2"],
        "zones": [
            {"coordinates": zone.coordinates[0], "dx": _zone_dx(zone)} for zone in mesh.get("zones", [])
        ],
    }


def preview_job(values: dict, out_dir: Path | str) -> dict:
    """A job with the terrain and its objects only: a preview needs no water."""
    blank = {"hms": values.get("hms") or True, "boundaries": [], "design": [], "terrain_map": False}
    job = build_job({**values, **blank}, out_dir)
    job.pop("storm", None)
    job["run"] = {}
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

    The import owns the storm, the network and the simulated time. The dock owns the mode of each subbasin.
    """
    merged = {**job}
    for key in ("storm", "arf"):
        if key in imported:
            merged[key] = imported[key]
    if "duration_s" in imported.get("run", {}):
        merged["run"] = {**job["run"], "duration_s": imported["run"]["duration_s"]}
    hydrology = {**imported.get("hydrology", {}), **job.get("hydrology", {})}
    modes = hms.get("modes", {})
    known = {entry["name"]: entry for entry in hydrology.get("subbasins", [])}
    hydrology["subbasins"] = [
        {**known.get(name, {}), "name": name, "mode": mode} for name, mode in modes.items()
    ] or list(known.values())
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


def layer_features(layer, crs, fields: dict[str, str] | None = None) -> list[Feature]:
    """Every feature of a layer, one per part, reprojected to ``crs``; ``fields`` maps property to field."""
    from qgis.core import QgsCoordinateTransform, QgsGeometry, QgsProject, QgsWkbTypes

    transform = QgsCoordinateTransform(layer.crs(), crs, QgsProject.instance())
    features = []
    for source in layer.getFeatures():
        geometry = QgsGeometry(source.geometry())
        if geometry.isNull() or geometry.isEmpty():
            continue
        geometry.transform(transform)
        properties = {key: _plain(source[name]) for key, name in (fields or {}).items() if name}
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
