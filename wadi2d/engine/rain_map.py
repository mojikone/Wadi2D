"""The storm as a map before the run (W77): each lumped subbasin and the 2D area by its depth, and for rain that varies
in space, gridded files and gauges, the total depth over the domain.

``wadi2d rain-preview --map DIR`` writes ``rain_map.json`` (the system, every area of the preview with its polygon as
WKT, the raster's name) and, for gridded or gauge rain, ``rain_total.tif``. The depths of the areas are the preview's
own; the raster is what the cells read: a gridded storm's pixels summed over the event times the area factor, a gauge
storm's totals spread by the job's method at pixel centres (gauge weights a job gives a lumped subbasin replace the
method for that subbasin only, so they are not on the raster).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
import shapely
from rasterio.features import geometry_mask
from rasterio.transform import from_origin

from wadi2d.storm.gauges import GaugeStorm
from wadi2d.storm.gridded import GriddedStorm, _moved_polygon

MAP_FILE = "rain_map.json"
TOTAL_FILE = "rain_total.tif"
GAUGE_PIXELS = 400
"""Pixels along the domain's longer side for gauge rain: the method is smooth or a step, so this shows it whole."""
NODATA = np.nan


def _write(path: Path, depth: np.ndarray, transform, crs: str) -> None:
    profile = {"driver": "GTiff", "height": depth.shape[0], "width": depth.shape[1], "count": 1, "dtype": "float32",
               "crs": crs or None, "transform": transform, "nodata": NODATA, "compress": "deflate"}  # fmt: skip
    with rasterio.open(path, "w", **profile) as out:
        out.write(depth.astype(np.float32), 1)


def _gridded(storm: GriddedStorm, domain: shapely.Geometry, crs: str, path: Path) -> bool:
    frames = storm.frames
    area = _moved_polygon(domain, crs, frames.crs)
    left, bottom, right, top = shapely.bounds(area)
    first_column = max(int(np.floor((left - frames.west) / frames.dx)), 0)
    last_column = min(int(np.ceil((right - frames.west) / frames.dx)), frames.columns)
    first_row = max(int(np.floor((frames.north - top) / frames.dy)), 0)
    last_row = min(int(np.ceil((frames.north - bottom) / frames.dy)), frames.rows)
    if first_column >= last_column or first_row >= last_row:
        return False
    depth = storm.reduced(frames.totals()[first_row:last_row, first_column:last_column])
    transform = from_origin(
        frames.west + first_column * frames.dx, frames.north - first_row * frames.dy, frames.dx, frames.dy
    )
    outside = geometry_mask([area], depth.shape, transform, all_touched=True)
    _write(path, np.where(outside, NODATA, depth), transform, frames.crs or crs)
    return True


def _gauges(storm: GaugeStorm, domain: shapely.Geometry, crs: str, path: Path) -> bool:
    left, bottom, right, top = shapely.bounds(domain)
    pixel = max(right - left, top - bottom) / GAUGE_PIXELS
    if pixel <= 0.0:
        return False
    columns, rows = max(int(np.ceil((right - left) / pixel)), 1), max(int(np.ceil((top - bottom) / pixel)), 1)
    transform = from_origin(left, top, pixel, pixel)
    inside = ~geometry_mask([domain], (rows, columns), transform, all_touched=True)
    row, column = np.nonzero(inside)
    x, y = left + (column + 0.5) * pixel, top - (row + 0.5) * pixel
    weights, _beyond = storm.weights_at(x, y)
    depth = np.full((rows, columns), NODATA)
    depth[row, column] = np.asarray(weights, np.float64) @ np.asarray(storm.totals, np.float64)
    _write(path, depth, transform, crs)
    return True


def write_rain_map(folder: Path | str, rows: list[dict], shapes: dict, storm, domain, crs: str) -> dict:
    """The map's files in ``folder``; ``shapes`` holds a polygon by area name, ``domain`` the 2D domain's outline."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    areas, missing = [], []
    for row in rows:
        shape = shapes.get(row["name"])
        if shape is None or shape.is_empty:
            missing.append(row["name"])
            continue
        keep = {key: row[key] for key in ("name", "mode", "area_km2", "depth_mm", "peak_mm_h")}
        areas.append({**keep, "wkt": shapely.to_wkt(shape, rounding_precision=3)})
    drawn = (isinstance(storm, GriddedStorm) and _gridded(storm, domain, crs, folder / TOTAL_FILE)) or (
        isinstance(storm, GaugeStorm) and _gauges(storm, domain, crs, folder / TOTAL_FILE)
    )
    found = {"crs": crs, "areas": areas, "missing": missing, "total": TOTAL_FILE if drawn else None}
    (folder / MAP_FILE).write_text(json.dumps(found), encoding="utf-8")
    return found
