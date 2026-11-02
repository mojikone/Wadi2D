"""What the engine was given, as map layers: subbasins, inflows, open boundaries, design lines, reaches.

They go into the run's GeoPackage, so a map sheet can be made from the run folder alone, long after the inputs moved.
"""

from __future__ import annotations

from collections import defaultdict

import shapely

from wadi2d.config.schema import RunConfig
from wadi2d.forcing import load_polygons
from wadi2d.hms import sqlite as hms_sqlite
from wadi2d.io.geopackage import LINES, POINTS, VectorLayer
from wadi2d.products.smooth_geometry import chaikin_rings

SUBBASIN_LAYER = "subbasins"
INFLOW_LAYER = "inflows"
BOUNDARY_LAYER = "boundaries"
LINE_LAYER = "design_lines"
REACH_LAYER = "reaches"
ROUND = 1
"""Decimals of a coordinate when two inflows are the same point, m."""
SUBBASIN_CHAIKIN = 2
"""Corner-cutting passes on a subbasin outline: HMS traces them along raster cells. The polygon that masks rain is not touched."""


def subbasins(cfg: RunConfig, crs: str) -> list[VectorLayer]:
    modes = {s.name: s.mode for s in cfg.hydrology.subbasins}
    polygons = load_polygons(cfg.hydrology, crs)
    if not polygons:
        return []
    rows = []
    for name, shape in polygons.items():
        mode = modes.get(name, "2d")
        label = f"{name}\nlumped" if mode == "lumped" else f"{name}\n2D"
        rows.append((name, mode, float(shapely.area(shape)) / 1e6, label))
    return [
        VectorLayer(
            SUBBASIN_LAYER,
            {"name": str, "mode": str, "area_km2": float, "label": str},
            rows,
            [chaikin_rings(shape, SUBBASIN_CHAIKIN) for shape in polygons.values()],
        )
    ]


def inflows(cfg: RunConfig) -> list[VectorLayer]:
    """One point per entry, naming every hydrograph that enters there."""
    points: dict[tuple[float, float], list[str]] = defaultdict(list)
    for sub in cfg.hydrology.subbasins:
        if sub.mode == "lumped" and sub.outlet is not None:
            points[(round(sub.outlet[0], ROUND), round(sub.outlet[1], ROUND))].append(sub.name)
    for inflow in cfg.hydrology.inflows:
        points[(round(inflow.x, ROUND), round(inflow.y, ROUND))].append(inflow.name)
    if not points:
        return []
    rows = [(", ".join(names), "Inflow " + ", ".join(names)) for names in points.values()]
    shapes = [shapely.Point(xy) for xy in points]
    return [VectorLayer(INFLOW_LAYER, {"names": str, "label": str}, rows, shapes, POINTS)]


def _line(coordinates) -> shapely.Geometry:
    return shapely.MultiLineString([coordinates])


def boundaries(cfg: RunConfig) -> list[VectorLayer]:
    if not cfg.boundaries:
        return []
    rows = [(b.kind, f"Open boundary {n}") for n, b in enumerate(cfg.boundaries, start=1)]
    shapes = [_line(b.coordinates) for b in cfg.boundaries]
    return [VectorLayer(BOUNDARY_LAYER, {"kind": str, "label": str}, rows, shapes, LINES)]


def design_lines(cfg: RunConfig) -> list[VectorLayer]:
    lines = cfg.outputs.lines
    if not lines:
        return []
    shapes = [_line(line.coordinates) for line in lines]
    return [VectorLayer(LINE_LAYER, {"label": str}, [(line.name,) for line in lines], shapes, LINES)]


def reaches(cfg: RunConfig) -> list[VectorLayer]:
    path = cfg.hydrology.hms_sqlite
    if path is None:
        return []
    lines = [line for line in hms_sqlite.reach_lines(path) if line.length is not None]
    if not lines:
        return []
    shapes = [line.shape() for line in lines]
    return [VectorLayer(REACH_LAYER, {"label": str}, [(line.name,) for line in lines], shapes, LINES)]


def setup_layers(cfg: RunConfig, crs: str) -> list[VectorLayer]:
    return subbasins(cfg, crs) + inflows(cfg) + boundaries(cfg) + design_lines(cfg) + reaches(cfg)
