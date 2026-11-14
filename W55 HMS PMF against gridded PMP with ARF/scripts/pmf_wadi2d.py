"""Test 2, the Wadi2D side and the HMS inputs, per dam, on Basin 3 with its reservoirs (lumped on the HMS route).

From the DSS PMP grid (`Precipitation_PMP_10min.dss`, 144 frames of 10 min) for each dam:

- the catchment's areal rain: the polygon-area-weighted mean over the subbasins above the dam of each subbasin's
  pixel mean (pixels weighted by the area they share with the polygon, the engine's lumped reading), i.e. the mean
  over the catchment; its total depth and its cumulative time pattern on the grid's 10-minute edges. These go to
  ``results/pmf_inputs.json`` for the HMS side (one lumped depth, one pattern, ARF FM at the dam's area);
- Wadi2D, distributed: every subbasin takes its own pixels of the grid, every frame multiplied by ARF FM at the dam's
  drainage area, and the network above the reservoir is run; also without ARF (d), and with the HMS side's own
  lumped storm (the code check of the HMS set-up);
- (a)/(b): HMS's own PMF, the FM PMP storm of DA PMP B3, from the replication.

Writes ``results/pmf_wadi2d.json``.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from wadi2d.hms.sqlite import subbasin_polygons
from wadi2d.hydrology.constants import SECONDS_PER_MINUTE
from wadi2d.hydrology.depth_area import analyse_point, point_storm
from wadi2d.hydrology.from_hms import grid_from_hms
from wadi2d.hydrology.replication import _point_storm, _Project
from wadi2d.hms import load_nals
from wadi2d.io.rain import read_rain
from wadi2d.storm import HypotheticalStorm, PercentPattern
from wadi2d.storm.gridded import GriddedStorm
from wadi2d.storm.rain_frames import RainSpec

HERE = Path(__file__).resolve().parents[1]
HMS = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02\HEC_HMS_Block_02.hms")
GRID = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\Grid\DSS\Precipitation_PMP_10min.dss")
DAMS = ["Bidah 03", "Faydh 01", "R2A", "R5A", "Z4C"]
RUN_START = "2000-01-01T00:00:00"  # Control 1: 31 Dec 1999 24:00
ARF_TABLE = "ARF FM"
PERCENT = 100.0


def reservoir_numbers(run, reservoir, routing, dt_minutes):
    inflow, outflow = run.inflow[reservoir], run.outflow[reservoir]
    storage, level = routing.pool(inflow, outflow, dt_minutes)
    dt_s = dt_minutes * SECONDS_PER_MINUTE
    return {
        "inflow_peak": float(inflow.max()),
        "inflow_peak_h": float(np.argmax(inflow)) * dt_minutes / 60.0,
        "outflow_peak": float(outflow.max()),
        "outflow_peak_h": float(np.argmax(outflow)) * dt_minutes / 60.0,
        "inflow_volume_Mm3": float(np.trapezoid(inflow)) * dt_s / 1e6,
        "outflow_volume_Mm3": float(np.trapezoid(outflow)) * dt_s / 1e6,
        "max_level_m": float(level.max()),
        "max_storage_Mm3": float(storage.max()) / 1e6,
    }


def catchment_rain(engine, storm: GriddedStorm, shapes, point: str):
    """Total depth and cumulative series (on the grid's edges) over the subbasins above ``point``, mm."""
    above = [name for name in engine.basin.subbasins if name in engine.basin.upstream_of(point)]
    weights = np.array([shapes[name].area for name in above])
    series = [storm.over(name) for name in above]
    edges = series[0].edges_min if hasattr(series[0], "edges_min") else None
    cumulative = sum(w * s.cumulative_depth(EDGES) for w, s in zip(weights, series)) / weights.sum()
    return above, edges, cumulative


def main() -> None:
    global EDGES
    project = _Project(HMS)
    analysis = load_nals(HMS.with_suffix(".nals")).analysis("DA PMP B3")
    hms_basin, engine = project.model("Basin 3")
    grid = grid_from_hms(analysis)
    dt = grid.dt_minutes
    arf = project.tables.area_reductions[ARF_TABLE]
    crs = hms_basin.spatial.coordinate_system if hms_basin.spatial is not None else ""
    shapes = {p.name: p.shape() for p in subbasin_polygons(HMS.parent / "Basin_3.sqlite")}
    frames = read_rain(GRID, RainSpec(), start=RUN_START)
    EDGES = np.concatenate(([frames.starts_min[0]], frames.ends_min))
    whole = GriddedStorm(frames, arf=arf).bind(shapes, crs)
    plain = GriddedStorm(frames).bind(shapes, crs)  # no table: factor 1
    basin_path = project.project.path_of(project.project.basins["Basin 3"])
    met_path = project.project.path_of(project.project.mets["FM PMP"])
    fm_pmp = _point_storm(met_path, project.tables, hms_basin, engine.basin, basin_path, HMS.stem)
    inputs, out = {}, {}
    for dam in DAMS:
        reservoir = f"{dam} Reservoir"
        routing = engine.basin.elements[reservoir].routing
        area = engine.basin.drainage_area(reservoir)
        factor = float(arf.factor(area))
        above, _, cumulative = catchment_rain(engine, plain, shapes, reservoir)
        depth = float(cumulative[-1])
        span = EDGES[-1] - EDGES[0]
        pattern_time = PERCENT * (EDGES - EDGES[0]) / span
        pattern_depth = PERCENT * cumulative / depth
        inputs[dam] = {
            "drainage_area_km2": area, "arf": factor, "subbasins": above, "grid_depth_mm": depth,
            "reduced_depth_mm": depth * factor, "duration_h": span / 60.0, "start_min": float(EDGES[0]),
            "pattern_time_percent": pattern_time.tolist(), "pattern_depth_percent": pattern_depth.tolist(),
            "largest_10min_mm": float(np.diff(cumulative).max()),
        }
        rows = {}
        # (a)/(b): HMS's own PMF storm, through the depth-area analysis's rule at this point.
        fm = fm_pmp(reservoir, area)
        result = analyse_point(engine, lambda _p, _a, s=fm: s, grid, reservoir)
        rows["b_fm_pmp"] = reservoir_numbers(result.run, reservoir, routing, dt) | {
            "rain_mm": float(fm.total_depth), "factor": float(fm.area_factor)}
        # (c) the grid, distributed, ARF at the dam's area.
        result = analyse_point(engine, point_storm(whole), grid, reservoir)
        reduced = whole.at_area(area)
        rows["c_grid_arf"] = reservoir_numbers(result.run, reservoir, routing, dt) | {
            "rain_mm": depth * reduced.area_factor, "factor": float(reduced.area_factor)}
        # (d) the grid, distributed, no ARF.
        result = analyse_point(engine, point_storm(plain), grid, reservoir)
        rows["d_grid_no_arf"] = reservoir_numbers(result.run, reservoir, routing, dt) | {
            "rain_mm": depth, "factor": 1.0}
        # The HMS side's storm in Wadi2D: one lumped depth, the catchment pattern, ARF FM at the dam's area.
        lumped = HypotheticalStorm(
            depth_mm=depth, pattern=PercentPattern(pattern_time, pattern_depth), duration_hours=span / 60.0,
            storm_area_km2=area, arf=arf)
        result = analyse_point(engine, point_storm(lumped), grid, reservoir)
        rows["e_lumped_depth_arf"] = reservoir_numbers(result.run, reservoir, routing, dt) | {
            "rain_mm": float(lumped.at_area(area).total_depth), "factor": float(lumped.at_area(area).area_factor)}
        # The split of rain into depth and shape: the grid's lumped depth on HMS's FM PMP pattern, same ARF.
        shaped = replace(lumped, pattern=project.tables.patterns["FM PMP"], duration_hours=24.0)
        result = analyse_point(engine, point_storm(shaped), grid, reservoir)
        rows["f_grid_depth_fm_pattern"] = reservoir_numbers(result.run, reservoir, routing, dt) | {
            "rain_mm": float(shaped.at_area(area).total_depth), "factor": float(shaped.at_area(area).area_factor)}
        out[dam] = rows
        print(dam, f"A={area:.2f} ARF={factor:.6f} grid {depth:.2f} mm, FM {rows['b_fm_pmp']['rain_mm']:.2f} mm")
        for key, row in rows.items():
            print(f"   {key:20s} rain {row['rain_mm']:8.2f} in {row['inflow_peak']:8.1f} @{row['inflow_peak_h']:5.2f}h"
                  f" out {row['outflow_peak']:8.1f} @{row['outflow_peak_h']:5.2f}h vol {row['inflow_volume_Mm3']:7.2f}"
                  f" lvl {row['max_level_m']:.3f}")
    (HERE / "results" / "pmf_inputs.json").write_text(json.dumps(inputs, indent=1), encoding="utf-8")
    (HERE / "results" / "pmf_wadi2d.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
