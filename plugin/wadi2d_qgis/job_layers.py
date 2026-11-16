# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A GeoPackage of the lines, points and polygons a job holds inline (W101), one layer each, in the DEM's CRS, with
the fields the dock's sections read. GDAL's own writer, as QGIS ships it."""

from __future__ import annotations

import json
from pathlib import Path

GEOMETRIES = {"LineString": ("wkbLineString", "wkbLineString25D"), "Point": ("wkbPoint", "wkbPoint25D"), "Polygon": ("wkbPolygon", "wkbPolygon25D")}


def _has_z(spec: dict) -> bool:
    if spec["geometry"] != "LineString":
        return False
    return any(len(point) == 3 for coordinates, _props in spec["features"] for point in coordinates)


def write_gpkg(path: Path | str, layers: dict, wkt: str) -> Path:
    from osgeo import ogr, osr

    ogr.UseExceptions()
    path = Path(path)
    source = ogr.GetDriverByName("GPKG").CreateDataSource(str(path))
    srs = None
    if wkt:
        srs = osr.SpatialReference()
        srs.ImportFromWkt(wkt)
    for name, spec in layers.items():
        flat, with_z = GEOMETRIES[spec["geometry"]]
        layer = source.CreateLayer(name, srs, getattr(ogr, with_z if _has_z(spec) else flat))
        for field, kind in spec["fields"].items():
            layer.CreateField(ogr.FieldDefn(field, ogr.OFTString if kind is str else ogr.OFTReal))
        definition = layer.GetLayerDefn()
        for coordinates, props in spec["features"]:
            feature = ogr.Feature(definition)
            feature.SetGeometry(ogr.CreateGeometryFromJson(json.dumps({"type": spec["geometry"], "coordinates": coordinates})))
            for key, value in props.items():
                if value is not None and key in spec["fields"]:
                    feature.SetField(key, value)
            layer.CreateFeature(feature)
            feature = None
    source = None
    return path
