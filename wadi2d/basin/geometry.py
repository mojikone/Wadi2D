"""The map of a basin model, read back: the layers of ``basin.gpkg`` by element name, in the job's CRS.

Read with the standard library, as the file was written: a second GDAL beside rasterio and CuPy is not an option on
Windows (see :mod:`wadi2d.io.geopackage`). The columns are not read; ``basin.json`` holds the numbers.

Interface: :func:`read_layer`, :func:`model_geometry`, :class:`ModelGeometry`.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import shapely
from rasterio.crs import CRS
from rasterio.warp import transform_geom

from wadi2d.basin.contract import Model

ENVELOPE_BYTES = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
"""Bytes of the envelope of a GeoPackage geometry blob, by the indicator in its flags."""
HEADER_BYTES = 8
"""'GP', version, flags, srs_id."""
SUBBASINS, REACHES, JUNCTIONS = "subbasins", "reaches", "junctions"


def _geometry(blob: bytes) -> shapely.Geometry:
    """The WKB behind the GeoPackage header."""
    if blob[:2] != b"GP":
        raise ValueError("not a GeoPackage geometry")
    flags = blob[3]
    envelope = ENVELOPE_BYTES[(flags >> 1) & 0x07]
    return shapely.from_wkb(blob[HEADER_BYTES + envelope :])


def _srs_wkt(db: sqlite3.Connection, layer: str) -> str | None:
    row = db.execute(
        "SELECT s.definition FROM gpkg_geometry_columns g JOIN gpkg_spatial_ref_sys s ON g.srs_id = s.srs_id "
        "WHERE g.table_name = ?",
        (layer,),
    ).fetchone()
    return None if row is None or row[0] in ("undefined",) else str(row[0])


def _moved(geometry: shapely.Geometry, source: str | None, target: str) -> shapely.Geometry:
    if not target or not source or CRS.from_user_input(source) == CRS.from_user_input(target):
        return geometry
    return shapely.geometry.shape(transform_geom(source, target, shapely.geometry.mapping(geometry)))


def read_layer(path: str | Path, layer: str, crs: str = "") -> dict[str, shapely.Geometry]:
    """Geometry by ``name`` of one layer, moved to ``crs`` when that is given and differs."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    uri = f"{source.resolve().as_uri()}?mode=ro"
    db = sqlite3.connect(uri, uri=True)
    try:
        system = _srs_wkt(db, layer)
        rows = db.execute(f'SELECT name, geom FROM "{layer}"').fetchall()
    finally:
        db.close()
    return {str(name): _moved(_geometry(geom), system, crs) for name, geom in rows}


@dataclass(frozen=True)
class ModelGeometry:
    """The three layers of a model, by element name."""

    subbasins: dict[str, shapely.Geometry]
    reaches: dict[str, shapely.Geometry]
    junctions: dict[str, shapely.Geometry]


def geometry_file(model: Model, model_path: str | Path) -> Path:
    """``basin.gpkg`` as the model names it, beside the model's file."""
    return Path(model_path).parent / model["geometry_file"]


def model_geometry(model: Model, model_path: str | Path, crs: str = "") -> ModelGeometry:
    """Every layer of a model's map."""
    path = geometry_file(model, model_path)
    return ModelGeometry(*(read_layer(path, layer, crs) for layer in (SUBBASINS, REACHES, JUNCTIONS)))


def first_direction(line: shapely.Geometry) -> tuple[float, float]:
    """Unit vector along the first stretch of a line (the first part of a multi-part one)."""
    part: Any = shapely.get_geometry(line, 0) if line.geom_type == "MultiLineString" else line
    coordinates = shapely.get_coordinates(part)
    (x0, y0), (x1, y1) = coordinates[0], coordinates[1]
    length = float(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5)
    if length == 0.0:
        raise ValueError("a reach line has no length")
    return (x1 - x0) / length, (y1 - y0) / length
