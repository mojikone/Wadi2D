"""What ``wadi2d domain`` writes into its folder: the domain as GeoJSON (what a job's ``grid.domain`` reads), a
GeoPackage with the domain and the pieces that moved (what QGIS shows, with its CRS), and the report as JSON.

Interface: :data:`DOMAIN_FILE`, :data:`LAYERS_FILE`, :data:`REPORT_FILE`, :func:`write_domain`.
"""

from __future__ import annotations

import json
from pathlib import Path

import shapely
from shapely.geometry import mapping

from wadi2d.io.geopackage import POLYGONS, VectorLayer, write_geopackage

DOMAIN_FILE = "domain.geojson"
LAYERS_FILE = "domain.gpkg"
REPORT_FILE = "domain_report.json"
DOMAIN_LAYER, CHANGES_LAYER = "domain", "changes"
CHANGE_COLUMNS = {"kind": str, "area_km2": float, "catchment": int, "x": float, "y": float}


def write_domain(
    out: Path, polygon: shapely.Polygon, name: str, crs: str, report: dict, changes: list[tuple]
) -> dict[str, str]:
    """``changes`` are (kind, geometry, km2, catchment, x, y). Returns the paths written by role."""
    out.mkdir(parents=True, exist_ok=True)
    domain = out / DOMAIN_FILE
    feature = {"type": "Feature", "properties": {"name": name}, "geometry": mapping(polygon)}
    domain.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}, separators=(",", ":")),
                      encoding="utf-8")  # fmt: skip
    rows = [(kind, round(km2, 4), int(big), round(x, 1), round(y, 1)) for kind, _g, km2, big, x, y in changes]
    whole = VectorLayer(
        DOMAIN_LAYER, {"name": str, "area_km2": float}, [(name, round(polygon.area / 1e6, 4))]
    )
    whole.geometries.append(polygon)
    layers = [
        whole,
        VectorLayer(CHANGES_LAYER, CHANGE_COLUMNS, rows, [g for _k, g, *_rest in changes], POLYGONS),
    ]
    layers_path = write_geopackage(out / LAYERS_FILE, layers, crs)
    report_path = out / REPORT_FILE
    report_path.write_text(json.dumps(report, indent=1), encoding="utf-8")
    return {"domain": str(domain), "layers": str(layers_path), "report": str(report_path)}
