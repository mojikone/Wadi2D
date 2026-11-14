"""Reservoir routing of Basin 3's five dams against HMS, PMP and 100 yr, from copies of his DSS results.

Two checks per dam and storm. Routing alone: HMS's own inflow (FLOW-COMBINE) through Wadi2D's reservoir, against HMS's
outflow, storage and pool level. The whole chain: the engine reruns the network above the reservoir from the rain,
the depth-area analysis's own storm at the reservoir's drainage area, and inflow, outflow and level are compared.
Writes ``results/reservoirs.json``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from wadi2d.hms import daa_fpart, load_nals, open_dss
from wadi2d.hydrology.constants import SECONDS_PER_MINUTE
from wadi2d.hydrology.depth_area import analyse_point
from wadi2d.hydrology.from_hms import grid_from_hms
from wadi2d.hydrology.replication import _point_storm, _Project

HERE = Path(__file__).resolve().parents[1]
HMS = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02\HEC_HMS_Block_02.hms")
DAMS = ["Bidah 03", "Faydh 01", "R2A", "R5A", "Z4C"]
RUNS = {"DA PMP B3": "DA_PMP_B3.dss", "DA 100yr B3": "DA_100yr_B3.dss"}
THOUSAND = 1000.0


def volume(flow: np.ndarray, dt_s: float) -> float:
    return float(np.trapezoid(flow) * dt_s)


def summary(inflow, outflow, level, storage, dt_s):
    return {
        "inflow_peak": float(inflow.max()),
        "outflow_peak": float(outflow.max()),
        "attenuation_percent": 100.0 * (1.0 - outflow.max() / inflow.max()),
        "inflow_peak_h": float(np.argmax(inflow)) * dt_s / 3600.0,
        "outflow_peak_h": float(np.argmax(outflow)) * dt_s / 3600.0,
        "inflow_volume_Mm3": volume(inflow, dt_s) / 1e6,
        "outflow_volume_Mm3": volume(outflow, dt_s) / 1e6,
        "max_level_m": float(level.max()),
        "max_storage_Mm3": float(storage.max()) / 1e6,
    }


def main() -> None:
    project = _Project(HMS)
    nals = load_nals(HMS.with_suffix(".nals"))
    out: dict = {}
    for name, dss_name in RUNS.items():
        analysis = nals.analysis(name)
        hms_basin, engine = project.model(analysis.basin_model_name)
        basin_path = project.project.path_of(project.project.basins[analysis.basin_model_name])
        met_path = project.project.path_of(project.project.mets[analysis.met_model_name])
        storm = _point_storm(met_path, project.tables, hms_basin, engine.basin, basin_path, HMS.stem)
        grid = grid_from_hms(analysis)
        dt_s = grid.dt_minutes * SECONDS_PER_MINUTE
        with open_dss(HERE / "_work" / "hms_copy" / dss_name) as dss:
            for dam in DAMS:
                reservoir = f"{dam} Reservoir"
                routing = engine.basin.elements[reservoir].routing
                fpart = daa_fpart(name, reservoir)
                hms = {part: dss.read_timeseries(reservoir, part, fpart).values
                       for part in ("FLOW-COMBINE", "FLOW", "STORAGE", "ELEVATION")}
                hms_storage = hms["STORAGE"] * THOUSAND
                alone = routing.route(hms["FLOW-COMBINE"], grid.dt_minutes)
                alone_storage, alone_level = routing.pool(hms["FLOW-COMBINE"], alone, grid.dt_minutes)
                result = analyse_point(engine, storm, grid, reservoir)
                inflow = result.run.inflow[reservoir][-len(hms["FLOW"]):]
                outflow = result.outflow[-len(hms["FLOW"]):]
                storage, level = routing.pool(inflow, outflow, grid.dt_minutes)
                out.setdefault(name, {})[dam] = {
                    "drainage_area_km2": engine.basin.drainage_area(reservoir),
                    "initial_elevation_m": routing.initial_elevation_m,
                    "table_bottom_m": float(routing.elevations_m[0]),
                    "table_top_m": float(routing.elevations_m[-1]),
                    "hms": summary(hms["FLOW-COMBINE"], hms["FLOW"], hms["ELEVATION"], hms_storage, dt_s),
                    "wadi2d": summary(inflow, outflow, level, storage, dt_s),
                    "routing_alone": {
                        "outflow_max_abs_diff": float(np.abs(alone - hms["FLOW"]).max()),
                        "outflow_peak_error_percent": (
                            100.0 * (alone.max() / hms["FLOW"].max() - 1.0) if hms["FLOW"].max() > 0.0 else 0.0
                        ),
                        "level_max_abs_diff_m": float(np.abs(alone_level - hms["ELEVATION"]).max()),
                        "storage_max_rel_diff": float(np.abs(alone_storage - hms_storage).max() / hms_storage.max()),
                    },
                    "chain": {
                        "inflow_max_abs_diff": float(np.abs(inflow - hms["FLOW-COMBINE"]).max()),
                        "outflow_max_abs_diff": float(np.abs(outflow - hms["FLOW"]).max()),
                        "level_max_abs_diff_m": float(np.abs(level - hms["ELEVATION"]).max()),
                    },
                }
    target = HERE / "results" / "reservoirs.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(out, indent=1), encoding="utf-8")
    for name, dams in out.items():
        print(name)
        for dam, row in dams.items():
            h, w, a, c = row["hms"], row["wadi2d"], row["routing_alone"], row["chain"]
            print(f"  {dam:9s} A={row['drainage_area_km2']:7.2f} start {row['initial_elevation_m']:.2f} (bottom "
                  f"{row['table_bottom_m']:.2f}, top {row['table_top_m']:.2f}) | HMS in {h['inflow_peak']:8.1f} out "
                  f"{h['outflow_peak']:8.1f} att {h['attenuation_percent']:5.1f}% lvl {h['max_level_m']:.3f} | W in "
                  f"{w['inflow_peak']:8.1f} out {w['outflow_peak']:8.1f} lvl {w['max_level_m']:.3f} | alone dQ "
                  f"{a['outflow_max_abs_diff']:.2e} dz {a['level_max_abs_diff_m']:.1e} | chain dQ "
                  f"{c['outflow_max_abs_diff']:.2e} dz {c['level_max_abs_diff_m']:.1e}")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
