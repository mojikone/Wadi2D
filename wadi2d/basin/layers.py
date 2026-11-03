"""``basin.gpkg``: the map of a basin model. The numbers of record are in ``basin.json``; these columns only show them.

Interface: :func:`write_layers`.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np
import shapely
from rasterio import features

from wadi2d.basin.contract import JUNCTION, REACH, RESERVOIR, SUBBASIN, Element, value_of
from wadi2d.basin.delineate import Surface
from wadi2d.basin.elements import Built
from wadi2d.basin.kernels import NONE
from wadi2d.io.geopackage import LINES, POINTS, POLYGONS, VectorLayer, write_geopackage

SUBBASIN_COLUMNS = {
    "curve_number": float,
    "lag_minutes": float,
    "area_km2": float,
    "flow_length_m": float,
    "slope": float,
}
REACH_COLUMNS = {
    "length_m": float,
    "slope": float,
    "manning_n": float,
    "bottom_width_m": float,
    "side_slope": float,
}
NODE_COLUMNS = {"drainage_area_km2": float}


def _polygons(surface: Surface, label: np.ndarray) -> dict[int, shapely.Geometry]:
    """Each label's pixels as one exact geometry; 4-connected pieces stay parts of it.

    Not simplified: these polygons mask the rain under a lumped subbasin, so they must hold exactly the pixels its area
    counts. Simplified one by one they overlapped along shared edges, and a cell under two lumped polygons counted its rain
    twice (found by the rain-once check of `W27`); simplified as a coverage the edges still moved up to a pixel, and cells
    along them changed owner. The vertex count of a pixel staircase is small beside the raster it comes from.
    """
    grid = label.reshape(surface.shape).astype(np.int32)
    pieces: dict[int, list[shapely.Geometry]] = defaultdict(list)
    shapes = features.shapes(grid, mask=grid != NONE, connectivity=4, transform=surface.transform)
    for geometry, value in shapes:
        pieces[int(value)].append(shapely.geometry.shape(geometry))
    return {link: shapely.coverage_union_all(parts) for link, parts in pieces.items()}


def _layer(
    name: str, kind: str, elements: list[Element], columns: dict[str, type], shapes: list
) -> VectorLayer:
    head = {"name": str, "kind": str, "downstream": str, "missing": str}
    rows = [
        (
            e["name"],
            e["kind"],
            e["downstream"],
            ", ".join(e["missing"]),
            *(value_of(e, column) for column in columns),
        )
        for e in elements
    ]
    return VectorLayer(name, {**head, **columns}, rows, shapes, kind)


def write_layers(path: Path, surface: Surface, label: np.ndarray, built: Built) -> Path:
    """Write the three layers."""
    polygons = _polygons(surface, label)
    subbasins = [e for e in built.elements if e["kind"] == SUBBASIN]
    reaches = [e for e in built.elements if e["kind"] == REACH]
    nodes = [e for e in built.elements if e["kind"] in (JUNCTION, RESERVOIR)]
    layers = [
        _layer(
            "subbasins",
            POLYGONS,
            subbasins,
            SUBBASIN_COLUMNS,
            [polygons[built.links[e["name"]]] for e in subbasins],
        ),
        _layer(
            "reaches",
            LINES,
            reaches,
            REACH_COLUMNS,
            [shapely.simplify(built.lines[e["name"]], surface.pixel) for e in reaches],
        ),
        _layer("junctions", POINTS, nodes, NODE_COLUMNS, [shapely.Point(e["outlet"]) for e in nodes]),
    ]
    return write_geopackage(path, layers, surface.crs)
