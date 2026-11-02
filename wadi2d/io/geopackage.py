"""A GeoPackage of polygon layers, written with the standard library.

SQLite plus the few tables of the OGC standard. A second GDAL in the process is not an option here: the wheels of
rasterio and pyogrio each bring their own, and loading both beside CuPy crashes the interpreter on Windows.
"""

from __future__ import annotations

import sqlite3
import struct
from dataclasses import dataclass, field
from pathlib import Path

import shapely
from rasterio.crs import CRS

APPLICATION_ID = 0x47504B47
"""'GPKG'."""
USER_VERSION = 10300
"""GeoPackage 1.3."""
LOCAL_SRS = 99999
HEADER_FLAGS = 0b0000_0011
"""Little-endian, with an envelope of minx, maxx, miny, maxy."""
SQL_TYPES = {int: "INTEGER", float: "DOUBLE", str: "TEXT"}
UNDEFINED_SRS = (
    ("Undefined Cartesian SRS", -1, "NONE", -1, "undefined", "undefined Cartesian coordinate reference system"),
    ("Undefined geographic SRS", 0, "NONE", 0, "undefined", "undefined geographic coordinate reference system"),
)
SCHEMA = """
CREATE TABLE gpkg_spatial_ref_sys (srs_name TEXT NOT NULL, srs_id INTEGER PRIMARY KEY, organization TEXT NOT NULL,
    organization_coordsys_id INTEGER NOT NULL, definition TEXT NOT NULL, description TEXT);
CREATE TABLE gpkg_contents (table_name TEXT NOT NULL PRIMARY KEY, data_type TEXT NOT NULL, identifier TEXT UNIQUE,
    description TEXT DEFAULT '', last_change DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE, srs_id INTEGER,
    CONSTRAINT fk_gc_srs FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id));
CREATE TABLE gpkg_geometry_columns (table_name TEXT NOT NULL, column_name TEXT NOT NULL,
    geometry_type_name TEXT NOT NULL, srs_id INTEGER NOT NULL, z TINYINT NOT NULL, m TINYINT NOT NULL,
    CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name));
"""


@dataclass
class PolygonLayer:
    """Rows of a layer: ``columns`` names to Python types, ``rows`` tuples in that order, one geometry each."""

    name: str
    columns: dict[str, type]
    rows: list[tuple] = field(default_factory=list)
    geometries: list[shapely.Geometry] = field(default_factory=list)


def _as_multipolygon(geometry: shapely.Geometry) -> shapely.MultiPolygon:
    parts = shapely.get_parts(geometry)
    return shapely.MultiPolygon([p for p in parts if p.geom_type == "Polygon"])


def _blob(geometry: shapely.Geometry, srs_id: int) -> bytes:
    xmin, ymin, xmax, ymax = shapely.bounds(geometry).tolist()
    head = b"GP" + struct.pack("<BBi4d", 0, HEADER_FLAGS, srs_id, xmin, xmax, ymin, ymax)
    return head + shapely.to_wkb(geometry, byte_order=1, output_dimension=2)


def _srs_row(crs_wkt: str) -> tuple:
    crs = CRS.from_wkt(crs_wkt) if crs_wkt else None
    epsg = crs.to_epsg() if crs is not None else None
    if epsg is None:
        return ("local", LOCAL_SRS, "NONE", LOCAL_SRS, crs_wkt or "undefined", "the CRS of the run")
    return (f"EPSG:{epsg}", epsg, "EPSG", epsg, crs_wkt, "the CRS of the run")


def _write_layer(db: sqlite3.Connection, layer: PolygonLayer, srs_id: int) -> None:
    names = ", ".join(f'"{n}" {SQL_TYPES[t]}' for n, t in layer.columns.items())
    db.execute(
        f'CREATE TABLE "{layer.name}" (fid INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, geom BLOB, {names})'
    )
    shapes = [_as_multipolygon(g) for g in layer.geometries]
    shapes_kept = [(s, row) for s, row in zip(shapes, layer.rows, strict=True) if not s.is_empty]
    quoted = ", ".join(f'"{n}"' for n in layer.columns)
    marks = ", ".join("?" for _ in layer.columns)
    db.executemany(
        f'INSERT INTO "{layer.name}" (geom, {quoted}) VALUES (?, {marks})',
        [(_blob(s, srs_id), *row) for s, row in shapes_kept],
    )
    bounds = shapely.total_bounds([s for s, _row in shapes_kept]).tolist() if shapes_kept else [None] * 4
    db.execute(
        "INSERT INTO gpkg_contents (table_name, data_type, identifier, min_x, min_y, max_x, max_y, srs_id) "
        "VALUES (?, 'features', ?, ?, ?, ?, ?, ?)",
        (layer.name, layer.name, *bounds, srs_id),
    )
    db.execute(
        "INSERT INTO gpkg_geometry_columns VALUES (?, 'geom', 'MULTIPOLYGON', ?, 0, 0)", (layer.name, srs_id)
    )


def write_geopackage(path: Path, layers: list[PolygonLayer], crs_wkt: str) -> Path:
    """A new GeoPackage, through a temporary name, so a stop never leaves half a file under the real name."""
    tmp = path.with_name(f"{path.stem}.tmp{path.suffix}")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    try:
        db.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        db.execute(f"PRAGMA user_version = {USER_VERSION}")
        db.executescript(SCHEMA)
        srs = _srs_row(crs_wkt)
        db.executemany("INSERT INTO gpkg_spatial_ref_sys VALUES (?, ?, ?, ?, ?, ?)", (*UNDEFINED_SRS, srs))
        for layer in layers:
            _write_layer(db, layer, srs[1])
        db.commit()
    finally:
        db.close()
    tmp.replace(path)
    return path
