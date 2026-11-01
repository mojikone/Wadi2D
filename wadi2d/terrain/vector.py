"""Vector inputs: polygons for the domain and the subbasins, moved to the DEM's coordinate system.

GeoJSON is read directly. A shapefile or a GeoPackage goes through Fiona when it is installed (the ``vector``
extra); without it the file is refused by name. Coordinates that cannot be in the DEM's system are refused too:
a polygon that lands nowhere would mask no rain and say nothing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import shapely
from rasterio.crs import CRS
from rasterio.warp import transform_geom

GEOJSON_SUFFIXES = {".geojson", ".json"}
GEOJSON_DEFAULT_CRS = "EPSG:4326"
"""What RFC 7946 says a GeoJSON without a ``crs`` member is in."""
LONGITUDE_LIMIT = 360.0
"""Coordinates under this in a metric system are almost surely degrees."""


def _moved(geometry: dict[str, Any], source: Any, target: str) -> dict[str, Any]:
    if not target or source is None or CRS.from_user_input(source) == CRS.from_user_input(target):
        return geometry
    return transform_geom(source, target, geometry)


def _geojson(path: Path, crs: str) -> list[tuple[dict[str, Any], Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    declared = data.get("crs", {}).get("properties", {}).get("name") if isinstance(data, dict) else None
    items = data.get("features", [{"geometry": data, "properties": {}}])
    out = [
        (f.get("properties") or {}, shapely.geometry.shape(_moved(f["geometry"], declared, crs)))
        for f in items
    ]
    if declared is None and crs and CRS.from_user_input(crs).is_projected:
        for _properties, shape in out:
            if max(abs(v) for v in shape.bounds) < LONGITUDE_LIMIT:
                raise ValueError(
                    f"{path.name} looks like degrees and names no crs, but the DEM is projected; "
                    f"give it a crs member (GeoJSON without one means {GEOJSON_DEFAULT_CRS})"
                )
    return out


def _fiona(path: Path, crs: str) -> list[tuple[dict[str, Any], Any]]:
    try:
        import fiona
    except ImportError as error:
        raise ValueError(
            f"{path.name}: reading this format needs Fiona (extra 'vector'); use GeoJSON"
        ) from error
    with fiona.open(path) as source:
        system = source.crs.to_wkt() if source.crs else None
        return [
            (
                dict(f["properties"]),
                shapely.geometry.shape(_moved(dict(f["geometry"].__geo_interface__), system, crs)),
            )
            for f in source
        ]


def read_features(path: str | Path, crs: str = "") -> list[tuple[dict[str, Any], Any]]:
    """(properties, shapely geometry) per feature, in ``crs`` when it is given."""
    source = Path(path)
    return _geojson(source, crs) if source.suffix.lower() in GEOJSON_SUFFIXES else _fiona(source, crs)
