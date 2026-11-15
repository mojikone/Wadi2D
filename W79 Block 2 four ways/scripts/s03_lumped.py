"""Run 2, the full HMS way: Basin 3 on the lumped engine alone, no grid, as HMS's depth-area analysis.

Every subbasin, reach, junction and the five reservoirs (Modified Puls on their elevation-area-outflow tables, starting
at the bottom of each table, empty) of his HMS project, under FM_200yr with ARF FM. His rule of 2026-11-15: every element
reads the ARF at its own total upstream area, as HMS's depth-area analysis does: for each element the sub-network above
it is run again with the storm area set to its drainage area (``wadi2d.hydrology.depth_area.analyse_point``), and the
element's series of record is the one of its own run. A dam's inflow and outflow are therefore at the dam's own area. A
2D run would add nothing here: with every element lumped no water reaches the grid. The script calls the pieces
``wadi2d run`` uses (``run._lumped_basin``, ``run._lumped_rain``, ``LumpedEngine``) and writes every element's series as
``series/network_<element>.csv``, the engine's own format, plus ``network_peaks.csv`` (with each element's storm area and
factor) and ``network.gpkg`` (subbasins with their peaks, the reaches, and the junction and reservoir points at their
HMS icons) for the QGIS project. The first attempt's run 2 read every element at Basin 3's 1,370.77 km2 in one run.
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from w79 import BASIN, HMS_DIR, JOBS, RUN_NAMES, RUNS, load_json, write_json  # noqa: E402

from wadi2d.config.schema import RunConfig  # noqa: E402
from wadi2d.engine.network_series import rain_columns, reservoir_columns  # noqa: E402
from wadi2d.forcing import arf_table, build_storm  # noqa: E402
from wadi2d.hydrology.depth_area import analyse_point, point_storm  # noqa: E402
from wadi2d.hydrology.constants import SECONDS_PER_MINUTE  # noqa: E402
from wadi2d.hydrology.model import TimeGrid  # noqa: E402
from wadi2d.hydrology.network import LumpedEngine  # noqa: E402
from wadi2d.io.results import safe_name, write_series_csv  # noqa: E402
from wadi2d.run import _lumped_basin, _lumped_rain  # noqa: E402

CRS = "EPSG:32640"


def main() -> None:
    name = RUN_NAMES[2]
    cfg = RunConfig.model_validate(load_json(JOBS / f"{name}.json"))
    out = RUNS / name
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    storm = build_storm(cfg)
    basin, hms_basin, _cut = _lumped_basin(cfg, CRS)
    h = cfg.hydrology
    steps = int(np.ceil(cfg.run.duration_s / SECONDS_PER_MINUTE / h.time_step_min))
    grid = TimeGrid(h.time_step_min, steps)
    rain = _lumped_rain(cfg, storm, basin, hms_basin, CRS)
    engine = LumpedEngine(basin)
    table = arf_table(cfg.storm)
    at_point = point_storm(rain)
    t = grid.minutes * SECONDS_PER_MINUTE
    dt = h.time_step_min * SECONDS_PER_MINUTE
    rows = []
    for element in basin.topological_order():
        found = analyse_point(engine, at_point, grid, element)
        run = found.run
        columns = {"inflow_m3s": run.inflow[element], "outflow_m3s": run.outflow[element]}
        columns |= reservoir_columns(basin.elements[element], run.inflow[element], run.outflow[element], run.grid.dt_minutes)
        columns |= rain_columns(basin, run.water, element, t.size)
        write_series_csv(out / "series" / f"network_{safe_name(element)}.csv", t, columns)
        q_in, q_out = np.asarray(run.inflow[element]), np.asarray(run.outflow[element])
        row = {
            "element": element, "kind": type(basin.elements[element]).__name__,
            "storm_area_km2": found.storm_area_km2, "arf": table.factor(found.storm_area_km2),
            "inflow_peak_m3s": float(q_in.max()), "inflow_peak_h": float(t[q_in.argmax()] / 3600.0),
            "inflow_volume_Mm3": float(np.trapezoid(q_in, dx=dt) / 1e6),
            "outflow_peak_m3s": float(q_out.max()), "outflow_peak_h": float(t[q_out.argmax()] / 3600.0),
            "outflow_volume_Mm3": float(np.trapezoid(q_out, dx=dt) / 1e6),
        }
        for key in ("pool_m", "storage_m3"):
            if key in columns:
                row[f"max_{key}"] = float(np.max(columns[key]))
        rows.append(row)
    wall = time.perf_counter() - t0
    keys = sorted({k for r in rows for k in r}, key=lambda k: list(rows[0]).index(k) if k in rows[0] else 99)
    with (out / "network_peaks.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    write_json(out / "run2_summary.json", {
        "wall_s": wall, "elements": len(rows), "time_step_min": h.time_step_min, "duration_h": cfg.run.duration_s / 3600,
        "storm_area": "each element at its own drainage area (HMS depth-area analysis)", "depth_mm": cfg.storm.depth_mm,
        "note": "lumped engine alone; no 2D run (every element lumped, nothing reaches the grid)",
    })
    gpkg(out, rows)
    print(f"{len(rows)} elements in {wall:.1f} s -> {out}")
    for r in rows:
        if r["kind"] == "Reservoir":
            print(r)


def label(name: str, r: dict) -> str:
    """An element's map label: its name, peak outflow and time to peak, and the ARF it read."""
    if not r:
        return name
    return (f"{name}\n{r['outflow_peak_m3s']:,.0f} m3/s at {r['outflow_peak_h']:.1f} h\n"
            f"ARF {r['arf']:.3f} at {r['storm_area_km2']:,.1f} km2")


def gpkg(out: Path, rows: list[dict]) -> None:
    """Subbasins with their peaks, the reaches, and the junction and reservoir points, for QGIS."""
    import geopandas as gpd
    import shapely
    from shapely import wkb

    from wadi2d.hms import load_basin
    from wadi2d.hms import sqlite as hms_sqlite

    by = {r["element"]: r for r in rows}
    sqlite = HMS_DIR / BASIN.replace(".basin", ".sqlite")
    model = load_basin(HMS_DIR / BASIN)
    subs = []
    for p in hms_sqlite.subbasin_polygons(sqlite):
        r = by.get(p.name, {})
        subs.append({"name": p.name, "area_km2": p.area_sqkm, "peak_m3s": r.get("outflow_peak_m3s"),
                     "peak_h": r.get("outflow_peak_h"), "volume_Mm3": r.get("outflow_volume_Mm3"),
                     "arf_area_km2": r.get("storm_area_km2"), "arf": r.get("arf"), "mode": "lumped",
                     "label": label(p.name, r), "geometry": shapely.make_valid(p.shape())})
    gpd.GeoDataFrame(subs, crs=CRS).to_file(out / "network.gpkg", layer="subbasins", driver="GPKG")
    reaches = []
    for line in hms_sqlite.reach_lines(sqlite):
        r = by.get(line.name, {})
        geom = line.shape() if hasattr(line, "shape") else wkb.loads(line.GEOMETRY)
        reaches.append({"name": line.name, "peak_m3s": r.get("outflow_peak_m3s"), "peak_h": r.get("outflow_peak_h"),
                        "arf_area_km2": r.get("storm_area_km2"), "arf": r.get("arf"), "label": label(line.name, r),
                        "geometry": geom})
    if reaches:
        gpd.GeoDataFrame(reaches, crs=CRS).to_file(out / "network.gpkg", layer="reaches", driver="GPKG")
    points = []
    for e in model.elements:
        kind = type(e).__name__
        if kind in ("Junction", "Reservoir", "Sink") and e.canvas_x is not None:
            r = by.get(e.name, {})
            points.append({"name": e.name, "kind": kind, "inflow_peak_m3s": r.get("inflow_peak_m3s"),
                           "inflow_peak_h": r.get("inflow_peak_h"), "outflow_peak_m3s": r.get("outflow_peak_m3s"),
                           "outflow_peak_h": r.get("outflow_peak_h"), "max_pool_m": r.get("max_pool_m"),
                           "arf_area_km2": r.get("storm_area_km2"), "arf": r.get("arf"), "label": label(e.name, r),
                           "geometry": shapely.Point(e.canvas_x, e.canvas_y)})
    gpd.GeoDataFrame(points, crs=CRS).to_file(out / "network.gpkg", layer="junctions", driver="GPKG")


if __name__ == "__main__":
    main()
