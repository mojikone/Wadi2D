"""The lumped network of a run as map layers (W88): ``network.gpkg`` beside the series, and ``network_peaks.csv``.

What the plugin puts in a run's group, so the catchments that ran the HMS way are seen on the map with their peaks:

- ``subbasins``: every lumped subbasin of the run, its polygon, area, peak outflow and its time, volume, the
  area-reduction it read, whether the 2D mesh left it out, and where its water entered the grid; ``label`` is what the
  map writes.
- ``reaches``: the reaches whose series the run wrote, on the HMS basin's lines (the basin's .sqlite) or a generated
  basin's.
- ``points``: junctions, reservoirs, sinks, diversions and sources whose series the run wrote, at the HMS icons or a
  generated basin's junctions, with inflow and outflow peaks and a reservoir's highest pool.

Every feature carries ``name``, the element's, so a right-click on it opens its hydrograph (W64). Nothing here changes
a number; a layer the geometry is missing for is left out, never guessed.

Interface: :func:`element_rows`, :func:`write_network`, :data:`FILE`, :data:`PEAKS_FILE`.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import shapely

from wadi2d.config.constants import M2_PER_KM2
from wadi2d.config.schema import RunConfig
from wadi2d.hydrology.model import Basin, Reach, Subbasin
from wadi2d.io.geopackage import LINES, POINTS, POLYGONS, VectorLayer, add_layer, write_geopackage

FILE = "network.gpkg"
PEAKS_FILE = "network_peaks.csv"
SECONDS_PER_HOUR = 3600.0
M3_PER_MM3 = 1.0e6
SUBBASIN_COLUMNS = {
    "name": str, "area_km2": float, "peak_m3s": float, "peak_h": float, "volume_Mm3": float,
    "storm_area_km2": float, "arf": float, "left_out": int, "enters_at": str, "label": str,
}  # fmt: skip
REACH_COLUMNS = {"name": str, "peak_m3s": float, "peak_h": float, "label": str}
POINT_COLUMNS = {
    "name": str, "kind": str, "inflow_peak_m3s": float, "inflow_peak_h": float, "outflow_peak_m3s": float,
    "outflow_peak_h": float, "max_pool_m": float, "drainage_km2": float, "label": str,
}  # fmt: skip


def _peak(t: np.ndarray, q) -> tuple[float, float]:
    q = np.asarray(q, np.float64)
    if q.size == 0:
        return 0.0, 0.0
    k = int(np.argmax(q))
    return float(q[k]), float(t[k] / SECONDS_PER_HOUR)


def element_rows(
    basin: Basin,
    series: dict[str, dict],
    t_s: np.ndarray,
    areas: dict[str, tuple[float | None, float | None]] | None = None,
) -> dict[str, dict]:
    """One row per element with a series: kind, drainage area, inflow and outflow peaks and times, outflow volume,
    highest pool; ``areas`` gives each element's storm area and factor where the run read one of its own."""
    rows = {}
    dt = float(np.diff(t_s).mean()) if t_s.size > 1 else 0.0
    for name, columns in series.items():
        element = basin.elements[name]
        q_in, t_in = _peak(t_s, columns["inflow_m3s"])
        q_out, t_out = _peak(t_s, columns["outflow_m3s"])
        storm_area, factor = (areas or {}).get(name, (None, None))
        rows[name] = {
            "element": name,
            "kind": type(element).__name__,
            "drainage_km2": float(basin.drainage_area(name)),
            "storm_area_km2": storm_area,
            "arf": factor,
            "inflow_peak_m3s": q_in,
            "inflow_peak_h": t_in,
            "outflow_peak_m3s": q_out,
            "outflow_peak_h": t_out,
            "outflow_volume_Mm3": float(np.trapezoid(np.asarray(columns["outflow_m3s"]), dx=dt) / M3_PER_MM3),
            "max_pool_m": float(np.max(columns["pool_m"])) if "pool_m" in columns else None,
        }
    return rows


def write_peaks(out: Path, rows: dict[str, dict]) -> Path:
    path = out / PEAKS_FILE
    keys = list(next(iter(rows.values()))) if rows else ["element"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows.values())
    return path


def _flow_label(name: str, row: dict | None) -> str:
    if not row:
        return name
    return f"{name}\n{row['outflow_peak_m3s']:,.0f} m3/s at {row['outflow_peak_h']:.1f} h"


def _subbasin_label(name: str, area_km2: float, row: dict | None, left_out: bool) -> str:
    text = f"{name}\n{area_km2:,.2f} km2"
    if row:
        text += f"\n{row['outflow_peak_m3s']:,.0f} m3/s at {row['outflow_peak_h']:.1f} h"
    return text + ("\nleft out of the 2D mesh" if left_out else "")


def _geometry(cfg: RunConfig, crs: str):
    """(subbasin polygons, reach lines, point locations) by element name, from whatever the job's network holds."""
    from wadi2d.forcing import load_polygons

    h = cfg.hydrology
    polygons = load_polygons(h, crs)
    lines: dict[str, shapely.Geometry] = {}
    points: dict[str, shapely.Geometry] = {}
    if h.basin_json is not None:
        from wadi2d.basin.contract import read_model
        from wadi2d.basin.geometry import JUNCTIONS, REACHES, geometry_file, read_layer

        path = geometry_file(read_model(h.basin_json), h.basin_json)
        lines = read_layer(path, REACHES, crs)
        points = read_layer(path, JUNCTIONS, crs)
    elif h.hms_basin is not None:
        from wadi2d.hms import load_basin

        for element in load_basin(h.hms_basin).elements:
            if element.canvas_x is not None and element.canvas_y is not None:
                points[element.name] = shapely.Point(element.canvas_x, element.canvas_y)
        if h.hms_sqlite is not None:
            from wadi2d.hms import sqlite as hms_sqlite

            lines = {line.name: line.shape() for line in hms_sqlite.reach_lines(h.hms_sqlite)}
    return polygons, lines, points


def write_network(
    out: Path,
    cfg: RunConfig,
    basin: Basin,
    rows: dict[str, dict],
    crs: str,
    left_out: set[str] = frozenset(),
    enters_at: dict[str, str] | None = None,
) -> Path | None:
    """``network.gpkg`` and ``network_peaks.csv`` of a run (see the module's words); None when nothing is drawable."""
    write_peaks(out, rows)
    polygons, lines, points = _geometry(cfg, crs)
    lumped = [s.name for s in cfg.hydrology.subbasins if s.mode == "lumped" and s.name in basin.elements]
    enters_at = enters_at or {}
    layers = []
    sub_rows, sub_shapes = [], []
    for name in lumped:
        shape = polygons.get(name)
        if shape is None:
            continue
        row = rows.get(name)
        element = basin.elements[name]
        area = element.area_km2 if isinstance(element, Subbasin) else shape.area / M2_PER_KM2
        sub_rows.append((
            name, float(area), row["outflow_peak_m3s"] if row else None, row["outflow_peak_h"] if row else None,
            row["outflow_volume_Mm3"] if row else None, row["storm_area_km2"] if row else None,
            row["arf"] if row else None, int(name in left_out), enters_at.get(name, ""),
            _subbasin_label(name, float(area), row, name in left_out),
        ))  # fmt: skip
        sub_shapes.append(shapely.make_valid(shape))
    if sub_rows:
        layers.append(VectorLayer("subbasins", SUBBASIN_COLUMNS, sub_rows, sub_shapes, POLYGONS))
    reach_rows, reach_shapes = [], []
    for name, row in rows.items():
        if isinstance(basin.elements[name], Reach) and name in lines:
            reach_rows.append((name, row["outflow_peak_m3s"], row["outflow_peak_h"], _flow_label(name, row)))
            reach_shapes.append(lines[name])
    if reach_rows:
        layers.append(VectorLayer("reaches", REACH_COLUMNS, reach_rows, reach_shapes, LINES))
    point_rows, point_shapes = [], []
    for name, row in rows.items():
        element = basin.elements[name]
        if isinstance(element, Subbasin | Reach) or name not in points:
            continue
        label = _flow_label(name, row)
        if row["max_pool_m"] is not None:
            label += f"\npool {row['max_pool_m']:.2f} m"
        point_rows.append((
            name, row["kind"], row["inflow_peak_m3s"], row["inflow_peak_h"], row["outflow_peak_m3s"],
            row["outflow_peak_h"], row["max_pool_m"], row["drainage_km2"], label,
        ))  # fmt: skip
        point_shapes.append(points[name])
    if point_rows:
        layers.append(VectorLayer("points", POINT_COLUMNS, point_rows, point_shapes, POINTS))
    if not layers:
        return None
    path = out / FILE
    if not path.is_file():
        return write_geopackage(path, layers, crs)
    for layer in layers:  # in place: QGIS may hold the last run's file open
        add_layer(path, layer, crs)
    return path

